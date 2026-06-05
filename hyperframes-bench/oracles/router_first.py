"""router_first oracle — was `hyperframes-read-first` the FIRST skill invoked?

Most informative under collision envs: with competitor skills present, does the agent
still enter through the HyperFrames router before choosing a workflow?

Returns router_first ∈ {True, False, None}. None = the router skill isn't installed in
this env (so the question is moot — e.g. hf-online main has no router yet).
"""


def score(parsed, expect, installed, cfg):
    router = cfg.get("router_skill", "hyperframes-read-first")
    names = {router, *cfg.get("router_aliases", [])}
    installed = set(installed)

    if not (names & installed):
        return {"router_first": None, "first_skill": parsed.get("first_skill"),
                "note": "router skill not installed in this env"}

    first = parsed.get("first_skill")
    ok = first in names
    return {"router_first": ok, "first_skill": first,
            "note": "" if ok else f"first skill was {first!r}, not the router"}
