# baselines/ — RESERVED (not used by the routing MVP yet)

A baseline is a **frozen `results.jsonl` from a known-good system version**, used to
answer "did my skill edit regress routing?" via `bench diff`.

Add this after the first clean `bench run` you trust: freeze its `results.jsonl`
here, then implement `bench diff <run> <baseline>`. Commit only the manifest/jsonl,
never large artifacts.
