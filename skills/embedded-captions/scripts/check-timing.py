#!/usr/bin/env python3
"""Verify plan.json word timings align with transcript.json.

Reads <project>/plan.json and <project>/transcript.json and reports any
word whose start time drifts > DRIFT_TOL from the matching transcript word.

Usage: python3 check-timing.py <project-dir> [--strict]
  --strict : exit 1 on any drift > DRIFT_TOL (for CI / pre-render gate)

Packed word entries (e.g. {"text": "FUTURE OF"} or "IT<br>ALL") are flagged
because the second/third sub-word inherits the first sub-word's timestamp
instead of getting its own — they should be split into separate word
entries for accurate per-word animation.

Creative substitutions (caption text that doesn't appear verbatim in the
transcript, e.g. "15%" for "fifteen percent") are detected by presence in
CREATIVE_SUBS and skipped from drift checking. Add new substitutions as
needed.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

DRIFT_TOL = 0.08  # seconds — anything above this is audibly off

# caption text → list of transcript words it replaces (all lowercase, no punct)
CREATIVE_SUBS: dict[str, list[str]] = {
    "15%": ["fifteen", "percent"],
    "1/3": ["one", "third"],
    "2x":  ["two", "times"],
}

def norm(s: str) -> str:
    return s.strip(" .,?!\"'").lower()

def split_packed(text: str) -> list[str]:
    return [p for p in re.split(r"<br>|\s+", text) if p]

def estimate_vertical_band(css: str, words: list[dict], frame_w: int, frame_h: int) -> tuple[float, float] | None:
    """Return (top_pct, bottom_pct) of this group's rendered bbox, 0–100 scale.

    Approximates line count by summing word widths (using 0.72 char-multiplier
    matching typographic-moves.md), then wrapping at frame width. This is an
    over-estimate for tight layouts but catches the obvious collisions.
    Returns None if CSS is missing positioning info (group may use default).
    """
    top_m = re.search(r"top:\s*(-?[\d.]+)%", css)
    if not top_m:
        return None
    top_pct = float(top_m.group(1))
    size_m = re.search(r"font-size:\s*calc\(\s*([\d.]+)\s*\*\s*var\(--h\)\s*\)", css)
    font_px = float(size_m.group(1)) * frame_h if size_m else 0.05 * frame_h
    lh_m = re.search(r"line-height:\s*([\d.]+)", css)
    line_height = float(lh_m.group(1)) if lh_m else 1.1
    uppercase = "uppercase" in css.lower() or "text-transform:" in css.lower() and "uppercase" in css.lower()
    # rough char-width multiplier at this weight; uppercase 900 is ~0.72, else ~0.6
    char_w = 0.72 if uppercase else 0.60
    # estimate lines by wrapping
    line_count = 1
    cur_line_w = 0.0
    space_w = font_px * 0.3
    for w in words:
        # split on <br> — each <br> forces a new line
        parts = re.split(r"<br>", w["text"])
        for i, part in enumerate(parts):
            part_w = len(part) * font_px * char_w
            if i > 0:
                line_count += 1
                cur_line_w = part_w
            else:
                test_w = cur_line_w + (space_w if cur_line_w > 0 else 0) + part_w
                if test_w > frame_w and cur_line_w > 0:
                    line_count += 1
                    cur_line_w = part_w
                else:
                    cur_line_w = test_w
    height_px = line_count * font_px * line_height
    bottom_pct = top_pct + 100.0 * height_px / frame_h
    return (top_pct, bottom_pct)

def check(project: Path, strict: bool) -> int:
    plan = json.loads((project / "plan.json").read_text())
    t = json.loads((project / "transcript.json").read_text())
    seq = [(norm(w["text"]), w["start"], w["end"])
           for w in t.get("words", []) if w.get("type") == "word"]

    issues: list[str] = []
    # Collision check: any two groups whose time windows overlap AND whose
    # vertical bboxes overlap will render as text-on-text. Intentional
    # overlap can be silenced by adding { "allow_overlap": true } to one of
    # the groups in plan.json (e.g. for deliberate layered typography).
    frame_w = plan.get("width", 720)
    frame_h = plan.get("height", 1290)
    groups = plan.get("groups", [])
    bands = []
    for g in groups:
        # Plane-mode groups: the plane container owns layout, so bbox from
        # per-group CSS is meaningless (there's no top%/left% on the group).
        # Trust the plane's flex/grid to avoid collisions; skip collision
        # check for grouped-in-plane caps.
        if g.get("plane"):
            bands.append((g.get("id", "?"), g.get("in"), g.get("out"), None, True))
            continue
        band = estimate_vertical_band(g.get("css", ""), g.get("words", []), frame_w, frame_h)
        bands.append((g.get("id", "?"), g.get("in"), g.get("out"), band, g.get("allow_overlap", False)))
    for i in range(len(bands)):
        gi, ai, bi, bbi, ok_i = bands[i]
        if bbi is None:
            continue
        for j in range(i + 1, len(bands)):
            gj, aj, bj, bbj, ok_j = bands[j]
            if bbj is None:
                continue
            if ok_i or ok_j:
                continue
            t_overlap = min(bi, bj) - max(ai, aj)
            if t_overlap <= 0.05:
                continue
            v_overlap = min(bbi[1], bbj[1]) - max(bbi[0], bbj[0])
            if v_overlap > 2.0:  # >2% of frame height = visible collision
                issues.append(
                    f"[{gi}↔{gj}] groups overlap in time ({max(ai,aj):.2f}–{min(bi,bj):.2f}s) "
                    f"AND vertically (band {max(bbi[0],bbj[0]):.0f}%–{min(bbi[1],bbj[1]):.0f}% "
                    f"of frame) — reposition one or add \"allow_overlap\": true if deliberate."
                )

    ti = 0  # cursor into transcript
    for g in plan.get("groups", []):
        gid = g.get("id", "?")
        # Group window must not clamp word timings. A word whose start is
        # earlier than group.in won't animate until the group mounts — it gets
        # silently delayed by (group.in - word.start). Same for group.out: any
        # word.end after group.out is clipped. Both destroy sync.
        gin = g.get("in")
        gout = g.get("out")
        word_starts = [w["start"] for w in g.get("words", [])]
        word_ends = [w["end"] for w in g.get("words", [])]
        if word_starts and gin is not None:
            earliest = min(word_starts)
            if earliest < gin - 0.01:
                issues.append(
                    f"[{gid}] group.in={gin:.2f} but earliest word starts at {earliest:.2f} "
                    f"— word will be delayed by {gin - earliest:+.2f}s. Lower group.in."
                )
        if word_ends and gout is not None:
            latest = max(word_ends)
            if latest > gout + 0.01:
                issues.append(
                    f"[{gid}] group.out={gout:.2f} but latest word ends at {latest:.2f} "
                    f"— word will be clipped. Raise group.out."
                )
        for w in g.get("words", []):
            parts_raw = split_packed(w["text"])
            parts = [norm(p) for p in parts_raw]
            for pi, part in enumerate(parts):
                if not part:
                    continue
                if part in CREATIVE_SUBS:
                    # consume the substituted transcript words
                    for sub in CREATIVE_SUBS[part]:
                        j = next((k for k in range(ti, len(seq)) if seq[k][0] == sub), -1)
                        if j >= 0:
                            ti = j + 1
                    continue
                found = next((j for j in range(ti, len(seq)) if seq[j][0] == part), -1)
                if found < 0:
                    found = next((j for j in range(len(seq)) if seq[j][0] == part), -1)
                if found < 0:
                    issues.append(f"[{gid}] {part!r}: NOT IN TRANSCRIPT (plan start={w['start']:.3f})")
                    continue
                ts = seq[found][1]
                ti = found + 1
                if pi == 0:
                    drift = w["start"] - ts
                    if abs(drift) > DRIFT_TOL:
                        issues.append(
                            f"[{gid}] {part!r}: plan={w['start']:.3f} transcript={ts:.3f} drift {drift:+.3f}s")
                else:
                    issues.append(
                        f"[{gid}] {part!r} packed with {parts[0]!r}: transcript={ts:.3f} but entry has no distinct timing — split into separate word entries")

    name = project.name
    if not issues:
        print(f"{name}: timing OK ✓ ({len(seq)} transcript words)")
        return 0
    print(f"{name}: {len(issues)} timing issue(s):")
    for i in issues:
        print(f"  {i}")
    return 1 if strict else 0

def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--strict"]
    strict = "--strict" in sys.argv
    if not args:
        print("usage: check-timing.py <project-dir> [--strict]", file=sys.stderr)
        return 2
    return check(Path(args[0]).resolve(), strict)

if __name__ == "__main__":
    sys.exit(main())
