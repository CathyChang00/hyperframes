"""Scoring: run oracles for a cell, aggregate a run, and re-score a finished run.

`bench score <run>` re-runs only this file's logic over saved traces — it never re-invokes
the agent, so tweaking an oracle is cheap and never costs a model call.
"""
import os
import json
from collections import Counter, defaultdict

from core import load_json, load_jsonl
import oracles as oracle_pkg

DEFAULT_ORACLES = ["route", "router_first", "intent"]
GOOD = {"correct", "clarify_ok", "oos_ok"}          # "the agent did the right thing"
EXCLUDE_FROM_ACC = {"unavailable"}                  # capability absent — not the agent's fault


def run_oracles(parsed, case, installed, cfg):
    names = case.get("oracles") or DEFAULT_ORACLES
    return oracle_pkg.run(names, parsed, case.get("expect", {}), installed, cfg)


def _route_verdict(row):
    return (row.get("oracles", {}).get("route", {}) or {}).get("verdict")


def aggregate(results, cfg):
    by_status = Counter(r.get("status") for r in results)
    route_verdicts = Counter()
    rf_true = rf_total = 0
    by_category = defaultdict(lambda: Counter())
    per_case = defaultdict(list)
    cost = 0.0
    turns = []

    for r in results:
        v = _route_verdict(r)
        if v:
            route_verdicts[v] += 1
            by_category[r.get("category") or "?"][("good" if v in GOOD else "bad")] += 1
        per_case[r["case"]].append(v)
        rf = (r.get("oracles", {}).get("router_first", {}) or {}).get("router_first")
        if rf is not None:
            rf_total += 1
            rf_true += 1 if rf else 0
        if isinstance(r.get("cost_usd"), (int, float)):
            cost += r["cost_usd"]
        if isinstance(r.get("turns"), int):
            turns.append(r["turns"])

    scorable = sum(c for v, c in route_verdicts.items() if v not in EXCLUDE_FROM_ACC)
    good = sum(c for v, c in route_verdicts.items() if v in GOOD)

    # per-case consistency across repeats (majority verdict + agreement %)
    consistency = {}
    for cid, verdicts in per_case.items():
        vs = [v for v in verdicts if v]
        if not vs:
            continue
        top, n = Counter(vs).most_common(1)[0]
        consistency[cid] = {"majority": top, "agreement": round(n / len(vs), 2), "n": len(vs)}

    return {
        "cells": len(results),
        "by_status": dict(by_status),
        "route": {
            "verdicts": dict(route_verdicts),
            "scorable": scorable,
            "good": good,
            "accuracy": round(good / scorable, 3) if scorable else None,
        },
        "router_first": {
            "rate": round(rf_true / rf_total, 3) if rf_total else None,
            "true": rf_true, "applicable": rf_total,
        },
        "by_category": {k: dict(v) for k, v in by_category.items()},
        "consistency": consistency,
        "cost_usd_total": round(cost, 4),
        "turns_avg": round(sum(turns) / len(turns), 2) if turns else None,
    }


def rescore_run(out_dir, cfg):
    """Re-run oracles over every saved cell trace and rewrite results/aggregate/report."""
    cells_dir = os.path.join(out_dir, "cells")
    results = []
    for key in sorted(os.listdir(cells_dir)):
        cdir = os.path.join(cells_dir, key)
        rp = os.path.join(cdir, "result.json")
        tp = os.path.join(cdir, "trace.json")
        if not os.path.exists(rp):
            continue
        row = load_json(rp)
        if os.path.exists(tp) and row.get("status") == "ok":
            parsed = load_json(tp)
            case = {"id": row["case"], "expect": row.get("expected", {}), "oracles": None}
            row["oracles"] = run_oracles(parsed, case, row.get("installed", []), cfg)
            with open(rp, "w") as f:
                json.dump(row, f, indent=2, ensure_ascii=False)
            with open(os.path.join(cdir, "verdict.json"), "w") as f:
                json.dump(row["oracles"], f, indent=2, ensure_ascii=False)
        results.append(row)

    results.sort(key=lambda r: r["key"])
    with open(os.path.join(out_dir, "results.jsonl"), "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    agg = aggregate(results, cfg)
    with open(os.path.join(out_dir, "aggregate.json"), "w") as f:
        json.dump(agg, f, indent=2, ensure_ascii=False)

    manifest = load_json(os.path.join(out_dir, "run_manifest.json")) if \
        os.path.exists(os.path.join(out_dir, "run_manifest.json")) else {}
    from core import report as report_mod
    report_mod.write_report(out_dir, results, agg, cfg, manifest)
    return {"results": results, "aggregate": agg}
