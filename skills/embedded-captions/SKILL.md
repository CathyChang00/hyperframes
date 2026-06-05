---
name: embedded-captions
description: Add cinematic captions to a talking-head video that feel EMBEDDED in the scene — not overlaid on top. Text is occluded by the subject (head, shoulders, mic), picks up the background via mix-blend-mode, and sits on a surface with perspective when one exists. Use when the user asks for "embed/embedded/cinematic captions", "字幕嵌入/嵌到场景里", "captions that go behind the subject", or similar. The effect is podcast/interview-style — not bouncy TikTok captions, not plain subtitles. Pipeline: ElevenLabs transcription → RVM matting → hyperframes HTML composition render → ffmpeg overlay. Requires hyperframes (github.com/heygen-com/hyperframes) installed and a video with a single primary subject.
metadata:
  tags: captions, embedded-captions, occlusion, matting, talking-head, rvm, elevenlabs, ffmpeg, cinematic
---

# Embedded Captions

Captions that look like they belong to the scene: subject body occludes them, blend mode picks up backdrop texture, emphasis lands on surfaces with perspective. This skill ships **two modes** — pick first, then plan.

---

## Operational flow (TL;DR)

The craft prose below is long; the **pipeline itself is short**:

1. **Decision gate** (refuse bad clips) → **pick mode** (template vs custom)
2. `hyperframes init` → `matte-rvm.py` (subject matte) → `transcribe.py` (words)
3. **author**: template → write `plan.json` → `make-composition.py`; custom → hand-write `index.html`
4. `render-and-composite.sh` → `final.mp4`

Load-bearing rules people miss:

- **The video is delivered UNTOUCHED** — captions are the only thing added; the matte just lets the subject occlude them. Never grade/recolor/scanline the footage.
- Scripts auto-resolve `source.mp4` and the source's **native fps**; `ELEVENLABS_API_KEY` is **optional** (falls back to an existing transcript).
- Custom mode can still render **fg** (captions on top, no occlusion) via `data-caption-layer="fg"` on `#root`; per-caption hybrid bg/fg is template-only.
- Everything from **"Aesthetic decision"** down is craft detail, mirrored in `references/` (see Shared knowledge) — skim by need.

---

## Step 0 — pick the mode

| Mode | When | What agent does | Output consistency |
|---|---|---|---|
| **template** | User named a template **OR** wants something off-the-shelf, OR just says "add captions" with no design direction | Decide layout via `cinematic-cream`'s DNA (planes, per-group typography, block-sync accumulation), write minimal `plan.json`, compile, render | High — predictable family of looks |
| **custom** | User says "be creative" / "越酷炫越好" / "make it wow" / gives a specific reference / scene has a unique element no template addresses | **Throw out template architecture entirely.** Design a one-off composition directly in HTML — no plan.json, no planes/groups/tone, no checker, no DNA constraint. Invent visual + motion vocabulary per scene. | Per-scene unique, "wow" bar |

Default for ambiguous input: ask once. If the user is in a hurry or
default-ish, pick `template > champion` for landscape, `portrait-header` for 9:16.

**The mode determines which directory the agent works in:**
- Template mode → [modes/template/](modes/template/) — `template.html` + `spec.md` per template
- Custom mode → [modes/custom/](modes/custom/) — `skeleton.html` + `examples/`

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

---

## Pipeline — 6 steps

```
1. hyperframes init <project> --non-interactive --video <video.mp4> --skip-skills
2. python scripts/matte-rvm.py <project>       # → frames_fg/*.png
3. python scripts/transcribe.py <project>      # → transcript.json (Scribe v2)
4. [AGENT STEP] mode-dependent — see below
5. (template mode only) python scripts/make-composition.py <project>
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
3. **Skip `plan.json` entirely.** No checker runs in custom mode. No `make-composition.py`. The HTML is the artifact.
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

## Composition craft — read before authoring

The full per-scene playbook lives in **[references/composition-craft.md](references/composition-craft.md)**:
bg/fg layering & hybrid, transcript role-annotation, phrase grouping, planes & clean-zone
anchoring, zone coherence, climax pop & readability, edge-breathing, the occlusion 3-step
judgement, and accumulation/persistence patterns. Read it before writing a `plan.json`
(template) or a custom `index.html`. The granular references below drill into single topics.

---

## Shared knowledge

| Doc | What |
|---|---|
| [references/composition-craft.md](references/composition-craft.md) | **The per-scene playbook** — bg/fg & hybrid, grouping, planes, climax pop, occlusion judgement, accumulation/persistence. Read before authoring. |
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
- **Matte = the subject (RVM person matting).** RVM segments people, not props — a gripped mic/cup is best-effort and may not be fully captured, and bright incidental objects can leak in. Sample `frames_fg/` and sanity-check before relying on tight prop occlusion.
- **Captions stay on-frame.** Template mode hard-gates frame-overflow; custom mode runs `check-overflow.js` as a WARNING (intentional bleed is the only exception — read the warning).
- **Each caption ≥ 0.5s on screen** — shorter = unreadable.
- **Word timings must match transcript.json within 80ms** — a caption firing 500ms off-beat destroys the scene illusion. `render-and-composite.sh` runs `check-timing.py --strict` before rendering; fix drift before the gate. Never pack multiple transcript words into one entry (e.g. `"FUTURE OF"` or `"IT<br>ALL"` with one start/end) — the second word inherits the first's timestamp and fires early. Split them into separate word entries with their own timings, even if you want them on the same visual line (use CSS `white-space` / natural wrap instead of `<br>`). Creative substitutions where caption text ≠ transcript (e.g. `"15%"` replacing `"fifteen percent"`) are supported — register them in `CREATIVE_SUBS` inside `check-timing.py`.
- **Group windows must envelop their words** — `group.in ≤ min(word.start)` and `group.out ≥ max(word.end)` for every group. If `group.in` is later than a word's start, the word is silently delayed until the container mounts (we've shipped 800ms lag bugs from this). The validator enforces this.
- **No two caption groups may overlap in both time AND screen region** — overlapping-in-time captions create text-on-text pileups. Options: (a) **spatial separation** — place each group in a non-overlapping vertical band so they can coexist (memory-wall cascade style); (b) **handoff** — set the earlier group's `out` ≤ the next group's `in` so only one is on screen; (c) **deliberate layered typography** — add `"allow_overlap": true` on one of the groups to silence the validator. The validator estimates each group's vertical bbox from its CSS and flags collisions. Pick (a) by default — it's what makes cinematic-cream feel like a poem accumulating, not a subtitle track replacing itself.
- **Screen-blend fails on bright backgrounds** — if region luminance > 180, switch to `mix-blend-mode: normal` + opaque color.
- **Don't animate `letter-spacing` or `filter:blur` on word entrance** — inline-block reflow causes line-jumps.
- **CoreML banned for RVM matting** — it corrupts face alpha, so matting is CPU-only (~3 fps @1080p ≈ 1 min per 10s clip; budget for it on long clips).

---

## Dependencies

- **hyperframes**, built (`packages/cli/dist/cli.js`). Scripts auto-resolve the checkout: `HYPERFRAMES_ROOT` env → repo root if this skill ships *inside* hyperframes → `~/Downloads/hyperframes`. Build with `bun install && bun run build`.
- **Python venv** with `onnxruntime`, `pillow`, `numpy` (matting) + `elevenlabs` (transcription) — see `requirements.txt`.
- `ffmpeg` available.
- **`ELEVENLABS_API_KEY` — optional.** With it, `transcribe.py` runs Scribe v2 (tightest word timings). Without it, the skill reuses an existing word-level `transcript.json` (the one `hyperframes init` writes, or one you drop in).
- **Source video** — `matte-rvm.py` / `transcribe.py` auto-resolve `source.mp4` (or glob the clip / read `hyperframes.json`), so `hyperframes init --video X.mp4` needs no manual rename.
- **fps** — `matte-rvm.py` extracts at the source's native rate and records `matte.fps`; `render-and-composite.sh` uses that so the matte stays frame-aligned with the render.
- `assets/rvm_mobilenetv3_fp32.onnx` (14 MB) — auto-downloaded on first matte run.

If a hard dependency is missing, STOP and ask the user — don't silently skip steps.
