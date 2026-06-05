#!/usr/bin/env python3
"""Pixel-perfect occlusion check using real Chromium layout.

Replaces v1's heuristic char_ratio bbox estimation. v2 uses
measure-layout.js (headless Chromium DOM API) to get the EXACT pixel
coordinates of every cap, line, and word at multiple sample times,
then computes occlusion against the real RVM matte.

Catches what v1 misses:
  - Per-word obliteration (5 words visible, 3 fully eaten = same bbox %
    as 8 words half-eaten, but very different visual outcome)
  - Per-line obliteration in multi-line wraps (line 1 clean, line 2
    eaten — bbox average hides this)
  - Subject motion within a block (denser temporal sampling)
  - Wrong char_ratio estimates (no estimates — actual measured pixels)

Usage:
    python check-occlusion-v2.py <project-dir> [--strict]
        [--word-fail 0.65] [--word-warn 0.35]

Exit 0 = pass, 2 = fail (with --strict).
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("[v2] missing deps: pip install pillow numpy", file=sys.stderr)
    sys.exit(3)

HERE = Path(__file__).parent


def ensure_layout_measured(project: Path, force: bool = False) -> dict:
    """Run measure-layout.js if _layout.json missing or stale."""
    layout_path = project / "_layout.json"
    index_path = project / "index.html"
    if not index_path.exists():
        sys.exit(f"[v2] missing {index_path} — run make-composition.py first")
    needs_measure = force or not layout_path.exists()
    if not needs_measure:
        # stale check: index.html newer than _layout.json
        if index_path.stat().st_mtime > layout_path.stat().st_mtime:
            needs_measure = True
    if needs_measure:
        print(f"[v2] measuring layout via headless Chromium…")
        rc = subprocess.run(
            ["node", str(HERE / "measure-layout.js"), str(project)],
            capture_output=True, text=True
        )
        if rc.returncode != 0:
            print(rc.stderr, file=sys.stderr)
            sys.exit(f"[v2] measure-layout.js failed (exit {rc.returncode})")
    return json.loads(layout_path.read_text())


def load_alpha_mask(png_path: Path, threshold: int = 128) -> np.ndarray | None:
    if not png_path.exists():
        return None
    im = Image.open(png_path)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    alpha = np.array(im)[:, :, 3]
    return (alpha > threshold).astype(np.uint8)


def occlusion_for_rect(mask: np.ndarray, x: float, y: float, w: float, h: float) -> float:
    H, W = mask.shape
    x0 = max(0, int(round(x)))
    y0 = max(0, int(round(y)))
    x1 = min(W, int(round(x + w)))
    y1 = min(H, int(round(y + h)))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    sub = mask[y0:y1, x0:x1]
    if sub.size == 0:
        return 0.0
    return float(sub.sum()) / float(sub.size)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--word-fail", type=float, default=0.65,
                    help="Per-word occlusion fraction that counts as obliterated (default 0.65)")
    ap.add_argument("--word-warn", type=float, default=0.35,
                    help="Per-word occlusion that counts as warning (default 0.35)")
    ap.add_argument("--cap-fail", type=float, default=0.50,
                    help="Per-cap avg occlusion that counts as fail (default 0.50)")
    ap.add_argument("--remeasure", action="store_true")
    args = ap.parse_args()

    project = Path(args.project)
    layout = ensure_layout_measured(project, force=args.remeasure)
    frames_dir = project / "frames_fg"
    if not frames_dir.exists():
        sys.exit(f"[v2] missing {frames_dir}")

    plan = json.loads((project / "plan.json").read_text()) if (project / "plan.json").exists() else {}
    plan_layer = plan.get("caption_layer", "bg")

    # Per-cap aggregation across all samples
    cap_stats = {}  # id → list of (t, frame_idx, layer, words_occl)
    for sample in layout["samples"]:
        t = sample["t"]
        frame_idx = sample["frame_idx"]
        png = frames_dir / f"f_{frame_idx:04d}.png"
        mask = load_alpha_mask(png)
        if mask is None:
            continue
        for cap in sample["caps"]:
            gid = cap["id"]
            layer = cap.get("layer") or plan_layer
            entry = cap_stats.setdefault(gid, {"layer": layer, "samples": []})
            words_data = []
            for w in cap.get("words", []):
                if w.get("opacity", 1) < 0.3:
                    continue  # not yet animated in
                occ = occlusion_for_rect(mask, w["x"], w["y"], w["w"], w["h"])
                words_data.append({"text": w["text"], "occlusion": occ,
                                   "bbox": (w["x"], w["y"], w["w"], w["h"])})
            cap_occl = occlusion_for_rect(mask, cap["cap_bbox"]["x"], cap["cap_bbox"]["y"],
                                          cap["cap_bbox"]["w"], cap["cap_bbox"]["h"])
            entry["samples"].append({"t": t, "frame_idx": frame_idx,
                                     "cap_occl": cap_occl, "words": words_data})

    # Report
    failures = []
    fg_skipped = 0
    print(f"[v2] {project.name}  word-fail≥{args.word_fail:.0%}  cap-fail≥{args.cap_fail:.0%}")
    print(f"  {'id':<6} {'layer':<5} {'avg-cap':>7} {'peak-cap':>8} {'obliterated words (peak occ%)':<60}")

    for gid, entry in cap_stats.items():
        layer = entry["layer"]
        if layer == "fg" or plan_layer == "fg" and not entry["samples"][0].get("words"):
            # Skip fg layer (renders on top of matte, no occlusion)
            print(f"  {gid:<6} fg    (skipped — fg renders above matte)")
            fg_skipped += 1
            continue
        cap_occls = [s["cap_occl"] for s in entry["samples"]]
        avg_cap = sum(cap_occls) / len(cap_occls) if cap_occls else 0
        peak_cap = max(cap_occls) if cap_occls else 0

        # Find peak occlusion per word across all samples
        word_peaks = {}
        for s in entry["samples"]:
            for wd in s["words"]:
                txt = wd["text"]
                word_peaks[txt] = max(word_peaks.get(txt, 0), wd["occlusion"])

        obliterated = [(t, p) for t, p in word_peaks.items() if p >= args.word_fail]
        warning = [(t, p) for t, p in word_peaks.items() if args.word_warn <= p < args.word_fail]

        status = "OK"
        if obliterated or peak_cap >= args.cap_fail:
            status = "FAIL"
            failures.append(gid)
        elif warning:
            status = "WARN"

        oblit_str = ""
        if obliterated:
            oblit_str = " ".join(f"{t}({p*100:.0f}%)" for t, p in obliterated[:5])
            if len(obliterated) > 5:
                oblit_str += f" …+{len(obliterated)-5}"
        elif warning:
            oblit_str = "[warn] " + " ".join(f"{t}({p*100:.0f}%)" for t, p in warning[:3])

        print(f"  {gid:<6} {layer:<5} {avg_cap*100:>6.0f}% {peak_cap*100:>7.0f}%  {status:<5}  {oblit_str}")

    if failures:
        print(f"\n[v2] {len(failures)} cap(s) FAIL: {', '.join(failures)}", file=sys.stderr)
        print(f"  → likely fixes: change layer to fg for that specific cap, OR shrink/reposition", file=sys.stderr)

    if args.strict and failures:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
