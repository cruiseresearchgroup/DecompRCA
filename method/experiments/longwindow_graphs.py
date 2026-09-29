#!/usr/bin/env python3
"""Graph heads on global graphs learned from long normal-operation windows.

One global PC and FCI graph per dataset is learned from the normal-operation
corpus (after dropping constant / near-constant / exactly collinear
columns), then PageRank / RandomWalk / CIRCA rank every fault scenario
against the fixed graph (scenario construction unchanged).

  WADI, SWaT  full multi-day normal corpus (load_normal_data)
  HVAC        union of the seasonal occupied baselines
  RE1-OB/SS   concatenated pre-injection baselines (no continuous normal
              corpus exists), rows subsampled 1:5 for tractability
  RE1-TT is not run: 241 metric columns are infeasible for constraint-based CD.

Per method the failure is split with the decomposition: retrieval failure =
cause absent from the graph's nodes; reranking failure = present, not top-1.

Graphs are cached as <graph-cache-dir>/<dataset>_<PC|FCI>_global.pkl.

Outputs (method/results/longwindow_graphs/):
  longwindow.csv, longwindow_split.csv

    python -m method.experiments.longwindow_graphs
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from method.algorithms.cd.fci import FCIAdapter
from method.algorithms.cd.pc import PCAdapter
from method.algorithms.cd.per_scenario import _drop_collinear, preprocess_for_cd
from method.algorithms.rca.circa import CIRCAAdapter
from method.algorithms.rca.pagerank import PageRankAdapter
from method.algorithms.rca.random_walk import RandomWalkAdapter
from method.datasets.hvac import HVACDataset
from method.datasets.rcaeval_dataset import RCAEvalDataset
from method.datasets.swat import SWaTDataset
from method.datasets.wadi import WADIDataset
from method.evaluation.metrics import top_at_k
from method.experiments._shared import CACHE_ROOT, out_dir, score_block

HEADS = (("PageRank", PageRankAdapter), ("RandomWalk", RandomWalkAdapter),
         ("CIRCA", CIRCAAdapter))
DATASETS = ("WADI", "SWaT", "HVAC", "RE1-OB", "RE1-SS")


def learn_global(name, normal_df, gdir: Path, require_cached=False):
    """Fit (or load) the global PC and FCI graphs; failures map to None."""
    graphs, cleaned = {}, None
    for cd_name, cd_cls in (("PC", PCAdapter), ("FCI", FCIAdapter)):
        cache = gdir / f"{name}_{cd_name}_global.pkl"
        if cache.exists():
            graphs[cd_name] = pd.read_pickle(cache)
            print(f"  [{name}] {cd_name}: cached ({graphs[cd_name].shape[0]} nodes)")
            continue
        if require_cached:
            raise FileNotFoundError(f"graph not cached: {cache}")
        if cleaned is None:
            cleaned = _drop_collinear(preprocess_for_cd(normal_df.ffill().fillna(0.0)))
            print(f"  [{name}] normal corpus for CD: {cleaned.shape[0]} rows x "
                  f"{cleaned.shape[1]} cols")
        t0 = time.time()
        try:
            g = cd_cls().fit(cleaned)
            graphs[cd_name] = g
            gdir.mkdir(parents=True, exist_ok=True)
            pd.to_pickle(g, cache)
            print(f"  [{name}] {cd_name}: {g.shape[0]} nodes in {time.time()-t0:.0f}s")
        except Exception as e:
            graphs[cd_name] = None
            print(f"  [{name}] {cd_name}: FAILED after {time.time()-t0:.0f}s: {str(e)[:120]}")
    return graphs


def run_heads(name, scenarios, graphs, service_level):
    rows, split_rows = [], []
    for cd_name, g in graphs.items():
        if g is None or g.empty:
            rows.append({"dataset": name, "method": f"(global {cd_name})",
                         "status": "CD fit failed"})
            continue
        nodes = set(g.index)
        if service_level:
            def in_graph(sc):
                svcs = {"_".join(t.split("_")[:-1]).replace("-db", "")
                        for t in sc.ground_truth_causes}
                return any(m.split("_")[0].replace("-db", "") in svcs for m in nodes)
        else:
            def in_graph(sc):
                return any(t in nodes for t in sc.ground_truth_causes)
        n_retr_fail = sum(1 for sc in scenarios if not in_graph(sc))

        for head_name, head_cls in HEADS:
            preds, n_fallback = [], 0
            for sc in scenarios:
                try:
                    preds.append(head_cls().predict(sc, graph=g))
                except Exception as e:
                    print(f"  [{sc.scenario_id}] {head_name}: {str(e)[:90]}")
                    n_fallback += 1
                    preds.append(list(sc.alarm_nodes))
            n = len(scenarios)
            n_rerank_fail = sum(
                1 for sc, p in zip(scenarios, preds)
                if in_graph(sc) and not (
                    top_at_k(["_".join(t.split("_")[:-1]).replace("-db", "")
                              for t in sc.ground_truth_causes],
                             [q.split("_")[0].replace("-db", "")
                              for q in dict.fromkeys(p)], 1)
                    if service_level else
                    top_at_k(sc.ground_truth_causes, p, 1)))
            row = {"dataset": name, "method": f"{head_name} (global {cd_name})",
                   "n": n, "n_fallback": n_fallback, "graph_nodes": len(nodes),
                   **score_block(scenarios, preds, service_level)}
            rows.append(row)
            split_rows.append({"dataset": name, "method": row["method"],
                               "retrieval_failure": round(n_retr_fail / n, 4),
                               "reranking_failure": round(n_rerank_fail / n, 4),
                               "top@1": row["top@1"]})
            print(f"  {row}")
    return rows, split_rows


def load(name):
    """(normal corpus, fault scenarios, service_level) for one dataset."""
    if name == "WADI":
        ds = WADIDataset()
    elif name == "SWaT":
        ds = SWaTDataset()
    elif name == "HVAC":
        ds = HVACDataset()
    else:
        ds = RCAEvalDataset(suites=[name])
        normal = ds.load_normal_data().iloc[::5]
        return normal, ds.load_fault_scenarios(), True
    normal = ds.load_normal_data()
    return normal, ds.load_fault_scenarios(), False


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--datasets", nargs="+", default=list(DATASETS), choices=DATASETS)
    p.add_argument("--graph-cache-dir", default=str(CACHE_ROOT / "global_graphs"))
    p.add_argument("--require-cached", action="store_true")
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)
    out = out_dir("longwindow_graphs", a.out_dir)

    rows, splits = [], []
    for name in a.datasets:
        print(f"== {name} ==")
        normal, scenarios, svc = load(name)
        graphs = learn_global(name, normal, Path(a.graph_cache_dir), a.require_cached)
        r, s = run_heads(name, scenarios, graphs, svc)
        rows += r
        splits += s
        pd.DataFrame(rows).to_csv(out / "longwindow.csv", index=False)
        pd.DataFrame(splits).to_csv(out / "longwindow_split.csv", index=False)
    print(f"wrote {out}")


if __name__ == "__main__":
    from method.runners._common import ensure_hash_seed
    ensure_hash_seed()
    main()
