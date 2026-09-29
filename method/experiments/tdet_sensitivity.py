#!/usr/bin/env python3
"""Detection-timestamp sensitivity of Retrieval@K.

Shifts t_det by delta in {-15, -5, +5, +15} min (WADI / SWaT / HVAC) and
{-2, -1, +1, +2} min (RCAEval), re-extracts the baseline / fault windows with
the adapters' slicing logic, recomputes the three scorers and reports
Retrieval@K (K in {5, 10, 15}) of the +stc pool. A scenario whose shifted
fault window keeps fewer than 5 minutes of data (RCAEval: fewer than 150
rows, 2.5 min) is skipped and counted.
delta = 0 must reproduce Table 1's +stc column.

For WADI / SWaT, whose positive shifts skip short attacks, the change is also
computed against delta = 0 restricted to the same evaluated scenarios; for
the other datasets the change is against the full delta = 0 set
(``matched_subset`` is False where a scenario was skipped).

Outputs (method/results/tdet_sensitivity/):
  tdet_sensitivity.csv    Retrieval@K per (dataset, delta)
  per_scenario_hits.csv   WADI / SWaT per-scenario hits
  tdet_table.csv          change in Retrieval@15 vs delta = 0 (matched subsets)

    python -m method.experiments.tdet_sensitivity
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from method.datasets.base import FaultScenario
from method.datasets.hvac import HVACDataset
from method.datasets.rcaeval_dataset import RCAEvalDataset, SUITES, _preprocess_rcaeval
from method.datasets.swat import SWaTDataset
from method.datasets.wadi import ATTACKS as WADI_ATTACKS, WADIDataset
from method.experiments._shared import out_dir
from method.runners.compute_retrieval_recall_cumulative import (
    _build_pool_cumulative, _hit,
)

CPS_DELTAS = [-15, -5, 0, 5, 15]        # minutes
RCA_DELTAS = [-2, -1, 0, 1, 2]          # minutes
MIN_FAULT_SECONDS = 300
RCAEVAL_MIN_FAULT_ROWS = 150            # RCAEval fault-window floor (2.5 min at 1 Hz)
K_LIST = (5, 10, 15)

TABLE1_STC = {  # Table 1, +stc column (delta = 0 reference)
    ("WADI", 5): 0.500, ("WADI", 10): 0.571, ("WADI", 15): 0.643,
    ("SWaT", 5): 0.306, ("SWaT", 10): 0.611, ("SWaT", 15): 0.667,
    ("HVAC", 5): 0.250, ("HVAC", 10): 0.542, ("HVAC", 15): 0.625,
    ("RE1-OB", 5): 0.936, ("RE1-OB", 10): 0.960, ("RE1-OB", 15): 0.976,
    ("RE1-SS", 5): 0.960, ("RE1-SS", 10): 0.992, ("RE1-SS", 15): 1.000,
    ("RE1-TT", 5): 0.736, ("RE1-TT", 10): 0.896, ("RE1-TT", 15): 0.912,
}


def make_scenario(sid, data_df, cols, diag, truths, sample_rate_hz):
    data = data_df[cols].copy()
    data.index = np.arange(len(data), dtype=float)
    data.index.name = "time_s"
    data = data.ffill().fillna(0)
    return FaultScenario(scenario_id=sid, data=data, diagnosis_time=float(diag),
                         ground_truth_causes=truths, alarm_nodes=[],
                         sample_rate_hz=sample_rate_hz)


def water_scenarios(ds, attacks, delta_min):
    """WADI / SWaT: re-slice the attack log with t0' = t0 + delta (1 Hz)."""
    attack_df = ds._attack_df
    cols = ds._sensor_cols
    out, skipped = [], []
    for atk in attacks:
        t0 = pd.Timestamp(atk["start"])
        t1 = pd.Timestamp(atk["end"])
        t0p = t0 + pd.Timedelta(minutes=delta_min)
        if (t1 - t0p).total_seconds() < MIN_FAULT_SECONDS and delta_min > 0:
            skipped.append(atk["id"])
            continue
        atk_win = attack_df.loc[
            (attack_df["datetime"] >= t0p) & (attack_df["datetime"] <= t1)]
        base_start = t0p - pd.Timedelta(minutes=ds.baseline_minutes)
        base_win = attack_df.loc[
            (attack_df["datetime"] >= base_start) & (attack_df["datetime"] < t0p)]
        if atk_win.empty or base_win.empty:
            skipped.append(atk["id"])
            continue
        combined = pd.concat([base_win, atk_win], ignore_index=True)
        avail = [c for c in cols if c in combined.columns]
        truths = [t for t in atk["targets"] if t in avail] or atk["targets"]
        out.append(make_scenario(atk["id"], combined, avail, len(base_win),
                                 truths, 1.0))
    return out, skipped


def hvac_scenarios(base_scenarios, delta_min):
    """HVAC (1-min rows): move the baseline / fault split inside the data.

    delta > 0 moves the first fault-day rows into the baseline; delta < 0
    moves the last baseline rows into the fault window.
    """
    out, skipped = [], []
    for sc in base_scenarios:
        diag = int(sc.diagnosis_time) + delta_min
        n_fault = len(sc.data) - diag
        if diag < 1 or n_fault * 60 < MIN_FAULT_SECONDS:
            skipped.append(sc.scenario_id)
            continue
        out.append(FaultScenario(
            scenario_id=sc.scenario_id, data=sc.data,
            diagnosis_time=float(diag),
            ground_truth_causes=sc.ground_truth_causes, alarm_nodes=[],
            sample_rate_hz=sc.sample_rate_hz))
    return out, skipped


def rcaeval_scenarios(ds, suite, delta_min):
    """RCAEval (1-s rows): re-slice around inject_time' = inject + delta."""
    out, skipped = [], []
    for s, service, fault, instance, data_csv, inject_time in ds._iter_cases():
        if s != suite:
            continue
        sid = f"{s}|{service}_{fault}|{instance}"
        tp = inject_time + delta_min * 60
        df = pd.read_csv(data_csv)
        pre = df[df["time"] < tp].tail(ds.baseline_seconds)
        post = df[df["time"] >= tp].head(ds.post_seconds)
        if pre.empty or len(post) < RCAEVAL_MIN_FAULT_ROWS:
            skipped.append(sid)
            continue
        base_win = _preprocess_rcaeval(pre)
        fault_win = _preprocess_rcaeval(post)
        common = [c for c in base_win.columns if c in fault_win.columns]
        if not common:
            skipped.append(sid)
            continue
        combined = pd.concat([base_win[common], fault_win[common]],
                             ignore_index=True)
        combined = combined.replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)
        out.append(make_scenario(sid, combined, common, len(base_win),
                                 [f"{service}_{fault}"], 1.0))
    return out, skipped


def eval_block(display, scenarios, skipped, delta, service_level, n_total):
    row = {"dataset": display, "delta_min": delta,
           "n_eval": len(scenarios), "n_skipped": len(skipped),
           "n_total": n_total, "skipped_ids": ";".join(skipped)}
    for k in K_LIST:
        hits = 0
        for sc in scenarios:
            pool, _ = _build_pool_cumulative(sc, k, 3)
            hits += _hit(sc.ground_truth_causes, pool, service_level=service_level)
        row[f"recall@{k}"] = round(hits / max(len(scenarios), 1), 4)
    ref = TABLE1_STC.get((display, 15))
    if delta == 0 and ref is not None:
        row["delta0_matches_table1"] = bool(abs(row["recall@15"] - ref) < 5e-4)
    return row


def per_scenario_hits(ds, attacks, name):
    recs = []
    for d in CPS_DELTAS:
        scs, _ = water_scenarios(ds, attacks, d)
        for sc in scs:
            for k in K_LIST:
                pool, _ = _build_pool_cumulative(sc, k, 3)
                recs.append({"dataset": name, "scenario_id": sc.scenario_id,
                             "delta_min": d, "K": k,
                             "hit": _hit(sc.ground_truth_causes, pool,
                                         service_level=False)})
    return pd.DataFrame(recs)


def matched_table(df, hits):
    """Change in Retrieval@15 vs delta = 0 on the same evaluated scenarios."""
    rows = []
    for name in ("WADI", "SWaT"):
        sub = hits[(hits["dataset"] == name) & (hits["K"] == 15)]
        base = sub[sub["delta_min"] == 0].set_index("scenario_id")["hit"]
        for d in CPS_DELTAS:
            if d == 0:
                continue
            cur = sub[sub["delta_min"] == d].set_index("scenario_id")["hit"]
            r_d, r_0 = cur.mean(), base.loc[cur.index].mean()
            rows.append({"dataset": name, "delta_min": d, "n_subset": len(cur),
                         "matched_subset": True,
                         "recall@15": round(r_d, 4),
                         "recall@15_delta0_same_subset": round(r_0, 4),
                         "change_pp": round((r_d - r_0) * 100, 1)})
    for name in ["HVAC"] + list(SUITES):
        sub = df[df["dataset"] == name]
        if sub.empty:
            continue
        r_0 = sub[sub["delta_min"] == 0]["recall@15"].iloc[0]
        for _, r in sub[sub["delta_min"] != 0].iterrows():
            # No per-scenario hits here: the comparison is matched only when
            # no scenario was skipped at this delta.
            rows.append({"dataset": name, "delta_min": int(r["delta_min"]),
                         "n_subset": int(r["n_eval"]),
                         "matched_subset": bool(r["n_skipped"] == 0),
                         "recall@15": r["recall@15"],
                         "recall@15_delta0_same_subset": r_0,
                         "change_pp": round((r["recall@15"] - r_0) * 100, 1)})
    return pd.DataFrame(rows)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--datasets", nargs="+",
                   default=["WADI", "SWaT", "HVAC"] + list(SUITES))
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)
    out = out_dir("tdet_sensitivity", a.out_dir)
    rows, hits = [], []

    if "WADI" in a.datasets:
        wadi = WADIDataset(); wadi._ensure_loaded()
        for d in CPS_DELTAS:
            scs, sk = water_scenarios(wadi, WADI_ATTACKS, d)
            rows.append(eval_block("WADI", scs, sk, d, False, len(WADI_ATTACKS)))
            print(f"  WADI d={d:+d}: {rows[-1]}")
        hits.append(per_scenario_hits(wadi, WADI_ATTACKS, "WADI"))
    if "SWaT" in a.datasets:
        swat = SWaTDataset(); swat._ensure_loaded()
        for d in CPS_DELTAS:
            scs, sk = water_scenarios(swat, swat._attacks, d)
            rows.append(eval_block("SWaT", scs, sk, d, False, len(swat._attacks)))
            print(f"  SWaT d={d:+d}: {rows[-1]}")
        hits.append(per_scenario_hits(swat, swat._attacks, "SWaT"))
    if "HVAC" in a.datasets:
        base = HVACDataset().load_fault_scenarios()
        for d in CPS_DELTAS:
            scs, sk = hvac_scenarios(base, d)
            rows.append(eval_block("HVAC", scs, sk, d, False, len(base)))
            print(f"  HVAC d={d:+d}: {rows[-1]}")
    for suite in SUITES:
        if suite not in a.datasets:
            continue
        ds = RCAEvalDataset(suites=[suite])
        n_total = sum(1 for _ in ds._iter_cases())
        for d in RCA_DELTAS:
            scs, sk = rcaeval_scenarios(ds, suite, d)
            rows.append(eval_block(suite, scs, sk, d, True, n_total))
            print(f"  {suite} d={d:+d}: {rows[-1]}")

    df = pd.DataFrame(rows)
    df.to_csv(out / "tdet_sensitivity.csv", index=False)
    hits_df = pd.concat(hits) if hits else pd.DataFrame(
        columns=["dataset", "scenario_id", "delta_min", "K", "hit"])
    hits_df.to_csv(out / "per_scenario_hits.csv", index=False)
    table = matched_table(df, hits_df)
    table.to_csv(out / "tdet_table.csv", index=False)
    print(table.to_string(index=False))
    bad = df[(df["delta_min"] == 0) & (df.get("delta0_matches_table1") == False)]  # noqa: E712
    if len(bad):
        print("delta = 0 does not reproduce Table 1 on:", list(bad["dataset"]))
        raise SystemExit(1)
    print(f"wrote {out}")


if __name__ == "__main__":
    from method.runners._common import ensure_hash_seed
    ensure_hash_seed()
    main()
