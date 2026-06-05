# Template mode — pick a locked visual style

Use this mode when the user wants a **consistent, predictable look** —
either they named a template or they want something off-the-shelf.
Visual style (typography, blend, motion) is locked by the template;
agent only decides **layout** (where the plane sits, perspective angle,
font scale, caption grouping, slot assignment, crown enable/disable).

## Catalog

| Template | Best for | Frame | Has crown? | Look |
|---|---|---|---|---|
| `memory-wall` | Introspective monologue, side wall visible | 16:9 landscape | No (right-aligned cascade is the climax) | Italic poem, bone-white, screen blend |
| `champion` | Podcast/interview, cluttered backdrop | 16:9 landscape | Yes (center-stage OR clean-zone) | 5-slot upper-left column + WIMBLEDON-style crown |
| `portrait-header` | 9:16 talking head, single subject | Portrait | Optional bottom | Centered top header strip, screen blend |
| `documentary-dignified` | Documentary interview, formal setting, long-form | 16:9 / 9:16 / 1:1 | No (speaker name card instead) | Errol Morris feel — burn-in, gradient bar, 2-line max |

Each template directory contains:
- `template.html` — the locked HTML/CSS/GSAP shell with `{{PLACEHOLDERS}}`
- `spec.md` — when to use, what to configure, plan.json shape

## Workflow

1. Pick a template (user-specified or agent-chosen by scene fit)
2. Read its `spec.md` for the layout decisions you must make
3. Probe the scene (3 frames at 20/50/80%) for plane positioning
4. Group transcript words and assign slots (`spec.md` describes the slot arc)
5. Write `<project>/plan.json` with template-specific fields
6. `python scripts/make-composition.py <project>` → `index.html`
7. `bash scripts/render-and-composite.sh <project>` → `final.mp4`

## What you DON'T do in template mode

- Override `.cap`, `.cap-*`, `mix-blend-mode`, `color`, `text-shadow`,
  `filter`, GSAP animation, or any locked CSS.
- Add custom DOM layers (grain, vignette, focus flash, etc.)
- Tweak GSAP motion curves or word reveal timing per group

If the user wants any of those → **switch to custom mode** (`modes/custom/`).
That's exactly what custom mode is for.

## Adding a new template

1. Create `modes/template/<name>/` with `template.html` + `spec.md`
2. Use `{{PLACEHOLDERS}}` only for layout (not style):
   - `{{WIDTH}} {{HEIGHT}} {{DURATION}}` — frame + duration
   - `{{FONT_SCALE}}` — multiplier on locked sizes (use CSS `calc()`)
   - `{{PLANE_TOP}} {{PLANE_LEFT}} {{PLANE_RIGHT}} {{PLANE_WIDTH}} {{PLANE_HEIGHT}}` — geometry
   - `{{ROTATE_Y}} {{ROTATE_X}}` — perspective
   - `{{CROWN_TOP}}` — crown plane Y (if template has crown)
   - `{{HEADER_TOP}} {{HEADER_HEIGHT}}` — for header-strip templates
   - `{{GROUPS_HTML}} {{GROUPS_JSON}}` — caption HTML + JS data
   - `{{CROWN_HTML}} {{CROWN_JSON}}` — optional crown block
3. Add a row to the catalog table above
4. (Optional) Render a sample MP4 + commit `preview.gif` for browsing
