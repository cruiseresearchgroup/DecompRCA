#!/usr/bin/env python3
"""Same-candidate controls: rule rankers on the LLM's exact candidate lists.

For WADI, SWaT and the RCAEval suites the candidate set C is regenerated
deterministically (the balanced K=15 union) and checked against the logged
LLM prompts: the response cache is keyed by md5(scenario_id + summary), so a
matching cache file with an identical stored summary means C and its evidence
lines are byte-for-byte what the LLM saw. C is then ranked by magnitude,
onset, state change and a Borda fusion of the three; LLM rows are re-scored
from the logged responses (n=3 runs, T=1.0, without and with DK).

HVAC's LLM runs were made on the retrieval-controlled retriever pools, so its
rule rankers are computed on those pools (--pools).

The LLM rows and the candidate check need the logged end-to-end responses
(method/runners/run_llm_balanced.py, n=3, T=1.0). Where a group's logs are
absent, a warning is printed and only its rule / fusion rows are written.

Scoring: metric-level for WADI/SWaT/HVAC, service-level for RCAEval.

Outputs (method/results/same_candidate/):
  same_candidate.csv     rule rankers (candidates = llm-prompt | retriever-pool)
  llm_rows.csv           LLM rows re-scored from the logged responses
  candidate_check.json   regenerated-vs-logged candidate verification
  sanity.json            Retrieval@15 of C per group
  per_scenario.json      per-scenario C and top-5 of each ranker

    python -m method.experiments.same_candidate
    python -m method.experiments.same_candidate --verify-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from method.experiments._shared import (
    RESULTS_ROOT, RULES, build_rankings, hit_in_pool, load_group, load_pools,
    out_dir, score_block,
)
from method.runners._common import build_balanced_summary
from method.runners._datasets import DATASETS_ROOT

CACHE_FMT = ("llm_rca_cache_openai_gpt-oss-120b_{level}_hybrid_clean_"
             "balanced_k15_dklight_run{run}_t100")
LOGGED_GROUPS = ("WADI", "SWaT", "RE1-OB", "RE1-SS", "RE1-TT")
LLM_ROW_COLS = ["group", "level", "run", "n", "top@1", "top@3", "top@5", "avg@5"]
# Table 1, +stc column at K=15 (reference for the Retrieval@15-of-C check)
TABLE1_STC_K15 = {"WADI": 0.643, "SWaT": 0.667, "RE1-OB": 0.976,
                  "RE1-SS": 1.000, "RE1-TT": 0.912}


def cache_file(root, cfg, suite, level, run, scenario_id, summary):
    d = Path(root) / cfg.name / CACHE_FMT.format(level=level, run=run)
    if suite:
        d = d / suite
    key = hashlib.md5((scenario_id + summary).encode()).hexdigest()
    return d / f"rank_{key}.json"


def run_logged_group(group, root, verify_only=False):
    cfg, scenarios, service_level = load_group(group, exclude=False)
    suite = group if service_level else None
    preds = {r: [] for r in RULES}
    llm_preds = {(lvl, r): [] for lvl in ("none", "light") for r in range(3)}
    # No logged cache directory at all -> the logs were not produced here (as
    # opposed to a regenerated summary that misses its logged file).
    logs = cache_file(root, cfg, suite, "none", 0, "", "").parent
    check = {"group": group, "total": 0, "matched": 0, "missing": [],
             "logs_found": logs.is_dir()}
    if not check["logs_found"]:
        print(f"  WARNING: no logged LLM responses at {logs}; skipping the "
              f"candidate check and LLM rows for {group} (run "
              f"method/runners/run_llm_balanced.py first). Rule / fusion rows "
              f"are still computed.")
        llm_preds = {}
    pool_hits, audit = 0, []

    for sc in scenarios:
        summary, C = build_balanced_summary(sc, cfg.time_unit)
        check["total"] += 1
        if check["logs_found"]:
            f0 = cache_file(root, cfg, suite, "none", 0, sc.scenario_id, summary)
            if f0.exists() and json.loads(f0.read_text())["anomaly_summary"] == summary:
                check["matched"] += 1
            else:
                check["missing"].append(sc.scenario_id)
        if verify_only:
            continue
        rankings = build_rankings(sc, C)
        for name, order in rankings.items():
            preds[name].append(order)
        for (lvl, r) in llm_preds:
            f = cache_file(root, cfg, suite, lvl, r, sc.scenario_id, summary)
            if f.exists():
                cached = json.loads(f.read_text())
                llm_preds[(lvl, r)].append(
                    cached["ranked"] if isinstance(cached, dict) else cached)
            else:
                llm_preds[(lvl, r)].append(None)
        pool_hits += hit_in_pool(sc.ground_truth_causes, C, service_level)
        audit.append({"scenario_id": sc.scenario_id,
                      "ground_truth": sc.ground_truth_causes, "C": C,
                      "rankings_top5": {n: o[:5] for n, o in rankings.items()}})
    if verify_only:
        return [], [], None, None, check

    n = len(scenarios)
    rows = [dict({"group": group, "ranker": name, "n": n},
                 **score_block(scenarios, preds[name], service_level),
                 candidates="llm-prompt") for name in RULES]
    llm_rows = []
    for lvl in ("none", "light") if check["logs_found"] else ():
        per_run = []
        for r in range(3):
            pr = llm_preds[(lvl, r)]
            miss = sum(p is None for p in pr)
            if miss:
                print(f"  {group} {lvl} run{r}: {miss} logged responses missing")
                continue
            m = score_block(scenarios, pr, service_level)
            m.update({"group": group, "level": lvl, "run": r, "n": n})
            per_run.append(m)
        if per_run:
            agg = {"group": group, "level": lvl, "run": "mean±std", "n": n}
            for k in ("top@1", "top@3", "top@5", "avg@5"):
                vals = [m[k] for m in per_run]
                agg[k] = f"{np.mean(vals):.4f}±{np.std(vals, ddof=1):.4f}"
            llm_rows.extend(per_run + [agg])
    sanity = {"group": group, "recall@15_of_C": round(pool_hits / n, 4),
              "table1_+stc_K15": TABLE1_STC_K15.get(group)}
    return rows, llm_rows, sanity, audit, check


def run_pool_group(group, pools_doc):
    """Rule rankers on the retriever pools (HVAC)."""
    _, scenarios, service_level = load_group(group)
    scenarios = [s for s in scenarios if s.scenario_id in pools_doc[group]]
    preds = {r: [] for r in RULES}
    audit = []
    for sc in scenarios:
        C = pools_doc[group][sc.scenario_id]["retriever"]["pool"]
        rankings = build_rankings(sc, C)
        for name, order in rankings.items():
            preds[name].append(order)
        audit.append({"scenario_id": sc.scenario_id,
                      "ground_truth": sc.ground_truth_causes, "C": C,
                      "rankings_top5": {n: o[:5] for n, o in rankings.items()}})
    rows = [dict({"group": group, "ranker": name, "n": len(scenarios)},
                 **score_block(scenarios, preds[name], service_level),
                 candidates="retriever-pool") for name in RULES]
    return rows, audit


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--logged-cache-root", default=str(DATASETS_ROOT),
                   help="directory holding <dataset>/llm_rca_cache_* "
                        "(the logged end-to-end LLM responses)")
    p.add_argument("--pools", default=str(RESULTS_ROOT / "controlled_pools" / "pools.json"))
    p.add_argument("--groups", nargs="+", default=list(LOGGED_GROUPS) + ["HVAC"])
    p.add_argument("--verify-only", action="store_true",
                   help="only check regenerated candidates against the logs")
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)
    out = out_dir("same_candidate", a.out_dir)

    rows, llm_rows, sanity, audit, checks = [], [], [], {}, []
    for group in a.groups:
        print(f"== {group} ==")
        if group in LOGGED_GROUPS:
            r, lr, s, au, chk = run_logged_group(group, a.logged_cache_root,
                                                 a.verify_only)
            checks.append(chk)
            if chk["logs_found"]:
                print(f"  candidates: {chk['matched']}/{chk['total']} match the logged prompts")
            if a.verify_only:
                continue
            rows += r
            llm_rows += lr
            sanity.append(s)
            audit[group] = au
        elif not a.verify_only:
            r, au = run_pool_group(group, load_pools(a.pools))
            rows += r
            audit[group] = au

    (out / "candidate_check.json").write_text(json.dumps(checks, indent=2))
    ok = all(not c["missing"] for c in checks)
    no_logs = [c["group"] for c in checks if not c["logs_found"]]
    if a.verify_only and no_logs:
        ok = False     # nothing to verify against
    if not a.verify_only:
        pd.DataFrame(rows).to_csv(out / "same_candidate.csv", index=False)
        pd.DataFrame(llm_rows, columns=LLM_ROW_COLS).to_csv(
            out / "llm_rows.csv", index=False)
        (out / "sanity.json").write_text(json.dumps(sanity, indent=2))
        (out / "per_scenario.json").write_text(json.dumps(audit, indent=2))
        print(pd.DataFrame(rows).to_string(index=False))
        for s in sanity:
            good = abs(s["recall@15_of_C"] - s["table1_+stc_K15"]) < 5e-4
            ok &= good
            print(f"  Retrieval@15 of C {s['group']}: {s['recall@15_of_C']} "
                  f"vs Table 1 {s['table1_+stc_K15']} [{'OK' if good else 'FAIL'}]")
    if no_logs:
        print(f"WARNING: no logged LLM responses for {', '.join(no_logs)}: "
              f"candidate check and LLM rows skipped there")
    print(f"wrote {out}; candidate check {'OK' if ok else 'FAILED'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    from method.runners._common import ensure_hash_seed
    ensure_hash_seed()
    main()
