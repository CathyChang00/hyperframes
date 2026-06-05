# fixtures/assets — input materials (not expected outputs)

Real input files the multimodal cases reference by `asset_id` (see `../assets.registry.jsonl`).

**For routing**, the agent decides the route from the prompt's _surface handle_
(`[attached file: acme-product-onepager.pdf]`) plus the file _type_ — it does not parse file
contents in the 3-turn routing probe. So routing runs even when these files are absent; the
registry name is what reaches the prompt.

Drop the real files in `pdf/` and `image/` (paths per the registry) when:

- you add E2E authoring cases that must actually open them, or
- a routing case starts mis-clarifying because a referent is missing.

Keep them tiny and synthetic. Never commit large binaries to git here — see the top-level
plan for the object-store path when artifacts get big.
