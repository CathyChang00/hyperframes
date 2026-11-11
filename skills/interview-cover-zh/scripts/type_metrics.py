#!/usr/bin/env python3
"""Measure real title ink, not font boxes or a wordmark's taller mascot.

Requires Pillow; text measurements also require fontTools for missing-glyph checks.
Measurements use alpha >= 128 and exclusive right/bottom bounds.
The logo letter ROI must be chosen visually; this tool does not infer its content.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ALPHA_THRESHOLD = 128
MAX_FONT_SIZE = 4096
MAX_RENDER_PIXELS = 32_000_000


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def ink_box(alpha: Image.Image) -> tuple[int, int, int, int]:
    result = alpha.point(lambda a: 255 if a >= ALPHA_THRESHOLD else 0).getbbox()
    if result is None:
        raise ValueError("No visible ink at alpha >= 128; check the text or letter ROI.")
    return result


def checked_size(width: int, height: int) -> None:
    if width < 1 or height < 1 or width * height > MAX_RENDER_PIXELS:
        raise ValueError("Requested render is empty or exceeds 32 million pixels; use a shorter title or smaller size.")


@lru_cache(maxsize=16)
def font_coverage(font_path: Path, index: int) -> frozenset[int]:
    try:
        from fontTools.ttLib import TTFont, TTLibError
    except ImportError as exc:
        raise ValueError("The text command requires fontTools for glyph checks. Install fonttools in the selected project environment; no global installation or font substitution was attempted.") from exc
    try:
        with TTFont(str(font_path), fontNumber=index, lazy=True) as source:
            cmap = source.getBestCmap()
            if not cmap:
                raise ValueError("The requested font has no usable Unicode cmap; glyph coverage cannot be verified.")
            return frozenset(codepoint for codepoint, glyph in cmap.items() if glyph != ".notdef")
    except (OSError, TTLibError, IndexError) as exc:
        raise ValueError(f"Cannot inspect glyph coverage for the requested font/index: {exc}") from exc


def measure_text(font_path: Path, text: str, size: int, index: int) -> tuple[dict, Image.Image]:
    if not 1 <= size <= MAX_FONT_SIZE:
        raise ValueError(f"Font size must be between 1 and {MAX_FONT_SIZE}.")
    if index < 0:
        raise ValueError("Font collection index cannot be negative.")
    if not text.strip() or "\n" in text or "\r" in text:
        raise ValueError("Supply one nonempty line; measure each line separately.")
    if not font_path.is_file():
        raise ValueError(f"Font file does not exist: {font_path}")
    try:
        font = ImageFont.truetype(str(font_path), size, index=index)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot load the requested font/index; no fallback was used: {exc}") from exc
    coverage = font_coverage(font_path.resolve(), index)
    missing = sorted({char for char in text if not char.isspace() and ord(char) not in coverage}, key=ord)
    if missing:
        description = ", ".join(f"{char!r} (U+{ord(char):04X})" for char in missing)
        raise ValueError(f"The requested font/index lacks glyphs for: {description}. Choose a font covering every character; no tofu glyph or fallback was measured.")
    declared = font.getbbox(text, anchor="ls")
    pad = max(8, math.ceil(size / 8))
    width = declared[2] - declared[0] + 2 * pad
    height = declared[3] - declared[1] + 2 * pad
    checked_size(width, height)
    baseline = (pad - declared[0], pad - declared[1])
    rendered = Image.new("RGBA", (width, height))
    ImageDraw.Draw(rendered).text(baseline, text, font=font, anchor="ls", fill=(255, 255, 255, 255))
    bounds = ink_box(rendered.getchannel("A"))
    if bounds[0] == 0 or bounds[1] == 0 or bounds[2] == width or bounds[3] == height:
        raise ValueError("Ink touches the render boundary; increase padding before using this measurement.")
    ascent, descent = font.getmetrics()
    metrics = {
        "font": str(font_path.resolve()), "font_name": font.getname(), "font_index": index,
        "text": text, "font_size": size, "alpha_threshold": ALPHA_THRESHOLD,
        "ink_bbox": bounds, "ink_height": bounds[3] - bounds[1], "ink_width": bounds[2] - bounds[0],
        "baseline_xy": baseline,
        "ink_bbox_from_baseline": [bounds[0] - baseline[0], bounds[1] - baseline[1], bounds[2] - baseline[0], bounds[3] - baseline[1]],
        "font_bbox_from_baseline": declared, "advance_width": font.getlength(text),
        "ascent": ascent, "descent": descent, "render_size": [width, height], "clipped": False,
        "glyph_coverage_checked": True,
    }
    return metrics, rendered


def fit_text(font_path: Path, text: str, target: int, index: int) -> tuple[dict, Image.Image]:
    if target > 2048:
        raise ValueError("Target ink height must be between 1 and 2048 pixels.")
    measured: dict[int, tuple[dict, Image.Image]] = {}

    def get(size: int) -> tuple[dict, Image.Image]:
        if size not in measured:
            measured[size] = measure_text(font_path, text, size, index)
        return measured[size]

    # Bracket around a real measurement, then inspect the local pixel-hinting steps.
    sample = get(100)[0]["ink_height"]
    high = min(MAX_FONT_SIZE, max(16, math.ceil(target * 100 / sample * 1.2)))
    while get(high)[0]["ink_height"] < target and high < MAX_FONT_SIZE:
        high = min(MAX_FONT_SIZE, high * 2)
    low = 1
    while low < high:
        mid = (low + high) // 2
        if get(mid)[0]["ink_height"] < target:
            low = mid + 1
        else:
            high = mid
    candidates = range(max(1, low - 8), min(MAX_FONT_SIZE, low + 8) + 1)
    selected = min(candidates, key=lambda size: (abs(get(size)[0]["ink_height"] - target), size))
    metrics, rendered = get(selected)
    metrics.update(target_ink_height=target, target_delta=metrics["ink_height"] - target)
    return metrics, rendered


def parse_roi(value: str) -> tuple[int, int, int, int]:
    try:
        values = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("letter ROI must contain four integers: x0,y0,x1,y1") from exc
    if len(values) != 4:
        raise argparse.ArgumentTypeError("letter ROI must contain four integers: x0,y0,x1,y1")
    return values


def measure_logo(path: Path, roi: tuple[int, int, int, int], target: int | None) -> tuple[dict, Image.Image]:
    if not path.is_file():
        raise ValueError(f"Image file does not exist: {path}")
    source = Image.open(path)
    if "A" not in source.getbands() and "transparency" not in source.info:
        raise ValueError("Logo has no transparency. Remove or mask its background first; a white rectangle is not letter ink.")
    image = source.convert("RGBA")
    alpha = image.getchannel("A")
    if alpha.getextrema()[0] >= ALPHA_THRESHOLD:
        raise ValueError("Logo has no transparent background at alpha < 128. Remove its background instead of using an opaque or uniformly translucent RGBA rectangle.")
    x0, y0, x1, y1 = roi
    if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
        raise ValueError(f"Letter ROI {roi} is outside the {image.width}x{image.height} image or has no area.")
    full = ink_box(alpha)
    local = ink_box(alpha.crop(roi))
    letters = (local[0] + x0, local[1] + y0, local[2] + x0, local[3] + y0)
    letter_height = letters[3] - letters[1]
    metrics = {
        "image": str(path.resolve()), "source_size": image.size, "alpha_threshold": ALPHA_THRESHOLD,
        "full_ink_bbox": full, "full_ink_height": full[3] - full[1], "letter_roi": roi,
        "letter_ink_bbox": letters, "letter_ink_height": letter_height,
        "roi_semantics": "User-selected letters only; mascot exclusion is not inferred automatically.",
    }
    rendered = image
    if target is not None:
        scale = target / letter_height
        dimensions = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        checked_size(*dimensions)
        rendered = image.resize(dimensions, Image.Resampling.LANCZOS)
        sx, sy = rendered.width / image.width, rendered.height / image.height
        scaled_roi = (math.floor(x0 * sx), math.floor(y0 * sy), min(rendered.width, math.ceil(x1 * sx)), min(rendered.height, math.ceil(y1 * sy)))
        local_scaled = ink_box(rendered.getchannel("A").crop(scaled_roi))
        achieved = local_scaled[3] - local_scaled[1]
        metrics.update(target_letter_height=target, nominal_scale=scale, rendered_size=dimensions,
                       rendered_letter_roi=scaled_roi, rendered_letter_height=achieved, target_delta=achieved - target)
    return metrics, rendered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    text = sub.add_parser("text", help="Measure a font's visible single-line glyphs.")
    text.add_argument("--font", type=Path, required=True)
    text.add_argument("--text", required=True)
    text.add_argument("--index", type=int, default=0)
    sizing = text.add_mutually_exclusive_group(required=True)
    sizing.add_argument("--size", type=positive_int)
    sizing.add_argument("--target-height", type=positive_int)
    text.add_argument("--preview", type=Path, help="Optional transparent PNG of the measured line.")
    logo = sub.add_parser("logo", help="Measure a visually selected letter region in a transparent logo.")
    logo.add_argument("--image", type=Path, required=True)
    logo.add_argument("--letters", type=parse_roi, required=True, metavar="x0,y0,x1,y1")
    logo.add_argument("--target-height", type=positive_int)
    logo.add_argument("--preview", type=Path, help="Optional transparent PNG, scaled when a target is given.")
    args = parser.parse_args()
    try:
        if args.command == "text":
            metrics, rendered = (fit_text(args.font, args.text, args.target_height, args.index) if args.target_height is not None
                                 else measure_text(args.font, args.text, args.size, args.index))
        else:
            metrics, rendered = measure_logo(args.image, args.letters, args.target_height)
        if args.preview:
            if args.preview.suffix.lower() != ".png":
                raise ValueError("Preview must use .png to preserve the measured alpha.")
            rendered.save(args.preview)
            metrics["preview"] = str(args.preview.resolve())
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
