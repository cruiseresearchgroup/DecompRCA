"""Helpers shared by the controlled-experiment scripts."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd

from method.algorithms.cd.per_scenario import (
    DATASET_SAMPLE_RATE_HZ, DEFAULT_WINDOW_MINUTES, _cache_path, _drop_collinear,
    fit_graph_per_scenario, preprocess_for_cd, window_around_inject,
)
from method.algorithms.rca.candidate_selection import (
    detect_earliest_onset, detect_state_changes, score_metrics,
)
from method.datasets.base import FaultScenario
from method.evaluation.metrics import avg_at_k, top_at_k
from method.runners._datasets import get as get_dataset

REPO = Path(__file__).resolve().parents[2]
RESULTS_ROOT = REPO / "method" / "results"
CACHE_ROOT = RESULTS_ROOT / "cache"
PROMPTS_ROOT = REPO / "method" / "prompts"

K = 15
CONFIGS = ("retriever", "all", "random")
# Scenarios whose ground-truth cause has no data column: the cause cannot be
# placed in a pool, so they are left out of the retrieval-controlled analysis.
EXCLUDE = {"wadi": {"13"}, "swat": {"4"}}

GROUPS = ("WADI", "SWaT", "HVAC", "RE1-OB", "RE1-SS", "RE1-TT")
GROUP_DS = {"WADI": ("wadi", None), "SWaT": ("swat", None),
            "HVAC": ("hvac", None),
            "RE1-OB": ("rcaeval", "RE1-OB"), "RE1-SS": ("rcaeval", "RE1-SS"),
            "RE1-TT": ("rcaeval", "RE1-TT")}
RULES = ("mag-on-C", "ons-on-C", "stc-on-C", "fusion-on-C")


def out_dir(name: str, root: str | Path | None = None) -> Path:
    d = Path(root) if root else RESULTS_ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_group(group: str, exclude: bool = True):
    """Return (cfg, scenarios, service_level) for one evaluation group."""
    ds, suite = GROUP_DS[group]
    cfg = get_dataset(ds)
    loader = cfg.loader(suites=[suite]) if suite else cfg.loader()
    scenarios = loader.load_fault_scenarios()
    if exclude:
        scenarios = [s for s in scenarios
                     if s.scenario_id not in EXCLUDE.get(ds, set())]
    return cfg, scenarios, ds == "rcaeval"


def parse_overrides(items) -> dict[str, Path]:
    """Parse repeated ``KEY=PATH`` command-line items into a dict."""
    out = {}
    for it in items or []:
        key, _, path = it.partition("=")
        if not path:
            raise SystemExit(f"expected KEY=PATH, got {it!r}")
        out[key] = Path(path)
    return out


# ---------------------------------------------------------------------------
# Scoring (metric-level for CPS, service-level for RCAEval)
# ---------------------------------------------------------------------------

def service_of(metric: str) -> str:
    return metric.split("_")[0].replace("-db", "")


def gt_services(truths) -> set[str]:
    return {"_".join(t.split("_")[:-1]).replace("-db", "") for t in truths}


def service_ranks(pred):
    """Metric ranking -> deduplicated service ranking (RCAEval protocol)."""
    seen = []
    for p in pred:
        if not p or "_" not in p:
            continue
        svc = p.split("_")[0].replace("-db", "")
        if svc not in seen:
            seen.append(svc)
    return seen


def service_truths(truths):
    return ["_".join(t.split("_")[:-1]).replace("-db", "") for t in truths]


def score_block(scenarios, preds, service_level):
    """top@1/3/5 and Avg@5, rounded to 4 decimals."""
    if service_level:
        y_true = [service_truths(sc.ground_truth_causes) for sc in scenarios]
        y_pred = [service_ranks(p) for p in preds]
    else:
        y_true = [sc.ground_truth_causes for sc in scenarios]
        y_pred = preds
    row = {}
    for k in (1, 3, 5):
        row[f"top@{k}"] = round(float(np.mean(
            [top_at_k(t, p, k) for t, p in zip(y_true, y_pred)])), 4)
    row["avg@5"] = round(avg_at_k(y_true, y_pred, 5), 4)
    return row


def hit_in_pool(truths, pool, service_level):
    if service_level:
        return int(any(t in [p.split("_")[0].replace("-db", "") for p in pool]
                       for t in service_truths(truths)))
    return int(any(t in pool for t in truths))


# ---------------------------------------------------------------------------
# Deterministic rankers over a fixed candidate list C
# ---------------------------------------------------------------------------

def build_rankings(scenario, C):
    """Order C by magnitude, onset, state change, and a Borda fusion of all three.

    mag-on-C    : phi_mag descending (BARO's robust scoring restricted to C)
    ons-on-C    : candidates with a detected onset first (earliest first),
                  the rest by phi_mag
    stc-on-C    : state-change candidates first (scorer order), the rest by
                  phi_mag
    fusion-on-C : Borda count over the three per-signal ranks within C
                  (missing signal = worst rank + 1), ties broken by phi_mag
    """
    data = scenario.data.ffill().fillna(0)
    diag = int(scenario.diagnosis_time)
    normal = data.iloc[:diag]
    anomal = data.iloc[diag:]

    mag = dict(score_metrics(scenario))
    ons = dict(detect_earliest_onset(normal, anomal, z_low=1.5))
    stc_list = detect_state_changes(normal, anomal)
    stc_order = [m for m, _ in stc_list if m in set(C)]

    def by_mag(items):
        return sorted(items, key=lambda m: -mag.get(m, 0.0))

    mag_on_C = by_mag(C)
    with_onset = sorted([m for m in C if m in ons],
                        key=lambda m: (ons[m], -mag.get(m, 0.0)))
    ons_on_C = with_onset + by_mag([m for m in C if m not in ons])
    stc_set = set(stc_order)
    stc_on_C = stc_order + by_mag([m for m in C if m not in stc_set])

    def ranks_from_order(order, universe):
        r = {m: i + 1 for i, m in enumerate(order)}
        worst = len(order) + 1
        return {m: r.get(m, worst) for m in universe}

    r_mag = ranks_from_order(mag_on_C, C)
    r_ons = ranks_from_order(with_onset, C)
    r_stc = ranks_from_order(stc_order, C)
    fusion_on_C = sorted(C, key=lambda m: (r_mag[m] + r_ons[m] + r_stc[m],
                                           -mag.get(m, 0.0)))
    return {"mag-on-C": mag_on_C, "ons-on-C": ons_on_C,
            "stc-on-C": stc_on_C, "fusion-on-C": fusion_on_C}


# ---------------------------------------------------------------------------
# Pools
# ---------------------------------------------------------------------------

def seeded_rng(scenario_id: str) -> random.Random:
    return random.Random(int(hashlib.md5(scenario_id.encode()).hexdigest(), 16) % 2**32)


def subset_scenario(scenario, pool):
    """Restrict a scenario's data and alarm nodes to the pool's columns."""
    cols = [c for c in scenario.data.columns if c in set(pool)]
    return FaultScenario(
        scenario_id=scenario.scenario_id,
        data=scenario.data[cols],
        diagnosis_time=scenario.diagnosis_time,
        ground_truth_causes=scenario.ground_truth_causes,
        alarm_nodes=[a for a in scenario.alarm_nodes if a in set(pool)],
        sample_rate_hz=scenario.sample_rate_hz,
    )


def load_pools(path: str | Path) -> dict:
    """Return ``{group: {scenario_id: {config: {...}}}}`` from a pools file.

    Accepts both the multi-group file written by controlled_pools and the
    single-group HVAC file written by hvac_pools (keyed as group ``HVAC``).
    """
    doc = json.loads(Path(path).read_text())
    pools = doc["pools"]
    if pools and all(c in next(iter(pools.values())) for c in CONFIGS):
        return {"HVAC": pools}
    return pools


# ---------------------------------------------------------------------------
# Graph cache access
# ---------------------------------------------------------------------------

def per_scenario_graph(cd_cls, scenario, *, dataset, cd_name, cache_dir,
                       require_cached=False):
    """Per-scenario PC/FCI graph via the shared fitting helper.

    With ``require_cached`` a missing cache file raises instead of fitting,
    except where the helper would return an empty graph without fitting.
    """
    if require_cached:
        w = DEFAULT_WINDOW_MINUTES.get(dataset, 10)
        path = _cache_path(cache_dir, scenario.scenario_id, cd_name, w)
        if not path.exists():
            windowed = window_around_inject(
                scenario, w, DATASET_SAMPLE_RATE_HZ.get(dataset, 1.0))
            cleaned = preprocess_for_cd(windowed)
            if (cleaned.shape[1] < 2 or cleaned.shape[0] < 10
                    or _drop_collinear(cleaned).shape[1] < 2):
                return pd.DataFrame()
            raise FileNotFoundError(f"graph not cached: {path}")
    return fit_graph_per_scenario(cd_cls(), scenario, dataset=dataset,
                                  cd_name=cd_name, cache_dir=cache_dir)


def write_csv(df: pd.DataFrame, path: Path) -> Path:
    df.to_csv(path, index=False)
    return path
