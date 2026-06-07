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
GOOD = {"correct", "clarify_ok", "oos_ok", "asked_ok"}   # "the agent did the right thing"
# "no fair routing decision observed" → excluded from accuracy (NOT counted as a failure):
# capability absent / agent built it inline / oracle couldn't read a decision. The real
# routing failures (miss, competitor, soft) are everything that is neither GOOD nor excluded.
EXCLUDE_FROM_ACC = {"unavailable", "inline", "unparsed"}


def _bucket(v):
    return "good" if v in GOOD else ("excluded" if v in EXCLUDE_FROM_ACC else "bad")

# Bin's scope view: project route verdicts onto "did the agent correctly decide to
# accept / ask / decline, vs the request's true scope" — a DIFFERENT question from
# "did it pick the right workflow" (that stays in route.accuracy). A workflow being
# invoked at all = "accept", regardless of which one.
_VERDICT_TO_RESPONSE = {
    "correct": "accept", "miss": "accept", "competitor": "accept",
    "clarify_ok": "clarify", "soft": "clarify", "asked_ok": "clarify",
    "oos_ok": "refuse",
    # unavailable / inline / unparsed -> no scope decision observed (excluded)
}


def run_oracles(parsed, case, installed, cfg):
    names = case.get("oracles") or DEFAULT_ORACLES
    return oracle_pkg.run(names, parsed, case.get("expect", {}), installed, cfg)


def _route_verdict(row):
    return (row.get("oracles", {}).get("route", {}) or {}).get("verdict")


def _scope_truth(expected_route, workflows):
    if expected_route in workflows:
        return "in-scope"      # the agent SHOULD take it on
    if expected_route == "clarify":
        return "ambiguous"     # the agent SHOULD ask first
    if expected_route == "out-of-scope":
        return "can't"         # the agent SHOULD decline
    return None


def scope_matrix(results, cfg):
    """Bin/Wenbo confusion view, derived (no re-run) from each cell's expect + route verdict.
    Rows = true scope; cols = observed response. The diagonal of correctness is TP/guide_ok/TN."""
    workflows = set(cfg["workflow_skills"])
    rows = ["in-scope", "ambiguous", "can't"]
    cols = ["accept", "clarify", "refuse"]
    grid = {t: {c: 0 for c in cols} for t in rows}
    excluded = 0
    for r in results:
        rv = (r.get("oracles", {}).get("route", {}) or {})
        truth = _scope_truth((r.get("expected") or {}).get("route"), workflows)
        # capability absent (skill not installed) is not a fair scope decision → exclude
        if rv.get("verdict") == "unavailable":
            excluded += 1
            continue
        # prefer the behaviour-derived response; fall back to the verdict map for old runs
        resp = rv.get("response") or _VERDICT_TO_RESPONSE.get(rv.get("verdict"))
        if resp == "none":
            resp = None
        if truth is None or resp is None:
            excluded += 1
            continue
        grid[truth][resp] += 1
    confusion = {
        "TP": grid["in-scope"]["accept"],          # could do, took it on        ✓
        "FN": grid["in-scope"]["refuse"],           # could do, declined          ✗
        "over_clarify": grid["in-scope"]["clarify"],# clear request, still asked   ✗-ish
        "guide_ok": grid["ambiguous"]["clarify"],   # ambiguous, asked            ✓ (Wenbo's "guide")
        "premature_accept": grid["ambiguous"]["accept"],   # ambiguous, committed ✗
        "refused_ambiguous": grid["ambiguous"]["refuse"],  # ambiguous, declined  ✗
        "FP": grid["can't"]["accept"],              # can't do, took it on        ✗
        "TN": grid["can't"]["refuse"],              # can't do, declined          ✓
        "weak_clarify": grid["can't"]["clarify"],   # can't do, asked (should decline)
    }
    scored = sum(sum(c.values()) for c in grid.values())
    good = confusion["TP"] + confusion["TN"] + confusion["guide_ok"]
    return {
        "truth_x_response": grid,
        "confusion": confusion,
        "scored": scored,
        "excluded": excluded,
        "scope_accuracy": round(good / scored, 3) if scored else None,
        "caveat": ("accept/refuse decision only — ignores WHICH workflow (see route.accuracy). "
                   "FP = accepted an out-of-scope request; 'accepted but botched' needs the E2E "
                   "oracle. excluded = unavailable/unparsed cells (no scope decision observed)."),
    }


def aggregate(results, cfg):
    by_status = Counter(r.get("status") for r in results)
    route_verdicts = Counter()
    rf_true = rf_total = 0
    by_category = defaultdict(lambda: Counter())
    per_case = defaultdict(list)
    cost = 0.0
    turns = []
    artifact_suspected = 0   # A3: failures where the agent asked for an asset the bench never supplied
    miss_kinds = Counter()   # R2: which KIND of miss (overreach / wrong_workflow / premature / refused)

    for r in results:
        ro = r.get("oracles", {}).get("route", {}) or {}
        v = _route_verdict(r)
        if v:
            route_verdicts[v] += 1
            by_category[r.get("category") or "?"][_bucket(v)] += 1
        if v == "miss":
            miss_kinds[ro.get("kind") or "unclassified"] += 1
        if _bucket(v) == "bad" and ro.get("asked_for_missing_input"):
            artifact_suspected += 1
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
    excluded = sum(c for v, c in route_verdicts.items() if v in EXCLUDE_FROM_ACC)

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
            "miss_breakdown": dict(miss_kinds),     # R2: overreach vs wrong_workflow vs premature vs refused
            "excluded": excluded,                   # R3: unavailable + inline + unparsed (no fair decision)
            "artifact_suspected": artifact_suspected,
        },
        "router_first": {
            "rate": round(rf_true / rf_total, 3) if rf_total else None,
            "true": rf_true, "applicable": rf_total,
        },
        "by_category": {k: dict(v) for k, v in by_category.items()},
        "scope_matrix": scope_matrix(results, cfg),
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
