---
name: general-video
description: General HTML video composition authoring — the router fallback for any "make a video" request that is NOT a marketed product (→ product-launch-video), a topic explainer (→ faceless-explainer), a GitHub PR (→ pr-to-video), existing footage to recut (→ footage-recut), or a Remotion port (→ remotion-to-hyperframes). Use for title cards, lower thirds, logo reveals, kinetic typography, data / stat montages, brand reels, motion posters, overlays, or any custom composition, at any length and format. Input- and length-agnostic. This is the original `hyperframes` authoring flow — design system → prompt expansion → plan → layout-before-animation → build → validate — delegating contract / creative / motion details to the `hyperframes-*` domain skills.
metadata:
  tags: orchestrator, general-video, fallback, freeform, composition-authoring
---

# general-video — general composition authoring

The router's fallback for video creation that doesn't fit a specialized workflow. This is the original `hyperframes` authoring flow: **you (the main agent) author the composition directly**, pulling the technical contract, creative direction, and motion from the `hyperframes-*` domain skills. There is no capture step and no fixed pipeline — it adapts to whatever was asked, at any length or format.

**Build exactly what was asked.** A title card is a title card — not a title card + three supporting scenes + ambient music + captions. If extra scenes or elements would genuinely improve the piece, _propose_ them; don't add them silently. For small edits (fix a color, adjust one duration, add one element), skip the planning steps and go straight to the build.

## Approach

### Discovery — open-ended requests only

For vague, exploratory requests ("make something for our brand", "a cool intro") — understand intent before picking colors:

- **Audience** — who watches? developers / executives / general consumers?
- **Platform** — where does it play? social (15s) / website hero / product demo / internal?
- **Priority** — what matters most? motion quality / content accuracy / brand fidelity / speed?
- **Variations** — one best shot, or 2-3 meaningfully different options (different pacing, energy, or structure — not just color swaps)?

For specific requests ("add a title card", "fix the timing on scene 3"), skip discovery.

### Step 1 — Design system → `hyperframes-creative`

Establish the visual identity first. If the project has a design spec, read it (precedence `frame.md` → `design.md` → `DESIGN.md`; treat it as brand truth — exact colors, fonts, constraints). If none exists, pick a route via `hyperframes-creative`: a named style/mood → `references/visual-styles.md`; fast defaults → `references/house-style.md`; interactive picker → `references/design-picker.md`. The spec defines the **brand**, not the composition rules.

<HARD-GATE>
Before writing ANY composition HTML, verify you have a visual identity from Step 1. If you are reaching for `#333`, `#3b82f6`, or `Roboto`, you skipped it.
</HARD-GATE>

### Step 2 — Prompt expansion → `hyperframes-creative`

Run for every multi-scene composition (skip for single-scene pieces and trivial edits). Ground the request against the design spec + house style into a consistent intermediate that downstream work reads the same way. See `hyperframes-creative/references/prompt-expansion.md`.

### Step 3 — Plan

Before writing HTML, think at a high level:

1. **What** — the viewer experience: narrative arc, key moments, emotional beats.
2. **Structure** — how many compositions, sub-comp vs inline, which tracks carry video / audio / overlays / captions.
3. **Rhythm** — name the pattern before implementing (e.g. `fast-fast-SLOW-SHADER-hold`); see `hyperframes-creative/references/beat-direction.md`.
4. **Timing** — which clips drive duration, where transitions land, the pacing.
5. **Layout** — build the end state first (see below).
6. **Animate** — then add motion via `hyperframes-animation`.

## Layout Before Animation

Position every element where it sits at its **most visible moment** — fully entered, correctly placed, not yet exiting. Write that as static HTML + CSS first. **No GSAP yet.**

**Why:** if you position elements at their animated start state (offscreen, scaled to 0, opacity 0) and tween to where you _think_ they land, you are guessing the final layout — overlaps stay invisible until render. Build the end state first and you see and fix layout problems before adding motion.

1. **Identify the hero frame** for each scene — the moment the most elements are simultaneously visible. That is the layout you build.
2. **Write static CSS** for that frame. The content container must fill the scene with padding, not absolute offsets:

```css
.scene-content {
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 120px 160px; /* padding positions content; fills any scene size */
  gap: 24px;
  box-sizing: border-box;
}
```

Never use `position: absolute; top: Npx` on a content container — it overflows when content is taller than the space. Reserve absolute positioning for decoratives.

3. **Add entrances** — animate FROM offscreen/invisible TO the CSS position with `gsap.from()` (in sub-compositions prefer `gsap.fromTo()` so the start state is explicit; see `hyperframes-core/references/sub-compositions.md`). The CSS position is ground truth; the tween is the journey to it.
4. **Exits are transition-handled** — per the scene-transition rules in `hyperframes-animation/transitions/`, only the **final** scene animates elements out; between scenes the transition IS the exit.

**Shared space across time:** if element A exits before element B enters in the same area, both still need correct CSS positions for their respective hero frames — timeline ordering keeps them from coexisting, and the layout step catches accidental overlap. Layered glows/shadows and z-stacked depth are _intentional_ overlap; the step is about catching _unintentional_ collisions (two headlines on top of each other, content bleeding off-frame).

## Build — delegate to the domain skills

Author the HTML against the domain skills; do not reinvent their contracts here:

- **Composition contract** — `data-*` attributes, clips, tracks, sub-compositions, variables, media, the single paused `window.__timelines` registration, and the non-negotiable determinism rules → **`hyperframes-core`**.
- **Motion** — atomic rules, multi-phase scene blueprints, scene transitions, broader techniques, and runtime adapters (GSAP default; Lottie / Three.js / Anime.js / CSS / WAAPI / TypeGPU) → **`hyperframes-animation`**.
- **Creative direction** — palettes, typography, narration, audio-reactive visuals, composition patterns → **`hyperframes-creative`**.
- **Media** — TTS narration, transcription, captions, background removal → **`hyperframes-media`**.
- **Pre-built blocks / components** — install and wire via **`hyperframes-registry`** (`hyperframes add`).

## Output checklist → `hyperframes-cli`

- [ ] `npx hyperframes lint` and `npx hyperframes validate` pass (block on results)
- [ ] design adherence verified if a spec (`frame.md` / `design.md`) exists
- [ ] `npx hyperframes inspect` passes, or every overflow is intentionally marked
- [ ] contrast warnings addressed; for multi-scene work, review the animation map (`hyperframes-animation/scripts/animation-map.mjs`)
- [ ] deliver the preview; render to MP4 only on explicit request

## Not this workflow

- A specific **product / company / SaaS / website** being marketed, launched, or promoted → `/product-launch-video`
- A **concept / topic / article / how-X-works** being explained, no product → `/faceless-explainer`
- A **GitHub PR / code change** → `/pr-to-video`
- An **existing video file** to re-edit, recut, or annotate → `/footage-recut`
- Porting an existing **Remotion** composition → `/remotion-to-hyperframes`
- Cutting / editing a **finished video file** like an NLE → out of scope (HyperFrames composites HTML and media into a deterministic timeline; it does not edit footage)
