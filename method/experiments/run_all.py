#!/usr/bin/env python3
"""Run the controlled experiments in order and list where each table lands.

Deterministic steps always run; the LLM step runs only with --llm-cache-dir
(offline re-scoring of stored responses) or --run-llm (API calls for
responses missing from the cache). Every step is a subprocess with
PYTHONHASHSEED=0. same_candidate's LLM rows re-score the logged end-to-end
responses, so they need method/runners/run_llm_balanced.py runs first;
without them it writes the rule / fusion rows only.

    python -m method.experiments.run_all
    python -m method.experiments.run_all --llm-cache-dir DIR
    python -m method.experiments.run_all --only controlled_pools tables
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from method.experiments._shared import REPO, RESULTS_ROOT

STEPS = ["controlled_pools", "controlled_baselines", "hvac_baselines",
         "hvac_pools", "tdet_sensitivity", "longwindow_graphs",
         "controlled_llm", "same_candidate", "tables"]

TABLE_MAP = [
    ("Table 1 (HVAC row)", "hvac_pools/hvac_recall.csv"),
    ("Tables 3, 5 (HVAC columns)", "hvac_baselines/hvac_baselines.csv, "
                                   "controlled_llm/llm_end_to_end_summary.csv"),
    ("Table 4", "tables/table04_retrieval_controlled.csv"),
    ("Tables 7-8", "same_candidate/same_candidate.csv, same_candidate/llm_rows.csv"),
    ("Table 9", "same_candidate/same_candidate.csv (HVAC), controlled_llm/llm_summary.csv"),
    ("Tables 10-11", "controlled_baselines/pool_baselines.csv, controlled_llm/llm_summary.csv"),
    ("Tables 12-14", "controlled_llm/llm_summary.csv"),
    ("Table 15", "tdet_sensitivity/tdet_table.csv"),
    ("Table 16", "longwindow_graphs/longwindow.csv, longwindow_graphs/longwindow_split.csv"),
    ("All assembled", "tables/"),
]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--only", nargs="+", choices=STEPS, default=None)
    p.add_argument("--run-llm", action="store_true")
    p.add_argument("--llm-cache-dir", default=None)
    p.add_argument("--require-cached", action="store_true",
                   help="never fit a causal graph; fail if one is not cached")
    p.add_argument("--pool-graph-root", default=None,
                   help="pool-restricted graphs at ROOT/<group>/<config>")
    p.add_argument("--hvac-pool-graph-cache", default=None,
                   help="HVAC pool-restricted graphs at DIR/<config>")
    p.add_argument("--global-graph-cache", default=None,
                   help="global long-window graphs <dataset>_<PC|FCI>_global.pkl")
    p.add_argument("--keep-going", action="store_true")
    a = p.parse_args(argv)

    env = dict(os.environ, PYTHONHASHSEED="0")
    graph_flag = ["--require-cached"] if a.require_cached else []
    pool_args, hvac_args, lw_args = [], [], []
    if a.pool_graph_root:
        pool_args += ["--graph-cache-root", a.pool_graph_root]
        hvac_args += ["--pool-graph-cache", os.path.join(a.pool_graph_root, "HVAC")]
    if a.hvac_pool_graph_cache:
        pool_args += ["--group-graph-cache", f"HVAC={a.hvac_pool_graph_cache}"]
        hvac_args = ["--pool-graph-cache", a.hvac_pool_graph_cache]
    if a.global_graph_cache:
        lw_args = ["--graph-cache-dir", a.global_graph_cache]
    extra = {
        "controlled_baselines": graph_flag + pool_args,
        "hvac_baselines": graph_flag,
        "hvac_pools": graph_flag + hvac_args,
        "longwindow_graphs": graph_flag + lw_args,
        "controlled_llm": ["--paper-grid"]
        + (["--cache-dir", a.llm_cache_dir] if a.llm_cache_dir else [])
        + (["--run-llm"] if a.run_llm else []),
    }
    for step in a.only or STEPS:
        if step == "controlled_llm":
            if not (a.run_llm or a.llm_cache_dir):
                print("controlled_llm: skipped (pass --llm-cache-dir or --run-llm)")
                continue
        cmd = [sys.executable, "-m", f"method.experiments.{step}"] + extra.get(step, [])
        print(f"\n### {' '.join(cmd[1:])}", flush=True)
        rc = subprocess.call(cmd, cwd=REPO, env=env)
        if rc != 0:
            print(f"step {step} exited with {rc}")
            if not a.keep_going:
                sys.exit(rc)

    print("\nPaper tables -> CSVs under", RESULTS_ROOT)
    for table, path in TABLE_MAP:
        print(f"  {table:28s} {path}")


if __name__ == "__main__":
    main()
