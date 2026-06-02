---
name: video-workflows
description: >
  Router for all video creation workflows. Use FIRST whenever the user wants to
  make a video — launch video, promo, explainer, tutorial, social ad, testimonial,
  feature reveal, hook reel, motion poster, or any "make me a video / create a /
  generate a video / build a [X] video" intent. Maps the request to the right
  workflow via an INPUT × OUTPUT-length decision table, and asks clarifying
  questions when the intent is under-specified. Always consult before invoking
  a specific workflow.
metadata:
  tags: router, index, video-workflows, intent-routing, disambiguation
---

# Video Workflow Router

The single entry point for "I want to make a video" intent. Routes to the correct workflow based on **INPUT type** and **OUTPUT length**. Asks clarifying questions when the request is under-specified.

This router knows ONLY top-level workflows. It does not load workflow-internal phases, domain skills (`hyperframes-*`), or technical references.

## Decision table

Two axes pick the workflow: **INPUT type** and **OUTPUT length**. Inside the 30-90s row, a third axis decides between the two text-fed workflows — the **subject**: a product being _marketed_ vs a topic being _explained_ (see the disambiguation rule in step 3 below).

| Length / Input  | URL                     | Product brief / script  | Topic / article / notes (no product, no URL) | Existing footage |
| --------------- | ----------------------- | ----------------------- | -------------------------------------------- | ---------------- |
| < 15s hook      | —                       | —                       | —                                            | —                |
| 15-30s ad       | —                       | —                       | —                                            | —                |
| **30-90s**      | `/product-launch-video` | `/product-launch-video` | `/faceless-explainer`                        | —                |
| 2-5min tutorial | —                       | —                       | —                                            | —                |
| 5min+ deep dive | —                       | —                       | —                                            | —                |
| Static / loop   | —                       | —                       | —                                            | —                |

Only the **30-90s** row is covered today — by two workflows split on subject. Empty cells mean **no workflow exists for that combination**: say so directly (the generic / "通用" outcome) rather than forcing a near-fit.

## Routing procedure

1. **Determine INPUT type + target length.** If either is unknown, ask at most 2 clarifying questions:
   - "What's your input — a product URL, a product brief / script, a topic or article to explain, or existing footage?"
   - "Target length — under 30s, 30-90s, 2-5 minutes, or longer?"
2. **Pick the cell.** If length ≠ 30-90s, or input = existing footage, **no workflow exists** → tell the user plainly (the "通用" / none outcome). Do NOT route to a wrong workflow as a fallback.
3. **Disambiguate `/product-launch-video` vs `/faceless-explainer`** — only the 30-90s row, and only when the input is text. The decisive question is **what the video is about**, not the input format:
   - A specific **product / company / SaaS / app / website** is being **marketed, launched, or promoted** — **or any URL is given** → `/product-launch-video`.
   - A **concept / topic / article / how-something-works** is being **explained**, with **no product and no URL** → `/faceless-explainer`.
   - Tie-breakers: a URL always wins for `/product-launch-video` (it scrapes the site). "Promote / launch / sell / our product" wording → PLV. "Explain / teach / how X works / what is X" wording with no product → faceless. The shipped style for faceless is always `pin-and-paper`.
   - Still unclear after reading the request → ask exactly one question: _"Is this promoting a specific product/website, or explaining a topic/concept?"_
4. **Never fake-route.** When nothing matches, say "we don't have a workflow for this yet" — that is the generic ("通用") result, not a reason to pick the closest workflow.

## Workflow descriptions (for disambiguation)

### `/product-launch-video`

- **Input:** Product URL (crawled with headless Chrome for assets, brand tokens, page structure) **OR** a pre-written script / text brief with **no URL** (no-capture mode — you pick a style preset; the preset supplies the palette + design system, scenes are text/typography with no scraped assets)
- **Output:** 60-90s product launch / SaaS explainer / promo video as a HyperFrames composition rendered to MP4
- **Triggers:** "make me a launch video for X", "promo for our website", "explain my SaaS in a minute", "feature reveal for X.com", "marketing video for our product", "I have a script — turn it into a 60s promo", "make a text-only launch video, no website"
- **Do NOT use for:** pure-text explainers about a topic / concept with **no product and no URL** (→ `/faceless-explainer`); tutorials, customer interviews, social ads under 30s, motion graphics without a product context, static brand assets

### `/faceless-explainer`

- **Input:** Arbitrary text — a topic line, an article, notes, or a brief — with **no URL and no product to capture**. Forked from `/product-launch-video`; the input phase needs no website scrape (no headless Chrome for input)
- **Output:** 60-90s faceless explainer video as a HyperFrames composition rendered to MP4. Every visual is LLM-invented per scene (typography / abstract graphics / diagram / data-viz); ships the `pin-and-paper` style preset
- **Triggers:** "make a faceless explainer about X", "explain how DNS works as a video", "turn this article into an explainer video", "video explaining [concept], no product", "topic → short educational video", "explainer from my notes"
- **Do NOT use for:** anything centered on a specific product / company being marketed, or any request that supplies a URL (→ `/product-launch-video`); tutorials over 2 min; social ads under 30s; videos that need real screenshots or scraped brand assets

## Out of scope for this router

- **Domain skills** (`/hyperframes-core`, `/hyperframes-animation`, `/hyperframes-cli`, `/hyperframes-creative`, `/hyperframes-media`, `/hyperframes-registry`) — technical references loaded by a workflow's build phase, not user-triggered through this router.
- **Workflow-internal phases** — phases live inside each workflow's folder and are dispatched by that workflow's orchestrator, not by this router.

## Adding a new workflow

When a new video workflow lands at `skills/<workflow-name>/`:

1. Add a row / cell to the decision table above.
2. Add a description block under "Workflow descriptions" with **Input**, **Output**, **Triggers**, **Do NOT use for**.
3. Update existing workflows' `Do NOT use for` lines to reference the new workflow where appropriate (mutual reverse-edges keep router precision).
4. If two workflows could legitimately match the same cell, refine each one's `Triggers` and `Do NOT use for` until they are mutually exclusive.
