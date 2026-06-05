#!/usr/bin/env python3
"""PreToolUse hook (routing benchmark): the instant the agent invokes a WORKFLOW
Skill, stop the run. The routing decision is already in the assistant's tool_use
block (emitted before this hook runs), so the oracle still sees `skills_invoked`;
we just don't pay for the workflow's build-prep (reading refs, spawning subagents,
authoring + rendering).

Stdin = the PreToolUse event JSON. Stdout (only for a workflow Skill) = a combined
stop + deny decision. The router (`hyperframes-read-first`), support skills, and every
other tool pass through untouched — so clarify/decline cases are unaffected and still
run to --max-turns. Disable the whole thing with BENCH_STOP_ON_ROUTE=0 in launch.sh.
"""
import sys, json

WORKFLOWS = {"product-launch-video", "faceless-explainer", "footage-recut",
             "pr-to-video", "remotion-to-hyperframes", "general-video"}

try:
    ev = json.load(sys.stdin)
except Exception:
    sys.exit(0)

if ev.get("tool_name") != "Skill":
    sys.exit(0)

ti = ev.get("tool_input") or {}
skill = str(ti.get("skill") or ti.get("name") or ti.get("command") or "").lstrip("/")

if skill in WORKFLOWS:
    # continue:false halts the agent; the deny decision prevents the Skill from
    # executing. We emit both so it works whichever the runtime honours.
    print(json.dumps({
        "continue": False,
        "stopReason": f"BENCH route captured: {skill} (stopped before build)",
        "decision": "block",
        "reason": f"routing-only benchmark: {skill} invoked; halt before the build.",
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"routing-only benchmark: {skill} invoked; halt before the build.",
        },
    }))

sys.exit(0)
