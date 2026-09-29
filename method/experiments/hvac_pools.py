#!/usr/bin/env python3
"""HVAC Retrieval@K, retrieval-controlled pools and the baselines on them.

  1. Cumulative-budget Retrieval@K (mag / +ons / +stc, K in {5, 10, 15}).
  2. The three pool configurations (same construction as controlled_pools).
  3. BARO, RCD, epsilon-Diagnosis (seeded) and PageRank / RandomWalk / CIRCA
     over per-scenario PC / FCI graphs on each pool (pool-restricted graphs
     for `retriever` / `random`, full-data graphs for `all`). Method errors
     and empty graphs fall back to the alarm ranking, counted in n_fallback.

Outputs (method/results/hvac_pools/):
  hvac_recall.csv, hvac_pools.json, hvac_pool_baselines.csv

    python -m method.experiments.hvac_pools
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from method.algorithms.cd.fci import FCIAdapter
from method.algorithms.cd.pc import PCAdapter
from method.algorithms.rca.baro import BaroAdapter
from method.algorithms.rca.circa import CIRCAAdapter
from method.algorithms.rca.epsilon_diagnosis import EpsilonDiagnosisAdapter
from method.algorithms.rca.pagerank import PageRankAdapter
from method.algorithms.rca.random_walk import RandomWalkAdapter
from method.algorithms.rca.rcd import RCDAdapter
from method.experiments._shared import (
    CACHE_ROOT, CONFIGS, K, load_group, out_dir, per_scenario_graph,
    score_block, subset_scenario,
)
from method.experiments.controlled_pools import build_pools, pool_has_gt
from method.runners.compute_retrieval_recall_cumulative import (
    _build_pool_cumulative, _hit,
)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--pool-graph-cache", default=str(CACHE_ROOT / "pool_graphs" / "HVAC"),
                   help="pool-restricted graphs at DIR/<config>")
    p.add_argument("--graph-cache-dir", default=None,
                   help="full-data per-scenario graphs (default: the dataset "
                        "registry's HVAC graph cache)")
    p.add_argument("--require-cached", action="store_true")
    p.add_argument("--skip-baselines", action="store_true")
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)
    out = out_dir("hvac_pools", a.out_dir)

    cfg, scenarios, _ = load_group("HVAC")
    full_cache = Path(a.graph_cache_dir) if a.graph_cache_dir else cfg.graph_cache_dir
    print(f"{len(scenarios)} HVAC scenarios")

    rows = []
    for k in (5, 10, 15):
        row = {"K": k}
        for n_sig, label in ((1, "mag"), (2, "+ons"), (3, "+stc")):
            hits = 0
            for sc in scenarios:
                pool, _ = _build_pool_cumulative(sc, k, n_sig)
                hits += _hit(sc.ground_truth_causes, pool, service_level=False)
            row[label] = round(hits / len(scenarios), 4)
        rows.append(row)
        print(f"  Retrieval@{k}: {row}")
    pd.DataFrame(rows).to_csv(out / "hvac_recall.csv", index=False)

    pools_out, inj = {}, {c: 0 for c in CONFIGS}
    for sc in scenarios:
        pools = build_pools(sc, False)
        assert pools is not None
        for c in CONFIGS:
            assert pool_has_gt(pools[c]["pool"], sc, False)
            inj[c] += int(pools[c]["injected"])
        pools_out[sc.scenario_id] = pools
    (out / "hvac_pools.json").write_text(json.dumps(
        {"K": K, "injected": inj, "pools": pools_out}, indent=2))
    print(f"  pools written; injected: {inj}")
    if a.skip_baselines:
        return

    brows = []

    def run(config, label, fn, seeded=False):
        preds, n_fb = [], 0
        for sc in scenarios:
            sub = subset_scenario(sc, pools_out[sc.scenario_id][config]["pool"])
            if seeded:
                np.random.seed(0)
            try:
                pr = fn(sc, sub)
            except Exception as e:
                print(f"  [{sc.scenario_id}] {label}({config}) error: {str(e)[:90]}")
                n_fb += 1
                pr = list(sub.alarm_nodes)
            preds.append(pr)
        row = {"config": config, "method": label, "n": len(scenarios),
               "n_fallback": n_fb}
        row.update(score_block(scenarios, preds, False))
        brows.append(row)
        print(f"  {config:9s} {label}: top@1={row['top@1']} (fb={n_fb})")
        pd.DataFrame(brows).to_csv(out / "hvac_pool_baselines.csv", index=False)

    for config in CONFIGS:
        run(config, "BARO", lambda sc, sub: BaroAdapter().predict(sub))
        run(config, "RCD", lambda sc, sub: RCDAdapter(patch=cfg.patch).predict(sub),
            seeded=True)
        run(config, "EpsilonDiagnosis",
            lambda sc, sub: EpsilonDiagnosisAdapter(patch=cfg.patch).predict(sub),
            seeded=True)
        for cd_name, cd_cls in (("PC", PCAdapter), ("FCI", FCIAdapter)):
            graphs = {}
            for sc in scenarios:
                sub = subset_scenario(sc, pools_out[sc.scenario_id][config]["pool"])
                target = sc if config == "all" else sub
                cache = full_cache if config == "all" \
                    else Path(a.pool_graph_cache) / config
                graphs[sc.scenario_id] = per_scenario_graph(
                    cd_cls, target, dataset="hvac", cd_name=cd_name,
                    cache_dir=cache, require_cached=a.require_cached)
            for head_name, head_cls in (("PageRank", PageRankAdapter),
                                        ("RandomWalk", RandomWalkAdapter),
                                        ("CIRCA", CIRCAAdapter)):
                def fn(sc, sub, _h=head_cls, _g=graphs, _cfg=config):
                    g = _g[sc.scenario_id]
                    if g is None or g.empty:
                        raise RuntimeError("empty graph")
                    return _h().predict(sc if _cfg == "all" else sub, graph=g)
                run(config, f"{head_name} ({cd_name})", fn)
    print(f"wrote {out}")


if __name__ == "__main__":
    from method.runners._common import ensure_hash_seed
    ensure_hash_seed()
    main()
