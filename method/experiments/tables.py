#!/usr/bin/env python3
"""Assemble the paper-table CSVs from the experiment outputs.

Reads method/results/<experiment>/ and writes method/results/tables/:

  table01_hvac_retrieval.csv        HVAC row of Table 1
  table03_05_hvac.csv               HVAC columns of Tables 3 and 5
  table04_retrieval_controlled.csv  Table 4 (BB, LLM, delta in pp)
  table07_09_same_candidate.csv     Tables 7-9 (rules + LLM, top@1/3/5/Avg@5)
  table10_pool_retriever.csv        Table 10 (top@1, retriever pools)
  table11_pool_all.csv              Table 11 (top@1, all candidates)
  table12_backbone.csv              Table 12
  table13_temperature.csv           Table 13
  table14_anonymization.csv         Table 14
  table15_tdet.csv                  Table 15
  table16_longwindow.csv            Table 16

Missing inputs are skipped with a note.

    python -m method.experiments.tables
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from method.experiments._shared import GROUPS, RESULTS_ROOT, out_dir

BASELINES = ["BARO", "RCD", "EpsilonDiagnosis", "PageRank (PC)", "PageRank (FCI)",
             "RandomWalk (PC)", "RandomWalk (FCI)", "CIRCA (PC)", "CIRCA (FCI)"]
GPT = "openai/gpt-oss-120b"
M4 = ["top@1", "top@3", "top@5", "avg@5"]


def _read(path: Path):
    if not path.exists():
        print(f"  skip: {path} not found")
        return None
    return pd.read_csv(path)


def _llm(summary, group, config, dk="none", anon=False, model=GPT, t=1.0):
    s = summary[(summary.group == group) & (summary.config == config)
                & (summary.dk == dk) & (summary.anon == anon)
                & (summary.model == model) & (summary.temperature == t)]
    return s.iloc[0] if len(s) else None


def _fmt(row, m="top@1"):
    return None if row is None else f"{row[f'{m}_mean']:.3f}±{row[f'{m}_std']:.3f}"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--results-root", default=str(RESULTS_ROOT))
    a = p.parse_args(argv)
    R = Path(a.results_root)
    out = out_dir("tables", R / "tables")
    written = []

    def save(df, name):
        df.to_csv(out / name, index=False)
        written.append(out / name)

    rec = _read(R / "hvac_pools" / "hvac_recall.csv")
    if rec is not None:
        save(rec, "table01_hvac_retrieval.csv")

    llm = _read(R / "controlled_llm" / "llm_summary.csv")
    e2e = _read(R / "controlled_llm" / "llm_end_to_end_summary.csv")
    hb = _read(R / "hvac_baselines" / "hvac_baselines.csv")
    if hb is not None:
        t = hb[["method"] + M4].copy()
        if e2e is not None:
            for dk, label in (("none", "LLM (no DK)"), ("light", "LLM (with DK)")):
                r = _llm(e2e, "HVAC", "retriever", dk)
                if r is not None:
                    t.loc[len(t)] = [label] + [_fmt(r, m) for m in M4]
        save(t, "table03_05_hvac.csv")

    pb = _read(R / "controlled_baselines" / "pool_baselines.csv")
    if pb is not None:
        for config, name in (("retriever", "table10_pool_retriever.csv"),
                             ("all", "table11_pool_all.csv")):
            grid = (pb[pb.config == config].pivot_table(
                index="ranker", columns="group", values="top@1", aggfunc="first")
                .reindex(index=BASELINES, columns=list(GROUPS)))
            if llm is not None:
                grid.loc["LLM (no DK, n=3)"] = [
                    None if _llm(llm, g, config) is None
                    else round(_llm(llm, g, config)["top@1_mean"], 4) for g in GROUPS]
            save(grid.reset_index().rename(columns={"index": "method"}), name)
        if llm is not None:
            rows = []
            for g in GROUPS:
                row = {"group": g}
                for config in ("retriever", "all"):
                    sub = pb[(pb.group == g) & (pb.config == config)]
                    bb = sub["top@1"].max()
                    row[f"BB_{config}"] = bb
                    r_none = _llm(llm, g, config)
                    row[f"LLM_noDK_{config}"] = _fmt(r_none)
                    best = r_none["top@1_mean"] if r_none is not None else None
                    if config == "retriever":
                        r_dk = _llm(llm, g, config, "light")
                        row["LLM_DK_retriever"] = _fmt(r_dk)
                        if r_dk is not None:
                            best = max(best, r_dk["top@1_mean"])
                    row[f"delta_pp_{config}"] = None if best is None \
                        else round((best - bb) * 100, 1)
                rows.append(row)
            save(pd.DataFrame(rows), "table04_retrieval_controlled.csv")

    sc = _read(R / "same_candidate" / "same_candidate.csv")
    lr = _read(R / "same_candidate" / "llm_rows.csv")
    if sc is not None:
        t = sc[["group", "ranker"] + M4].copy()
        if lr is not None:
            agg = lr[lr["run"] == "mean±std"]
            for _, r in agg.iterrows():
                t.loc[len(t)] = [r["group"], f"LLM ({'no DK' if r['level'] == 'none' else 'with DK'}, n=3)"] + [r[m] for m in M4]
        if llm is not None:
            for dk in ("none", "light"):
                r = _llm(llm, "HVAC", "retriever", dk)
                if r is not None:
                    t.loc[len(t)] = ["HVAC", f"LLM ({'no DK' if dk == 'none' else 'with DK'}, n=3)"] + [_fmt(r, m) for m in M4]
        save(t, "table07_09_same_candidate.csv")

    if llm is not None:
        rows = []
        for g in GROUPS:
            gpt = _llm(llm, g, "retriever")
            lla = _llm(llm, g, "retriever", model="llama-3.3-70b-versatile")
            if lla is not None:
                rows.append({"group": g, "gpt-oss-120b": _fmt(gpt),
                             "llama-3.3-70b": _fmt(lla)})
        save(pd.DataFrame(rows), "table12_backbone.csv")
        rows = []
        for t_ in (0.0, 1.0, 2.0):
            r = _llm(llm, "WADI", "retriever", t=t_)
            if r is not None:
                rows.append({"temperature": t_, **{m: _fmt(r, m) for m in M4[:3]}})
        save(pd.DataFrame(rows), "table13_temperature.csv")
        rows = []
        for g in GROUPS:
            vals = [_llm(llm, g, "retriever", dk, an) for dk, an in
                    (("none", False), ("none", True), ("light", False), ("light", True))]
            rows.append({"group": g, **{k: None if v is None else round(v["top@1_mean"], 4)
                         for k, v in zip(("real_noDK", "anon_noDK", "real_DK", "anon_DK"),
                                         vals)}})
        save(pd.DataFrame(rows), "table14_anonymization.csv")

    td = _read(R / "tdet_sensitivity" / "tdet_table.csv")
    if td is not None:
        grid = td.pivot_table(index="dataset", columns="delta_min",
                              values="change_pp", aggfunc="first")
        rca = [s for s in ("RE1-OB", "RE1-SS", "RE1-TT") if s in grid.index]
        if rca:
            grid.loc["RCAEval max |change|"] = grid.loc[rca].abs().max().max()
        save(grid.reset_index(), "table15_tdet.csv")

    lw = _read(R / "longwindow_graphs" / "longwindow.csv")
    if lw is not None:
        grid = lw.pivot_table(index="method", columns="dataset", values="top@1",
                              aggfunc="first")
        save(grid.reset_index(), "table16_longwindow.csv")

    for w in written:
        print(f"  {w}")


if __name__ == "__main__":
    main()
