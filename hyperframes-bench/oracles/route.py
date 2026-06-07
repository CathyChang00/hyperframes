"""route oracle — did the agent route to the expected workflow?

verdict ∈ {correct, asked_ok, soft, competitor, miss, unavailable, unparsed, inline, clarify_ok, oos_ok}

  correct     observed workflow == expected (invoked the Skill, or named it AFFIRMATIVELY)
  asked_ok    in-scope request whose referenced input was NOT supplied, and the agent asked for
              it instead of routing — correct behaviour (per project rule: asking for a missing
              input counts as correct; no need to pre-stage the asset). Counted as good.
  competitor  a competitor skill (remotion / video-use) won the route
  miss        a real routing failure. The kind is recorded in `kind`:
                overreach      — reached for a HF workflow on an out-of-scope request
                wrong_workflow — in-scope, but routed to the WRONG HF workflow
                premature      — routed when the request was under-specified (should clarify)
                refused        — declined a request it should have handled
  soft        a clear request was met with clarifying questions instead of a route
  clarify_ok  expected "clarify" and the agent asked instead of routing  (correct behaviour)
  oos_ok      expected "out-of-scope" and the agent did NOT pull in a HF workflow (correct) —
              declined, redirected, asked for the file, or handled it outside HyperFrames
  unavailable the expected workflow skill is NOT installed in this env (e.g. online main lacks it)
  inline      no workflow routed, but the agent BUILT the composition itself (Write/Edit) —
              it did the task without the router. A routing outcome we don't grade, not a fail.
  unparsed    no route, no build, and no clear question/decline — the oracle could NOT read a
              decision (headless denies AskUserQuestion; novel phrasing). A MEASUREMENT GAP,
              not an agent failure → excluded from accuracy. A rising rate = fix the oracle.

`unavailable`/`inline`/`unparsed` are deliberately distinct from `miss`: they are "no fair
routing decision observed" (capability absent / did-it-inline / oracle-blind), and must read
as that — NOT as "the agent failed". Only `miss` (+`competitor`) is a real routing failure.

A NAMED-but-not-invoked workflow is a WEAK signal: agents name a workflow to DECLINE it
("remotion-to-hyperframes is for Remotion, not .aep") or mention one while asking for a file.
So a `named` route is demoted to no-route when the text is a decline, or a non-committal
question — only an affirmative naming ("I'd use X", "I'll run X") survives. See `_affirmative_route`.
"""

_COMPETITOR_HINTS = ("remotion", "video-use", "browser-use")


def _is_competitor(skill):
    s = skill.lower()
    return any(h in s for h in _COMPETITOR_HINTS)


def observed_route(parsed, workflows):
    """Return (route, how). how ∈ {invoked, competitor, named, none}."""
    for s in parsed.get("skills_invoked", []):
        if s in workflows:
            return s, "invoked"
        if _is_competitor(s):
            return s, "competitor"
    text = (parsed.get("final_text") or "").lower()
    named = [w for w in workflows if w in text]
    if len(named) == 1:
        return named[0], "named"
    return None, "none"


import re as _re


def _looks_like_question(parsed):
    t = parsed.get("final_text") or ""
    if "?" not in t:
        return False
    tl = t.lower()
    cues = ("could you", "can you", "which ", "what kind", "what sort", "clarify",
            "do you", "would you", "to confirm", "a few questions", "need to know",
            "is this", "are you looking",
            # broadened 2026-06-05: common "ask for the missing input" phrasings the
            # original list missed (e.g. "What's the channel name?"), which inflated `unparsed`.
            "what's the", "whats the", "what is the", "where's the", "where is the",
            "where should", "please share", "please paste", "please provide", "provide the",
            "could you provide", "could you share", "could you paste", "i'll need", "ill need",
            "before i can", "path to", "send me", "let me know", "tell me")
    return any(c in tl for c in cues)


def _looks_like_decline(parsed):
    tl = (parsed.get("final_text") or "").lower()
    cues = ("out of scope", "out-of-scope", "not something", "isn't supported",
            "not supported", "no skill", "doesn't cover", "don't have a", "not a fit",
            "won't be able", "can't help with that", "cannot help with that",
            "not the right tool", "beyond what",
            # broadened 2026-06-05: explicit refusals the original list missed.
            "i can't", "i cannot", "i'm unable", "im unable", "unable to", "not able to",
            "isn't something", "not within", "outside the scope", "out of the scope",
            "no way to", "there's no workflow", "there is no workflow", "no workflow that",
            "not a video", "isn't a video",
            # broadened 2026-06-06: decline-by-redirect to an external NLE, and the
            # "outside what my (available) tools can do" phrasing the agent uses for footage
            # edits the overlay-only workflow can't perform. Caught a clean decline that named
            # a workflow ("the footage-recut skill only overlays … it cannot re-time") and was
            # therefore mis-read as a route.
            "outside what", "nle-style", "nle editing", "dedicated video editor",
            "a video editor", "use a dedicated", "would need a", "you'd need a")
    return any(c in tl for c in cues)


# Affirmative commitment to RUN a named workflow — distinguishes "I'd use footage-recut, give
# me the file" (a real route intent) from "footage-recut is the closest match, but..." (a
# decline that merely names the skill) and incidental mentions. Used only to RESCUE a `named`
# route from being dropped; a decline cue always wins over these (see score()).
_AFFIRMATIVE = (
    "i'd use", "i'll use", "i will use", "let me use", "let's use",
    "i'd run", "i'll run", "i will run", "run it through",
    "i'd reach for", "i'll reach for",
    "i'd route", "i'll route", "route to the", "routing to",
    "i'd invoke", "i'll invoke", "i will invoke",
    "i'd go with", "i'll go with", "go with the",
    "i'd kick", "i'll kick", "kick it off", "kick off the",
    "i'd pick", "i'll pick", "i'd spin up", "i'll spin up",
    "best fit is", "the right workflow",
)


def _affirmative_route(parsed):
    tl = (parsed.get("final_text") or "").lower()
    return any(c in tl for c in _AFFIRMATIVE)


# A3 (2026-06-05): heuristic artifact detector. Many bench prompts reference a user asset
# ("my video / my blog post / this song") the harness never actually supplies, so the agent
# correctly asks for it instead of routing. Flagging this lets aggregate + the dashboard
# separate "harness didn't provide the input" from a real routing miss. Only meaningful when
# NO route was taken — a workflow that routed AND asked for the file made a real routing
# decision and must NOT be discounted (that's the 13 OOS false-positives, kept as misses).
_MISSING_INPUT = _re.compile(
    r"(what'?s the|provide the|paste|file path|path to|share the|do you have|"
    r"where (is|should)|could you (paste|provide|share)|channel name|"
    r"need .{0,30}(path|file|text|url)|don'?t see|didn'?t include|"
    r"isn'?t (in|attached)|no .{0,20}(file|clip) )", _re.I)


def _asks_for_missing_input(route, parsed, expected):
    # Only a (harness) artifact when supplying the asset would let the agent route correctly —
    # i.e. the request maps to a workflow (or clarify). For an out-of-scope request the right
    # answer is "no" regardless of the asset, so asking for the file is a REAL failure-to-decline,
    # not an artifact; don't flag it.
    if expected == "out-of-scope" or route is not None:
        return False
    return bool(_MISSING_INPUT.search(parsed.get("final_text") or ""))


def _response(route, parsed):
    """Behaviour-derived scope decision: did the agent accept (route a workflow), ask, or
    decline? Independent of WHICH workflow and of the verdict — this is the axis Bin's
    confusion matrix needs (so a doable request that's flatly declined reads as 'refuse')."""
    if route is not None:
        return "accept"
    # a real AskUserQuestion tool call is a stronger clarify signal than a regex on final_text
    # (headless denies the tool, so the question often isn't in the trailing message).
    if "AskUserQuestion" in (parsed.get("tools_used") or []):
        return "clarify"
    if _looks_like_question(parsed):
        return "clarify"
    if _looks_like_decline(parsed):
        return "refuse"
    return "none"


def score(parsed, expect, installed, cfg):
    workflows = set(cfg["workflow_skills"])
    expected = expect.get("route")
    route, how = observed_route(parsed, workflows)

    # Text-derived signals, computed independently of `route` so we can use them to gate a
    # weak `named` route. A real AskUserQuestion tool call is the strongest clarify signal
    # (headless denies it, so the question often isn't in the trailing message).
    asked = ("AskUserQuestion" in (parsed.get("tools_used") or [])) or _looks_like_question(parsed)
    declined = _looks_like_decline(parsed)

    # R1: demote a NAMED-but-not-invoked workflow that is buried in a decline ("X is for
    # Remotion, not .aep") or a non-committal question — the name is incidental, not a route.
    # An invoked Skill (a real tool call) or an affirmative naming ("I'd use X") survives.
    if how == "named" and (declined or (asked and not _affirmative_route(parsed))):
        route, how = None, "none"

    response = _response(route, parsed)
    ami = _asks_for_missing_input(route, parsed, expected)
    # R3: with no route, did the agent just BUILD the composition itself? (did the task inline)
    built_inline = route is None and any(
        t in (parsed.get("tools_used") or []) for t in ("Write", "Edit", "MultiEdit"))

    def out(verdict, observed, note, kind=None):
        d = {"verdict": verdict, "observed": observed, "how": how,
             "response": response, "asked_for_missing_input": ami, "note": note}
        if kind:
            d["kind"] = kind          # R2: which KIND of miss (overreach / wrong_workflow / …)
        return d

    if parsed.get("env_setup_failed"):
        return out("unavailable", None, "env template failed to install")

    # A workflow was expected but is not installed in this env → capability absent.
    if expected in workflows and expected not in set(installed):
        return out("unavailable", route, f"expected skill '{expected}' not installed in this env")

    if expected == "clarify":
        # A genuine AskUserQuestion tool call IS the expected behaviour for an under-specified
        # request — credit it even if the agent also loaded a workflow Skill to see what it needs.
        # Headless denies the tool, so its presence in the trace means the agent really tried to
        # ask the user before committing; that is the right move, not a premature route.
        asked_q = "AskUserQuestion" in (parsed.get("tools_used") or [])
        if asked_q or (route is None and (response == "clarify" or ami)):
            return out("clarify_ok", route, "asked a clarifying question instead of committing (expected)")
        if route is not None:
            return out("miss", route, "routed when the request was under-specified", kind="premature")
        if built_inline:
            return out("inline", None, "built inline on an under-specified request (no route, no ask)")
        return out("unparsed", None, "no route and no clear clarifying question")

    if expected == "out-of-scope":
        # Project scoring rule: an out-of-scope request is handled CORRECTLY as long as the agent
        # did NOT pull in a HyperFrames workflow to do it. Declining, redirecting, asking for the
        # file, or reaching for other tools (ffmpeg, etc.) all count as ok — the ONLY failure is
        # grabbing a HF workflow for a task HyperFrames can't serve (invoked or affirmatively named).
        if route is not None:
            return out("miss", route, "reached for a HyperFrames workflow on an out-of-scope request",
                       kind="overreach")
        return out("oos_ok", None, "did not pull in a HyperFrames workflow (correct)")

    # expected is a concrete workflow
    if route is None:
        if ami:
            # the prompt referenced an input the bench never supplied; asking for it is the
            # correct move (project rule: no need to pre-stage the asset — asking counts).
            return out("asked_ok", None, "asked for the missing input the prompt referenced but never supplied (correct)")
        if response == "clarify":
            return out("soft", None, "clarified instead of routing a clear request")
        if response == "refuse":
            return out("miss", None, "declined a request it should handle", kind="refused")
        if built_inline:
            return out("inline", None, "built the composition inline without invoking a workflow")
        return out("unparsed", None, "no workflow invoked or named")
    if how == "competitor":
        return out("competitor", route, "a competitor skill won the route")
    if route == expected:
        return out("correct", route, "")
    return out("miss", route, f"routed to {route}, expected {expected}", kind="wrong_workflow")
