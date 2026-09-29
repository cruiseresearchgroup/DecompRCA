#!/usr/bin/env python3
"""Deterministic de-identification maps for the anonymization control.

Sensor / service names are replaced by seeded, structure-preserving names;
data values are untouched.

  WADI    1_FIT_001_PV -> S1_FLOW_01_VALUE  (stage kept, type generalised,
          index permuted within each (stage, type) group, suffix generalised)
  SWaT    FIT101 -> S1_FLOW_01             (same recipe, suffix-less tags)
  HVAC    RTU_SA_TEMP -> AHU_SUPPLYAIR_TEMP, room numbers -> seeded F<f>R<nn>
  RCAEval service token -> svcNN (``-db`` variants pair with their service)

Maps are built from the column sets of the retrieval-controlled pools with
fixed seeds. The maps used for the paper runs ship in
``method/prompts/anon_maps/``; the anonymized domain documents are
``method/prompts/<group>_Context_Anon.md``.

    python -m method.experiments.anonymize --check       # rebuild + compare
    python -m method.experiments.anonymize --audit       # leakage audit of docs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path

from method.experiments._shared import (
    PROMPTS_ROOT, RESULTS_ROOT, load_pools, out_dir,
)

MAP_DIR = PROMPTS_ROOT / "anon_maps"
DEFAULT_POOLS = RESULTS_ROOT / "controlled_pools" / "pools.json"
CONFIG_ORDER = ("all", "retriever", "random")

ANON_DOC = {"WADI": "WADI_Context_Anon.md", "SWaT": "SWaT_Context_Anon.md",
            "HVAC": "HVAC_Context_Anon.md",
            "RE1-OB": "RE1-OB_Context_Anon.md",
            "RE1-SS": "RE1-SS_Context_Anon.md",
            "RE1-TT": "RE1-TT_Context_Anon.md"}
ANON_PHRASE = {"WADI": None, "SWaT": None,          # dataset's own phrase
               "HVAC": "building HVAC systems",
               "RE1-OB": "an e-commerce microservice platform",
               "RE1-SS": "an e-commerce microservice platform",
               "RE1-TT": "a travel-booking microservice platform"}
MAP_FILE = {"WADI": "wadi_anon_map.json", "SWaT": "swat_anon_map.json",
            "HVAC": "hvac_anon_map.json",
            "RE1-OB": "RE1-OB_anon_map.json", "RE1-SS": "RE1-SS_anon_map.json",
            "RE1-TT": "RE1-TT_anon_map.json"}


def _pool_columns(group_pools: dict) -> set[str]:
    cols = set()
    for p in group_pools.values():
        for c in CONFIG_ORDER:
            cols.update(p[c]["pool"])
    return cols


# ---------------------------------------------------------------------------
# WADI
# ---------------------------------------------------------------------------

TYPE_MAP = {"FIT": "FLOW", "LT": "LEVEL", "LS": "LEVELSW", "MV": "VALVE",
            "MCV": "OUTVALVE", "P": "PUMP", "AIT": "QUALITY",
            "PIC": "PRESSURE", "PIT": "PRESSURE", "DPIT": "DIFFPRESS"}
SUFFIX_MAP = {"PV": "VALUE", "STATUS": "STATE", "CO": "CMD",
              "SP": "SETPOINT", "SPEED": "SPEED",
              "AL": "ALARMLOW", "AH": "ALARMHIGH"}
TAG_RE = re.compile(r"^(\d)_([A-Z]+)_(\d{3})_([A-Z]+)$")
LEAK_RE = re.compile(r"WADI|WaDi|iTrust|SUTD|\b[123]A?_[A-Z]{1,4}_\d{3}")


def build_map_wadi(group_pools: dict) -> dict:
    cols = _pool_columns(group_pools)
    rng = random.Random(int(hashlib.md5(b"wadi-anon").hexdigest(), 16) % 2**32)
    groups: dict[tuple, list] = {}
    parsed = {}
    for name in sorted(cols):
        m = TAG_RE.match(name)
        if not m:
            raise ValueError(f"unparseable sensor tag: {name}")
        stage, typ, idx, suf = m.groups()
        parsed[name] = (stage, typ, idx, suf)
        groups.setdefault((stage, typ), [])
        if idx not in groups[(stage, typ)]:
            groups[(stage, typ)].append(idx)
    idx_map = {}
    for key, idxs in sorted(groups.items()):
        idxs_sorted = sorted(idxs)
        shuffled = idxs_sorted[:]
        rng.shuffle(shuffled)
        for old, newpos in zip(idxs_sorted, shuffled):
            idx_map[(key, old)] = f"{idxs_sorted.index(newpos) + 1:02d}"
    to_anon = {}
    for name, (stage, typ, idx, suf) in parsed.items():
        to_anon[name] = (f"S{stage}_{TYPE_MAP[typ]}_"
                         f"{idx_map[((stage, typ), idx)]}_{SUFFIX_MAP[suf]}")
    assert len(set(to_anon.values())) == len(to_anon), "anon collision"
    return to_anon


DOC_TAG_RE = re.compile(r"\b(\d)(A|B)?_([A-Z]{1,4})_(\d{3})(?:_([A-Z]+))?\b")


def anonymize_document_wadi(text: str, to_anon: dict) -> str:
    """Pattern-based anonymization of prose (device names, train variants,
    instruments outside the column set), consistent with the channel map."""
    idx_map: dict[tuple, str] = {}
    for real, anon in to_anon.items():
        m = TAG_RE.match(real)
        am = re.match(r"S(\d)_([A-Z]+)_(\d{2})_", anon)
        idx_map[(m.group(1), m.group(2), m.group(3))] = am.group(3)
    group_next: dict[tuple, int] = {}
    for (stage, typ, _), new in idx_map.items():
        group_next[(stage, typ)] = max(group_next.get((stage, typ), 0), int(new))

    def repl(m):
        stage, train, typ, idx, suf = m.groups()
        if typ not in TYPE_MAP:
            return m.group(0)
        key = (stage, typ, idx)
        if key not in idx_map:
            group_next[(stage, typ)] = group_next.get((stage, typ), 0) + 1
            idx_map[key] = f"{group_next[(stage, typ)]:02d}"
        out = f"S{stage}{train or ''}_{TYPE_MAP[typ]}_{idx_map[key]}"
        if suf:
            out += f"_{SUFFIX_MAP.get(suf, suf)}"
        return out

    return DOC_TAG_RE.sub(repl, text)


# ---------------------------------------------------------------------------
# SWaT (suffix-less tags: MV101 = type MV, stage 1, index 01)
# ---------------------------------------------------------------------------

SWAT_TYPE_MAP = {"FIT": "FLOW", "LIT": "LEVEL", "MV": "VALVE", "P": "PUMP",
                 "AIT": "QUALITY", "PIT": "PRESSURE", "DPIT": "DIFFPRESS",
                 "UV": "UVLAMP"}
SWAT_TAG_RE = re.compile(r"^([A-Z]+)(\d)(\d{2})$")
SWAT_LEAK_RE = re.compile(
    r"SWaT|Secure Water Treatment|iTrust|SUTD|"
    r"\b(?:MV|FIT|LIT|AIT|DPIT|PIT|UV|P)-?\d{3}\b")


def build_map_swat(group_pools: dict) -> dict:
    cols = _pool_columns(group_pools)
    rng = random.Random(int(hashlib.md5(b"swat-anon").hexdigest(), 16) % 2**32)
    groups, parsed = {}, {}
    for name in sorted(cols):
        m = SWAT_TAG_RE.match(name)
        if not m:
            raise ValueError(f"unparseable SWaT tag: {name}")
        typ, stage, idx = m.groups()
        parsed[name] = (typ, stage, idx)
        groups.setdefault((stage, typ), [])
        if idx not in groups[(stage, typ)]:
            groups[(stage, typ)].append(idx)
    idx_map = {}
    for key, idxs in sorted(groups.items()):
        s = sorted(idxs)
        sh = s[:]
        rng.shuffle(sh)
        for old, newpos in zip(s, sh):
            idx_map[(key, old)] = f"{s.index(newpos) + 1:02d}"
    to_anon = {n: f"S{st}_{SWAT_TYPE_MAP[t]}_{idx_map[((st, t), i)]}"
               for n, (t, st, i) in parsed.items()}
    assert len(set(to_anon.values())) == len(to_anon)
    return to_anon


SWAT_DOC_TAG_RE = re.compile(r"\b(MV|FIT|LIT|AIT|DPIT|PIT|UV|P)-?(\d)(\d{2})\b")


def anonymize_document_swat(text: str, to_anon: dict) -> str:
    idx_map, group_next = {}, {}
    for real, anon in to_anon.items():
        t, st, i = SWAT_TAG_RE.match(real).groups()
        new = re.match(r"S\d_[A-Z]+_(\d{2})", anon).group(1)
        idx_map[(st, t, i)] = new
        group_next[(st, t)] = max(group_next.get((st, t), 0), int(new))

    def repl(m):
        typ, stage, idx = m.groups()
        key = (stage, typ, idx)
        if key not in idx_map:
            group_next[(stage, typ)] = group_next.get((stage, typ), 0) + 1
            idx_map[key] = f"{group_next[(stage, typ)]:02d}"
        return f"S{stage}_{SWAT_TYPE_MAP[typ]}_{idx_map[key]}"

    return SWAT_DOC_TAG_RE.sub(repl, text)


# ---------------------------------------------------------------------------
# RCAEval (metric = {service}_{metrictype}; the service token is replaced)
# ---------------------------------------------------------------------------

RCA_APP_IDENTITY = {
    "RE1-OB": [r"Online Boutique", r"OnlineBoutique", r"Hipster Shop"],
    "RE1-SS": [r"Sock Shop", r"SockShop", r"sock retailer", r"socks?\b"],
    "RE1-TT": [r"Train Ticket", r"TrainTicket", r"railway"],
}


def _svc_of_metric(metric: str) -> str:
    return metric.split("_")[0]


def build_map_rcaeval(group_pools: dict, suite: str) -> dict:
    svcs = {_svc_of_metric(m) for m in _pool_columns(group_pools)}
    bases = sorted({s[:-3] if s.endswith("-db") else s for s in svcs})
    rng = random.Random(int(hashlib.md5(f"rcaeval-anon-{suite}".encode())
                            .hexdigest(), 16) % 2**32)
    order = bases[:]
    rng.shuffle(order)
    svc_map = {b: f"svc{order.index(b) + 1:02d}" for b in bases}
    for s in sorted(svcs):
        if s.endswith("-db"):
            svc_map[s] = svc_map[s[:-3]] + "-db"
    return svc_map


def metric_to_anon(metric: str, svc_map: dict) -> str:
    svc = _svc_of_metric(metric)
    if svc in svc_map:
        return svc_map[svc] + metric[len(svc):]
    return metric


def anonymize_document_rcaeval(text: str, suite: str, svc_map: dict) -> str:
    for real in sorted(svc_map, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(real)}\b", svc_map[real], text)
    for pat in RCA_APP_IDENTITY[suite]:
        text = re.sub(pat, "the platform", text, flags=re.IGNORECASE)
    return text


def leakage_audit_rcaeval(text: str, suite: str, svc_map: dict) -> list:
    hits = []
    for pat in RCA_APP_IDENTITY[suite]:
        hits += re.findall(pat, text, flags=re.IGNORECASE)
    for real in svc_map:
        hits += re.findall(rf"\b{re.escape(real)}\b", text)
    return hits


# ---------------------------------------------------------------------------
# HVAC (RTU naming -> generic AHU / zone naming)
# ---------------------------------------------------------------------------

HVAC_LEAK_RE = re.compile(
    r"\bRTU_|\bVAV_|\bTERM_|\bHVAC_|ERTU|ORNL|LBNL|rooftop|"
    r"\b(?:10[2-6]|20[2-6])\b")
_HVAC_QTY = {
    "RM_TEMP_CSPT": "COOLING_SETPOINT", "RM_TEMP_HSPT": "HEATING_SETPOINT",
    "OA_DMPR_DM": "OUTDOORAIR_DAMPER_POS", "RA_DMPR_DM": "RETURNAIR_DAMPER_POS",
    "SA_FAN_WATT": "SUPPLYFAN_POWER", "COMP_WATT": "COMPRESSOR_POWER",
    "TOT_WATT": "TOTAL_POWER", "GAS_CSUM": "GAS_CUMULATIVE",
    "MA_TEMP": "MIXEDAIR_TEMP", "OA_TEMP": "OUTDOORAIR_TEMP",
    "RA_TEMP": "RETURNAIR_TEMP", "SA_TEMP": "SUPPLYAIR_TEMP",
    "SA_FLOW": "SUPPLYAIR_FLOW", "RM_HUMD": "ROOMHUMIDITY",
    "RM_TEMP": "ROOMTEMP", "RM_SAT": "ROOMSUPPLYTEMP", "RM_WATT": "ROOMPOWER",
    "RA_FLOW": "RETURNAIR_FLOW", "OA_FLOW": "OUTDOORAIR_FLOW",
    "SA_HUM": "SUPPLYAIR_HUMIDITY", "RA_HUM": "RETURNAIR_HUMIDITY",
    "OA_HUM": "OUTDOORAIR_HUMIDITY", "MA_HUM": "MIXEDAIR_HUMIDITY",
    "STG_STA": "COMPRESSOR_STAGE_STATE",
}
_HVAC_SYS = {"HVAC": "PLANT", "RTU": "AHU", "TERM": "ZONE", "VAV": "ZONEBOX"}


def _hvac_room_map():
    rng = random.Random(int(hashlib.md5(b"hvac-anon").hexdigest(), 16) % 2**32)
    m = {}
    for floor, rooms in (("1", ["102", "103", "104", "105", "106"]),
                         ("2", ["202", "203", "204", "205", "206"])):
        target = [f"F{floor}R{i+1:02d}" for i in range(len(rooms))]
        rng.shuffle(target)
        m.update(dict(zip(rooms, target)))
    return m


def hvac_name_to_anon(name: str, room_map: dict) -> str:
    parts = name.split("_", 1)
    sys_tok, rest = parts[0], parts[1] if len(parts) > 1 else ""
    out_sys = _HVAC_SYS.get(sys_tok, sys_tok)
    qty, suffix = rest, ""
    m = re.match(r"^(.*?)_?(\d{3}|\d)$", rest)
    if m and m.group(2):
        qty, suffix = m.group(1), m.group(2)
    out_qty = _HVAC_QTY.get(qty, qty)
    if suffix in room_map:
        return f"{out_sys}_{out_qty}_{room_map[suffix]}"
    if suffix:
        return f"{out_sys}_{out_qty}_{suffix}"
    return f"{out_sys}_{out_qty}"


def build_map_hvac(group_pools: dict) -> dict:
    room_map = _hvac_room_map()
    to_anon = {n: hvac_name_to_anon(n, room_map)
               for n in sorted(_pool_columns(group_pools))}
    assert len(set(to_anon.values())) == len(to_anon), "hvac anon collision"
    return to_anon


def anonymize_document_hvac(text: str, to_anon: dict) -> str:
    for real in sorted(to_anon, key=len, reverse=True):
        text = text.replace(real, to_anon[real])
    room_map = _hvac_room_map()
    for r, a in room_map.items():
        text = re.sub(rf"\b{r}\b", a, text)

    def _tok(m):
        return hvac_name_to_anon(m.group(0), room_map)
    text = re.sub(r"\b(?:RTU|VAV|TERM|HVAC)_[A-Z][A-Z_0-9]*\b", _tok, text)
    text = re.sub(r"rooftop[- ]unit", "air-handling unit", text, flags=re.I)
    text = re.sub(r"\bRTUs?\b", "AHU", text)
    text = re.sub(r"\bERTU\b|\bORNL\b|\bLBNL\b", "the facility", text)
    return text


# ---------------------------------------------------------------------------
# Map access
# ---------------------------------------------------------------------------

def build_map(group: str, pools_doc: dict) -> dict:
    gp = pools_doc[group]
    if group == "WADI":
        return build_map_wadi(gp)
    if group == "SWaT":
        return build_map_swat(gp)
    if group == "HVAC":
        return build_map_hvac(gp)
    return build_map_rcaeval(gp, group)


def load_map(group: str, map_dir: Path = MAP_DIR, pools_path=None) -> dict:
    """The shipped map for ``group``; rebuilt from the pools if absent."""
    path = Path(map_dir) / MAP_FILE[group]
    if path.exists():
        return json.loads(path.read_text())
    return build_map(group, load_pools(pools_path or DEFAULT_POOLS))


def name_functions(group: str, map_dir: Path = MAP_DIR, pools_path=None):
    """Return (real -> anon, anon -> real) name functions for one group."""
    m = load_map(group, map_dir, pools_path)
    rev = {v: k for k, v in m.items()}
    if group.startswith("RE1-"):
        return (lambda n: metric_to_anon(n, m),
                lambda n: metric_to_anon(n, rev))
    return (lambda n: m.get(n, n), lambda n: rev.get(n, n))


def leakage_audit(group: str, text: str, to_anon: dict) -> list:
    if group == "WADI":
        return LEAK_RE.findall(text)
    if group == "SWaT":
        return SWAT_LEAK_RE.findall(text)
    if group == "HVAC":
        return HVAC_LEAK_RE.findall(text)
    return leakage_audit_rcaeval(text, group, to_anon)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--pools", default=str(DEFAULT_POOLS))
    p.add_argument("--check", action="store_true",
                   help="rebuild every map from the pools, write it to the "
                        "output dir and compare with the shipped map")
    p.add_argument("--audit", action="store_true",
                   help="leakage audit of the anonymized domain documents")
    p.add_argument("--out-dir", default=None)
    a = p.parse_args(argv)
    ok = True
    if a.check:
        out = out_dir("anonymize", a.out_dir)
        pools_doc = load_pools(a.pools)
        for group in MAP_FILE:
            if group not in pools_doc:
                print(f"  {group}: not in {a.pools}, skipped")
                continue
            built = build_map(group, pools_doc)
            (out / MAP_FILE[group]).write_text(
                json.dumps(built, indent=2, sort_keys=True))
            shipped = MAP_DIR / MAP_FILE[group]
            same = shipped.exists() and json.loads(shipped.read_text()) == built
            ok &= same
            print(f"  {group}: {len(built)} names, "
                  f"{'identical to' if same else 'DIFFERS from'} {shipped}")
    if a.audit:
        for group, doc in ANON_DOC.items():
            text = (PROMPTS_ROOT / doc).read_text()
            hits = leakage_audit(group, text, load_map(group, pools_path=a.pools))
            ok &= not hits
            print(f"  {doc}: {len(hits)} leakage hits {sorted(set(hits))[:10]}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
