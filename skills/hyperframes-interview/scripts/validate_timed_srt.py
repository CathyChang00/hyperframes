#!/usr/bin/env python3
"""Validate production SRT timing, line count, duration, and optional card width."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


TIMING = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3}) --> "
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$"
)


def seconds(parts: tuple[str, ...]) -> float:
    h, m, s, ms = map(int, parts)
    return h * 3600 + m * 60 + s + ms / 1000


def parse_srt(path: Path):
    cues = []
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip())
    for block_number, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        if len(lines) < 3:
            raise ValueError(f"block {block_number} is incomplete")
        match = TIMING.match(lines[1].strip())
        if not match:
            raise ValueError(f"block {block_number} has invalid timing: {lines[1]}")
        start = seconds(match.groups()[:4])
        end = seconds(match.groups()[4:])
        cues.append((lines[0].strip(), start, end, lines[2:]))
    return cues


def video_duration(path: Path) -> float:
    if not path.is_file():
        raise FileNotFoundError(f"video not found: {path}")
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        message = result.stderr.strip() or "ffprobe failed"
        raise RuntimeError(f"cannot read video duration: {message}")
    return float(result.stdout.strip())


def card_widths(cues, font_path: Path, font_size: int, padding_x: int):
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(str(font_path), font_size)
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    widths = []
    for cue_id, _, _, lines in cues:
        text_width = max(
            draw.textbbox((0, 0), line, font=font)[2] for line in lines
        )
        widths.append((text_width + padding_x * 2, cue_id))
    return widths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("srt", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--max-lines", type=int, default=2)
    parser.add_argument("--end-tolerance", type=float, default=0.25)
    parser.add_argument("--font", type=Path)
    parser.add_argument("--font-size", type=int, default=40)
    parser.add_argument("--padding-x", type=int, default=14)
    parser.add_argument("--max-card-width", type=int, default=940)
    args = parser.parse_args()

    try:
        cues = parse_srt(args.srt)
    except (OSError, ValueError) as error:
        print(json.dumps({"errors": [str(error)]}, ensure_ascii=False, indent=2))
        return 2
    errors = []
    one_line = 0
    two_line = 0
    previous_end = 0.0
    for cue_id, start, end, lines in cues:
        if end <= start:
            errors.append(f"cue {cue_id}: end <= start")
        if start < previous_end - 0.0005:
            errors.append(
                f"cue {cue_id}: overlaps previous cue by {previous_end - start:.3f}s"
            )
        if len(lines) > args.max_lines:
            errors.append(f"cue {cue_id}: {len(lines)} lines > {args.max_lines}")
        one_line += len(lines) == 1
        two_line += len(lines) == 2
        previous_end = max(previous_end, end)

    duration = None
    if args.video:
        try:
            duration = video_duration(args.video)
        except (OSError, ValueError, RuntimeError) as error:
            errors.append(str(error))
            duration = None
        if duration is None:
            report = {
                "cues": len(cues),
                "one_line": one_line,
                "two_line": two_line,
                "last_cue_end": cues[-1][2],
                "video_duration": None,
                "max_card_width": None,
                "errors": errors,
            }
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1
        if cues[-1][2] > duration + args.end_tolerance:
            errors.append(
                f"last cue ends at {cues[-1][2]:.3f}s, video ends at {duration:.3f}s"
            )

    max_width = None
    if args.font:
        widths = card_widths(cues, args.font, args.font_size, args.padding_x)
        max_width, widest_cue = max(widths)
        if max_width > args.max_card_width:
            errors.append(
                f"cue {widest_cue}: card width {max_width}px > {args.max_card_width}px"
            )

    report = {
        "cues": len(cues),
        "one_line": one_line,
        "two_line": two_line,
        "last_cue_end": cues[-1][2],
        "video_duration": duration,
        "max_card_width": max_width,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
