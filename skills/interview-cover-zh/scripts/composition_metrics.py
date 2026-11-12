#!/usr/bin/env python3
"""Measure layered cover geometry without changing source pixels.

Usage: python3 composition_metrics.py CONFIG.json [--output REPORT.json]
Layers are back-to-front, with uniform scale and integer translation. Polygon
coordinates belong to the unscaled source image. This is a geometric aid, not
a visual-quality judgement. Dependencies: Pillow and numpy.
The report output must not alias the input configuration or a source image.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def number(value, label, integer=False, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    if not math.isfinite(value) or (integer and int(value) != value):
        raise ValueError(f"{label} must be finite" + (" and integral" if integer else ""))
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    return int(value) if integer else float(value)


def pair(value, label, **kwargs):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must contain two numbers")
    return [number(v, label, **kwargs) for v in value]


def identifier(value, seen, label):
    if not isinstance(value, str) or not value.strip() or value in seen:
        raise ValueError(f"{label} must be a unique nonempty string")
    seen.add(value)
    return value


def clip_slices(origin, shape, canvas):
    x, y = origin
    h, w = shape
    cw, ch = canvas
    left, top, right, bottom = max(x, 0), max(y, 0), min(x + w, cw), min(y + h, ch)
    if left >= right or top >= bottom:
        return None
    return (slice(top - y, bottom - y), slice(left - x, right - x))


def outside_count(mask, origin, canvas):
    inside = clip_slices(origin, mask.shape, canvas)
    return int(mask.sum() - (mask[inside].sum() if inside else 0))


def edges_cross(a, b, c, d):
    def orient(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])

    def on_segment(p, q, r):
        return min(p[0], q[0]) <= r[0] <= max(p[0], q[0]) and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])

    values = [orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)]
    if values[0]*values[1] < 0 and values[2]*values[3] < 0:
        return True
    return any(abs(v) < 1e-9 and on_segment(p, q, r) for v, p, q, r in
               zip(values, [a, a, c, c], [b, b, d, d], [c, d, a, b]))


def measure(config, base):
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    canvas = pair(config.get("canvas"), "canvas", integer=True, minimum=1)
    thresholds = config.get("thresholds", {})
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds must be an object")
    visible = number(thresholds.get("visible_alpha", 16), "visible_alpha", integer=True, minimum=0)
    occlusion = number(thresholds.get("occlusion_alpha", 64), "occlusion_alpha", integer=True, minimum=0)
    if max(visible, occlusion) > 255:
        raise ValueError("Alpha thresholds must be between 0 and 255")
    definitions = config.get("layers")
    if not isinstance(definitions, list) or not definitions:
        raise ValueError("layers must be a nonempty back-to-front array")
    layers, results, violations, ids = [], [], [], set()
    for item in definitions:
        if not isinstance(item, dict):
            raise ValueError("Every layer must be an object")
        name = identifier(item.get("id"), ids, "layer id")
        scale = number(item.get("scale", 1), f"{name}.scale", minimum=0)
        if scale == 0:
            raise ValueError(f"{name}.scale must be positive")
        origin = pair(item.get("translate", [0, 0]), f"{name}.translate", integer=True)
        require_inside = item.get("require_inside", False)
        if not isinstance(require_inside, bool):
            raise ValueError(f"{name}.require_inside must be boolean")
        if not isinstance(item.get("image"), str) or not item["image"]:
            raise ValueError(f"{name}.image must be a path")
        path = (base / item["image"]).resolve()
        with Image.open(path) as image:
            source_size = image.size
            size = [round(d * scale) for d in image.size]
            if min(size) < 1:
                raise ValueError(f"{name}.scale produces a zero-size image")
            alpha = np.array(image.convert("RGBA").resize(size, Image.Resampling.LANCZOS).getchannel("A"))
        mask = alpha > visible
        ys, xs = np.where(mask)
        if not len(xs):
            raise ValueError(f"{name} has no pixels above visible_alpha")
        bbox = [int(xs.min()) + origin[0], int(ys.min()) + origin[1],
                int(xs.max()) + 1 + origin[0], int(ys.max()) + 1 + origin[1]]
        outside = outside_count(mask, origin, canvas)
        if require_inside and outside:
            violations.append(f"{name}: {outside} visible pixels outside canvas")
        results.append({"id": name, "image": str(path), "source_size": list(source_size),
                        "rendered_size": size, "scale": scale, "translate": origin,
                        "visible_bbox_xyxy_exclusive": bbox,
                        "margins_px": {"left": bbox[0], "top": bbox[1], "right": canvas[0] - bbox[2], "bottom": canvas[1] - bbox[3]},
                        "outside_pixels": outside, "require_inside": require_inside})
        layers.append({"id": name, "alpha": alpha, "origin": origin, "scale": scale, "source_size": source_size})

    regions = config.get("protected_regions", [])
    if not isinstance(regions, list):
        raise ValueError("protected_regions must be an array")
    region_results, region_ids = [], set()
    for region in regions:
        if not isinstance(region, dict):
            raise ValueError("Every protected region must be an object")
        name = identifier(region.get("id"), region_ids, "region id")
        owner_index = next((i for i, layer in enumerate(layers) if layer["id"] == region.get("layer")), None)
        if owner_index is None:
            raise ValueError(f"{name}.layer does not identify a configured layer")
        owner = layers[owner_index]
        polygon = region.get("polygon")
        if not isinstance(polygon, list) or len(polygon) < 3:
            raise ValueError(f"{name}.polygon needs at least three points")
        points = [pair(p, f"{name}.polygon point") for p in polygon]
        sw, sh = owner["source_size"]
        if any(x < 0 or y < 0 or x >= sw or y >= sh for x, y in points):
            raise ValueError(f"{name}.polygon must lie within the source image")
        area2 = sum(a[0]*b[1] - b[0]*a[1] for a, b in zip(points, points[1:] + points[:1]))
        if len(set(map(tuple, points))) != len(points) or abs(area2) < 1e-9:
            raise ValueError(f"{name}.polygon is degenerate")
        for i in range(len(points)):
            for j in range(i+1, len(points)):
                if j == i+1 or (i == 0 and j == len(points)-1):
                    continue
                if edges_cross(points[i], points[(i+1) % len(points)], points[j], points[(j+1) % len(points)]):
                    raise ValueError(f"{name}.polygon must not self-intersect")
        points = [(round(x*owner["scale"]) + owner["origin"][0], round(y*owner["scale"]) + owner["origin"][1]) for x, y in points]
        left, top = min(x for x, _ in points), min(y for _, y in points)
        right, bottom = max(x for x, _ in points) + 1, max(y for _, y in points) + 1
        image = Image.new("L", (right-left, bottom-top))
        ImageDraw.Draw(image).polygon([(x-left, y-top) for x, y in points], fill=255)
        mask = np.array(image) > 0
        covered = np.zeros(mask.shape, dtype=bool)
        by_layer = {}
        for front in layers[owner_index+1:]:
            x, y = front["origin"]
            fh, fw = front["alpha"].shape
            l, t, r, b = max(left, x, 0), max(top, y, 0), min(right, x+fw, canvas[0]), min(bottom, y+fh, canvas[1])
            count = 0
            if l < r and t < b:
                covered_part = mask[t-top:b-top, l-left:r-left] & (front["alpha"][t-y:b-y, l-x:r-x] > occlusion)
                covered[t-top:b-top, l-left:r-left] |= covered_part
                count = int(covered_part.sum())
            by_layer[front["id"]] = count
        outside = outside_count(mask, (left, top), canvas)
        count = int(covered.sum())
        max_occluded = number(region.get("max_occluded_pixels", 0), f"{name}.max_occluded_pixels", integer=True, minimum=0)
        max_outside = number(region.get("max_outside_pixels", 0), f"{name}.max_outside_pixels", integer=True, minimum=0)
        if count > max_occluded:
            violations.append(f"{name}: {count} occluded pixels exceeds {max_occluded}")
        if outside > max_outside:
            violations.append(f"{name}: {outside} outside pixels exceeds {max_outside}")
        region_results.append({"id": name, "layer": owner["id"], "transformed_polygon": points,
                               "total_pixels": int(mask.sum()), "occluded_pixels": count,
                               "occluded_by_layer": by_layer, "outside_pixels": outside,
                               "max_occluded_pixels": max_occluded, "max_outside_pixels": max_outside})
    return {"ok": not violations, "canvas": canvas,
            "thresholds": {"visible_alpha": visible, "occlusion_alpha": occlusion, "comparison": ">"},
            "bbox_convention": "[left, top, right_exclusive, bottom_exclusive] before canvas clipping",
            "layers": results, "protected_regions": region_results, "violations": violations}


class OutputPathError(ValueError):
    """An output path cannot safely be separated from a protected input."""


def guard_report_output(output, source):
    if output is None:
        return
    try:
        matches = output.resolve() == source.resolve()
        if not matches:
            try:
                matches = output.samefile(source)
            except FileNotFoundError:
                matches = False
    except (OSError, RuntimeError) as error:
        raise OutputPathError(f"Cannot verify report destination: {error}") from error
    if matches:
        raise OutputPathError(f"Report path must differ from the input configuration and source images: {source}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        config = args.config.resolve()
        guard_report_output(args.output, config)
        data = json.loads(config.read_text())
        definitions = data.get("layers", []) if isinstance(data, dict) else []
        if isinstance(definitions, list):
            for item in definitions:
                if isinstance(item, dict) and isinstance(item.get("image"), str):
                    guard_report_output(args.output, config.parent / item["image"])
        result = measure(data, config.parent)
        status = 0 if result["ok"] else 1
    except OutputPathError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except (ValueError, OSError, TypeError, KeyError) as error:
        result, status = {"ok": False, "error": str(error)}, 2
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")
    return status


if __name__ == "__main__":
    sys.exit(main())
