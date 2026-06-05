#!/usr/bin/env bash
# The ONLY shell in the engine: launch one headless Claude Code routing probe.
#   usage: launch.sh <model_id> <full_prompt>
# cwd is set by the runner to a cloned workspace that already has .claude/skills/ installed.
# stdout = stream-json trace (the runner captures it); we always exit 0 because claude's
# non-zero max-turns exit is EXPECTED — the captured trace is the product, not the exit code.
#
# When a second agent framework arrives, add launch-<framework>.sh beside this — that one
# file is the whole "harness", no registry needed.
#
# Flags (calibrated against Claude Code 2.x):
#   --output-format stream-json --verbose : one full JSON message per line incl. tool_use
#   --max-turns N        : router -> workflow Skill is ~2 hops; 3 gives the decision room
#                          while still stopping before the full build.
#   --strict-mcp-config  : load ZERO MCP servers so the hosted Hyperframes MCP can't compete
#                          with the local skills under test.
#   --dangerously-skip-permissions : autonomous tool use, no prompts.
#   </dev/null           : skip the ~3s "waiting for stdin" stall on every cell.
set -uo pipefail
MODEL_ID="$1"; FULL="$2"
MAX_TURNS="${BENCH_MAX_TURNS:-3}"
HERE="$(cd "$(dirname "$0")" && pwd)"

# Routing-only stop: a PreToolUse hook halts the run the instant the agent invokes a
# WORKFLOW Skill. The routing decision is already in the tool_use block (so skills_invoked
# is still captured), and we skip paying for the workflow's build-prep. Clarify/decline
# cases invoke no workflow Skill → unaffected, still run to --max-turns.
# Disable with BENCH_STOP_ON_ROUTE=0.
STOP_ON_ROUTE="${BENCH_STOP_ON_ROUTE:-1}"
SETTINGS_JSON='{"hooks":{"PreToolUse":[{"matcher":"Skill","hooks":[{"type":"command","command":"python3 '"$HERE"'/route-stop-hook.py"}]}]}}'

if [ "$STOP_ON_ROUTE" != "0" ]; then
  claude -p "$FULL" \
    --model "$MODEL_ID" \
    --output-format stream-json --verbose \
    --dangerously-skip-permissions \
    --strict-mcp-config \
    --max-turns "$MAX_TURNS" \
    --settings "$SETTINGS_JSON" \
    </dev/null
else
  claude -p "$FULL" \
    --model "$MODEL_ID" \
    --output-format stream-json --verbose \
    --dangerously-skip-permissions \
    --strict-mcp-config \
    --max-turns "$MAX_TURNS" \
    </dev/null
fi

exit 0
