"""route oracle — did the agent route to the expected workflow?

verdict ∈ {correct, soft, competitor, miss, unavailable, unparsed, clarify_ok, oos_ok}

  correct     observed workflow == expected (or the agent named it in its conclusion)
  competitor  a competitor skill (remotion / video-use) won the route
  miss        routed to the wrong HF workflow / routed when it should have clarified/declined
  soft        a clear request was met with clarifying questions instead of a route
  clarify_ok  expected "clarify" and the agent asked instead of routing  (correct behaviour)
  oos_ok      expected "out-of-scope" and the agent declined               (correct behaviour)
  unavailable the expected workflow skill is NOT installed in this env (e.g. online main lacks it)
  unparsed    no workflow invoked or named, and no clear question/decline

`unavailable` is deliberately distinct from `miss`: under hf-online (main) most workflows
are not published yet, and that must read as "capability absent", not "agent failed".
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


def _looks_like_question(parsed):
    t = parsed.get("final_text") or ""
    if "?" not in t:
        return False
    tl = t.lower()
    cues = ("could you", "can you", "which ", "what kind", "what sort", "clarify",
            "do you", "would you", "to confirm", "a few questions", "need to know",
            "is this", "are you looking")
    return any(c in tl for c in cues)


def _looks_like_decline(parsed):
    tl = (parsed.get("final_text") or "").lower()
    cues = ("out of scope", "out-of-scope", "not something", "isn't supported",
            "not supported", "no skill", "doesn't cover", "don't have a", "not a fit",
            "won't be able", "can't help with that", "cannot help with that",
            "not the right tool", "beyond what")
    return any(c in tl for c in cues)


def score(parsed, expect, installed, cfg):
    workflows = set(cfg["workflow_skills"])
    expected = expect.get("route")
    route, how = observed_route(parsed, workflows)

    if parsed.get("env_setup_failed"):
        return {"verdict": "unavailable", "observed": None, "how": "env_setup_failed",
                "note": "env template failed to install"}

    # A workflow was expected but is not installed in this env → capability absent.
    if expected in workflows and expected not in set(installed):
        return {"verdict": "unavailable", "observed": route, "how": how,
                "note": f"expected skill '{expected}' not installed in this env"}

    if expected == "clarify":
        if route is None and _looks_like_question(parsed):
            return {"verdict": "clarify_ok", "observed": None, "how": how,
                    "note": "asked a clarifying question instead of routing (expected)"}
        if route is not None:
            return {"verdict": "miss", "observed": route, "how": how,
                    "note": "routed when the request was under-specified"}
        return {"verdict": "unparsed", "observed": None, "how": how,
                "note": "no route and no clear clarifying question"}

    if expected == "out-of-scope":
        if route is None and _looks_like_decline(parsed):
            return {"verdict": "oos_ok", "observed": None, "how": how,
                    "note": "declined / flagged out of scope (expected)"}
        if route is not None:
            return {"verdict": "miss", "observed": route, "how": how,
                    "note": "routed an out-of-scope request"}
        return {"verdict": "unparsed", "observed": None, "how": how,
                "note": "no route and no clear decline"}

    # expected is a concrete workflow
    if route is None:
        if _looks_like_question(parsed):
            return {"verdict": "soft", "observed": None, "how": how,
                    "note": "clarified instead of routing a clear request"}
        return {"verdict": "unparsed", "observed": None, "how": how,
                "note": "no workflow invoked or named"}
    if how == "competitor":
        return {"verdict": "competitor", "observed": route, "how": how,
                "note": "a competitor skill won the route"}
    if route == expected:
        return {"verdict": "correct", "observed": route, "how": how, "note": ""}
    return {"verdict": "miss", "observed": route, "how": how,
            "note": f"routed to {route}, expected {expected}"}
