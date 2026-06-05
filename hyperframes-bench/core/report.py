"""Render a run into report.md (human-facing). The machine-facing summary is aggregate.json;
this is the prose an agent pastes back to the user, or a human skims directly.
"""
import os


def _bar(verdicts):
    order = ["correct", "clarify_ok", "oos_ok", "soft", "miss", "competitor",
             "unavailable", "unparsed"]
    rows = []
    for v in order:
        if verdicts.get(v):
            rows.append(f"| {v} | {verdicts[v]} |")
    return rows


def write_report(out_dir, results, agg, cfg, manifest):
    lines = []
    a = lines.append
    git = manifest.get("local_hf", {})
    a(f"# hyperframes-bench — {manifest.get('label', 'run')}")
    a("")
    a(f"- cells: **{agg['cells']}**  ·  models: {', '.join(manifest.get('models', []))}  "
      f"·  envs: {', '.join(manifest.get('envs', []))}")
    if git.get("commit"):
        a(f"- local hyperframes: `{git.get('branch', '?')}@{git['commit']}`")
    if manifest.get("dry_run"):
        a("- **DRY RUN** — env installed + prompts rendered, agent NOT launched (no verdicts).")
    a("")

    acc = agg["route"]["accuracy"]
    a("## Routing")
    a("")
    a(f"- accuracy (good / scorable): **{acc if acc is not None else 'n/a'}**  "
      f"({agg['route']['good']} / {agg['route']['scorable']})  "
      f"— good = correct + clarify_ok + oos_ok; scorable excludes `unavailable`")
    rf = agg["router_first"]
    if rf["applicable"]:
        a(f"- router-first rate: **{rf['rate']}**  ({rf['true']} / {rf['applicable']} applicable)")
    a("")
    bar = _bar(agg["route"]["verdicts"])
    if bar:
        a("| route verdict | n |")
        a("|---|---|")
        lines.extend(bar)
        a("")

    if agg["by_category"]:
        a("## By category")
        a("")
        a("| category | good | bad |")
        a("|---|---|---|")
        for cat in sorted(agg["by_category"]):
            c = agg["by_category"][cat]
            a(f"| {cat} | {c.get('good', 0)} | {c.get('bad', 0)} |")
        a("")

    # surface the cells that need a human eye
    flagged = [r for r in results
               if (r.get("oracles", {}).get("route", {}) or {}).get("verdict")
               in ("miss", "competitor", "soft", "unparsed")]
    if flagged:
        a("## Flagged (miss / competitor / soft / unparsed)")
        a("")
        a("| cell | verdict | observed | note |")
        a("|---|---|---|---|")
        for r in sorted(flagged, key=lambda x: x["key"]):
            rv = r["oracles"]["route"]
            a(f"| {r['key']} | {rv.get('verdict')} | {rv.get('observed')} | {rv.get('note', '')} |")
        a("")

    unavail = [r for r in results
               if (r.get("oracles", {}).get("route", {}) or {}).get("verdict") == "unavailable"]
    if unavail:
        cases = sorted({r["case"] for r in unavail})
        a(f"## Unavailable ({len(unavail)} cells)")
        a("")
        a("Expected workflow not installed in this env (capability absent, **not** a routing "
          "failure). Cases: " + ", ".join(cases))
        a("")

    sm = agg.get("scope_matrix")
    if sm and sm.get("scored"):
        a("## Scope — accept / clarify / refuse vs. true scope")
        a("")
        a(f"- scope accuracy: **{sm['scope_accuracy']}**  "
          f"(TP + TN + guide_ok = {sm['confusion']['TP'] + sm['confusion']['TN'] + sm['confusion']['guide_ok']}"
          f" / {sm['scored']} scored; {sm['excluded']} excluded)")
        a("")
        g = sm["truth_x_response"]
        labels = {"in-scope": "in-scope (can do)", "ambiguous": "ambiguous (ask)", "can't": "can't (decline)"}
        a("| true scope ↓ \\ response → | accept | clarify | refuse |")
        a("|---|---|---|---|")
        for t in ("in-scope", "ambiguous", "can't"):
            r = g[t]
            a(f"| {labels[t]} | {r['accept']} | {r['clarify']} | {r['refuse']} |")
        a("")
        c = sm["confusion"]
        a(f"- **TP** {c['TP']} · **TN** {c['TN']} · **FP** {c['FP']} · **FN** {c['FN']} · "
          f"guide_ok {c['guide_ok']} · over_clarify {c['over_clarify']} · "
          f"premature_accept {c['premature_accept']}")
        a(f"- _{sm['caveat']}_")
        a("")

    a(f"_cost: ${agg['cost_usd_total']}  ·  avg turns: {agg['turns_avg']}_")
    with open(os.path.join(out_dir, "report.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
