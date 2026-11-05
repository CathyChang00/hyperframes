#!/usr/bin/env python3
"""Global tone grade for a cover photo: white balance, exposure, shadow lift, highlight pull-back.

Every adjustment is applied to the whole frame; faces are never brightened locally.
Presets come from the 2026-11-05 backlit two-person photo: `a` (slightly darker) and `b`
(darker) were both approved after `bright` was judged a little too bright. Deliver two levels.
Requires Pillow, numpy and opencv-python.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

PRESETS = {
    "bright": dict(white_b=3.0, ev=0.35, shadows=1.4, vib=0.35, gsat=1.05, gold=1.0, glow=0.06, highlights=0.0),
    "a": dict(white_b=3.0, ev=0.22, shadows=1.25, vib=0.35, gsat=1.05, gold=1.0, glow=0.04, highlights=0.12),
    "b": dict(white_b=3.0, ev=0.10, shadows=1.10, vib=0.35, gsat=1.05, gold=1.0, glow=0.04, highlights=0.20),
}


def to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.clip(c, 0, None), 1 / 2.4) - 0.055)


def load_rgb(path):
    im = ImageOps.exif_transpose(Image.open(path))
    return np.asarray(im.convert("RGB")).astype(np.float32) / 255, im.info.get("icc_profile")


def grade(rgb, white_b, ev, shadows, vib, gsat, gold, glow, highlights=0.0, matte=0.012):
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    # White balance from bright near-neutral pixels, toward a slightly warm target.
    neutral = (lab[..., 0] > 50) & (chroma < 30) & (rgb.max(-1) < 0.98)
    lin = to_lin(rgb)
    mean = np.median(lin[neutral], axis=0)
    target = cv2.cvtColor(np.array([[[float(np.median(lab[..., 0][neutral])), 0.0, white_b]]], np.float32),
                          cv2.COLOR_LAB2RGB)[0, 0]
    gains = to_lin(np.clip(target, 0, 1)) / mean
    lin = lin * (gains / gains[1]) * (2 ** ev)
    # Exposure with a soft highlight shoulder so the window side does not clip.
    lum = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    knee = 0.6
    comp = np.where(lum > knee, knee + (1 - knee) * np.tanh((lum - knee) / (1 - knee)), lum)
    rgb = np.clip(to_srgb(lin * (comp / np.maximum(lum, 1e-6))[..., None]), 0, 1).astype(np.float32)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    x = lab[..., 0] / 100
    x = x + shadows * x * (1 - x) ** 2                       # lift shadows and mids (faces)
    x = x - 0.10 * np.sin(2 * np.pi * x) / (2 * np.pi)        # mild S-curve
    x = x - highlights * 0.3 * np.clip((x - 0.7) / 0.3, 0, 1) ** 2   # pull near-white walls back
    lab[..., 0] = np.clip(x, 0, 1) * 100
    a, b = lab[..., 1], lab[..., 2]
    vib_k = 1 + vib * (1 - np.clip(np.hypot(a, b) / 60, 0, 1))
    hi = np.clip((x - 0.5) / 0.45, 0, 1)
    lab[..., 1], lab[..., 2] = a * vib_k * gsat + gold * 0.3 * hi, b * vib_k * gsat + gold * hi
    out = np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB), 0, 1)
    l2 = 0.2126 * out[..., 0] + 0.7152 * out[..., 1] + 0.0722 * out[..., 2]
    bright = np.clip((l2 - 0.75) / 0.25, 0, 1)[..., None] * np.array([1.0, 0.9, 0.75], np.float32)
    out = 1 - (1 - out) * (1 - glow * cv2.GaussianBlur(bright, (0, 0), out.shape[1] * 0.012))
    return matte + out * (1 - matte)


def measure(rgb, box):
    """Median L/a/b inside a source-pixel box; use it to report face brightness before and after."""
    x0, y0, x1, y1 = box
    region = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[y0:y1, x0:x1].reshape(-1, 3)
    return [round(float(v), 1) for v in np.median(region, axis=0)]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("src", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--preset", choices=sorted(PRESETS), default="a")
    parser.add_argument("--params", help="JSON overrides on top of the preset")
    parser.add_argument("--measure", action="append", default=[], metavar="x0,y0,x1,y1",
                        help="source-pixel box (for example a face) to report median LAB before/after")
    args = parser.parse_args()
    params = {**PRESETS[args.preset], **json.loads(args.params or "{}")}
    rgb, icc = load_rgb(args.src)
    out = grade(rgb, **params)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((out * 255 + 0.5).astype(np.uint8)).save(args.out, quality=95, subsampling=0, icc_profile=icc)
    report = {"out": str(args.out.resolve()), "params": params, "boxes": []}
    for spec in args.measure:
        box = [int(v) for v in spec.split(",")]
        report["boxes"].append({"box": box, "before_lab": measure(rgb, box), "after_lab": measure(out.astype(np.float32), box)})
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
