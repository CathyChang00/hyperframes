#!/usr/bin/env python3
"""Plan a contained source frame and one Chinese line below baked English.

No media is rendered. Source dimensions must already account for rotation and
sample aspect ratio. Coordinates use exclusive right/bottom edges. Style values
come from the preset, with explicit CLI overrides; they scale from the preset's
reference canvas width to the output width.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys


def rounded(value: float) -> int:
    return math.floor(value + 0.5)


def aspect(width: int, height: int) -> str:
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def read_style(args: argparse.Namespace) -> dict:
    try:
        preset = json.loads(args.preset.read_text(encoding="utf-8"))
        values = {
            "reference_width": preset["canvas"]["width"],
            "zh_height": preset["chinese"]["box_height_px"],
            "gap": preset["chinese"]["gap_below_english_px"],
            "font_size": preset["chinese"]["font_size_px"],
            "max_card_width": preset["chinese"]["max_card_width_px"],
        }
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Cannot read required layout preset fields from {args.preset}: {exc}; no fallback was used.") from exc
    for key, value in values.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < (0 if key == "gap" else 1):
            raise ValueError(f"Preset field {key} must be {'nonnegative' if key == 'gap' else 'positive'} integer pixels; no fallback was used.")
    for key in ("zh_height", "gap", "font_size", "max_card_width"):
        if getattr(args, key) is not None:
            values[key] = getattr(args, key)
    return values


def plan(args: argparse.Namespace) -> dict:
    style = read_style(args)
    sw, sh = args.source
    cw, ch = args.canvas
    if min(sw, sh, cw, ch) <= 0:
        raise ValueError("Source and canvas dimensions must be positive.")
    if cw % 2 or ch % 2:
        raise ValueError("Use even canvas dimensions for video output; no dimensions were silently changed.")
    if min(style["zh_height"], style["font_size"], style["max_card_width"]) <= 0 or style["gap"] < 0:
        raise ValueError("Style sizes must be positive and gap must be nonnegative.")
    x0, y0, x1, y1 = args.english_box
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
        raise ValueError("English box coordinates must be finite.")
    if not (0 <= x0 < x1 <= sw and 0 <= y0 < y1 <= sh):
        raise ValueError("English box must be a nonempty measured rectangle inside the normalized source picture.")

    # Keep the exact content transform uniform. The even raster container may
    # have a fractional spare border; it is not an instruction to stretch to it.
    scale = min(cw / sw, ch / sh)
    exact_w, exact_h = sw * scale, sh * scale
    exact_x, exact_y = (cw - exact_w) / 2, (ch - exact_h) / 2
    raster_w = min(cw, 2 * math.ceil((exact_w - 1e-9) / 2))
    raster_h = min(ch, 2 * math.ceil((exact_h - 1e-9) / 2))
    raster_x, raster_y = (cw - raster_w) // 2, (ch - raster_h) // 2
    english = [math.floor(exact_x + x0 * scale + 1e-9),
               math.floor(exact_y + y0 * scale + 1e-9),
               math.ceil(exact_x + x1 * scale - 1e-9),
               math.ceil(exact_y + y1 * scale - 1e-9)]
    style_scale = cw / style["reference_width"]
    zh_height = max(1, rounded(style["zh_height"] * style_scale))
    gap = rounded(style["gap"] * style_scale)
    font_size = max(1, rounded(style["font_size"] * style_scale))
    max_width = max(1, rounded(style["max_card_width"] * style_scale))
    anchor_bottom = english[3] if args.zh_placement == "below-english" else raster_y + raster_h
    zh_top = anchor_bottom + gap
    left = (cw - max_width) // 2
    chinese = [left, zh_top, left + max_width, zh_top + zh_height]
    out_of_bounds = left < 0 or chinese[2] > cw or chinese[3] > ch
    if out_of_bounds:
        raise ValueError(
            f"Chinese card {chinese} does not fit canvas {cw}x{ch}. "
            "Re-layout editable captions or choose a taller/wider canvas; "
            "do not crop the source, move baked English, or silently shrink type."
        )
    if zh_top < english[3]:
        raise ValueError("Chinese would overlap English; re-layout captions without changing the source picture.")
    return {
        "status": "planned",
        "preset": str(args.preset.resolve()),
        "coordinate_system": "pixels; boxes are x0,y0,x1,y1 with exclusive right/bottom",
        "source": {"size": [sw, sh], "display_aspect_ratio": aspect(sw, sh),
                   "assumption": "rotation and sample aspect ratio already normalized"},
        "canvas": {"size": [cw, ch], "display_aspect_ratio": aspect(cw, ch),
                   "orientation": "landscape" if cw > ch else "portrait" if ch > cw else "square"},
        "foreground": [raster_x, raster_y, raster_w, raster_h],
        "foreground_format": "x,y,width,height; even-sized raster container",
        "source_transform": {"uniform_scale": scale,
                             "exact_content_rect": [exact_x, exact_y, exact_w, exact_h],
                             "raster_spare_pixels": [raster_w - exact_w, raster_h - exact_h],
                             "render_note": "Preserve source aspect ratio using the uniform transform; pad fractional/even rounding instead of stretching content to the raster container."},
        "padding": {"top": raster_y, "bottom": ch - raster_y - raster_h,
                    "left": raster_x, "right": cw - raster_x - raster_w},
        "english_box": english,
        "chinese": {"placement": args.zh_placement, "max_card_box": chinese,
                    "top": zh_top, "height": zh_height, "gap_from_anchor": gap,
                    "font_size": font_size, "max_card_width": max_width,
                    "alignment": "center", "max_lines": 1,
                    "style_reference_width": style["reference_width"]},
        "safe_margins": {"chinese_left": left, "chinese_right": cw - chinese[2],
                         "chinese_bottom": ch - chinese[3],
                         "english_to_chinese": zh_top - english[3]},
        "out_of_bounds": False,
        "checks_remaining": ["Measure actual text width and glyph coverage with the selected font.",
                             "Inspect final frames for faces, titles, name cards, and platform UI collisions.",
                             "Verify cue timing and one line per language; geometry alone does not prove subtitle correctness."],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=int, nargs=2, required=True, metavar=("W", "H"))
    parser.add_argument("--canvas", type=int, nargs=2, required=True, metavar=("W", "H"))
    parser.add_argument("--english-box", type=float, nargs=4, required=True, metavar=("X0", "Y0", "X1", "Y1"))
    parser.add_argument("--preset", type=Path, default=Path(__file__).resolve().parents[1] / "assets/cathy-bilingual-4x3.json", help="Layout style JSON; required fields must exist even when CLI overrides are used")
    parser.add_argument("--zh-height", type=int, help="Override Chinese card height at the preset reference width")
    parser.add_argument("--gap", type=int, help="Override gap at the preset reference width")
    parser.add_argument("--font-size", type=int, help="Override font size at the preset reference width")
    parser.add_argument("--max-card-width", type=int, help="Override maximum card width at the preset reference width")
    parser.add_argument("--zh-placement", choices=("below-english", "below-picture"), default="below-english")
    args = parser.parse_args()
    try:
        result = plan(args)
    except ValueError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
