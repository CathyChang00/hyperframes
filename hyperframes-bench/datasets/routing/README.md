# dataset: routing

**Contract for "did the agent route the user's request to the right workflow?"** One case
per line in `cases.jsonl`. This is the source of truth — nothing here is generated.

## Case shape

```json
{
  "id": "cand-p42",
  "category": "A-direct",
  "tags": [],
  "intent": "make-a-video",
  "inputs": [
    {
      "type": "text",
      "value": "Make a changelog video for github.com/tailwindlabs/tailwindcss/pull/12345"
    }
  ],
  "expect": { "route": "pr-to-video", "intent": "make-a-video" },
  "notes": "A GitHub PR URL with changelog intent → pr-to-video. [evidence: …]"
}
```

The current dataset (built from the `candidates.*.jsonl` proposal pools) authors each case as a
**single inline `text` input** — URLs and attachment mentions live in the prose, so the rendered
prompt equals the case text verbatim. The contract below is richer than that and still supported:

- `inputs[].type` ∈ `text | link | pdf | image | video`, **freely combined**. The prompt the
  agent receives is `inputs` rendered to surface text at run time (link → the URL, pdf/image →
  `[attached file: <name>]`). For routing only the _handle_ matters, not file contents.
- `pdf/image/video` reference a fixture by `asset_id` (see `../../fixtures/assets.registry.jsonl`),
  not a hard path.
- `expect.route` is one of the workflows, or `clarify` / `out-of-scope` (see `taxonomy.json`).
- `oracles` is optional; default is `["route", "router_first", "intent"]`.

## Add or edit a case

1. Add/edit a line in `cases.jsonl`.
2. Re-run — that's it. The cell cache is **content-addressed** (keyed on the rendered prompt +
   env + model), so an edited case re-runs automatically. No manual cache-busting.

## Authoring guidance

Direct (A) cases are a floor; the signal is in **C-adversarial**, **D-clarify**, **E-oos**, and
**G-multimodal**. When adding cases, add decoys and boundaries, not more textbook phrasings.
Always write `notes` explaining _why_ the expected route is correct — it's the rubric for the
next person and the place a wrong `expect` gets caught.
