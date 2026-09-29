#!/usr/bin/env python3
"""LLM reranker on the retrieval-controlled pools.

One listwise call per scenario and run: the stored pool is rendered in its
frozen order with the paper's evidence-line format, the response's JSON
``ranked`` list is restricted to the pool and back-filled in pool order, and
a response that stays unparsable after two retries scores as an empty
ranking (counted in ``parse_failures``).

Two modes:
  --cache-dir DIR   offline: score responses already stored in DIR; a missing
                    response is counted in ``n_missing`` and scored as empty.
                    No API client is created.
  --run-llm         call the Groq API for responses missing from the cache
                    and store them (needs GROQ_API_KEY; Langfuse tracing only
                    if LANGFUSE_* keys are set).

Cache layout: DIR/<group>_<config>[_light][_<model>][_tNNN][_anon]/run<i>/
rank_<md5(scenario_id + summary)>.json.

Outputs (method/results/controlled_llm/):
  llm_runs.csv             one row per (group, config, dk, anon, model, T, run)
  llm_summary.csv          mean / std over runs
  llm_end_to_end.csv       retriever-pool runs with the scenarios whose cause
                           the retriever missed scored as misses

    python -m method.experiments.controlled_llm --cache-dir DIR --paper-grid
    python -m method.experiments.controlled_llm --run-llm --groups WADI \
        --configs retriever --dk light
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from method.algorithms.rca.candidate_selection import score_metrics
from method.algorithms.rca.llm_ranking import (
    build_hybrid_clean_user_prompt, build_system_prompt,
)
from method.datasets.base import FaultScenario
from method.experiments import anonymize
from method.experiments._shared import (
    CACHE_ROOT, GROUPS, GROUP_DS, PROMPTS_ROOT, REPO, RESULTS_ROOT,
    load_group, load_pools, out_dir, score_block,
)
from method.runners._datasets import (
    get as get_dataset, rcaeval_context_for_suite, rcaeval_domain_for_suite,
)

DEFAULT_MODEL = "openai/gpt-oss-120b"
METRICS = ("top@1", "top@3", "top@5", "avg@5")
KEY_COLS = ["group", "config", "dk", "anon", "model", "temperature"]

# Exactly the configurations the paper reports: Tables 4 and 9-14, plus the
# HVAC LLM rows of the end-to-end tables (retriever pool, scored end to end).
_ALL = list(GROUPS)
_NO_HVAC = [g for g in GROUPS if g != "HVAC"]
PAPER_GRID = [
    dict(groups=_ALL, configs=["retriever", "all", "random"], dk="none", anon=False),
    dict(groups=_ALL, configs=["retriever"], dk="light", anon=False),
    dict(groups=_ALL, configs=["retriever"], dk="none", anon=True),
    dict(groups=_ALL, configs=["retriever"], dk="light", anon=True),
    dict(groups=_NO_HVAC, configs=["retriever"], dk="none", anon=False,
         model="llama-3.3-70b-versatile"),
    dict(groups=["WADI"], configs=["retriever"], dk="none", anon=False,
         temperature=0.0),
    dict(groups=["WADI"], configs=["retriever"], dk="none", anon=False,
         temperature=2.0),
]


# ---------------------------------------------------------------------------
# Prompt rendering and parsing
# ---------------------------------------------------------------------------

def render_summary(scenario, pool, time_unit):
    """Evidence lines in the frozen pool order."""
    data = scenario.data.ffill().fillna(0)
    diag = int(scenario.diagnosis_time)
    normal, anomal = data.iloc[:diag], data.iloc[diag:]
    b_mean, b_std = normal.mean(), normal.std()
    mag = dict(score_metrics(scenario))
    lines = []
    for rank, metric in enumerate(pool, 1):
        z = mag.get(metric, 0.0)
        mean_before = b_mean.get(metric, 0)
        std_before = b_std.get(metric, 0)
        mean_after = anomal[metric].mean() if metric in anomal else 0
        if std_before > 0:
            zvals = ((anomal[metric] - mean_before) / std_before).abs()
            exceeds = zvals[zvals >= 1.5]
            offset = int(exceeds.index[0]) - diag if not exceeds.empty else "?"
        else:
            changed = anomal[metric][(anomal[metric] - mean_before).abs() > 1e-4]
            offset = int(changed.index[0]) - diag if not changed.empty else "?"
        delta = mean_after - mean_before
        pct = (delta / mean_before * 100) if mean_before != 0 else 0
        lines.append(
            f"  {rank}. {metric}  |  z-score={z:.1f}  |  +{offset}{time_unit}  |  "
            f"before={mean_before:.3f} → after={mean_after:.3f} "
            f"(Δ={delta:+.3f}, {pct:+.1f}%)")
    return "\n".join(lines)


def strict_parse(content, pool):
    """Return (ranked, ok); ok is False iff no ``ranked`` list can be read."""
    s = content.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0]
    try:
        obj = json.loads(s)
        ranked = obj.get("ranked")
        if not isinstance(ranked, list):
            return [], False
    except Exception:
        m = re.search(r'"ranked"\s*:\s*\[([^\]]*)\]', content, re.DOTALL)
        if not m:
            return [], False
        ranked = re.findall(r'"([^"]+)"', m.group(1))
        if not ranked:
            return [], False
    pool_set = set(pool)
    out = [m for m in ranked if m in pool_set]
    out += [m for m in pool if m not in set(out)]
    return out, True


# ---------------------------------------------------------------------------
# API access (only with --run-llm)
# ---------------------------------------------------------------------------

class _Online:
    """Groq client + optional Langfuse tracing, created only on --run-llm."""

    def __init__(self, model):
        from dotenv import load_dotenv
        from openai import OpenAI
        from method.runners._common import llm_call_with_retry
        load_dotenv(REPO / ".env")
        self.model = model
        self.call = llm_call_with_retry
        self.client = OpenAI(api_key=os.environ.get("GROQ_API_KEY", ""),
                             base_url="https://api.groq.com/openai/v1")
        self.langfuse = None
        if os.environ.get("LANGFUSE_PUBLIC_KEY"):
            try:
                from langfuse import get_client
                self.langfuse = get_client()
            except Exception:
                self.langfuse = None

    def complete(self, messages, temperature):
        kw = dict(temperature=temperature, max_tokens=4096)
        for outer in range(6):
            try:
                return self.call(self.client, self.model, messages, kw)
            except Exception as e:
                msg = str(e)
                if outer < 5 and ("429" in msg or "rate_limit" in msg.lower()):
                    time.sleep(20 * (outer + 1))
                    continue
                raise

    def trace(self, *, name, session_id, metadata, messages, content, ranked,
              gt, usage):
        if self.langfuse is None:
            return
        lf = self.langfuse
        try:
            with lf.start_as_current_span(name=name, input=metadata):
                lf.update_current_trace(name=name, session_id=session_id,
                                        metadata=metadata)
                with lf.start_as_current_generation(
                        name="llm_one_shot_call", model=self.model,
                        input=messages) as gen:
                    gen.update(output=content, usage_details=usage)
                pos = next((i + 1 for i, m in enumerate(ranked) if m in gt), -1)
                lf.update_current_trace(output={"ranked_top10": ranked[:10],
                                                "gt_position": pos})
                for k in (1, 3, 5):
                    lf.score_current_trace(
                        name=f"hit@{k}", value=int(any(g in ranked[:k] for g in gt)))
                lf.score_current_trace(name="reciprocal_rank",
                                       value=(1.0 / pos) if pos > 0 else 0.0)
        except Exception as e:
            print(f"    [Langfuse] trace failed: {e}")


def one_call(online, cache_dir, sc, pool, tag, run_idx, time_unit,
             temperature, system_prompt, session_id):
    """Return (scenario_id, ranked, parse_ok, source)."""
    summary = render_summary(sc, pool, time_unit)
    user_prompt = build_hybrid_clean_user_prompt(summary)
    key = hashlib.md5((sc.scenario_id + summary).encode()).hexdigest()
    cfile = Path(cache_dir) / tag / f"run{run_idx}" / f"rank_{key}.json"
    if cfile.exists():
        cached = json.loads(cfile.read_text())
        return sc.scenario_id, cached["ranked"], cached.get("parse_ok", True), "cache"
    if online is None:
        return sc.scenario_id, [], False, "missing"

    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}]
    ranked, ok, content, usage = [], False, "", None
    for _ in range(3):                         # 1 try + 2 parse retries
        resp = online.complete(messages, temperature)
        content = resp.choices[0].message.content or ""
        if resp.usage:
            usage = {"input": resp.usage.prompt_tokens,
                     "output": resp.usage.completion_tokens,
                     "total": resp.usage.total_tokens}
        ranked, ok = strict_parse(content, pool)
        if ok:
            break
    online.trace(name=f"pools::{tag}::{sc.scenario_id}", session_id=session_id,
                 metadata={"scenario_id": sc.scenario_id, "tag": tag,
                           "run_idx": run_idx, "parse_ok": ok},
                 messages=messages, content=content, ranked=ranked,
                 gt=sc.ground_truth_causes, usage=usage)
    cfile.parent.mkdir(parents=True, exist_ok=True)
    cfile.write_text(json.dumps({
        "ranked": ranked, "parse_ok": ok, "scenario_id": sc.scenario_id,
        "model": online.model, "config": tag, "run_idx": run_idx,
        "temperature": temperature, "session_id": session_id,
        "system_prompt": system_prompt, "usage": usage,
        "user_prompt": user_prompt, "anomaly_summary": summary,
        "raw_response": content}, indent=2))
    return sc.scenario_id, ranked, ok, "fresh"


# ---------------------------------------------------------------------------
# One (groups, configs, dk, anon, model, temperature) specification
# ---------------------------------------------------------------------------

def system_prompt_for(group, dk, anon):
    if dk == "none":
        return build_system_prompt("none", "", "")
    ds, suite = GROUP_DS[group]
    cfg = get_dataset(ds)
    if anon:
        doc = (PROMPTS_ROOT / anonymize.ANON_DOC[group]).read_text()
        phrase = anonymize.ANON_PHRASE[group] or cfg.domain_phrase
    elif suite:
        doc = rcaeval_context_for_suite(suite, "light").read_text()
        phrase = rcaeval_domain_for_suite(suite)
    else:
        doc = cfg.context_path.read_text()
        phrase = cfg.domain_phrase
    return build_system_prompt("light", phrase, doc)


def cache_tag(group, config, dk, anon, model, temperature):
    tag = f"{group}_{config}"
    tag += "" if dk == "none" else f"_{dk}"
    tag += "" if model == DEFAULT_MODEL else "_" + model.split("/")[-1]
    if temperature != 1.0:
        tag += f"_t{int(round(temperature * 100)):03d}"
    if anon:
        tag += "_anon"
    return tag


def run_spec(spec, pools_doc, cache_dir, online_for, n_runs, workers, scen_cache):
    rows, e2e_rows = [], []
    dk, anon = spec["dk"], spec["anon"]
    model = spec.get("model", DEFAULT_MODEL)
    temperature = spec.get("temperature", 1.0)
    online = online_for(model) if online_for else None
    for group in spec["groups"]:
        if group not in scen_cache:
            scen_cache[group] = load_group(group)
        cfg, scenarios, service_level = scen_cache[group]
        scenarios = [s for s in scenarios if s.scenario_id in pools_doc[group]]
        sys_prompt = system_prompt_for(group, dk, anon)
        if anon:
            r2a, a2r = anonymize.name_functions(group)
            targets = {sc.scenario_id: FaultScenario(
                scenario_id=sc.scenario_id, data=sc.data.rename(columns=r2a),
                diagnosis_time=sc.diagnosis_time,
                ground_truth_causes=[r2a(t) for t in sc.ground_truth_causes],
                alarm_nodes=[r2a(x) for x in sc.alarm_nodes],
                sample_rate_hz=sc.sample_rate_hz) for sc in scenarios}
        else:
            r2a = a2r = (lambda n: n)
            targets = {sc.scenario_id: sc for sc in scenarios}
        for config in spec["configs"]:
            tag = cache_tag(group, config, dk, anon, model, temperature)
            session_id = f"{tag}_nruns{n_runs}_{time.strftime('%Y%m%d_%H%M%S')}"
            for run_idx in range(n_runs):
                t0 = time.time()
                results, fails, missing = {}, 0, 0
                with concurrent.futures.ThreadPoolExecutor(workers) as ex:
                    futs = {}
                    for sc in scenarios:
                        pool = pools_doc[group][sc.scenario_id][config]["pool"]
                        pool = [r2a(m) for m in pool]
                        futs[ex.submit(one_call, online, cache_dir,
                                       targets[sc.scenario_id], pool, tag,
                                       run_idx, cfg.time_unit, temperature,
                                       sys_prompt, session_id)] = sc
                    for f in concurrent.futures.as_completed(futs):
                        sc = futs[f]
                        try:
                            sid, ranked, ok, src = f.result()
                        except Exception as e:
                            print(f"  [{sc.scenario_id}] call failed: {str(e)[:120]}")
                            sid, ranked, ok, src = sc.scenario_id, [], False, "error"
                        results[sid] = [a2r(m) for m in ranked]
                        missing += int(src == "missing")
                        fails += int(not ok and src != "missing")
                preds = [results[s.scenario_id] for s in scenarios]
                base = {"group": group, "config": config, "run": run_idx,
                        "n": len(scenarios), "parse_failures": fails,
                        "n_missing": missing,
                        "secs": round(time.time() - t0, 1) if online else np.nan,
                        "dk": dk, "anon": bool(anon), "model": model,
                        "temperature": temperature}
                row = dict(base, **score_block(scenarios, preds, service_level))
                rows.append(row)
                print({k: row[k] for k in ("group", "config", "dk", "anon", "model",
                                           "temperature", "run", "n_missing",
                                           "parse_failures", "top@1")})
                if config == "retriever":
                    inj = [pools_doc[group][s.scenario_id]["retriever"]["injected"]
                           for s in scenarios]
                    e2e = [[] if i else p for i, p in zip(inj, preds)]
                    e2e_rows.append(dict(base, n_injected=sum(inj),
                                         **score_block(scenarios, e2e, service_level)))
    return rows, e2e_rows


def upsert(path: Path, new: pd.DataFrame) -> pd.DataFrame:
    """Replace rows with the same (keys, run) and append the rest."""
    if path.exists():
        old = pd.read_csv(path)
        keys = set(map(tuple, new[KEY_COLS + ["run"]].astype(str).values))
        mask = old[KEY_COLS + ["run"]].astype(str).apply(tuple, axis=1).isin(keys)
        new = pd.concat([old[~mask], new], ignore_index=True, sort=False)
    new.to_csv(path, index=False)
    return new


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for key, sub in df.groupby(KEY_COLS, sort=False):
        row = dict(zip(KEY_COLS, key), n_runs=len(sub))
        for m in METRICS:
            row[f"{m}_mean"] = round(sub[m].mean(), 4)
            row[f"{m}_std"] = round(sub[m].std(ddof=1), 4) if len(sub) > 1 else 0.0
        out.append(row)
    return pd.DataFrame(out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--run-llm", action="store_true",
                   help="allow API calls for responses missing from the cache")
    p.add_argument("--cache-dir", default=None,
                   help=f"response cache (default with --run-llm: "
                        f"{CACHE_ROOT / 'llm_pools'})")
    p.add_argument("--pools", default=str(RESULTS_ROOT / "controlled_pools" / "pools.json"))
    p.add_argument("--paper-grid", action="store_true",
                   help="every configuration reported in the paper")
    p.add_argument("--groups", nargs="+", default=list(GROUPS), choices=GROUPS)
    p.add_argument("--configs", nargs="+", default=["retriever", "random"])
    p.add_argument("--dk", choices=["none", "light"], default="none")
    p.add_argument("--anon", action="store_true",
                   help="de-identified names (prompts rendered and parsed in "
                        "anonymized space, scored in real space)")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--n-runs", type=int, default=3)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)

    if not a.run_llm and not a.cache_dir:
        sys.exit("Nothing to do: pass --cache-dir DIR to score stored responses "
                 "offline, or --run-llm to allow API calls.")
    cache_dir = Path(a.cache_dir) if a.cache_dir else CACHE_ROOT / "llm_pools"
    clients = {}

    def online_for(model):
        if model not in clients:
            clients[model] = _Online(model)
        return clients[model]
    out = out_dir("controlled_llm", a.out_dir)
    pools_doc = load_pools(a.pools)

    specs = PAPER_GRID if a.paper_grid else [dict(
        groups=a.groups, configs=a.configs, dk=a.dk, anon=a.anon,
        model=a.model, temperature=a.temperature)]
    rows, e2e, scen_cache = [], [], {}
    for spec in specs:
        r, e = run_spec(spec, pools_doc, cache_dir,
                        online_for if a.run_llm else None, a.n_runs,
                        a.workers, scen_cache)
        rows += r
        e2e += e
    for c in clients.values():
        if c.langfuse is not None:
            c.langfuse.flush()

    runs = upsert(out / "llm_runs.csv", pd.DataFrame(rows))
    summarize(runs).to_csv(out / "llm_summary.csv", index=False)
    e2e_all = upsert(out / "llm_end_to_end.csv", pd.DataFrame(e2e)) if e2e else None
    if e2e_all is not None:
        summarize(e2e_all).to_csv(out / "llm_end_to_end_summary.csv", index=False)
    n_missing = int(pd.DataFrame(rows)["n_missing"].sum())
    print(f"wrote {out / 'llm_runs.csv'} and summaries; "
          f"{n_missing} responses missing from {cache_dir}")


if __name__ == "__main__":
    from method.runners._common import ensure_hash_seed
    ensure_hash_seed()
    main()
