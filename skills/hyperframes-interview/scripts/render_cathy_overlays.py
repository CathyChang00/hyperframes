#!/usr/bin/env python3
"""Render reusable Cathy 16:9 RGBA layers from the versioned numeric preset."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

DEFAULT_PRESET = Path(__file__).resolve().parents[1] / "assets/cathy-interview-16x9.json"


def load_font(style):
    font = ImageFont.truetype(
        style["font_path"], style["font_size"], index=style["font_index"]
    )
    expected = (style["font_family"], style["font_style"])
    if font.getname() != expected:
        raise ValueError(f"Expected {expected}, got {font.getname()}; no silent font substitution")
    return font


def render(kind, text, preset_path=DEFAULT_PRESET):
    preset_path = Path(preset_path)
    p = json.loads(preset_path.read_text())
    size = (p["canvas"]["width"], p["canvas"]["height"])
    layer = Image.new("RGBA", size)
    s = p[kind]
    if kind == "watermark":
        asset = preset_path.parent / s["asset"]
        if hashlib.sha256(asset.read_bytes()).hexdigest() != s["sha256"]:
            raise ValueError("Watermark asset hash differs from approved preset")
        with Image.open(asset) as source:
            mark = source.convert("RGBA")
        if mark.size != (s["width"], s["height"]):
            raise ValueError("Watermark dimensions differ from preset")
        layer.alpha_composite(mark, (s["x"], s["y"]))
        return layer

    if not text or not text.strip():
        raise ValueError("Text is required")
    lines = text.splitlines()
    if len(lines) > s["max_lines"]:
        raise ValueError(f"{kind} supports at most {s['max_lines']} lines")
    font = load_font(s)
    draw = ImageDraw.Draw(layer)
    if kind == "subtitle":
        width = draw.textlength(text, font=font)
        if width + 2 * s["padding_x"] > s["max_card_width"]:
            raise ValueError("Split this caption at real word timings; do not shrink or wrap it")
        x, y = s["position"]
        left = x - width / 2
        draw.rectangle(
            (left - s["padding_x"], s["box_top"], left + width + s["padding_x"], s["box_bottom_inclusive"]),
            fill=tuple(s["background_rgba"]),
        )
        draw.text((x, y), text, font=font, fill=s["color"], anchor=s["anchor"])
        return layer

    x, y = s["position"]
    points = [(x, y + i * s["line_step"]) for i in range(len(lines))]
    boxes = [draw.textbbox(point, line, font=font, anchor=s["anchor"], stroke_width=s["stroke_width"])
             for point, line in zip(points, lines)]
    if any(a < 0 or b < 0 or c > size[0] or d > p["subtitle"]["reserved_top"] for a, b, c, d in boxes):
        raise ValueError("Title exceeds safe area; shorten copy or record a project layout override")
    backing = s["backing"]
    box = (min(b[0] for b in boxes) - backing["padding_x"],
           min(b[1] for b in boxes) - backing["padding_y"],
           max(b[2] for b in boxes) + backing["padding_x"],
           max(b[3] for b in boxes) + backing["padding_y"])
    mask = Image.new("L", size)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=backing["radius"], fill=backing["alpha"])
    layer = Image.new("RGBA", size, (*backing["color"], 0))
    layer.putalpha(mask.filter(ImageFilter.GaussianBlur(backing["blur"])))
    shadow = Image.new("RGBA", size)
    sd = ImageDraw.Draw(shadow)
    sh = s["shadow"]
    for (x, y), line in zip(points, lines):
        sd.text((x, y + sh["offset_y"]), line, font=font, anchor=s["anchor"],
                fill=tuple(sh["rgba"]), stroke_width=sh["stroke_width"], stroke_fill=tuple(sh["rgba"]))
    layer.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(sh["blur"])))
    draw = ImageDraw.Draw(layer)
    for point, line in zip(points, lines):
        draw.text(point, line, font=font, anchor=s["anchor"], fill=s["color"],
                  stroke_width=s["stroke_width"], stroke_fill=s["color"])
    return layer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["watermark", "subtitle", "chapter"])
    parser.add_argument("--text")
    parser.add_argument("--preset", type=Path, default=DEFAULT_PRESET)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        layer = render(args.kind, args.text, args.preset)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        layer.save(args.out)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(args.out.resolve())


if __name__ == "__main__":
    main()
