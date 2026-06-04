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

| Length / Input  | Product URL             | GitHub PR / code change | Product brief / script  | Topic / article / notes (no product, no URL) | Existing footage |
| --------------- | ----------------------- | ----------------------- | ----------------------- | -------------------------------------------- | ---------------- |
| < 15s hook      | —                       | —                       | —                       | —                                            | —                |
| 15-30s ad       | —                       | —                       | —                       | —                                            | `/footage-recut` |
| **30-90s**      | `/product-launch-video` | `/pr-to-video`          | `/product-launch-video` | `/faceless-explainer`                        | `/footage-recut` |
| 2-5min tutorial | —                       | —                       | —                       | —                                            | `/footage-recut` |
| 5min+ deep dive | —                       | —                       | —                       | —                                            | `/footage-recut` |
| Static / loop   | —                       | —                       | —                       | —                                            | —                |

Coverage today: the **30-90s** row is covered for **Product URL / GitHub PR / brief / topic** inputs (a URL splits by _kind_ — see step 3), and the **Existing footage** column is covered at **any length** by `/footage-recut` (input-type-first — see step 2). **Every remaining cell falls back to `/general-video`** — the general HTML-composition authoring flow (input- and length-agnostic). The router does not dead-end on a creatable video; the only true "通用 / none" answer is a request outside HyperFrames itself (e.g. NLE-style editing of a finished video file).

## Migrating an existing composition (special case)

The table above is for **creating** a video from an input. One workflow sits outside it: if the user explicitly asks to **port / convert / migrate an existing Remotion (React) composition** into HyperFrames → `/remotion-to-hyperframes`. This is source translation, not creation-from-input, so it has no INPUT × LENGTH cell. Route here ONLY on explicit migration language ("port my Remotion project", "convert this Remotion comp", "rewrite this as HyperFrames") — a passing mention of Remotion is not a trigger; default to the creation table or `/hyperframes-core`.

## Routing procedure

1. **Determine INPUT type + target length.** If either is unknown, ask at most 2 clarifying questions:
   - "What's your input — a product URL, a GitHub PR / code change, a product brief / script, a topic or article to explain, or existing video footage?"
   - "Target length — under 30s, 30-90s, 2-5 minutes, or longer?"
2. **Pick by INPUT type first, then length.** Two inputs short-circuit the length axis:
   - **Existing video footage** (the user has a video to re-edit / repurpose) → `/footage-recut`, at **any length** (input type wins over length here).
   - **GitHub PR / code change** (a `github.com/<owner>/<repo>/pull/<N>` link, an `owner/repo#N` ref, or "this PR") → `/pr-to-video` (30-90s).
   - **Otherwise** (product URL / brief / topic text): only the **30-90s** row is covered → if length ≠ 30-90s, **no workflow exists** → tell the user plainly (the "通用" / none outcome). Do NOT route to a wrong workflow as a fallback.
3. **Disambiguate the 30-90s URL / text inputs.** Two splits:
   - **URL kind** — a URL no longer auto-wins for PLV; its _kind_ decides: a **GitHub PR** link (`.../pull/<N>`, `owner/repo#N`, "this PR") → `/pr-to-video`; any **other product / marketing website** URL → `/product-launch-video`. (Only product-site URLs get scraped with headless Chrome; PR URLs are read via `gh`.)
   - **Product vs topic** (text, no URL) — the decisive question is **what the video is about**, not the input format:
     - A specific **product / company / SaaS / app / website** being **marketed, launched, or promoted** → `/product-launch-video`.
     - A **concept / topic / article / how-something-works** being **explained**, with **no product and no URL** → `/faceless-explainer`.
     - Tie-breakers: "Promote / launch / sell / our product" wording → PLV. "Explain / teach / how X works / what is X" with no product → faceless. The shipped style for faceless is always `pin-and-paper`.
   - Still unclear after reading the request → ask exactly one question: _"Is this promoting a specific product/website, explaining a topic/concept, walking through a GitHub PR, or re-editing existing footage?"_
4. **Fall back to `/general-video`.** When no specialized workflow above matches, route to `/general-video` — the general HTML-composition authoring flow (the original `hyperframes` flow: design system → plan → layout-before-animation → build → validate), which is input- and length-agnostic. Do **not** _fake-route_ into a specialized workflow (don't force a tutorial into PLV); `/general-video` is the correct general home, not a near-fit. The only genuine "no workflow / 通用" answer is a request outside HyperFrames itself — e.g. NLE-style cutting/editing of a finished video file (existing-footage _recut with overlays_ is `/footage-recut`).

## Workflow descriptions (for disambiguation)

### `/product-launch-video`

- **Input:** Product URL (crawled with headless Chrome for assets, brand tokens, page structure) **OR** a pre-written script / text brief with **no URL** (no-capture mode — you pick a style preset; the preset supplies the palette + design system, scenes are text/typography with no scraped assets)
- **Output:** 60-90s product launch / SaaS explainer / promo video as a HyperFrames composition rendered to MP4
- **Triggers:** "make me a launch video for X", "promo for our website", "explain my SaaS in a minute", "feature reveal for X.com", "marketing video for our product", "I have a script — turn it into a 60s promo", "make a text-only launch video, no website"
- **Do NOT use for:** pure-text explainers about a topic / concept with **no product and no URL** (→ `/faceless-explainer`); a GitHub PR / code-change explainer (→ `/pr-to-video`); re-editing existing video footage (→ `/footage-recut`); tutorials, customer interviews, social ads under 30s, motion graphics without a product context, static brand assets

### `/faceless-explainer`

- **Input:** Arbitrary text — a topic line, an article, notes, or a brief — with **no URL and no product to capture**. Forked from `/product-launch-video`; the input phase needs no website scrape (no headless Chrome for input)
- **Output:** 60-90s faceless explainer video as a HyperFrames composition rendered to MP4. Every visual is LLM-invented per scene (typography / abstract graphics / diagram / data-viz); ships the `pin-and-paper` style preset
- **Triggers:** "make a faceless explainer about X", "explain how DNS works as a video", "turn this article into an explainer video", "video explaining [concept], no product", "topic → short educational video", "explainer from my notes"
- **Do NOT use for:** anything centered on a specific product / company being marketed (→ `/product-launch-video`); a request that supplies a URL — a product site (→ `/product-launch-video`) or a GitHub PR (→ `/pr-to-video`); re-editing existing video footage (→ `/footage-recut`); tutorials over 2 min; social ads under 30s; videos that need real screenshots or scraped brand assets

### `/footage-recut`

- **Input:** An existing **local video file** (MP4, any aspect / duration / fps) the user wants re-edited / repurposed — actual footage, not a URL or a text brief. Ingested with the `vtake` CLI (extract + transcribe); no website scrape, no headless Chrome.
- **Output:** The same footage re-rendered with transcript-synced, AI-designed HTML info-card overlays (the source video plays as a background layer). **Any length** — short reel to hour-long talk.
- **Triggers:** "recut my webinar/talk/podcast into a card video", "repurpose this recording", "add info cards / annotations to my video", "turn my screen recording into a styled edit", "二次剪辑这段视频", "给我的录像叠卡片重剪"
- **Do NOT use for:** generating a video from a URL (→ `/product-launch-video`); generating from a topic / article / text with no source footage (→ `/faceless-explainer`); a GitHub PR (→ `/pr-to-video`); a request with no existing video to transform

### `/pr-to-video`

- **Input:** A **GitHub pull request** — a code change, given as a PR URL (`github.com/<owner>/<repo>/pull/<N>`), an `owner/repo#N` ref, or "this PR" in a checked-out repo. A URL, but a **PR link** read via the `gh` CLI — NOT a marketing site to scrape.
- **Output:** 30-90s code-change explainer (changelog / feature-reveal / fix-explainer / refactor-walkthrough) — diff highlights, before/after, file-tree and impact scenes
- **Triggers:** "make a video about this PR", "turn PR #1187 into a changelog video", "explain what this pull request does as a video", "release-notes video from github.com/org/repo/pull/123", "把这个 PR 做成视频"
- **Do NOT use for:** a product / marketing website URL (→ `/product-launch-video`); a topic / article / text with no PR (→ `/faceless-explainer`); existing video footage (→ `/footage-recut`); a whole-repo tour or multi-PR release (no workflow yet → 通用)

### `/remotion-to-hyperframes`

- **Input:** An existing **Remotion** (React) video composition's source — the user explicitly asks to port / convert / migrate / rewrite it as HyperFrames. This is NOT a creation-from-input workflow.
- **Output:** A HyperFrames HTML composition translated from the Remotion source, graded against the Remotion render with an SSIM eval harness + tiered test corpus
- **Triggers:** "port my Remotion project to HyperFrames", "convert this Remotion comp", "migrate from Remotion", "rewrite this as HyperFrames HTML"
- **Do NOT use for:** authoring a NEW composition (even while A/B-testing a Remotion video), a passing mention of Remotion, or "the same video as my Remotion one" without an explicit migrate request (→ creation workflows / `/hyperframes-core`)

### `/general-video`

- **Input:** Anything not handled above — a creative brief, a single element to animate, an edit to a composition you're building. Input- and length-agnostic.
- **Output:** A HyperFrames HTML composition (any length / format) authored with the original `hyperframes` flow: design system → prompt expansion → plan → layout-before-animation → build (delegating to the `hyperframes-*` domain skills) → validate.
- **Triggers:** "make a title card / lower third / logo reveal", "animate this", "a 10s kinetic-type intro", "a data / stat montage", "a brand montage, no narration", "a motion poster / static loop", or any "make a video" that doesn't fit the workflows above.
- **Do NOT use for:** a marketed product / site (→ `/product-launch-video`); a topic / concept explainer (→ `/faceless-explainer`); a GitHub PR (→ `/pr-to-video`); recutting an existing video file (→ `/footage-recut`); porting Remotion (→ `/remotion-to-hyperframes`); NLE-style editing of a finished video (out of scope).

## Out of scope for this router

- **Domain skills** (`/hyperframes-core`, `/hyperframes-animation`, `/hyperframes-cli`, `/hyperframes-creative`, `/hyperframes-media`, `/hyperframes-registry`) — technical references loaded by a workflow's build phase, not user-triggered through this router.
- **Workflow-internal phases** — phases live inside each workflow's folder and are dispatched by that workflow's orchestrator, not by this router.

## Adding a new workflow

When a new video workflow lands at `skills/<workflow-name>/`:

1. Add a row / cell to the decision table above.
2. Add a description block under "Workflow descriptions" with **Input**, **Output**, **Triggers**, **Do NOT use for**.
3. Update existing workflows' `Do NOT use for` lines to reference the new workflow where appropriate (mutual reverse-edges keep router precision).
4. If two workflows could legitimately match the same cell, refine each one's `Triggers` and `Do NOT use for` until they are mutually exclusive.
