# hyperframes-bench

A parameterised engine for one question (MVP scope): **given a natural user request, does the
HyperFrames agent route it to the right workflow** (or correctly clarify / decline)?

> **This tool's primary consumer is an agent.** A human says "test whether sonnet still routes
> correctly when competitors are installed"; an agent maps that to a `bench run` and reads back
> `results.jsonl`. So the contract is discoverable (`bench list`), machine-readable
> (`results.jsonl` + `aggregate.json`), and every failure is a verdict, never a crash.

## The five concepts (keep them separate)

| concept    | what it is                                                   | where                                | MVP                                 |
| ---------- | ------------------------------------------------------------ | ------------------------------------ | ----------------------------------- |
| **case**   | the contract: a request + its expected route                 | `datasets/routing/cases.jsonl`       | ● live                              |
| **env**    | which skills are installed (local / online / +competitors)   | `envs/*.json`                        | ● live                              |
| **plan**   | a named matrix slice (which cases × models × envs × repeats) | `plans/*.json`                       | ● live                              |
| **oracle** | how a trace is judged                                        | `oracles/*.py` (route, router_first) | ● live                              |
| **result** | the raw evidence of one run                                  | `results/<run-id>/`                  | ● live                              |
| _golden_   | human-approved exemplar video                                | `references/`                        | ✗ N/A for routing (E2E only)        |
| _baseline_ | frozen results from a known-good version                     | `baselines/`                         | ◇ reserved (add `bench diff` later) |

Routing has **no golden** — its oracle compares the invoked workflow to `expect.route`, there is
no video to score.

## Quickstart

```bash
./bench schema                     # the whole driving contract for an agent (commands, flags,
                                   #   live valid values, NL→call recipes, verdict glossary) as JSON
./bench list                       # what can I run? (datasets / envs / plans / models)
./bench list --json                # same, machine-readable (+ plan/env descriptions)
./bench list cases [--json]        # every case's id / category / expected route / tags

./bench run --plan smoke            # fast sanity: 1 model × local × 7 cases
./bench run --plan smoke --dry-run  # install env + render prompts, DON'T call the agent (free)
./bench run --plan smoke --json     # stdout = one JSON {run_id, run_dir, selection, aggregate, report}

./bench run --plan routing-full     # full matrix vs local edits
./bench run --plan collision        # all cases × sonnet × competitor-collision env

./bench score     results/<run-id> [--json]   # re-judge saved traces (no agent calls)
./bench report    results/<run-id>            # regenerate report.md (short plain-text answer)
./bench dashboard results/<run-id>            # generate the HTML triage dashboard (trace_report.html)
./bench show      results/<run-id> cand-p02__hf-local__sonnet__r1 [--json]   # inspect one cell
```

**Agent entry point:** start at `bench schema --json` — it returns every command/flag (introspected
from the parser, so it never drifts), the live set of valid models/envs/plans/cases, a table of
natural-language ask → exact call, and the verdict glossary. Then drive `bench run … --json` and read
the `aggregate` straight off stdout.

## Expressing "the test I want" (agent guide)

Pick a **plan** for common asks; override **axes** for ad-hoc ones. Unspecified axes fall back to
the plan (or `default_plan`); explicit flags win.

| the user wants…                       | command                                                                        |
| ------------------------------------- | ------------------------------------------------------------------------------ |
| quick check after editing a skill     | `bench run --plan smoke`                                                       |
| did routing regress (local code)      | `bench run --plan routing-full`                                                |
| do competitors steal the route        | `bench run --plan collision`                                                   |
| just the adversarial cases on opus    | `bench run --dataset routing --tags adversarial --models opus --envs hf-local` |
| one case, many repeats, for flakiness | `bench run --cases cand-p20 --repeats 9 --models sonnet`                       |
| test the **online** published skills  | `bench run --envs hf-online` (pin a branch via `envs/hf-online.json`'s `ref`)  |

Then parse the run's `aggregate` and report back — either off `bench run … --json` stdout directly, or
from `results/<run-id>/aggregate.json` (or `results.jsonl`).

## Local vs online (the two run paths)

Just two `source` values in an env config — nothing more to build:

- **local** (`envs/hf-local.json`, `source: "self"`): installs the working-tree skills via
  `npx skills add <repo> --skill '*' --agent claude-code`, exactly like
  `scripts/test-product-launch-video.sh`. Use when you've edited skills locally.
- **online** (`envs/hf-online.json`, `source: "heygen-com/hyperframes"`): `npx skills add
heygen-com/hyperframes[#<ref>]`. `ref` pins a branch/tag. ⚠️ default branch (main) currently
  lacks 5/6 workflows + the router → those cases score **`unavailable`** (capability absent, not a
  routing failure) until merged; set `ref` to the feature branch to test real targets.

(Rendering / E2E needs the built CLI + `npm install` from that script too — out of routing MVP scope.)

## Output schema

`results.jsonl` — one line per cell:

```json
{
  "key": "cand-p42__hf-local__sonnet__r1",
  "case": "cand-p42",
  "category": "A-direct",
  "env": "hf-local",
  "model": "sonnet",
  "repeat": 1,
  "expected": { "route": "pr-to-video" },
  "oracles": {
    "route": { "verdict": "correct", "observed": "pr-to-video", "how": "invoked", "note": "" },
    "router_first": { "router_first": true, "first_skill": "hyperframes-read-first" }
  },
  "skills_invoked": ["hyperframes-read-first", "pr-to-video"],
  "cost_usd": 0.04,
  "turns": 3,
  "status": "ok",
  "prompt_hash": "…"
}
```

`aggregate.json` — `route.accuracy`, `route.verdicts`, `router_first.rate`, `by_category`,
`scope_matrix` (see below), per-case `consistency` (majority verdict + agreement across
repeats), cost/turns.

### route verdicts

`correct` · `clarify_ok` (asked, as expected) · `oos_ok` (declined, as expected) · `soft`
(clarified a clear request) · `miss` (wrong route) · `competitor` (a rival skill won) ·
`unavailable` (expected skill not installed) · `unparsed`. Accuracy = (correct + clarify_ok +
oos_ok) / scorable, where scorable excludes `unavailable`. Each verdict also carries a
behaviour-derived `response` ∈ `accept | clarify | refuse | none`.

### scope_matrix (the can-do / accept-clarify-refuse view)

A second projection of the **same** run — answers "did the agent correctly decide to **accept /
ask / decline** vs the request's true scope", which is **different** from "did it pick the right
workflow" (that's `route.accuracy`). True scope comes from `expect.route` (a workflow →
`in-scope`, `clarify` → `ambiguous`, `out-of-scope` → `can't`); response is behaviour-derived.
A 3×3 `truth_x_response` grid plus `confusion` (`TP` in-scope+accept · `FN` in-scope+refuse ·
`guide_ok` ambiguous+clarify · `FP` can't+accept · `TN` can't+refuse · …) and `scope_accuracy`.
Note: `FP` here = accepted an out-of-scope request; **"accepted but botched" needs the E2E
oracle** (not in routing MVP). `bench score <run>` recomputes this over old runs.

## Layout

```
bench               core/ (engine)   oracles/ (judges)   plans/ envs/ datasets/ fixtures/
results/ (gitignored)   references/ baselines/ (reserved)
```

The only file that knows Claude Code's native log format is `core/parse.py`; oracles read the
small dict it emits. A second agent framework = a second parser emitting that same dict + a
`launch-<fw>.sh` — no harness registry until then.

## Requirements

`python3` (stdlib only), `node`/`npx` (for `skills add`), and `claude` on PATH for real runs.
`--dry-run` needs everything except `claude`.
