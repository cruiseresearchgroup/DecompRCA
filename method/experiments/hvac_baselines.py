#!/usr/bin/env python3
"""End-to-end HVAC baselines (the HVAC columns of the main result tables).

Runs BARO, RCD and epsilon-Diagnosis (numpy seeded with 0 per scenario,
PyRCA patch size 4) and PageRank / RandomWalk / CIRCA over per-scenario
PC / FCI graphs on the HVAC scenarios (900-row occupied-day baseline). A
method error or an empty graph falls back to the alarm ranking and is
counted in n_fallback.

Output: method/results/hvac_baselines/hvac_baselines.csv

    python -m method.experiments.hvac_baselines
"""

from __future__ import annotations

import argparse
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
    load_group, out_dir, per_scenario_graph, score_block,
)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--graph-cache-dir", default=None,
                   help="per-scenario graph cache (default: the dataset "
                        "registry's HVAC graph cache)")
    p.add_argument("--require-cached", action="store_true")
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)
    out = out_dir("hvac_baselines", a.out_dir)

    cfg, scenarios, _ = load_group("HVAC")
    cache = Path(a.graph_cache_dir) if a.graph_cache_dir else cfg.graph_cache_dir
    print(f"{len(scenarios)} HVAC scenarios; graph cache {cache}")
    rows = []

    def run(label, fn, seeded=False):
        preds, n_fallback = [], 0
        for sc in scenarios:
            if seeded:
                np.random.seed(0)
            try:
                pr = fn(sc)
            except Exception as e:
                print(f"  [{sc.scenario_id}] {label} error: {str(e)[:90]}")
                pr = list(sc.alarm_nodes)
                n_fallback += 1
            preds.append(pr)
        row = {"method": label, "n": len(scenarios), "n_fallback": n_fallback}
        row.update(score_block(scenarios, preds, False))
        rows.append(row)
        print(f"  {row}")
        pd.DataFrame(rows).to_csv(out / "hvac_baselines.csv", index=False)

    run("BARO", lambda sc: BaroAdapter().predict(sc))
    run("RCD", lambda sc: RCDAdapter(patch=cfg.patch).predict(sc), seeded=True)
    run("EpsilonDiagnosis",
        lambda sc: EpsilonDiagnosisAdapter(patch=cfg.patch).predict(sc), seeded=True)

    for cd_name, cd_cls in (("PC", PCAdapter), ("FCI", FCIAdapter)):
        graphs = {sc.scenario_id: per_scenario_graph(
                      cd_cls, sc, dataset="hvac", cd_name=cd_name,
                      cache_dir=cache, require_cached=a.require_cached)
                  for sc in scenarios}
        for head_name, head_cls in (("PageRank", PageRankAdapter),
                                    ("RandomWalk", RandomWalkAdapter),
                                    ("CIRCA", CIRCAAdapter)):
            def fn(sc, _h=head_cls, _g=graphs):
                g = _g[sc.scenario_id]
                if g is None or g.empty:
                    raise RuntimeError("empty graph")
                return _h().predict(sc, graph=g)
            run(f"{head_name} ({cd_name})", fn)
    print(f"wrote {out / 'hvac_baselines.csv'}")


if __name__ == "__main__":
    from method.runners._common import ensure_hash_seed
    ensure_hash_seed()
    main()
