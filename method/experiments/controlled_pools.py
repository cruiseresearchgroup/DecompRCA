#!/usr/bin/env python3
"""Retrieval-controlled candidate pools and the rankers that need no graph.

Three pool configurations per scenario, each guaranteed to contain the
ground-truth cause (Retrieval@K = 1 by construction), so top@k differences
between rankers on the same pool are reranking differences only:

  retriever : balanced K=15 pool; if the cause is absent, the last item is
              replaced by the cause, inserted at a seeded random position
  all       : every column of the scenario
  random    : seeded random K-1 non-cause columns plus the cause

Rankers on each pool: the four rule rankers (mag / ons / stc / Borda), BARO
and RCD (seeded) with the data restricted to the pool. RCD on the full
RCAEval column space is expensive; by default those three cells reuse the
end-to-end RCD rows (identical scenario sets) unless --compute-rcd-all.

Outputs (method/results/controlled_pools/):
  pools.json          frozen pools, consumed by the other pool experiments
  pool_rankers.csv    one row per (group, config, ranker)

    python -m method.experiments.controlled_pools
    python -m method.experiments.controlled_pools --pools-only
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from method.algorithms.rca.baro import BaroAdapter
from method.algorithms.rca.candidate_selection import (
    score_metrics, select_candidates_balanced,
)
from method.algorithms.rca.rcd import RCDAdapter
from method.experiments._shared import (
    CONFIGS, EXCLUDE, GROUPS, K, RULES, build_rankings, gt_services,
    load_group, out_dir, score_block, seeded_rng, service_of,
    subset_scenario,
)

# End-to-end RCD rows (single run, service level) for RCAEval: the
# `all` configuration evaluates the same scenarios on the same columns.
RCAEVAL_RCD_END_TO_END = {
    "RE1-OB": {"top@1": 0.304, "top@3": 0.432, "top@5": 0.432, "avg@5": 0.4032},
    "RE1-SS": {"top@1": 0.248, "top@3": 0.512, "top@5": 0.512, "avg@5": 0.4464},
    "RE1-TT": {"top@1": 0.144, "top@3": 0.184, "top@5": 0.184, "avg@5": 0.176},
}


def pool_has_gt(pool, scenario, service_level) -> bool:
    if service_level:
        svcs = gt_services(scenario.ground_truth_causes)
        return any(service_of(m) in svcs for m in pool)
    return any(t in pool for t in scenario.ground_truth_causes)


def gt_inject_candidate(scenario, service_level, mag: dict) -> str | None:
    """The column to insert: the highest-phi_mag ground-truth representative."""
    cols = set(scenario.data.columns)
    if service_level:
        svcs = gt_services(scenario.ground_truth_causes)
        members = [c for c in cols if service_of(c) in svcs]
    else:
        members = [t for t in scenario.ground_truth_causes if t in cols]
    if not members:
        return None
    return max(members, key=lambda m: mag.get(m, float("-inf")))


def build_pools(scenario, service_level):
    """Return ``{config: {pool, injected, injected_gt, injected_pos}}``, or
    None when the cause has no column in the scenario data."""
    mag = dict(score_metrics(scenario))
    all_cols = list(scenario.data.columns)
    rng = seeded_rng(scenario.scenario_id)

    inject = gt_inject_candidate(scenario, service_level, mag)
    if inject is None:
        return None

    out = {}
    pool = [m for m, _, _ in select_candidates_balanced(scenario, k=K)]
    injected = not pool_has_gt(pool, scenario, service_level)
    pos = None
    if injected:
        pool = pool[:-1] if len(pool) >= K else pool[:]
        pos = rng.randint(0, len(pool))
        pool = pool[:pos] + [inject] + pool[pos:]
    out["retriever"] = {"pool": pool, "injected": injected,
                        "injected_gt": inject if injected else None,
                        "injected_pos": pos}

    out["all"] = {"pool": all_cols, "injected": False,
                  "injected_gt": None, "injected_pos": None}

    if service_level:
        svcs = gt_services(scenario.ground_truth_causes)
        non_gt = [c for c in all_cols if service_of(c) not in svcs]
    else:
        non_gt = [c for c in all_cols if c not in set(scenario.ground_truth_causes)]
    draw = rng.sample(non_gt, min(K - 1, len(non_gt)))
    pos = rng.randint(0, len(draw))
    pool = draw[:pos] + [inject] + draw[pos:]
    out["random"] = {"pool": pool, "injected": True,
                     "injected_gt": inject, "injected_pos": pos}
    return out


def run_group(group, cfg, scenarios, service_level, rankers=True,
              rcd_all_row=None):
    """Pools (+ optional ranker rows) for one group."""
    names = RULES + ("BARO", "RCD")
    preds = {(c, r): [] for c in CONFIGS for r in names}
    errors = {(c, r): 0 for c in CONFIGS for r in names}
    pools_out, injected_count = {}, {c: 0 for c in CONFIGS}
    kept = []

    for sc in scenarios:
        pools = build_pools(sc, service_level)
        if pools is None:
            print(f"  {group} {sc.scenario_id}: cause has no data column, skipped")
            continue
        kept.append(sc)
        pools_out[sc.scenario_id] = pools
        # RCAEval: BARO once on the original scenario (RCAEval's entry point,
        # same variant as end to end), restricted to each pool below.
        baro_full = BaroAdapter().predict(sc) if (rankers and service_level) \
            else None
        for c in CONFIGS:
            pool = pools[c]["pool"]
            assert pool_has_gt(pool, sc, service_level), (group, sc.scenario_id, c)
            injected_count[c] += int(pools[c]["injected"])
            if not rankers:
                continue
            rankings = build_rankings(sc, pool)
            for r in RULES:
                preds[(c, r)].append(rankings[r])
            sub = subset_scenario(sc, pool)
            # RCAEval (every config): the full-scenario BARO ranking restricted
            # to the pool, then any unranked pool columns in pool order. BARO
            # scores each metric independently, so this equals BARO on the
            # pool. Elsewhere the pool subset uses the RobustScaler path.
            if service_level:
                pool_set = set(pool)
                ranked = [m for m in baro_full if m in pool_set]
                seen = set(ranked)
                ranked += [m for m in pool if m not in seen]
                preds[(c, "BARO")].append(ranked)
            else:
                preds[(c, "BARO")].append(BaroAdapter().predict(sub))
            if c == "all" and rcd_all_row is not None:
                preds[(c, "RCD")].append(None)
            else:
                np.random.seed(0)
                try:
                    preds[(c, "RCD")].append(RCDAdapter(patch=cfg.patch).predict(sub))
                except Exception as e:
                    print(f"  [{sc.scenario_id}] RCD({c}) error: {e}; empty ranking")
                    errors[(c, "RCD")] += 1
                    preds[(c, "RCD")].append([])

    rows = []
    if rankers:
        for c in CONFIGS:
            for r in names:
                row = {"group": group, "config": c, "ranker": r, "n": len(kept)}
                if c == "all" and r == "RCD" and rcd_all_row is not None:
                    row["source"] = "end-to-end"
                    row.update(rcd_all_row)
                else:
                    row["source"] = "computed"
                    row.update(score_block(kept, preds[(c, r)], service_level))
                row["n_error"] = errors[(c, r)]
                rows.append(row)
    stats = {"group": group, "n": len(kept),
             "injected": {c: injected_count[c] for c in CONFIGS}}
    return rows, pools_out, stats


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--groups", nargs="+", default=list(GROUPS), choices=GROUPS)
    p.add_argument("--pools-only", action="store_true",
                   help="write pools.json only (skip the rankers)")
    p.add_argument("--compute-rcd-all", action="store_true",
                   help="run RCD on the RCAEval `all` pools instead of "
                        "reusing the end-to-end rows")
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)
    out = out_dir("controlled_pools", a.out_dir)

    all_rows, all_pools, all_stats = [], {}, []
    for group in a.groups:
        print(f"== {group} ==")
        cfg, scenarios, svc = load_group(group)
        rcd_row = None if (a.compute_rcd_all or not svc) \
            else RCAEVAL_RCD_END_TO_END[group]
        rows, pools, stats = run_group(group, cfg, scenarios, svc,
                                       rankers=not a.pools_only,
                                       rcd_all_row=rcd_row)
        all_rows += rows
        all_pools[group] = pools
        all_stats.append(stats)
        print(f"  {stats}")

    (out / "pools.json").write_text(json.dumps(
        {"K": K, "excluded": {k: sorted(v) for k, v in EXCLUDE.items()},
         "stats": all_stats, "pools": all_pools}, indent=2))
    print(f"wrote {out / 'pools.json'}")
    if all_rows:
        df = pd.DataFrame(all_rows)
        df.to_csv(out / "pool_rankers.csv", index=False)
        print(df.to_string(index=False))
        print(f"wrote {out / 'pool_rankers.csv'}")


if __name__ == "__main__":
    from method.runners._common import ensure_hash_seed
    ensure_hash_seed()
    main()
