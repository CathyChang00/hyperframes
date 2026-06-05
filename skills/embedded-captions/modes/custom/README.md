# Custom mode — design from a blank canvas

## Permission slip

**Be wild. Be weirder than feels professional. Aim for "wow" not "tasteful."**

The agent reading this is probably anchored from working in template mode for
the last several turns. That anchoring is the single biggest threat to good
custom-mode output. The most common failure isn't bad design — it's
"surprisingly competent template render dressed up as custom."

If you walk away from this README thinking *"OK, I'll do template mode but
with extra layers"*, you have misread the brief. The right reading is:
**throw the template playbook out, design something only this scene could
have, ship the version that would make the user say "holy shit" — not "nice
job."**

You have explicit permission to:
- ignore everything you learned about planes / groups / tone / caption_mode
- invent your own motion vocabulary (not soft/present)
- skip `mix-blend-mode` entirely if your visual idea doesn't need it
- use 47 caption elements with 47 different styles, or 1 element that morphs
  through 47 states, or no caption "elements" at all and just one canvas
- break grid alignment, deliberately mis-letter-space (in static states),
  let words exit through corners, fly past the camera plane, dissolve into
  particles
- design something that template mode literally cannot produce — that's the
  bar

If your output ends up looking like the cinematic-cream template with extra
grain, you did not enter custom mode. **Stop, delete, redesign.**

---

## What to drop at the door (template-mode baggage)

These concepts exist in template mode and **DO NOT APPLY** in custom mode.
Reusing them is what produces "template render in disguise":

| Template concept | Custom-mode replacement |
|---|---|
| `plan.json` (layout + groups + timings JSON) | None — write HTML directly |
| `planes` (parent containers like `body`/`crown`) | Whatever spatial structure your visual idea wants |
| `groups` array, `cg-N` IDs | Whatever you call your caption elements (`.flash`, `.scrawl`, `.stamp`, `.collapse`...) |
| `tone: "soft" \| "present"` motion vocabulary | Invent your own (blur→focus, ghost-collapse, glitch, invasion, drip, fracture, type-stamp, particle-burst...) |
| `caption_mode` field | Nonexistent — you decide what shows |
| `check-occlusion.cjs --strict` gate | Bypassed — you own occlusion judgment by eye |
| `check-timing.cjs` 80ms gate | Bypassed — you own timing by eye |
| `make-composition.cjs` compile step | Skipped — `index.html` is the artifact |
| Inter font + warm-cream color palette | Whatever the scene wants (custom font load, brand color, hand-drawn SVG, etc.) |
| Body-emphasis / climax size ratio rules | Whatever serves your visual idea |
| Block-synchronized accumulation w/ display:none exit | Whatever entry/exit choreography you design |

If you find yourself writing `<div class="plane">`, `data-tone="soft"`, or
`{ "groups": [...] }` — pause. You're slipping back to template mode. Either
fully commit to template mode, or rename and redesign so the structure
reflects YOUR concept, not the template's.

---

## When to enter custom mode

- User says: "be creative", "越酷炫越好", "make it wow", "design from scratch", "I trust you"
- User gives a reference video / mood image / brand and wants captions to feel like a continuation of THAT specific piece
- The scene has a unique element no template addresses (a surface to project type onto, brand asset to integrate, non-standard aspect, mid-clip scene shift)
- User explicitly asks for `--mode=custom`

If the user just says "add captions" with no design direction, that's
template mode. Custom is for when the brief or scene demands something a
stock template can't deliver.

---

## Hard contract — what the pipeline actually requires

These FOUR DOM elements + ONE JS export must exist or the render fails.
**Beyond them, nothing is required:**

```html
<div id="root"
     data-composition-id="main"
     data-start="0"
     data-duration="{{DURATION}}"
     data-width="{{WIDTH}}"
     data-height="{{HEIGHT}}">
  <video id="a-roll" src="source.mp4" muted playsinline
         data-duration="{{DURATION}}" data-track-index="0"></video>
  <div id="stage"><!-- YOUR DESIGN -->
  </div>
  <audio id="a-roll-audio" src="source.mp4"
         data-start="0" data-duration="{{DURATION}}"
         data-track-index="3" data-volume="1"></audio>
</div>
<script>
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  // ...your animations...
  tl.seek(0);
  window.__timelines["main"] = tl;
</script>
```

Caption pixels live inside `#stage` (z-index 2). The matte PNG sequence
overlays in post-composite (`ffmpeg overlay`), occluding caption pixels
where the subject is in front. That's the entire pipeline-level
constraint. Anything you put inside `#stage` is yours.

---

## The pipeline runs WITHOUT plan.json — really

`render-and-composite.sh` checks for `plan.json` and only runs the timing
+ occlusion gates when it finds one. **In custom mode, do not write a
plan.json.** The agent who insists on writing one is usually doing it
because the template-mode muscle memory fears the checker breaking — but
the checker doesn't run on you. You don't owe it bbox math or word
timings in JSON.

You DO need accurate word timings for the captions you DO want
animated — but those go directly in your GSAP timeline, sourced from
`transcript.json` or the `Whisper`-style word array. No intermediate
JSON layer.

Custom mode trades validation for design freedom. That's the deal.

---

## What custom mode UNLOCKS — concrete starter ideas

Use these as **launch points to invent your own**, not a checklist. The
real win is something not on this list because no one thought of it yet:

**Word-as-physical-object**
- Letters drip in like ink, then settle
- Words assemble glyph-by-glyph from particle scatter
- Type stamps in like a passport (snap + ink-bleed)
- Type that develops like Polaroid chemistry (white flash → fade-in)
- ASCII grid that resolves into the climax word
- Letters that physically collapse / shatter / explode at exit

**Type that interacts with the subject**
- Caption parallaxes with subject head movement
- Type wraps around the body silhouette (CSS shape-outside, or pre-baked SVG path tracing the matte)
- Hand gesture "splashes" the caption (caption deforms under the hand's bbox)
- Type that gets revealed BY the subject's hand sweeping past it
- Caption stuck to a surface in the scene with perspective transform

**Mid-render scene shifts**
- Color invert at the narrative pivot
- Focus pull (background blur ramp) on the subject during build-up
- Sepia → full color at climax (filter timeline)
- Letterbox bars sliding in, then out
- A grain layer that intensifies with emphasis lines
- Lighting flash that bleaches the frame momentarily

**Atmospheric layers**
- SVG turbulence-grain animated noise
- Vignette pulses with audio amplitude (pre-bake envelope)
- Lens-flare aligned to the climax word
- Film burn at chapter marks
- Light leaks at corners during emotional peaks

**Typography as moving graphics**
- Type morphing from word A to word B by glyph interpolation
- Hand-drawn SVG path captions traced in real-time
- Neon-tube text flicker on
- Glass-fracture shatter on climax exit
- Magazine masthead "stamping" into existence
- Scrawled-margin handwriting (handwriting font + path-trace animation)

**Audio-reactive elements**
- Type scales with vocal amplitude (pre-baked envelope, since GSAP is deterministic)
- Caption tracks the speaker's pitch contour
- Pulses on percussion hits in the underscore
- Letter spacing breathing in sync with breath pauses

**Multi-plane / depth**
- Billboard receding into perspective behind the speaker
- Type flying past on a plane closer than subject (object-fit)
- Depth-of-field blur on background type while foreground stays sharp
- Multiple opacity layers creating "stacked translucent" glass effect

**Frame-breaking moves**
- Words that slide off-frame and continue mentally
- Climax bleeds intentionally for masthead energy (one of the few times
  this is allowed — see template mode "readability is hard constraint" for
  contrast)
- Captions that exit through corners rather than edges
- Type that pierces the safe area diagonally

The **point** is that the visual idea drives mechanics, not the other way
round. Start with: *"I want this clip to feel like a Polaroid being taken,"*
or *"the narrator voice is hand-scrawled in the margin, the brand name is
stamped like a passport approval,"* or *"each word is a glitch fragment that
resolves into the next one." *Then design backward to the HTML.

---

## Workflow

1. **Probe the scene** — sample frames at 20/50/80%, study subject envelope,
   backdrop, motion, audio shape, semantic arc (where's the build, where's
   the payoff, what's the emotional shape). Spend more time here than in a
   template render — the design follows from this read.

2. **Decide the visual concept in one sentence.** Then a second sentence
   describing the climax moment. If you can't articulate the concept, you
   don't have a design — you have template mode in disguise. Don't proceed
   until the concept is sharp.

3. **Read the inspiration library — adversarially.** The `examples/` files
   in this directory are historical artifacts from the first 3 custom
   renders. They lean traditional (perspective plane + crown caption)
   because that was what landed early. **Do not let them anchor your
   vocabulary.** Use them ONLY to confirm pipeline contracts (matte overlay,
   GSAP timeline naming, blend mode mechanics) — then design something
   they don't predict.

4. **Write `<project>/index.html` from scratch.** Copy `skeleton.html` if
   you want the contract scaffolding pre-filled. Inside `#stage`, design
   freely — no `.plane`, no `cg-N`, no `tone: "soft"`. Name elements after
   the visual idea: `.polaroid-flash`, `.scrawl-margin`, `.brand-stamp`,
   `.glitch-shard`, `.particle-arrival`. The HTML reads like a moodboard.

5. **Render**:
   ```bash
   bash scripts/render-and-composite.sh <project>
   ```
   No `plan.json`. No checker. The script renders directly, applies the
   matte, produces `final.mp4`.

6. **Iterate visually.** Pull frames at concept-relevant moments. Judge by
   eye against the visual concept from step 2. If the render looks like a
   nicer template render, redesign — the bar is "wow," not "tasteful."

---

## Anti-patterns (bugs, not stylistic)

These break the pipeline regardless of design choices:

- `Math.random()`, `Date.now()`, `repeat: -1` → non-deterministic, breaks hyperframes capture
- Animating `letter-spacing` or `filter: blur` on word ENTRY (during opacity 0→1) → inline-block reflow causes line jumps. (Static letter-spacing or blur after entrance is fine. Tweening blur on a fully-visible element is fine.)
- WebM alpha layers as overlay → Chromium drops alpha during capture (use PNG sequences or SVG)
- CoreML execution provider for RVM matting → corrupts face alpha (CPU only)
- Text outside `#stage` → matte won't occlude correctly

These are NOT anti-patterns (and people have flagged them as such by accident):
- Skipping `plan.json` — REQUIRED in custom mode
- Skipping `caption_mode` — doesn't exist in custom mode
- No checker passing — there is no checker in custom mode
- `mix-blend-mode` switching mid-render — fine, often the right move
- Custom motion curves that don't match soft/present — fine, that's the point
- Caption sizes that don't follow body-emphasis-climax 1.8× ratio — fine, that's a template-mode rule
- Captions that bleed off-frame — fine in custom mode if the visual idea calls for it (template mode forbids this for body, allows readable mild bleed for climax; in custom mode YOU decide, no rules)
- Words with their own bespoke style — fine if the scene calls for it

---

## Examples (historical, not canonical — read once, then close)

| File | What it is | What it taught us |
|---|---|---|
| `examples/memory-wall-v1.html` | First wow render: grain + sepia vignette + focus flash at "suddenly" + aperture ring + blur+letter-spacing entrance | Embed effect mechanics; mid-render scene shifts work; some animation choices were unstable (letter-spacing reflow), refined in v2 |
| `examples/memory-wall-v2.html` | Refined v1: per-position bespoke typography, no anti-patterns | The `.plane` + `.crown-plane` + `.cap-N` pattern crystallized — and was later **promoted into template mode** as `cinematic-cream`. **DO NOT COPY THIS IN CUSTOM MODE** — that's exactly the trap. |
| `examples/champion-v1.html` | Podcast: side column + center-stage WIMBLEDON crown crossing subject | Subject-crossing climax with bg embed showcase |

These were custom-mode wins at the time. Several of their patterns
graduated into template mode. **What's left in custom mode is everything
template mode CAN'T do** — so designing custom while staying in these
examples' vocabulary is by definition a regression. Read once to see how
the pipeline holds together. Then close them and design something they
don't predict.

If the agent's first pass looks like an example here, the second pass
should not.
