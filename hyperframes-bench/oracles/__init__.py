"""Oracles: pure functions over the parsed-trace dict + a case's `expect` + the env's
installed-skills list. Each returns a small JSON-able verdict dict (always including a
human-readable `note` so an agent consumer can see WHY).

Every oracle has the same signature:  score(parsed, expect, installed, cfg) -> dict
"""
from oracles import route, router_first

REGISTRY = {
    "route": route.score,
    "router_first": router_first.score,
}


def run(names, parsed, expect, installed, cfg):
    out = {}
    for name in names:
        fn = REGISTRY.get(name)
        if fn:
            out[name] = fn(parsed, expect, installed, cfg)
    return out
