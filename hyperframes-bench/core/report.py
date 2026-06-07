"""Render a run into report.md — a SHORT, plain-language answer to one question:
"is my routing good right now?" The full machine-readable metrics live in aggregate.json;
this file is the human skim. Deliberately no scope-matrix / verdict tables / cost / router-first.
"""
import os

WORKFLOW_LABEL = "workflow"


def _verdict(r):
    return (r.get("oracles", {}).get("route", {}) or {}).get("verdict")


def _observed(r):
    return (r.get("oracles", {}).get("route", {}) or {}).get("observed") or "—"


def _expected(r):
    return (r.get("expected") or {}).get("route")


def _prompt(out_dir, r, n=95):
    try:
        t = open(os.path.join(out_dir, r.get("paths", {}).get("prompt", ""))).read().strip()
        t = " ".join(t.split())
        return (t[:n] + "…") if len(t) > n else t
    except Exception:
        return ""


def _pct(a, b):
    return f"{round(100 * a / b)}%" if b else "—"


def write_report(out_dir, results, agg, cfg, manifest):
    workflows = set(cfg.get("workflow_skills", []))
    L = []
    a = L.append

    a(f"# Routing check — {manifest.get('label', 'run')}")
    a("")
    a(f"`{', '.join(manifest.get('models', []))}` · env `{', '.join(manifest.get('envs', []))}` · "
      f"{len(results)} requests tested")
    a("")
    if manifest.get("dry_run"):
        a("**DRY RUN** — prompts rendered, agent not called, no verdicts.")
        with open(os.path.join(out_dir, "report.md"), "w") as f:
            f.write("\n".join(L) + "\n")
        return

    # "no fair routing decision observed" — excluded from the headline (keep in sync with
    # score.py EXCLUDE_FROM_ACC): capability absent / built inline / oracle couldn't read it.
    EXCLUDED = {"unavailable", "inline", "unparsed"}

    # three buckets that actually answer "is routing good"
    routeable = [r for r in results if _expected(r) in workflows]   # should pick a workflow
    graded = [r for r in routeable if _verdict(r) not in EXCLUDED]   # a routing decision was observed
    # pass = routed to the right workflow, OR correctly asked for an input the bench didn't supply
    route_ok = [r for r in graded if _verdict(r) in ("correct", "asked_ok")]
    oos = [r for r in results if _expected(r) == "out-of-scope"]     # should decline
    oos_ok = [r for r in oos if _verdict(r) == "oos_ok"]
    vague = [r for r in results if _expected(r) == "clarify"]        # should ask
    vague_ok = [r for r in vague if _verdict(r) == "clarify_ok"]
    excluded = [r for r in (routeable + vague) if _verdict(r) in EXCLUDED]

    a("## Is routing good?")
    a("")
    if graded:
        a(f"- ✅ **Picks the right workflow — {_pct(len(route_ok), len(graded))}** "
          f"({len(route_ok)}/{len(graded)} requests that map to one)")
    if oos:
        mark = "✅" if len(oos_ok) / len(oos) >= 0.7 else "⚠️"
        a(f"- {mark} **Keeps out-of-scope requests out of a workflow — {_pct(len(oos_ok), len(oos))}** "
          f"({len(oos_ok)}/{len(oos)}; the rest grabbed a workflow it shouldn't have)")
    if vague:
        a(f"- **Asks when the request is too vague — {_pct(len(vague_ok), len(vague))}** "
          f"({len(vague_ok)}/{len(vague)})")
    if excluded:
        a(f"- _{len(excluded)} not graded (built inline / unreadable trace) — excluded, see dashboard_")
    a("")

    # one-line bottom line driven by the two main numbers
    route_strong = graded and len(route_ok) / len(graded) >= 0.9
    oos_weak = oos and len(oos_ok) / len(oos) < 0.5
    oos_misuse = sum(1 for r in oos if _verdict(r) != "oos_ok")
    if route_strong and oos_weak:
        a("**Bottom line:** routing to the right workflow is reliable, but the agent too often "
          "pulls a workflow into an out-of-scope request instead of leaving it alone.")
    elif route_strong:
        tail = (f" The main thing left: **{oos_misuse}** out-of-scope request(s) still got pulled "
                f"into a workflow." if oos_misuse else "")
        a("**Bottom line:** routing is in good shape — it picks the right workflow reliably and "
          "keeps out-of-scope requests out of one." + tail)
    else:
        a("**Bottom line:** routing needs work — see below.")
    a("")

    # ---- what to fix (concise) -------------------------------------------------------
    a("## What to fix")
    a("")

    # 1) out-of-scope that wrongly pulled in a workflow — the real misuse
    oos_bad = sorted((r for r in oos if _verdict(r) != "oos_ok"), key=lambda r: r["case"])
    if oos_bad:
        a(f"**Pulled a workflow into an out-of-scope request — {len(oos_bad)} of {len(oos)}.** "
          "HyperFrames can't do these; it should have left them alone:")
        for r in oos_bad[:8]:
            a(f"- `{r['case']}` — \"{_prompt(out_dir, r)}\" → {_observed(r)}")
        if len(oos_bad) > 8:
            a(f"- …and {len(oos_bad) - 8} more")
        a("")

    # 2) should have routed / asked but didn't — the real misses on in-scope requests
    other = [r for r in (routeable + vague)
             if _verdict(r) not in ("correct", "clarify_ok")
             and _verdict(r) not in EXCLUDED
             and not (r.get("oracles", {}).get("route", {}) or {}).get("asked_for_missing_input")]
    other.sort(key=lambda r: r["case"])
    if other:
        a(f"**Other misses — {len(other)}** (a request that should route or ask, but didn't):")
        for r in other:
            obs = _observed(r)
            did = (f"→ {obs}" if obs != "—" else "→ no workflow chosen")
            a(f"- `{r['case']}` — \"{_prompt(out_dir, r)}\" {did} "
              f"_(expected {_expected(r)})_")
        a("")

    a("---")
    a("_full metrics: `aggregate.json` · per-request traces: `trace_report.html`_")
    with open(os.path.join(out_dir, "report.md"), "w") as f:
        f.write("\n".join(L) + "\n")
