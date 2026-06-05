---
name: embedded-captions
description: Add captions to a talking-head video in TWO tracks — a clean lower-third RAIL (standard readable subtitle; the default that carries most text) plus selective EMBED moments where a peak phrase / climax is composited INTO the scene behind the subject (matte occlusion + mix-blend). Most explainer / 口播 text stays on the rail; only peaks are embedded — embedding everything is wrong for most talking-head content. Use when the user asks for "captions / 字幕", "embed/embedded/cinematic captions", "字幕嵌入/嵌到场景里", "captions behind the subject", or similar. Pipeline: transcription → RVM matting → hyperframes HTML render → ffmpeg overlay. Requires hyperframes (github.com/heygen-com/hyperframes) and a single-subject clip.
metadata:
  tags: captions, embedded-captions, occlusion, matting, talking-head, rvm, whisper, ffmpeg, cinematic
---

# Embedded Captions

**Two presentation tracks:** a clean **rail** (standard lower-third subtitle — the default workhorse that carries most text) and selective **embed** moments where a peak phrase is composited *into* the scene behind the subject (matte occlusion + blend). Most text rides the rail; **embed is the scarce, earned hero treatment** — not the default for every word. (Authoring has two *modes* — **template** vs **custom** — which is orthogonal to the track.)

---

## Operational flow (TL;DR)

The craft prose below is long; the **pipeline itself is short**:

1. **Decision gate** (refuse bad clips) → **pick mode** (template vs custom)
2. `hyperframes init` → `matte.cjs` (subject matte) → `transcribe.cjs` (words)
3. **author**: template → write `plan.json` → `make-composition.cjs`; custom → hand-write `index.html`
4. `render-and-composite.sh` → `final.mp4`

Load-bearing rules people miss:

- **Two tracks: rail (default) + embed (promotion).** Render states are `drop` / `rail` / `embed`. **rail = clean lower-third subtitle, carries most text; embed = behind-the-subject hero, reserved for peaks.** Default is **rail-first** — for explainer / 口播, usually the whole clip is rail with only the climax(es) embedded. See **§ Caption model**.
- **The video is delivered UNTOUCHED** — captions are the only thing added; the matte just lets the subject occlude the embed track. Never grade/recolor/scanline the footage.
- Scripts auto-resolve `source.mp4` and the source's **native fps**; transcription uses hyperframes' **Whisper** (no API key) and falls back to an existing transcript.
- Two rulebooks: **rail → [references/rail.md](references/rail.md)** (thin), **embed craft → [references/composition-craft.md](references/composition-craft.md)** (rich, embed-only). Skim by need.

---

## Caption model — two tracks

Every spoken phrase resolves to one of **three render states**:

| State | What it is | How it's shown |
|---|---|---|
| **drop** | filler — um/uh, exact stutters, self-corrections | not shown |
| **rail** | the default — ordinary spoken content | clean lower-third subtitle, in front, readable → [references/rail.md](references/rail.md). Flag `emphasis` = active-word highlight (colour/weight) |
| **embed** | a promoted peak | composited INTO the scene behind the subject (matte occlusion + blend, hero typography) → [references/composition-craft.md](references/composition-craft.md). Flag `apex` = the single biggest embed |

**rail is the default; embed is a promotion you have to earn.** For an explainer / 口播 video the right output is usually *the whole transcript on the rail* with **only the climax(es) embedded** — embedding every word is wrong for most talking-head content.

**Role is the selection input, not a render type.** Read the transcript and grade each phrase coarsely → that picks the state:

- **drop** → drop
- **normal** (ordinary content) → rail
- **emphasis** (the 1–2 punch words in a phrase) → rail + `emphasis` highlight
- **peak** (the payoff of a beat/section) → **promote to embed**

**Embed scarcity (the discipline):** **≤1 embed per sentence/beat, never two adjacent or co-visible, spaced ≥ a beat apart, at most one `apex` size.** A short clip → usually one embed (its climax). A long/multi-section explainer → ~one per section. Count follows rhythm + structure — **not** a fixed "one climax per clip."

> This replaces the old 5-role render taxonomy (drop/narrator/body/emphasis/climax) and the bg/fg/hybrid layer axis: **rail** subsumes old fg/announce, **embed** subsumes bg/in-scene, and old "hybrid" is just rail + embed coexisting (the normal state).

---

## Step 0 — pick the authoring mode

| Mode | When | What agent does | Output consistency |
|---|---|---|---|
| **template** | User named a template **OR** wants something off-the-shelf, OR just says "add captions" with no design direction | Decide layout via `cinematic-cream`'s DNA (planes, per-group typography, block-sync accumulation), write minimal `plan.json`, compile, render | High — predictable family of looks |
| **custom** | User says "be creative" / "越酷炫越好" / "make it wow" / gives a specific reference / scene has a unique element no template addresses | **Throw out template architecture entirely.** Design a one-off composition directly in HTML — no plan.json, no planes/groups/tone, no checker, no DNA constraint. Invent visual + motion vocabulary per scene. | Per-scene unique, "wow" bar |

Default for ambiguous input: ask once. If the user is in a hurry or
default-ish, pick `template > champion` for landscape, `portrait-header` for 9:16.

**The mode determines which directory the agent works in:**
- Template mode → [modes/template/](modes/template/) — `template.html` + `spec.md` per template
- Custom mode → [modes/custom/](modes/custom/) — `skeleton.html` + `examples/`

**Mode ≠ track.** Mode is *how you author* (template DNA vs hand-written HTML); track (§ Caption model) is *how each caption is presented* (rail vs embed). The shipped templates are **embed-track DNA** — a rail-first explainer mostly rides the rail spec and promotes only the climax into a template/custom embed.

---

## Decision gate — RUN FIRST

Probe the video and classify the scene before either mode.

```bash
ffprobe <video.mp4>                    # specs
ffmpeg -ss <t> -i <video.mp4> -vframes 1 sample.png   # at 20/50/80%
```

Read the samples. Refuse if:
- Multiple speakers / hard cuts (split & render each shot, or refuse)
- No human subject (this skill is for talking-head)
- Under 3 seconds, no speech, or face never clearly visible
- Busy handheld with fast motion (matte flickers)

### Pre-flight probes (cost nothing, prevent the worst failures)

1. **Shot-cut probe.** Sample frames at 20%, 50%, 80%. If a different subject/scene appears, **trim the clip** before the cut.
2. **Letterbox / pillarbox probe.** Black bars on the first frame? Compute safe content rect and constrain caption placement inside it.
3. **Luminance probe.** Sample the caption region's average luminance — `<60` → screen blend, `60-180` → overlay, `>180` → normal+opaque. (Templates have defaults; custom-mode you decide.)
4. **Track default by tone.** Classify the content: **explainer / keynote / interview / 口播 → rail-first** (whole clip on the rail; embed only the climax(es)). **poetic / social / music-video / showcase → embed-heavy** is fine. When unsure, default **rail-first** — embedding everything is the more common mistake.

---

## Pipeline — 6 steps

```
1. hyperframes init <project> --non-interactive --video <video.mp4> --skip-skills
2. node scripts/matte.cjs <project>            # → frames_fg/*.png (RVM matte, onnxruntime-node)
3. node scripts/transcribe.cjs <project>       # → transcript.json (Whisper, our schema)
4. [AGENT STEP] mode-dependent — see below
5. (template mode only) node scripts/make-composition.cjs <project>
6. bash scripts/render-and-composite.sh <project>  # → final.mp4 + history/ snapshot
```

Step 4 differs by mode:

### Step 4 — template mode

1. Pick template (user-specified or pick from [modes/template/README.md](modes/template/README.md) catalog by scene fit)
2. Read its `spec.md` for required layout decisions
3. Write `<project>/plan.json` with:
   - `template`, `duration`, `fps`, `width`, `height`
   - Layout fields per template's spec (plane geometry, font_scale, crown placement)
   - `groups[]` — caption groups with `slot` + `tone` + `in/out` + `words`
4. Step 5 compiles plan.json → index.html via the template's `template.html`

### Step 4 — custom mode

**READ [modes/custom/README.md](modes/custom/README.md) FIRST AND IN FULL** before writing a single tag. The README explicitly lists what to drop at the door (planes, groups, tone, plan.json, the checker, the DNA constraints, the soft/present motion vocabulary) and gives wild-ideas starting points. Skipping it = falling back into template muscle memory.

The short version:
1. Probe the scene (frames at 20/50/80%, semantic arc, audio shape).
2. **State the visual concept in one sentence.** ("This climax should feel like a Polaroid develops from white." "The narrator voice is hand-scrawled in the margin." "Each word is a glitch shard that resolves into the next.") If you can't, you don't have a design — you'll regress to template mode. Don't proceed without a sharp concept.
3. **Skip `plan.json` entirely.** No checker runs in custom mode. No `make-composition.cjs`. The HTML is the artifact.
4. Read `modes/custom/skeleton.html` for the FOUR-element pipeline contract (root + a-roll video + #stage + a-roll-audio + GSAP `__timelines["main"]`). Beyond that contract, design freely.
5. **Read `examples/` adversarially, NOT as a template.** Those files crystallized into `cinematic-cream`. If your custom render reuses their `.plane` / `.cap-N` / soft-present vocabulary, you're back in template mode by accident.
6. Write `<project>/index.html` from scratch. Name elements after the visual idea (`.polaroid-flash`, `.brand-stamp`, `.glitch-shard`), not after slots.
7. Render: `bash scripts/render-and-composite.sh <project>` — render-and-composite.sh detects no plan.json and skips the timing + occlusion gates automatically.

The bar is **"wow"** — not "tasteful template render with extra grain." If your output looks like cinematic-cream with one new layer, you have not entered custom mode. Redesign.

---

## Catalog of shipped templates

| Template | Frame | Look | Spec |
|---|---|---|---|
| cinematic-cream | 16:9 + 9:16 (DNA-only) | DNA-only: Inter + soft/present motion + warm-cream palette. Agent composes planes + per-group typography + block-synced accumulation per scene. Unified template replacing memory-wall/champion/portrait-header for this aesthetic family. | [template.html](modes/template/cinematic-cream/template.html) header |
| memory-wall | 16:9 landscape | Italic poem + uppercase climax, right-aligned cascade (superseded by cinematic-cream, kept for reference) | [spec](modes/template/memory-wall/spec.md) |
| champion | 16:9 landscape | Side column + center-stage crown crossing subject (superseded by cinematic-cream) | [spec](modes/template/champion/spec.md) |
| portrait-header | 9:16 portrait | Centered header strip + optional bottom crown (superseded by cinematic-cream) | [spec](modes/template/portrait-header/spec.md) |

> **Two-track note:** these are **embed-track** looks — they composite text into the scene. The default **rail** subtitle track is specced in [references/rail.md](references/rail.md); a dedicated rail renderer is the next implementation step. Until then a rail-first explainer = the rail spec for the body + one of these (or custom) for the embedded climax only.

To add a new template: see [modes/template/README.md § Adding a new template](modes/template/README.md).

---

## Aesthetic decision — tone × shot × platform

Before picking a template, classify the clip on 3 axes:

**Tone** (what feel does the content have?)
- documentary | conversational | energetic | poetic | keynote | investigative | music-video

**Shot** (what's the framing?)
- close-up (head + shoulders) | mid-shot (torso+) | wide (full body+) | cut-montage (mixed shots)

**Platform** (where will it play?)
- 9:16 portrait (TikTok/IG/Shorts) | 16:9 landscape (YouTube/web) | 1:1 square | broadcast export

Cross-reference in [references/direction-catalog.md § Classification matrix](references/direction-catalog.md) → direction → shipped template OR custom-mode design.

## Composition craft (embed track) — read before embedding

The full **embed-track** playbook lives in **[references/composition-craft.md](references/composition-craft.md)**:
transcript role-annotation, phrase grouping, planes & clean-zone anchoring, zone coherence,
climax pop & readability, edge-breathing, the occlusion 3-step judgement, and
accumulation/persistence. It governs how a *promoted* phrase sits INTO the scene — read it
before authoring any embed (template `plan.json` or custom `index.html`). The default **rail**
track has its own, much simpler spec → **[references/rail.md](references/rail.md)**.

---

## Shared knowledge

| Doc | What |
|---|---|
| [references/rail.md](references/rail.md) | **The rail track** — standard lower-third subtitle spec (the default; carries most text). |
| [references/composition-craft.md](references/composition-craft.md) | **The embed-track playbook** — grouping, planes, climax pop, occlusion judgement, accumulation/persistence. Read before embedding. |
| [references/aesthetic-principles.md](references/aesthetic-principles.md) | **The 18 rules.** Beat Veed AI on taste. Read first. |
| [references/motion-vocabulary.md](references/motion-vocabulary.md) | 10 named motion primitives + tone→timing lookup |
| [references/direction-catalog.md](references/direction-catalog.md) | 10 ship-ready aesthetics + tone×shot×platform matrix |
| [references/anti-patterns.md](references/anti-patterns.md) | Bugs already locked out (CoreML, letter-spacing reflow, etc.) |
| [references/scene-types.md](references/scene-types.md) | When a wall surface is usable (4 conditions) |
| [references/layout-heuristics.md](references/layout-heuristics.md) | Plane positioning, clean-zone selection, crown 3 conditions, pillarbox math |
| [references/typography-presets.md](references/typography-presets.md) | Font-size × column-width matrix (starting points) |
| [references/caption-grouping.md](references/caption-grouping.md) | Word → group rules (pauses, sentence boundaries) |
| [references/failure-modes.md](references/failure-modes.md) | Long tail of dev gotchas |
| [references/bespoke-vs-presets.md](references/bespoke-vs-presets.md) | Why presets fail sometimes; clone-and-tweak pattern |

**Read the aesthetic principles and direction catalog FIRST.** Everything else is implementation detail.

---

## Non-negotiables

- **Face must never be 100%-covered continuously** — every 0.3s window, face bbox ≥30% uncovered.
- **WCAG contrast** — final render lints; fix palette if it fails.
- **Deterministic** — no `Math.random()`, no `Date.now()`, no `repeat:-1`.
- **Never grade/recolor the video.** The footage ships untouched — captions are the only addition. No full-frame scanlines / duotone / darken / vignette over the a-roll. Cyberpunk/CRT texture belongs *inside* a caption element, not over the whole frame.
- **Rail-first for talking-head / explainer.** Don't embed the whole transcript — most text is the rail; embed only peaks. Embedding everything is the default mistake.
- **Embed is scarce + spaced.** ≤1 embed per sentence/beat, never two adjacent or co-visible, ≥ a beat apart, at most one `apex`. climax = per-beat peak, **not** "the single payoff of the entire clip."
- **Matte = the subject (RVM person matting).** RVM segments people, not props — a gripped mic/cup is best-effort and may not be fully captured, and bright incidental objects can leak in. Sample `frames_fg/` and sanity-check before relying on tight prop occlusion.
- **Captions stay on-frame.** Template mode hard-gates frame-overflow; custom mode runs `check-overflow.js` as a WARNING (intentional bleed is the only exception — read the warning).
- **Each caption ≥ 0.5s on screen** — shorter = unreadable.
- **Word timings must match transcript.json within 80ms** — a caption firing 500ms off-beat destroys the scene illusion. `render-and-composite.sh` runs `check-timing.cjs --strict` before rendering; fix drift before the gate. Never pack multiple transcript words into one entry (e.g. `"FUTURE OF"` or `"IT<br>ALL"` with one start/end) — the second word inherits the first's timestamp and fires early. Split them into separate word entries with their own timings, even if you want them on the same visual line (use CSS `white-space` / natural wrap instead of `<br>`). Creative substitutions where caption text ≠ transcript (e.g. `"15%"` replacing `"fifteen percent"`) are supported — register them in `CREATIVE_SUBS` inside `check-timing.cjs`.
- **Group windows must envelop their words** — `group.in ≤ min(word.start)` and `group.out ≥ max(word.end)` for every group. If `group.in` is later than a word's start, the word is silently delayed until the container mounts (we've shipped 800ms lag bugs from this). The validator enforces this.
- **No two caption groups may overlap in both time AND screen region** — overlapping-in-time captions create text-on-text pileups. Options: (a) **spatial separation** — place each group in a non-overlapping vertical band so they can coexist (memory-wall cascade style); (b) **handoff** — set the earlier group's `out` ≤ the next group's `in` so only one is on screen; (c) **deliberate layered typography** — add `"allow_overlap": true` on one of the groups to silence the validator. The validator estimates each group's vertical bbox from its CSS and flags collisions. Pick (a) by default — it's what makes cinematic-cream feel like a poem accumulating, not a subtitle track replacing itself.
- **Screen-blend fails on bright backgrounds** — if region luminance > 180, switch to `mix-blend-mode: normal` + opaque color.
- **Don't animate `letter-spacing` or `filter:blur` on word entrance** — inline-block reflow causes line-jumps.
- **CoreML banned for RVM matting** — it corrupts face alpha, so matting is CPU-only (~3 fps @1080p ≈ 1 min per 10s clip; budget for it on long clips).

---

## Dependencies

- **hyperframes**, built (`packages/cli/dist/cli.js`). Scripts auto-resolve the checkout: `HYPERFRAMES_ROOT` env → repo root if this skill ships *inside* hyperframes → `~/Downloads/hyperframes`. Build with `bun install && bun run build`.
- **No Python — Node-only.** Everything runs on the toolchain hyperframes already ships: RVM matting via **`onnxruntime-node`**, image/alpha math via **`sharp`**, layout/occlusion/overflow via **`puppeteer`**, plus **`ffmpeg`**. The scripts auto-resolve these from the hyperframes checkout — nothing extra to install.
- **Transcription = hyperframes' Whisper** (whisper.cpp — native C++, no API key, no Python). `transcribe.cjs` wraps `hyperframes transcribe`; hyperframes auto-installs whisper.cpp (Homebrew or source build) and the model on first run. Falls back to an existing word-level `transcript.json` if present.
- **Source video** — `matte.cjs` / `transcribe.cjs` auto-resolve `source.mp4` (or glob the clip / read `hyperframes.json`), so `hyperframes init --video X.mp4` needs no manual rename.
- **fps** — `matte.cjs` extracts at the source's native rate and records `matte.fps`; `render-and-composite.sh` uses that so the matte stays frame-aligned.
- `assets/rvm_mobilenetv3_fp32.onnx` (14 MB) — auto-downloaded on first matte run.

If a hard dependency is missing, STOP and ask the user — don't silently skip steps.
