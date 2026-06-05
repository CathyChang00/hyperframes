# references/ — RESERVED (not used by the routing MVP)

`references/golden/` will hold **human-approved exemplar videos** for the E2E
authoring benchmark. Routing has **no golden**: its oracle is "which workflow did
the agent invoke", compared to `expect.route` — there is no video to compare.

Populate this only when the E2E authoring oracle lands. Do not put run outputs here
(those go to `results/`) and do not put input fixtures here (those go to `fixtures/`).
