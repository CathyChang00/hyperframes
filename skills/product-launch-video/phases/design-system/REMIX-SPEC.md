# Preset Palette + Remix Spec

> Status: **golden sample = `pin-and-paper`** (palette block added, §H removed). **R2 (engine consumes `palette{}`) is DONE + verified** — `pin-and-paper` text‑only now emits its native palette (`--ink #1F3A8A` on `--canvas #EFE56A`, no collapse) while a real URL capture is byte‑for‑byte unchanged. Remaining: **R1** (no‑URL SKILL.md entry), **R5** (component reframe), **rollout to the other 18 presets**, and reconciling `README.md` with this new standard.

## North Star

Make each preset **self‑sufficient and remixable**:

- A preset defines **style** — color palette, type scale, motion, voice, material/components.
- **Composition is decided per‑scene by Phase 3 visual‑design** (blueprints + `rules/`), not dictated preset‑wide.
- **Colors are remixable**: swap the semantic palette, keep the preset's identity (structure / type / motion / material). Brand DNA from capture overrides the palette when present + confident; with no capture the preset palette is the default, so videos can be made from **script + a chosen preset + a brand color, with no URL extraction**.

This decomposes into R1–R6 (below). R3/R4/R6 are realized in the golden sample; R1/R2/R5 are the remaining engine/orchestration work.

---

## The `palette{}` block (R2 + R3)

Lives inside the `preset-meta` JSON at the top of each `preset.md`. **`preset-meta` is parsed with strict `JSON.parse`** (`build-design.mjs` parsePreset) — **no `//` comments**, valid JSON only. Semantics go in the `constraint` strings.

### Slots (6)

The three color planes of 60‑30‑10 plus the brand hues:

| slot        | plane / role                                             | required    | notes                                              |
| ----------- | -------------------------------------------------------- | ----------- | -------------------------------------------------- |
| `canvas`    | 60% — the page/scene ground                              | ✅          | must contrast `ink`                                |
| `surface`   | 30% — card / panel fill                                  | ✅          | the "second surface"; distinct from `canvas`       |
| `ink`       | text + borders + strokes + shadows                       | ✅          | may `alias` another slot (see below)               |
| `primary`   | dominant brand hue / focal fills                         | ✅          |                                                    |
| `accent`    | 10% — the single high‑attention pop (CTA, marker, stamp) | ✅          |                                                    |
| `secondary` | optional 2nd brand hue / rare third tone                 | ⚪ optional | omit or keep minimal if the preset doesn't use one |

`tertiary` / `costume` are **preset‑internal** (only multi‑surface presets like `peoples-platform` use them; the other 18 inherit no‑op defaults) — don't add them unless the preset genuinely has >2 surfaces. Decoration colors (`deco-*`) are preset‑owned identity and stay in `§B`, not here.

### Per‑slot keys

```jsonc
"primary": { "value": "#1F3A8A", "constraint": "<R4 color personality — what a remixed brand color must respect>" }
"canvas":  { "value": "#EFE56A", "lock": "anchor", "constraint": "..." }
"ink":     { "alias": "primary" }
```

- **`value`** — the preset's native/original color (harvest from the source template's `:root`, e.g. `tmp/templates/<preset>/template.html`). This is the default used when no capture / no confident extraction.
- **`constraint`** (R4 "declare color constraints") — a one-line description of the slot's **color personality** so a remixed brand color can be harmonized into range (e.g. "deep desaturated ink — reads near-black on paper"). Not machine-enforced yet; it's the authoring contract + future harmonizer input.
- **`lock: "anchor"`** — this slot is a **structural signature**, not a palette choice. Brand DNA only **tints** it (via `color-mix()` declared in `§B`), never replaces it. Use for surfaces that define the preset's identity (e.g. pin‑and‑paper's yellow paper + cream card — without them the layered gradients / grain / contrast all fail).
- **`alias: "<slot>"`** — this slot equals another. Use when a preset collapses two roles (pin‑and‑paper: `ink` ≡ `primary`, the ink‑blue is both the brand hue and the structural ink).

### Worked example — `pin-and-paper` (golden sample)

Harvested from `tmp/templates/pin-and-paper/template.html` `:root`: `--paper #EFE56A`, `--cream #F8F1D6`, `--ink #1F3A8A`, `--red #C2342B`, `--kraft/--olive/--orange` tertiaries.

```jsonc
"palette": {
  "primary":   { "value": "#1F3A8A", "constraint": "deep desaturated ink — reads near-black on paper; carries every text fill, border, divider, pin illustration, and hard offset shadow" },
  "accent":    { "value": "#C2342B", "constraint": "single vivid warm — used in at most two spots (the rotated rubber stamp + the negative pill); never as body text, card fill, or chip" },
  "secondary": { "value": "#C9A66B", "constraint": "muted earthy third tone (kraft / olive / orange from the source palette); structurally optional, used only when a scene needs a rare third tone" },
  "canvas":    { "value": "#EFE56A", "lock": "anchor", "constraint": "warm saturated legal-pad yellow — the page ground; brand DNA tints it via color-mix() in §B, never replaces it, so the paper register survives every brand palette" },
  "surface":   { "value": "#F8F1D6", "lock": "anchor", "constraint": "off-white cream — the pinned-card fill; brand DNA tints via color-mix() in §B, never replaces" },
  "ink":       { "alias": "primary" }
}
```

Note pin‑and‑paper's `canvas`/`surface` are **anchors already wired in `§B`** as `--anchor-paper-yellow` / `--anchor-cream` + `color-mix()` formulas — the palette block formalizes them; `§B` already does the tinting.

---

## §H removal + composition → visual (R6)

§H ("Scene composition hints") is **deleted** from each preset. Composition (surface alternation, hero placement, card grids, element positioning) is decided per‑scene by Phase 3 visual‑design via **blueprints + `rules/`**. §H content decomposes three ways:

| §H content                                                                                   | disposition                                                                                                                                      |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Layout / composition (surface rotation, hero size+placement, grid columns/gaps, positioning) | **DELETE** → visual‑design owns it (blueprints + `rules/composition.md`)                                                                         |
| Brand‑color role contract (which slot goes where, 60‑30‑10)                                  | **MOVE → `palette{}`** (the `constraint` strings) — also in `rules/color-system.md`                                                              |
| Scene transitions (cross‑dissolve, never slide/wipe/zoom)                                    | **DELETE if redundant** — usually already in `§E`                                                                                                |
| **Material identity** (pins, stamp, grain, hairline borders, off‑axis tilts)                 | **KEEP — but it belongs in `components/*.md` + `§B` tokens + `§A` intent, NOT as composition prose.** Verify it's carried there before deleting. |

**Mechanical safety**: a preset with no `§H` is fine — `build-design.mjs` emits a **stub** `composition-hints.md` (`"preset declared no §H — plan agent picks components by id alone"`) so the plan agent's must‑read path stays uniform. `emit-chunks` → `hints_file` points at the stub; visual‑design reads it and decides composition itself. **No crash, no validator failure.**

**pin‑and‑paper check (why deletion was zero‑loss)**: its material identity is fully carried by `components/{safety-pin,stamp,paper-grain-overlay,pinned-card,...}.md` + `§B` tokens + `§T` type‑roles + `§E` motion + `§G` voice; the color contract moved to `palette{}`; transitions were already in `§E`. Only the layout dictation was removed — which is visual‑design's job.

---

## Per‑preset rollout checklist (the other 18)

For each `style-presets/<preset>/preset.md`:

1. **Harvest the original palette** from `tmp/templates/<preset>/template.html` `:root` (or `design.md`). Map to the 6 slots. Record per‑slot `constraint` (color personality). Mark structural surfaces as `lock: "anchor"`; collapse duplicate roles with `alias`.
2. **Add the `palette{}` block** to `preset-meta` (valid JSON, no comments).
3. **Delete `§H`** — but first confirm each material‑identity rule is carried by `components/*.md` / `§B` / `§A`. If a material rule lives ONLY in §H, relocate it to `§A` (prose) or the relevant component before deleting. Leave a one‑line `> §H removed.` note (see pin‑and‑paper).
4. **Verify it still builds** (no URL needed):
   ```bash
   SP=/tmp/<preset>-check; rm -rf "$SP"; mkdir -p "$SP/capture/extracted" "$SP/design-system"
   echo '{ "title":"X","colors":[],"fonts":[],"headings":[],"sections":[],"cssVariables":{} }' > "$SP/capture/extracted/tokens.json"
   echo "" > "$SP/capture/extracted/visible-text.txt"
   node <SKILL_DIR>/phases/design-system/scripts/build-design.mjs "$SP/design-system" --capture "$SP/capture" --style <preset>
   node <SKILL_DIR>/phases/design-system/scripts/emit-chunks.mjs "$SP/design-system"
   ```
   Expect: preset‑meta parses (palette valid JSON), components emit, `composition-hints.md` is the stub. Once **R2** lands, also expect the emitted `:root` palette to match the preset's `palette{}` values (not a `#000000`/hardcoded collapse).

Suggested order: start with the **"zero native color" presets** (`emerald-editorial`, `neo-brutalism`, `editorial`, `soft-editorial` — they currently have 0–1 declared hex, so they most need an authored palette), then the color‑rich ones (`scatterbrain`, `daisy-days`, `sakura-chroma` — mostly harvest).

---

## Engine + orchestration TODO (not in the golden sample)

### R2 — `build-design.mjs` consumes `palette{}` — ✅ DONE

**Policy (implemented)**: default = preset palette; extraction wins when present. The fallback fires **only when nothing was scraped** (`hfTokens.colors` empty) — so the URL path is byte‑identical and **needs no golden‑baseline regen** (verified: a capture with colors still uses the captured palette).

What landed in `build-design.mjs`:

1. `palette: meta.palette || null` added to `parsePreset`'s `return {…}` so `preset.palette` is reachable.
2. The seven color Hex vars (`primaryHex`/`secondaryHex`/`accentHex`/`canvasHex`/`inkHex`/`tertiaryHex`/`costumeHex`) + `signatureGradient` changed `const`→`let` (they're derived at ~§693‑806 from capture data, **before** the preset is chosen at `pickPreset()` ~§1201).
3. Right after `pickPreset()`, a fallback block: `if ((hfTokens.colors || []).length === 0 && preset.palette)` reassigns each Hex from `preset.palette` via `_ppGet(slot)` (resolves `alias` recursively, normalizes hex; `costume` falls back to `surface`), then recomputes `signatureGradient`. Feature scoring + `decoColors` stay on capture‑derived values (don't skew auto‑inference; `decoColors` keeps its built‑in fallback when no palette deco is declared).

**Trigger gotcha**: use `hfTokens.colors` (raw scraped palette), NOT `allColors` — the latter synthesizes black/white defaults from empty input, so it's never length 0.

Verified: pin‑and‑paper text‑only emits `--canvas #EFE56A`, `--ink #1F3A8A`, `--brand-primary #1F3A8A`, `--brand-accent #C2342B`, `--brand-secondary #C9A66B` (no collapse); a `#0aa3ff` capture stays `#0aa3ff`.

**Not yet (future, optional)**: per‑slot confident override for _degenerate‑but‑nonempty_ captures (e.g. a monochrome site with 1 real color) — currently those still use the extraction path. And `palette.deco` support so non‑`block-frame` presets don't inherit the hardcoded yellow/green/blue/pink deco when text‑only.

### R1 — no‑URL / text‑only entry (mostly SKILL.md)

No‑capture path needs only to synthesize `capture/extracted/tokens.json` + `visible-text.txt`; the existing Step‑1 commands (`derive-context-pack`, `build-design --no-emit`) then run unchanged, and `prep` tolerates empty assets (text‑only scenes use `assetCandidates: []`). So add a **Step 0/1 branch in `SKILL.md`** (inline Bash, no new script): pick preset → write a minimal `tokens.json` (seed `cssVariables.--background/--foreground` from the preset palette's `canvas`/`ink` so build‑design doesn't collapse even pre‑R2) + the brief as `visible-text.txt`. Plus a `hyperframes-read-first` decision‑table cell for (script/brief × 30‑90s) and a Resume‑table note. Brand‑color override in no‑capture mode rides in the seed's `colors[]` (R2's `--brand-primary` does not feed `primaryHex`).

### R5 — components as flexible style reference ("structure variable, material locked")

Reframe the scene worker's contract: components are a **style reference** the worker may restructure / compose / animate, **but the material signature stays locked** (borders/shadows/fonts/colors via tokens). Keep the self‑lint gate; degrade the component‑rank/exclusivity check from "by id" to "material compliance". Goal: stop videos reading as "animated web pages". (Edits land in `agents/hyperframes-scene.md` + `agents/visual-design.md`; out of scope for the preset golden sample.)
