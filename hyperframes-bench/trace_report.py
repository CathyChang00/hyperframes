#!/usr/bin/env python3
"""Visualize a routing run as a REVIEWABLE dashboard — did the agent REALLY route to
the intended workflow (invoked the Skill tool), and when it clarified, WHAT did it ask?

Reads a finished run dir (results/<run-id>/) and emits:
  - trace_report.html  — a triage dashboard: sticky summary + filter chips (verdict /
                         category / failures-only) + search; failures sorted to the top;
                         each case a COLLAPSED card (prompt, expected→observed, verdict,
                         a heuristic "asked-for-missing-input" artifact flag, and an
                         on-demand step timeline). Timelines are closed by default so the
                         page is scannable; expand one card, or "expand all", as needed.
  - stdout / .md       — a compact markdown table.

Usage: trace_report.py [RUN_DIR]   (default: most-recent results/* dir)
"""
import os, sys, json, html, glob, re

BENCH = os.path.dirname(os.path.abspath(__file__))
ROUTER_ALIASES = {"hyperframes-read-first", "video-workflows"}
WORKFLOWS = {"product-launch-video", "faceless-explainer", "footage-recut",
             "pr-to-video", "remotion-to-hyperframes", "general-video"}

VERDICT_COLOR = {
    "correct": "#1a7f37", "clarify_ok": "#0969da", "oos_ok": "#0969da",
    "soft": "#9a6700", "miss": "#cf222e", "competitor": "#bc4c00",
    "unavailable": "#6e7781", "inline": "#6e7781", "unparsed": "#9a6700",
}
# review priority: the things you most want to look at first sort to the top.
VERDICT_RANK = {"miss": 0, "competitor": 1, "unparsed": 2, "soft": 3,
                "inline": 4, "unavailable": 5, "clarify_ok": 6, "oos_ok": 7, "correct": 8}
GOOD_VERDICTS = {"correct", "clarify_ok", "oos_ok"}
# "no fair decision observed" — neither a pass nor a fail; kept off the red fail count
# (mirrors score.py EXCLUDE_FROM_ACC). A high `unparsed` rate means the ORACLE is blind.
EXCLUDED_VERDICTS = {"unavailable", "inline", "unparsed"}
HOW_BADGE = {"invoked": ("✅ invoked", "#1a7f37"), "named": ("⚠️ named-only", "#9a6700"),
             "competitor": ("competitor", "#bc4c00"), "none": ("— none", "#6e7781")}

# heuristic: the failure is probably an ARTIFACT of the bench not supplying an asset the
# prompt references ("my video / my blog post") — the agent correctly asked for it. Flagging
# these lets a reviewer discount them at a glance instead of reading every trace.
_ASK = re.compile(r"(what'?s the|provide the|paste|file path|path to|share the|do you have|"
                  r"where (is|should)|could you (paste|provide|share)|channel name|"
                  r"need .{0,30}(path|file|text|url)|don'?t see|didn'?t include|"
                  r"isn'?t (in|attached)|no .{0,20}(file|clip) )", re.I)


def latest_run():
    dirs = sorted(glob.glob(os.path.join(BENCH, "results", "*")), key=os.path.getmtime)
    return dirs[-1] if dirs else None


def load_json(p):
    try:
        return json.load(open(p))
    except Exception:
        return None


def read_text(p):
    try:
        return open(p).read().strip()
    except Exception:
        return ""


def fmt_tool_input(name, inp):
    """Compact, human-readable summary of a tool call's input."""
    if not isinstance(inp, dict):
        return html.escape(str(inp)[:200])
    if name == "Skill":
        return f'<code>{html.escape(str(inp.get("skill") or inp.get("command") or inp.get("name") or inp))}</code>'
    if name == "AskUserQuestion":
        out = []
        for q in inp.get("questions", []):
            opts = " · ".join(o.get("label", "") for o in q.get("options", []))
            out.append(f'<b>{html.escape(q.get("question",""))}</b>'
                       + (f'<br><span class="opts">options: {html.escape(opts)}</span>' if opts else ""))
        return "<br>".join(out)
    if name == "Bash":
        return f'<code>{html.escape((inp.get("command","") or "")[:240])}</code>'
    if name in ("Read", "Write", "Edit", "NotebookEdit"):
        return f'<code>{html.escape(inp.get("file_path",""))}</code>'
    if name == "WebSearch":
        return html.escape(inp.get("query", ""))
    if name == "WebFetch":
        return f'<code>{html.escape(inp.get("url",""))}</code>'
    s = json.dumps(inp, ensure_ascii=False)
    return html.escape(s[:200] + ("…" if len(s) > 200 else ""))


def parse_steps(raw_path):
    """Walk the stream-json into an ordered list of (kind, payload) steps, plus flags."""
    steps, asked, rate_limited = [], [], False
    if not os.path.exists(raw_path):
        return steps, asked, rate_limited
    for line in open(raw_path):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        t = o.get("type")
        if t == "assistant":
            for b in o.get("message", {}).get("content", []):
                bt = b.get("type")
                if bt == "thinking":
                    steps.append(("think", b.get("thinking", "")))
                elif bt == "text":
                    txt = (b.get("text") or "").strip()
                    if txt:
                        steps.append(("text", txt))
                elif bt == "tool_use":
                    steps.append(("tool", {"name": b.get("name", ""), "input": b.get("input", {})}))
                    if b.get("name") == "AskUserQuestion":
                        asked.extend(b.get("input", {}).get("questions", []))
        elif t == "user":
            for b in o.get("message", {}).get("content", []):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content")
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                    steps.append(("res", {"text": str(c)[:200], "err": bool(b.get("is_error"))}))
        elif t == "rate_limit_event":
            if o.get("rate_limit_info", {}).get("status") not in (None, "allowed"):
                rate_limited = True
        elif t == "result":
            # AskUserQuestion gets denied in headless; the question lives in permission_denials too
            for d in o.get("permission_denials", []):
                if d.get("tool_name") == "AskUserQuestion":
                    asked.extend(d.get("tool_input", {}).get("questions", []))
    # dedupe: the same question shows up in both the tool_use block and permission_denials
    seen, uniq = set(), []
    for q in asked:
        k = q.get("question", "")
        if k not in seen:
            seen.add(k)
            uniq.append(q)
    return steps, uniq, rate_limited


def step_html(kind, p):
    if kind == "think":
        head = html.escape(p[:110].replace("\n", " ")) + ("…" if len(p) > 110 else "")
        return (f'<details class="step think"><summary>🧠 reasoning: {head}</summary>'
                f'<pre>{html.escape(p[:2000])}</pre></details>')
    if kind == "text":
        return f'<div class="step text">💬 {html.escape(p[:600])}</div>'
    if kind == "tool":
        name = p["name"]
        icon = "🎯" if name == "Skill" else ("❓" if name == "AskUserQuestion" else "🔧")
        return f'<div class="step tool">{icon} <b>{html.escape(name)}</b> {fmt_tool_input(name, p["input"])}</div>'
    if kind == "res":
        cls = "err" if p["err"] else ""
        note = " <span class='muted'>(headless: no user to answer → re-asked as text)</span>" if p["err"] and "Answer questions" in p["text"] else ""
        return f'<div class="step res {cls}">↩ {html.escape(p["text"])}{note}</div>'
    return ""


def clarify_box(asked, final_text, verdict):
    if asked:
        rows = []
        for q in asked:
            opts = " · ".join(o.get("label", "") for o in q.get("options", []))
            rows.append(f'<b>{html.escape(q.get("question",""))}</b>'
                        + (f'<div class="opts">↳ {html.escape(opts)}</div>' if opts else ""))
        return f'<div class="clarify">❓ <span class="lbl">clarifying question(s) asked</span><br>{"<br>".join(rows)}</div>'
    if verdict in ("clarify_ok", "soft", "unparsed") and final_text:
        return f'<div class="clarify">❓ <span class="lbl">asked (as text)</span><br>{html.escape(final_text[:500])}</div>'
    return ""


def chip_row(label, kind, items, active="all"):
    """A row of filter chips. items = [(value, text, count)]; `all` chip is prepended."""
    out = [f'<span class="chip-label">{label}</span>',
           f'<button class="chip{" on" if active=="all" else ""}" data-k="{kind}" data-v="all">all</button>']
    for value, text, count in items:
        out.append(f'<button class="chip" data-k="{kind}" data-v="{html.escape(value)}">'
                   f'{html.escape(text)} <span class="cnt">{count}</span></button>')
    return f'<div class="chiprow">{"".join(out)}</div>'


def main():
    run_dir = sys.argv[1] if len(sys.argv) > 1 else latest_run()
    if not run_dir or not os.path.isdir(run_dir):
        sys.exit(f"no run dir found ({run_dir})")
    rp = os.path.join(run_dir, "results.jsonl")
    if not os.path.exists(rp):
        sys.exit(f"no results.jsonl in {run_dir}")
    rows = [json.loads(l) for l in open(rp) if l.strip()]
    agg = load_json(os.path.join(run_dir, "aggregate.json")) or {}
    man = load_json(os.path.join(run_dir, "run_manifest.json")) or {}

    # ---- build per-case records (and the markdown table) ----------------------------
    recs, md = [], ["| case | cat | expected | observed | how | rf | verdict |",
                    "|---|---|---|---|---|---|---|"]
    cat_counts, verdict_counts = {}, {}
    pos_total = pos_correct = artifact_fails = 0
    for r in rows:
        ro = r.get("oracles", {}).get("route", {}) or {}
        rf = r.get("oracles", {}).get("router_first", {}) or {}
        verdict, how = ro.get("verdict", "?"), ro.get("how", "none")
        observed = ro.get("observed") or "—"
        expected = (r.get("expected") or {}).get("route", "?")
        cat = r.get("category", "")
        paths = r.get("paths", {})
        trace = load_json(os.path.join(run_dir, paths.get("trace", ""))) or {}
        prompt = read_text(os.path.join(run_dir, paths.get("prompt", "")))
        steps, asked, rl = parse_steps(os.path.join(run_dir, paths.get("raw", "")))
        final = trace.get("final_text", "")
        rfv = rf.get("router_first")
        rf_txt = "✅" if rfv is True else ("✗" if rfv is False else "n/a")
        is_fail = verdict not in GOOD_VERDICTS and verdict not in EXCLUDED_VERDICTS
        # prefer the oracle's flag (route is None + asked for the asset); fall back to the
        # regex for runs scored before A3. NB a workflow that routed AND asked for the file
        # made a real routing decision → NOT an artifact (that's the OOS false-positives).
        ami = ro.get("asked_for_missing_input")
        artifact = is_fail and (ami if ami is not None else (ro.get("how") == "none" and bool(_ASK.search(final or ""))))

        if expected in WORKFLOWS:
            pos_total += 1
            if verdict == "correct":
                pos_correct += 1
        if artifact:
            artifact_fails += 1
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

        md.append(f"| {r['case']} | {cat} | {expected} | {observed} | {how} | {rf_txt} | **{verdict}** |")
        recs.append(dict(case=r["case"], cat=cat, verdict=verdict, how=how, observed=observed,
                         expected=expected, prompt=prompt, steps=steps, asked=asked, rl=rl,
                         final=final, rf_txt=rf_txt, turns=trace.get("turns", "?"),
                         is_fail=is_fail, artifact=artifact, kind=ro.get("kind")))

    # failures first, then by category, then case id
    recs.sort(key=lambda x: (VERDICT_RANK.get(x["verdict"], 9), x["cat"], x["case"]))

    # ---- render cards ----------------------------------------------------------------
    cards = []
    for x in recs:
        verdict = x["verdict"]
        vcol = VERDICT_COLOR.get(verdict, "#6e7781")
        htxt, hcol = HOW_BADGE.get(x["how"], (x["how"], "#6e7781"))
        if verdict == "correct":
            match = ("✓ routed to expected", "#1a7f37")
        elif verdict == "clarify_ok":
            match = ("✓ asked instead of routing (expected)", "#1a7f37")
        elif verdict == "oos_ok":
            match = ("✓ declined (expected)", "#1a7f37")
        elif verdict in EXCLUDED_VERDICTS:
            match = (f"— {verdict} (no fair decision graded)", "#6e7781")
        else:
            match = (f"✗ {verdict}" + (f" · {x['kind']}" if x.get("kind") else ""), "#cf222e")
        rl_badge = '<span class="badge" style="background:#cf222e">rate-limited</span>' if x["rl"] else ""
        art_badge = ('<span class="badge artifact" title="heuristic: the agent asked for an asset the '
                     'benchmark did not supply — likely a harness artifact, not a routing error">'
                     '⚠ asked-for-missing-input</span>') if x["artifact"] else ""
        timeline = "".join(step_html(k, p) for k, p in x["steps"]) or '<div class="muted">no trace captured</div>'
        search_blob = html.escape((x["case"] + " " + x["cat"] + " " + x["expected"] + " "
                                   + str(x["observed"]) + " " + x["prompt"]).lower())
        cards.append(f"""
        <div class="card{' fail' if x['is_fail'] else ' pass'}" data-verdict="{verdict}"
             data-cat="{html.escape(x['cat'])}" data-fail="{1 if x['is_fail'] else 0}"
             data-artifact="{1 if x['artifact'] else 0}" data-search="{search_blob}">
          <div class="hdr">
            <span class="cid">{html.escape(x['case'])}</span>
            <span class="cat">{html.escape(x['cat'])}</span>
            <span class="badge" style="background:{vcol}">{verdict}</span>
            <span class="badge" style="background:{hcol}">{htxt}</span>{art_badge}{rl_badge}
            <span class="rf">router-first: {x['rf_txt']} · turns: {x['turns']}</span>
          </div>
          <div class="prompt">{html.escape(x['prompt'])}</div>
          <div class="route"><span class="lbl">expected</span><code>{html.escape(x['expected'])}</code>
            <span class="arrow2">⇒</span><span class="lbl">observed</span><code>{html.escape(str(x['observed']))}</code>
            <span class="match" style="color:{match[1]}">{match[0]}</span></div>
          {clarify_box(x['asked'], x['final'], verdict)}
          <details class="tl"><summary>agent trace ({len(x['steps'])} steps)</summary>{timeline}</details>
        </div>""")

    # ---- summary header --------------------------------------------------------------
    acc = (agg.get("route") or {}).get("accuracy")
    good = (agg.get("route") or {}).get("good")
    scorable = (agg.get("route") or {}).get("scorable")
    rfr = (agg.get("router_first") or {}).get("rate")
    n_fail = sum(1 for x in recs if x["is_fail"])
    pos_pct = f"{pos_correct/pos_total:.0%}" if pos_total else "—"

    # chip rows: verdicts present (sorted by rank) + categories present (sorted)
    vchips = [(v, v, verdict_counts[v]) for v in sorted(verdict_counts, key=lambda v: VERDICT_RANK.get(v, 9))]
    cchips = [(c, c, cat_counts[c]) for c in sorted(cat_counts)]

    summary_chips = (
        f'<span class="kpi"><b>{agg.get("cells","?")}</b> cells</span>'
        f'<span class="kpi"><b>{acc}</b> route-acc <span class="muted">({good}/{scorable})</span></span>'
        f'<span class="kpi big"><b>{pos_pct}</b> on positives <span class="muted">({pos_correct}/{pos_total} concrete-workflow cases)</span></span>'
        f'<span class="kpi warn"><b>{n_fail}</b> fails · <b>{artifact_fails}</b> flagged missing-input</span>'
        f'<span class="kpi"><b>{rfr}</b> router-first</span>'
        f'<span class="kpi"><b>${agg.get("cost_usd_total")}</b></span>'
    )
    meta = (f"model: {', '.join(man.get('models', []))} · env: {', '.join(man.get('envs', []))} · "
            f"commit {man.get('local_hf',{}).get('commit','?')}")

    doc = f"""<!doctype html><meta charset="utf-8"><title>trace — {html.escape(man.get('label','run'))}</title>
<style>
 :root{{--bd:#d0d7de;--mut:#57606a;--bg:#f6f8fa}}
 *{{box-sizing:border-box}}
 body{{font:14px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;max-width:1080px;margin:0 auto;padding:0 16px 60px;color:#1f2328}}
 .bar{{position:sticky;top:0;background:#fffd;backdrop-filter:blur(8px);border-bottom:1px solid var(--bd);
       padding:12px 0 10px;margin:0 -16px 14px;padding-left:16px;padding-right:16px;z-index:5}}
 h1{{font-size:17px;margin:0 0 6px}} .meta{{color:var(--mut);font-size:12px;margin-bottom:8px}}
 .kpis{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px}}
 .kpi{{background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:4px 10px;font-size:12.5px;color:var(--mut)}}
 .kpi b{{color:#1f2328;font-size:14px}} .kpi.big{{background:#dafbe1;border-color:#a2d8ab}}
 .kpi.warn{{background:#fff8c5;border-color:#d4a72c}} .kpi .muted{{font-size:11px}}
 .chiprow{{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:5px 0}}
 .chip-label{{font-size:11px;text-transform:uppercase;color:#8c959f;margin-right:2px;min-width:62px}}
 .chip{{border:1px solid var(--bd);background:#fff;border-radius:20px;padding:3px 11px;font-size:12px;
        cursor:pointer;color:#1f2328;font-family:inherit}}
 .chip:hover{{background:var(--bg)}} .chip.on{{background:#0969da;border-color:#0969da;color:#fff}}
 .chip .cnt{{opacity:.6;font-size:11px}} .chip.on .cnt{{opacity:.85}}
 .tools{{display:flex;gap:8px;align-items:center;margin-top:6px}}
 #q{{flex:1;border:1px solid var(--bd);border-radius:8px;padding:5px 10px;font:13px inherit}}
 .tbtn{{border:1px solid var(--bd);background:#fff;border-radius:8px;padding:5px 10px;font-size:12px;cursor:pointer}}
 .tbtn:hover{{background:var(--bg)}}
 #shownwrap{{font-size:12px;color:var(--mut);white-space:nowrap}}
 .legend{{font-size:11.5px;color:var(--mut);margin:4px 0 0}}
 .card{{border:1px solid var(--bd);border-radius:10px;padding:11px 14px;margin:9px 0;background:#fff}}
 .card.fail{{border-left:4px solid #cf222e}} .card.pass{{border-left:4px solid #1a7f37;opacity:.78}}
 .card.pass:hover{{opacity:1}}
 .hdr{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
 .cid{{font-weight:700;font-family:ui-monospace,monospace}} .cat{{color:var(--mut);font-size:12px}}
 .badge{{color:#fff;border-radius:20px;padding:2px 9px;font-size:11.5px;font-weight:600}}
 .badge.artifact{{background:#8250df}}
 .rf{{margin-left:auto;font-size:11.5px;color:var(--mut)}}
 .prompt{{background:var(--bg);border-radius:6px;padding:7px 10px;font-family:ui-monospace,monospace;
          font-size:12.5px;white-space:pre-wrap;margin:7px 0}}
 .route{{margin:5px 0}} .lbl{{font-size:11px;text-transform:uppercase;color:#8c959f;margin:0 6px}}
 code{{background:#eff1f3;border-radius:4px;padding:1px 6px;font-size:12.5px}}
 .arrow2{{color:#8c959f}} .match{{margin-left:10px;font-weight:600;font-size:12px}}
 .clarify{{background:#fff8c5;border:1px solid #d4a72c;border-radius:8px;padding:7px 12px;margin:7px 0;font-size:13px}}
 .clarify .opts{{color:var(--mut);font-size:12px;margin:2px 0 6px 12px}}
 .tl{{margin-top:7px}} .tl>summary{{cursor:pointer;color:var(--mut);font-size:12px}}
 .step{{margin:4px 0;padding:4px 8px;border-left:3px solid var(--bd);font-size:13px}}
 .step.text{{border-color:#54aeff}} .step.tool{{border-color:#4ac26b;background:#f6fff8}}
 .step.res{{border-color:var(--bd);color:var(--mut);font-size:12px}} .step.res.err{{border-color:#cf222e;color:#cf222e}}
 .step.think{{border-color:#bf8700}} .step.think>summary{{cursor:pointer;color:#9a6700;font-size:12.5px}}
 .step.tool .opts{{color:var(--mut);font-size:12px}} .muted{{color:#8c959f}}
 pre{{background:var(--bg);padding:8px;border-radius:6px;overflow:auto;font-size:12px;white-space:pre-wrap;margin:4px 0}}
 .empty{{text-align:center;color:#8c959f;padding:30px}}
</style>
<div class="bar">
  <h1>routing review — {html.escape(man.get('label','run'))}</h1>
  <div class="meta">{meta}</div>
  <div class="kpis">{summary_chips}</div>
  {chip_row("verdict", "verdict", vchips)}
  {chip_row("category", "cat", cchips)}
  <div class="tools">
    <button class="tbtn" data-quick="fail">❌ failures only</button>
    <button class="tbtn" data-quick="artifact">⚠ flagged missing-input</button>
    <input id="q" placeholder="search case / prompt / route…">
    <button class="tbtn" id="expand">⊕ expand all</button>
    <button class="tbtn" id="collapse">⊖ collapse all</button>
    <span id="shownwrap"><b id="shown">{len(recs)}</b>/{len(recs)}</span>
  </div>
  <div class="legend">cards sorted worst-verdict first; ✅passes dimmed. <b>⚠ asked-for-missing-input</b> = heuristic flag:
   the agent asked for an asset the bench didn't supply (likely artifact, not a real miss). timeline: 🧠reasoning · 💬text · 🎯Skill · ❓ask · 🔧tool · ↩result.</div>
</div>
{''.join(cards)}
<div class="empty" id="empty" style="display:none">no cases match these filters</div>
<script>
const cards=[...document.querySelectorAll('.card')];
const state={{verdict:'all',cat:'all',q:'',artifact:false}};
function apply(){{
  let n=0;
  for(const c of cards){{
    const okV = state.verdict==='all' || (state.verdict==='__fail' && c.dataset.fail==='1')
              || c.dataset.verdict===state.verdict;
    const okC = state.cat==='all' || c.dataset.cat===state.cat;
    const okA = !state.artifact || c.dataset.artifact==='1';
    const okQ = !state.q || c.dataset.search.includes(state.q);
    const show = okV&&okC&&okA&&okQ;
    c.style.display = show?'':'none'; if(show)n++;
  }}
  document.getElementById('shown').textContent=n;
  document.getElementById('empty').style.display=n?'none':'';
}}
document.querySelectorAll('.chip').forEach(ch=>ch.onclick=()=>{{
  const k=ch.dataset.k,v=ch.dataset.v;
  document.querySelectorAll(`.chip[data-k="${{k}}"]`).forEach(o=>o.classList.remove('on'));
  ch.classList.add('on'); state[k]=v; apply();
}});
document.querySelectorAll('.tbtn[data-quick]').forEach(b=>b.onclick=()=>{{
  if(b.dataset.quick==='fail'){{
    state.verdict='__fail';
    document.querySelectorAll('.chip[data-k="verdict"]').forEach(o=>o.classList.remove('on'));
  }} else {{ state.artifact=!state.artifact; b.style.background=state.artifact?'#efe6ff':''; }}
  apply();
}});
document.getElementById('q').oninput=e=>{{state.q=e.target.value.trim().toLowerCase();apply();}};
document.getElementById('expand').onclick=()=>document.querySelectorAll('.tl').forEach(d=>d.open=true);
document.getElementById('collapse').onclick=()=>document.querySelectorAll('.tl').forEach(d=>d.open=false);
</script>
"""
    with open(os.path.join(run_dir, "trace_report.html"), "w") as f:
        f.write(doc)
    with open(os.path.join(run_dir, "trace_report.md"), "w") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md[:3]) + f"\n… {len(recs)} rows")
    print(f"\nHTML: {os.path.join(run_dir, 'trace_report.html')}")


if __name__ == "__main__":
    main()
