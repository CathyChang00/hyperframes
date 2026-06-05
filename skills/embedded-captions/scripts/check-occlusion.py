#!/usr/bin/env python3
"""
Pre-render occlusion gate.

Reads plan.json + frames_fg/*.png (the RVM matte), estimates each caption
group's screen bbox from CSS, and computes what fraction of each caption
rect is covered by the subject silhouette during the group's time window.

Why: we kept shipping renders where a caption sits on the forehead /
shoulder and the viewer sees only half the word. The matte tells us exactly
where the subject is at every frame — so we can catch it BEFORE burning a
render cycle.

Usage:
    python check-occlusion.py <project-dir> [--strict] [--threshold 0.35]

Exits 0 on pass, 2 on fail (with --strict).

Output: a per-group table
    cg-1 BLACKMAGIC POCKET 4K          bbox=(830,180,420,240)  occl=42%  FAIL
    cg-0 So I'm in this Facebook group  bbox=(830,40,420,140)   occl= 8%  OK

Approximations (NOT a browser-accurate layout engine):
  - Font-size parsed from `calc(K * var(--h))` or `Npx`.
  - Char-width ratio: 0.70 for uppercase+bold, 0.55 for italic, 0.58 otherwise.
  - Line-wrap: greedy fit into plane-width.
  - Stack-order: groups with the same plane + overlapping (in, out) stack
    flex-column from plane.top, separated by `gap`.
  - Right-aligned (flex-end) planes place caps hugging plane.right.

Enough to catch "caption sitting on the face" — not enough to distinguish
5% vs 8% overlap. Calibrate the threshold around 30-40% for "fail".
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("[check-occlusion] missing deps: pip install pillow numpy", file=sys.stderr)
    sys.exit(3)


def parse_calc_h(expr: str, height_px: int) -> float | None:
    m = re.search(r"calc\(\s*([\d.]+)\s*\*\s*var\(--h\)\s*\)", expr)
    if m:
        return float(m.group(1)) * height_px
    m = re.search(r"([\d.]+)\s*px", expr)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d.]+)\s*%", expr)
    if m:
        return float(m.group(1)) / 100 * height_px
    return None


def parse_dim(val: str | None, ref_px: int) -> float | None:
    if val is None:
        return None
    val = val.strip()
    m = re.match(r"([\d.]+)\s*px", val)
    if m:
        return float(m.group(1))
    m = re.match(r"([\d.]+)\s*%", val)
    if m:
        return float(m.group(1)) / 100 * ref_px
    return None


def css_dict(css: str) -> dict[str, str]:
    out = {}
    for kv in (css or "").split(";"):
        if ":" not in kv:
            continue
        k, v = kv.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def parse_plane(plane_css: str, width: int, height: int) -> dict:
    d = css_dict(plane_css)
    top = parse_dim(d.get("top", "0"), height) or 0
    left = parse_dim(d.get("left"), width)
    right = parse_dim(d.get("right"), width)
    w_attr = parse_dim(d.get("width"), width)
    if w_attr is not None:
        plane_width = w_attr
        if left is None and right is not None:
            left = width - right - plane_width
        if left is None:
            left = 0
    else:
        if left is None:
            left = 0
        plane_width = width - left - (right or 0)

    gap = 10.0
    m = re.search(r"gap:\s*(\d+)", plane_css or "")
    if m:
        gap = float(m.group(1))

    align = "flex-start"
    m = re.search(r"align-items:\s*([\w-]+)", plane_css or "")
    if m:
        align = m.group(1)

    return {
        "top": top,
        "left": left,
        "width": plane_width,
        "gap": gap,
        "align": align,
    }


def estimate_group_height(words: list[dict], css: str, plane_width: float, height_px: int) -> tuple[float, float, float]:
    """Return (height_px, font_px, width_px_of_longest_line).

    Handles overflow: if any single word (or short joinable run) is wider
    than plane_width, the browser does NOT wrap mid-word under default
    overflow-wrap:normal — it overflows the container. We report the
    actual occupied width (max of plane_width and longest unwrappable
    token), which the caller uses to compute a bbox that may extend
    outside the plane's bounds toward the subject.
    """
    d = css_dict(css)
    font_px = parse_calc_h(d.get("font-size", ""), height_px) or 0.08 * height_px
    try:
        line_height = float(d.get("line-height", "1.0"))
    except ValueError:
        line_height = 1.0
    is_upper = "uppercase" in (d.get("text-transform", ""))
    is_italic = "italic" in (d.get("font-style", ""))
    weight_m = re.match(r"(\d+)", d.get("font-weight", "400"))
    weight = int(weight_m.group(1)) if weight_m else 400
    is_bold = weight >= 700

    # Inter metrics (calibrated from observed rendered frames).
    # Uppercase is wider than mixed case; bold widens further.
    if is_upper and is_bold:
        char_ratio = 0.62
    elif is_upper:
        char_ratio = 0.55
    elif is_italic:
        char_ratio = 0.48
    else:
        char_ratio = 0.50

    text = " ".join(str(w.get("text", "")) for w in words)
    if is_upper:
        text = text.upper()

    char_w_px = font_px * char_ratio
    chars_per_line = max(1, int(plane_width / char_w_px))
    lines = 1
    col = 0
    longest_line_chars = 0
    longest_word = 0
    for word in text.split():
        wlen = len(word)
        longest_word = max(longest_word, wlen)
        if col == 0:
            col = wlen
        elif col + 1 + wlen <= chars_per_line:
            col += 1 + wlen
        else:
            longest_line_chars = max(longest_line_chars, col)
            lines += 1
            col = wlen
    longest_line_chars = max(longest_line_chars, col)
    # If any single word exceeds chars_per_line, that word OVERFLOWS the
    # plane horizontally (no mid-word break under default wrap). Occupied
    # width expands to fit the longest word.
    effective_line_chars = max(longest_line_chars, longest_word)
    height = lines * font_px * line_height
    width = effective_line_chars * char_w_px
    return height, font_px, width


def groups_active_at(groups: list[dict], t: float) -> list[dict]:
    return [g for g in groups if g["in"] <= t < g["out"]]


def groups_before_in_block(groups: list[dict], target: dict) -> list[dict]:
    """Groups in the same plane that entered before `target` and are still visible at target's `in`."""
    plane = target.get("plane")
    if not plane:
        return []
    out = []
    t_enter = target["in"]
    for g in groups:
        if g is target:
            continue
        if g.get("plane") != plane:
            continue
        if g["in"] < t_enter and g["out"] > t_enter:
            out.append(g)
    out.sort(key=lambda g: g["in"])
    return out


def compute_group_bbox(group: dict, plane: dict, previous_in_stack: list[dict], width: int, height: int) -> dict:
    """(x, y, w, h) in screen pixels. Best-effort approximation."""
    g_h, font_px, g_w_used = estimate_group_height(group["words"], group.get("css", ""), plane["width"], height)

    # Stack vertical offset
    stack_y = plane["top"]
    for g in previous_in_stack:
        prev_h, _, _ = estimate_group_height(g["words"], g.get("css", ""), plane["width"], height)
        stack_y += prev_h + plane["gap"]

    # Horizontal: flex-end → hug plane.right (may overflow LEFT if word too wide).
    # flex-start → plane.left (may overflow RIGHT). center → symmetric overflow.
    # Overflow matters most here: the caption extends OUT of its intended clean
    # zone and INTO the subject's space. That's exactly what we want to catch.
    plane_right = plane["left"] + plane["width"]
    if plane["align"] == "flex-end":
        x = plane_right - g_w_used
        w = g_w_used
    elif plane["align"] == "flex-start":
        x = plane["left"]
        w = g_w_used
    else:
        # center / stretch: if g_w_used > plane["width"] overflow is symmetric
        x = plane["left"] + (plane["width"] - g_w_used) / 2.0
        w = g_w_used

    return {"x": int(x), "y": int(stack_y), "w": int(w), "h": int(g_h), "font_px": font_px}


def sample_frame_indices(t_in: float, t_out: float, fps: int, max_samples: int = 6) -> list[int]:
    if t_out <= t_in:
        return [int(round(t_in * fps)) + 1]
    count = min(max_samples, max(2, int(round((t_out - t_in) * 2))))
    step = (t_out - t_in) / (count + 1)
    return [int(round((t_in + step * (i + 1)) * fps)) + 1 for i in range(count)]


def load_alpha_mask(png_path: Path, threshold: int = 128) -> np.ndarray | None:
    if not png_path.exists():
        return None
    im = Image.open(png_path)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    arr = np.array(im)
    alpha = arr[:, :, 3]
    return (alpha > threshold).astype(np.uint8)


def occlusion_for_bbox(mask: np.ndarray, bbox: dict) -> float:
    H, W = mask.shape
    x0 = max(0, bbox["x"])
    y0 = max(0, bbox["y"])
    x1 = min(W, bbox["x"] + bbox["w"])
    y1 = min(H, bbox["y"] + bbox["h"])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    sub = mask[y0:y1, x0:x1]
    if sub.size == 0:
        return 0.0
    return float(sub.sum()) / float(sub.size)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--strict", action="store_true", help="Exit 2 if any group exceeds --threshold.")
    ap.add_argument("--threshold", type=float, default=0.35, help="Occlusion fraction that counts as FAIL (default 0.35).")
    ap.add_argument("--warn", type=float, default=0.20, help="Occlusion fraction that counts as WARN (default 0.20).")
    ap.add_argument("--max-samples", type=int, default=6)
    ap.add_argument("--preview", action="store_true",
                    help="Also emit preview.png — sample matte frames per group's mid-window with bbox overlaid in OK/WARN/FAIL color. No Chromium render needed.")
    args = ap.parse_args()

    project = Path(args.project)
    plan_path = project / "plan.json"
    frames_dir = project / "frames_fg"
    if not plan_path.exists():
        print(f"[occlusion] no plan.json at {plan_path}", file=sys.stderr)
        return 3
    if not frames_dir.exists():
        print(f"[occlusion] no frames_fg/ at {frames_dir}", file=sys.stderr)
        return 3

    plan = json.loads(plan_path.read_text())
    width = int(plan["width"])
    height = int(plan["height"])
    fps = int(plan.get("fps", 24))
    planes = {
        name: parse_plane(p["css"], width, height)
        for name, p in (plan.get("planes") or {}).items()
    }

    groups = plan.get("groups", [])
    failures = []
    overflow_warnings = []
    rows = []
    plan_layer = plan.get("caption_layer", "bg")
    for g in groups:
        plane_name = g.get("plane")
        group_layer = g.get("layer", plan_layer)

        # Horizontal frame-edge overflow check — applies to BOTH bg and fg.
        # A 10-char uppercase word at 0.15h on a 720-wide portrait blows past
        # the frame edge and gets cropped by ffmpeg. subject-occlusion check
        # misses this because the word isn't being "occluded" — it's gone.
        if plane_name and plane_name in planes:
            plane = planes[plane_name]
            prev = groups_before_in_block(groups, g)
            bbox_est = compute_group_bbox(g, plane, prev, width, height)
            if bbox_est["x"] < -5 or bbox_est["x"] + bbox_est["w"] > width + 5:
                left_clip = max(0, -bbox_est["x"])
                right_clip = max(0, (bbox_est["x"] + bbox_est["w"]) - width)
                overflow_warnings.append(
                    (g["id"], left_clip, right_clip, bbox_est["w"])
                )

        # Groups rendered on top of the matte can't be occluded by the subject.
        # Plan-level caption_layer: fg means the whole clip skips the matte;
        # group-level layer: fg means this specific group joins the fg pass.
        # Either way, subject-occlusion % is not a risk we care about here.
        if plan_layer == "fg" or group_layer == "fg":
            text_preview = " ".join(str(w.get("text", "")) for w in g["words"])[:42]
            rows.append({
                "id": g["id"],
                "plane": plane_name or "-",
                "text": text_preview,
                "bbox": {"x": 0, "y": 0, "w": 0, "h": 0},
                "avg": 0.0,
                "peak": 0.0,
                "status": "FG",
            })
            continue
        if not plane_name or plane_name not in planes:
            continue  # free-mode caps not supported by this approximator yet
        plane = planes[plane_name]
        prev = groups_before_in_block(groups, g)
        bbox = compute_group_bbox(g, plane, prev, width, height)

        frames = sample_frame_indices(g["in"], g["out"], fps, args.max_samples)
        occlusions = []
        for idx in frames:
            png = frames_dir / f"f_{idx:04d}.png"
            mask = load_alpha_mask(png)
            if mask is None:
                continue
            occlusions.append(occlusion_for_bbox(mask, bbox))
        avg = sum(occlusions) / len(occlusions) if occlusions else 0.0
        peak = max(occlusions) if occlusions else 0.0

        status = "OK"
        if peak >= args.threshold:
            status = "FAIL"
            failures.append((g["id"], avg, peak))
        elif peak >= args.warn:
            status = "WARN"

        text_preview = " ".join(str(w.get("text", "")) for w in g["words"])[:42]
        rows.append({
            "id": g["id"],
            "plane": plane_name,
            "text": text_preview,
            "bbox": bbox,
            "avg": avg,
            "peak": peak,
            "status": status,
        })

    # Print report
    print(f"[occlusion] {project.name}  threshold={args.threshold:.0%} warn={args.warn:.0%}")
    print(f"  {'id':<6} {'plane':<8} {'bbox (x,y,w,h)':<22} {'avg':>5} {'peak':>5}  status  text")
    for r in rows:
        b = r["bbox"]
        print(f"  {r['id']:<6} {r['plane']:<8} "
              f"({b['x']},{b['y']},{b['w']},{b['h']}){'':<{max(0, 22 - len(f'''({b['x']},{b['y']},{b['w']},{b['h']})'''))}} "
              f"{r['avg']*100:>4.0f}% {r['peak']*100:>4.0f}%  {r['status']:<6}  {r['text']}")

    if failures:
        print(f"\n[occlusion] {len(failures)} group(s) exceed {args.threshold:.0%}:", file=sys.stderr)
        for gid, avg, peak in failures:
            print(f"  - {gid}: avg {avg*100:.0f}% peak {peak*100:.0f}%", file=sys.stderr)

    if overflow_warnings:
        print(f"\n[overflow] {len(overflow_warnings)} group(s) exceed frame width:", file=sys.stderr)
        for gid, left, right, bw in overflow_warnings:
            sides = []
            if left > 0:
                sides.append(f"left by {left:.0f}px")
            if right > 0:
                sides.append(f"right by {right:.0f}px")
            print(f"  - {gid}: {bw:.0f}px wide, cropped {' and '.join(sides)}", file=sys.stderr)

    if args.preview:
        try:
            from PIL import ImageDraw, ImageFont  # noqa
        except ImportError:
            print("[preview] missing PIL.ImageDraw — skipping preview render", file=sys.stderr)
        else:
            preview_path = render_preview(project, plan, rows, width, height, fps, frames_dir)
            print(f"[preview] wrote {preview_path}")

    if args.strict and (failures or overflow_warnings):
        return 2
    return 0


STATUS_COLORS = {
    "OK":   (90, 220, 130),    # green
    "WARN": (255, 180, 60),    # amber
    "FAIL": (255, 80, 80),     # red
    "FG":   (140, 180, 255),   # blue (rendered above matte, not occluded)
}


def render_preview(project: Path, plan: dict, rows: list[dict], width: int, height: int, fps: int, frames_dir: Path) -> Path:
    """Stitch a per-group preview grid: each cell = the matte sample at the group's
    mid-window time, with the estimated cap bbox outlined in OK/WARN/FAIL color
    + the cap text drawn inside. No Chromium needed. Useful for fast layout
    iteration before committing to a full render."""
    from PIL import Image as PImage, ImageDraw, ImageFont
    cells = []
    for r in rows:
        gid = r["id"]
        # Find the group dict to get in/out time.
        g = next((x for x in plan["groups"] if x["id"] == gid), None)
        if g is None:
            continue
        t_mid = (g["in"] + g["out"]) / 2.0
        idx = max(1, int(round(t_mid * fps)))
        png = frames_dir / f"f_{idx:04d}.png"
        if not png.exists():
            continue
        # Compose the source frame UNDER the matte, since matte alone is just a silhouette.
        src_video = project / "source.mp4"
        # Quick: use ffmpeg to extract a frame at t_mid from source.mp4
        bg_path = project / f"_preview_bg_{idx}.png"
        if not bg_path.exists():
            os.system(f'ffmpeg -y -ss {t_mid} -i "{src_video}" -vframes 1 "{bg_path}" -loglevel error 2>/dev/null')
        if not bg_path.exists():
            continue
        bg = PImage.open(bg_path).convert("RGBA")
        if bg.size != (width, height):
            bg = bg.resize((width, height))
        # Overlay matte in a 30% red tint so subject silhouette is visible
        matte = PImage.open(png).convert("RGBA")
        if matte.size != (width, height):
            matte = matte.resize((width, height))
        red_overlay = PImage.new("RGBA", (width, height), (255, 0, 60, 0))
        a = np.array(matte)[:, :, 3]
        red_arr = np.zeros((height, width, 4), dtype=np.uint8)
        red_arr[:, :, 0] = 255
        red_arr[:, :, 1] = 0
        red_arr[:, :, 2] = 60
        red_arr[:, :, 3] = (a * 0.30).astype(np.uint8)
        red_overlay = PImage.fromarray(red_arr, "RGBA")
        composed = PImage.alpha_composite(bg, red_overlay)

        draw = ImageDraw.Draw(composed)
        b = r["bbox"]
        if b["w"] > 0 and b["h"] > 0:
            color = STATUS_COLORS.get(r["status"], (200, 200, 200))
            for d in range(4):  # 4-pixel thick outline
                draw.rectangle([b["x"] - d, b["y"] - d,
                                b["x"] + b["w"] + d, b["y"] + b["h"] + d],
                               outline=color)
            # Top-left badge
            badge_h = 28
            draw.rectangle([b["x"], max(0, b["y"] - badge_h), b["x"] + 280, b["y"]],
                           fill=(0, 0, 0, 200))
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
            except Exception:
                font = ImageFont.load_default()
            draw.text((b["x"] + 6, max(2, b["y"] - badge_h + 4)),
                      f"{gid} {r['status']} {r['peak']*100:.0f}%",
                      fill=color, font=font)
        cells.append((gid, composed))

    if not cells:
        return project / "preview.png"
    # Tile cells: 2 columns
    cell_w, cell_h = cells[0][1].size
    cols = 2
    rows_n = (len(cells) + cols - 1) // cols
    pad = 16
    sheet_w = cols * cell_w + (cols + 1) * pad
    sheet_h = rows_n * cell_h + (rows_n + 1) * pad + 60  # 60 for header
    sheet = PImage.new("RGB", (sheet_w, sheet_h), (14, 12, 9))
    draw = ImageDraw.Draw(sheet)
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except Exception:
        title_font = ImageFont.load_default()
    draw.text((pad, 20),
              f"check-occlusion preview · {project.name} · {len(cells)} group(s) · subject silhouette in red, bbox outlined OK/WARN/FAIL",
              fill=(255, 244, 220), font=title_font)
    for i, (gid, im) in enumerate(cells):
        r_i, c_i = divmod(i, cols)
        x = pad + c_i * (cell_w + pad)
        y = 60 + pad + r_i * (cell_h + pad)
        sheet.paste(im.convert("RGB"), (x, y))
    out = project / "preview.png"
    sheet.save(out, "PNG")
    return out


if __name__ == "__main__":
    sys.exit(main())
