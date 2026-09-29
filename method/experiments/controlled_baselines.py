#!/usr/bin/env python3
"""The nine baselines on the retrieval-controlled pools.

Reads the frozen pools (controlled_pools) and runs epsilon-Diagnosis (seeded)
and PageRank / RandomWalk / CIRCA over per-scenario PC and FCI graphs on each
pool configuration. Graphs are fitted on the pool-restricted data for
`retriever` and `random` and reused from the per-scenario full-data graph
cache for `all`. BARO and RCD rows are taken from controlled_pools
(same pools). Empty-graph fallbacks to the alarm ranking are counted in
``n_fallback``; method errors in ``n_error``.

Graph caches:
  --graph-cache-root ROOT     pool graphs at ROOT/<group>/<config>
  --group-graph-cache G=DIR   pool graphs of group G at DIR/<config>
  --full-graph-cache G=DIR    full-data graphs of group G (config `all`);
                              default: the dataset registry's graph cache

Outputs (method/results/controlled_baselines/):
  pool_baselines_<group>.csv  epsilon-Diagnosis + graph rows per group
  pool_baselines.csv          all nine baselines, all groups

    python -m method.experiments.controlled_baselines
    python -m method.experiments.controlled_baselines --groups WADI SWaT
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from method.algorithms.cd.fci import FCIAdapter
from method.algorithms.cd.pc import PCAdapter
from method.algorithms.rca.circa import CIRCAAdapter
from method.algorithms.rca.epsilon_diagnosis import EpsilonDiagnosisAdapter
from method.algorithms.rca.pagerank import PageRankAdapter
from method.algorithms.rca.random_walk import RandomWalkAdapter
from method.experiments._shared import (
    CACHE_ROOT, CONFIGS, GROUPS, RESULTS_ROOT, load_group, load_pools,
    out_dir, parse_overrides, per_scenario_graph, score_block,
    subset_scenario,
)

CD_ALGOS = (("PC", PCAdapter), ("FCI", FCIAdapter))
HEADS = (("PageRank", PageRankAdapter), ("RandomWalk", RandomWalkAdapter),
         ("CIRCA", CIRCAAdapter))
ORDER = ["BARO", "RCD", "EpsilonDiagnosis",
         "PageRank (PC)", "PageRank (FCI)", "RandomWalk (PC)",
         "RandomWalk (FCI)", "CIRCA (PC)", "CIRCA (FCI)"]


def run_group(group, pools_doc, pool_cache, full_cache, require_cached):
    cfg, scenarios, service_level = load_group(group)
    scenarios = [s for s in scenarios if s.scenario_id in pools_doc[group]]
    full_cache = full_cache or cfg.graph_cache_dir
    rows = []

    for config in CONFIGS:
        subs = {sc.scenario_id: subset_scenario(
                    sc, pools_doc[group][sc.scenario_id][config]["pool"])
                for sc in scenarios}

        preds, n_err = [], 0
        for sc in scenarios:
            np.random.seed(0)
            try:
                preds.append(EpsilonDiagnosisAdapter(patch=cfg.patch)
                             .predict(subs[sc.scenario_id]))
            except Exception as e:
                print(f"  [{sc.scenario_id}] EpsilonDiagnosis({config}) error: {e}")
                n_err += 1
                preds.append([])
        row = {"group": group, "config": config, "ranker": "EpsilonDiagnosis",
               "n": len(scenarios), "n_fallback": 0}
        row.update(score_block(scenarios, preds, service_level))
        row["n_error"] = n_err
        rows.append(row)
        print(f"  {group}/{config} EpsilonDiagnosis: top@1={row['top@1']}")

        for cd_name, cd_cls in CD_ALGOS:
            graphs = {}
            for sc in scenarios:
                if config == "all":
                    target, cache = sc, full_cache
                else:
                    target, cache = subs[sc.scenario_id], pool_cache / config
                graphs[sc.scenario_id] = per_scenario_graph(
                    cd_cls, target, dataset=cfg.name, cd_name=cd_name,
                    cache_dir=cache, require_cached=require_cached)
            for head_name, head_cls in HEADS:
                preds, n_fallback = [], 0
                for sc in scenarios:
                    g = graphs[sc.scenario_id]
                    target = sc if config == "all" else subs[sc.scenario_id]
                    if g is None or g.empty:
                        n_fallback += 1
                        preds.append(list(target.alarm_nodes))
                        continue
                    try:
                        preds.append(head_cls().predict(target, graph=g))
                    except Exception as e:
                        print(f"  [{sc.scenario_id}] {head_name}({cd_name}) error: {e}")
                        n_fallback += 1
                        preds.append(list(target.alarm_nodes))
                row = {"group": group, "config": config,
                       "ranker": f"{head_name} ({cd_name})",
                       "n": len(scenarios), "n_fallback": n_fallback}
                row.update(score_block(scenarios, preds, service_level))
                row["n_error"] = 0
                rows.append(row)
                print(f"  {group}/{config} {head_name} ({cd_name}): "
                      f"top@1={row['top@1']} fallback={n_fallback}")
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--groups", nargs="+", default=list(GROUPS), choices=GROUPS)
    p.add_argument("--pools", default=str(RESULTS_ROOT / "controlled_pools" / "pools.json"))
    p.add_argument("--rankers-csv",
                   default=str(RESULTS_ROOT / "controlled_pools" / "pool_rankers.csv"),
                   help="controlled_pools output holding the BARO/RCD rows")
    p.add_argument("--graph-cache-root", default=str(CACHE_ROOT / "pool_graphs"))
    p.add_argument("--group-graph-cache", action="append", default=[],
                   metavar="GROUP=DIR")
    p.add_argument("--full-graph-cache", action="append", default=[],
                   metavar="GROUP=DIR")
    p.add_argument("--require-cached", action="store_true",
                   help="fail instead of fitting a graph that is not cached")
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)
    out = out_dir("controlled_baselines", a.out_dir)

    pools_doc = load_pools(a.pools)
    group_cache = parse_overrides(a.group_graph_cache)
    full_cache = parse_overrides(a.full_graph_cache)
    for group in a.groups:
        print(f"== {group} ==")
        rows = run_group(group, pools_doc,
                         group_cache.get(group, Path(a.graph_cache_root) / group),
                         full_cache.get(group), a.require_cached)
        pd.DataFrame(rows).to_csv(out / f"pool_baselines_{group}.csv", index=False)

    # Assemble every per-group file present with the BARO/RCD rows.
    parts = []
    if Path(a.rankers_csv).exists():
        prev = pd.read_csv(a.rankers_csv)
        keep = prev[prev["ranker"].isin(["BARO", "RCD"])].copy()
        keep["n_fallback"] = 0
        parts.append(keep)
    else:
        print(f"note: {a.rankers_csv} not found; BARO/RCD rows omitted")
    for g in GROUPS:
        f = out / f"pool_baselines_{g}.csv"
        if f.exists():
            parts.append(pd.read_csv(f))
    df = pd.concat(parts, ignore_index=True, sort=False)
    df.to_csv(out / "pool_baselines.csv", index=False)
    print(f"wrote {out / 'pool_baselines.csv'}")


if __name__ == "__main__":
    from method.runners._common import ensure_hash_seed
    ensure_hash_seed()
    main()
