"""intent oracle — chat / make-a-video / render.

Secondary for the routing dataset (every routing case is `make-a-video`), included
because cases carry an `intent` and an agent consumer may want to slice on it. The
discriminating cases (render / chat / edit) live in a future `intent` dataset.

  make-a-video : a workflow or the router was invoked
  render       : hyperframes-cli invoked, or a render/export command surfaced
  chat         : no skill invoked and the agent answered in prose
"""

_RENDER_CUES = ("hyperframes render", "npm run render", "hyperframes export", " render ")


def _has_render_signal(parsed):
    blob = " ".join(parsed.get("texts", [])).lower()
    return any(c in blob for c in _RENDER_CUES)


def score(parsed, expect, installed, cfg):
    expected = expect.get("intent")
    workflows = set(cfg["workflow_skills"]) | {cfg.get("router_skill"), *cfg.get("router_aliases", [])}
    skills = parsed.get("skills_invoked", [])

    if "hyperframes-cli" in skills or _has_render_signal(parsed):
        observed = "render"
    elif any(s in workflows for s in skills):
        observed = "make-a-video"
    elif not skills:
        observed = "chat"
    else:
        observed = "make-a-video"

    return {"intent": observed, "expected": expected,
            "match": (expected is None or observed == expected),
            "note": "" if expected in (None, observed) else f"observed {observed}, expected {expected}"}
