# Template: documentary-dignified

**Look:** Errol Morris / 60 Minutes / PBS Frontline. Caption in a locked
bottom-left block on a gradient bar (not a solid pill). No motion. No
emphasis per word. Gravitas through restraint.

**Visual identity (LOCKED):**
- Inter 500 body, Inter 700 name card
- Bone white `#F5EFE6` on 40% black gradient bar (not hard box)
- No text-shadow flourish — gradient IS the contrast
- Burn-in (zero animation, zero stagger, 1-frame opacity toggle)
- 2-line max body, 32-36 chars/line

**The competitive move:** no other AI caption tool ships documentary
restraint. Every preset in Veed/Submagic/Opus Clip is attention-grabby.
This direction is where the skill differentiates.

## When to apply

✅ **Good fit:**
- Documentary interview, field reporting, "talking head" in formal setting
- Content where the story carries emphasis (not typography)
- 16:9 landscape, 9:16 portrait, OR 1:1 — works all aspects
- Long-form content (5min+) where bouncy captions would exhaust the viewer

❌ **Wrong fit:**
- Short-form social hook clips → use high-energy-vlog
- Music video / lyrical → use lyrical-poem-on-wall or k-pop-lyric
- Product launch / keynote → use tech-keynote-confident
- Content with a clear single climax payoff → use champion (with crown)

## Rhetorical mode — important

This template has an opinionated **editorial** stance. It expects:

- **50-70% filler suppression.** Every word on screen is chosen. Drop
  um/uh/like/you know. Self-correction folding ON.
- **No per-word emphasis.** No bold highlights, no color accents, no size
  variation within a phrase. Let the content speak.
- **Long silences respected.** If speaker pauses 1.5s+, don't linger the
  prior caption. Let the silence breathe. 1.5s minimum gap between groups.
- **Breath-group segmentation.** Chunk on natural pauses ≥250ms.

The agent's job on this template is not typography — it's **editorial**.

## Layout decisions

| Field | What | Example (1920×1080) |
|---|---|---|
| `caption.top` | Y of the gradient bar top edge. Typically 75-85% of frame height. | `820` |
| `caption.height` | Gradient bar height. 180-240px usually. | `260` |
| `name_card.top` | Y of the speaker name card (optional). Typically upper-left 10% in. | `60` |
| `font_scale` | Multiplier on body 44px / name 30px. Scale for frame. | `1.0` for 1080p, `~1.25` for 1440p, `~0.75` for 720p |

## Slot assignment

Only 2 slots in this template:
- `body` — the dialogue captions (default)
- `name` — the speaker name card, rendered once in `crown_group` position

## Plan.json shape

```json
{
  "mode": "template",
  "template": "documentary-dignified",
  "caption_layer": "fg",
  "duration": 25.3, "fps": 24, "width": 1920, "height": 1080,
  "caption": { "top": 820, "height": 260 },
  "name_card": { "top": 60 },
  "font_scale": 1.0,
  "groups": [
    { "id": "cg-0", "slot": "body", "tone": "present",
      "in": 2.0, "out": 5.5,
      "words": [
        {"text": "I've", "start": 2.1, "end": 2.3},
        {"text": "had", "start": 2.4, "end": 2.6},
        {"text": "this", "start": 2.7, "end": 2.9},
        {"text": "kind", "start": 3.0, "end": 3.2},
        {"text": "of", "start": 3.25, "end": 3.3},
        {"text": "upbringing", "start": 3.4, "end": 4.5}
      ]}
  ],
  "crown_group": {
    "id": "name-card",
    "slot": "name",
    "in": 1.0, "out": 26.0,
    "words": [
      {"text": "Novak Djokovic", "start": 1.0, "end": 1.0}
    ]
  }
}
```

The name card uses `crown_group` as the carrier, rendered once at t=1s and
held for the whole clip. If no name card wanted, set `crown_group: null`.

## Key parameters the agent DOES NOT touch

Even in custom-mode thinking:
- Font (always Inter)
- Color (bone on gradient)
- Motion (always burn-in)
- Stagger (always 0)
- Emphasis styling (there is none)

If the user wants ANY of these changed → switch to `custom mode`. This
template's consistency IS the product.
