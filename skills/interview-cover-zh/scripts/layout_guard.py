#!/usr/bin/env python3
"""Read-only rectangular layout checks; coordinates are visible ink bounds.

Schema: {canvas: [W,H], elements: [{id, role: "title"|"signature",
bbox: [x0,y0,x1,y1]}], ui_reference?: {canvas: [W,H],
mapping_verified?: bool, zones: [{id,bbox}]}, constraints?: {
equal_title_gaps_tolerance_px?: number, signature_bottom_ratio?: number,
signature_bottom_tolerance_px?: number, signature_bottom_max_ratio?: number}}.

No image or input is changed. --output writes a JSON report. Aspect differences
over 1% are rejected even when mapping_verified=true: pre-map cropped UI boxes
into final-canvas coordinates and set ui_reference.canvas equal to canvas.
signature_bottom_ratio is a strict, two-sided alignment target; the optional
signature_bottom_max_ratio is a one-sided safety limit that permits moving up.
"""

import argparse
import itertools
import json
import math
from pathlib import Path
import sys


LIMITATION = (
    "Rectangle geometry only: this cannot verify alpha silhouettes, source "
    "content, photographic naturalness, or safety in every app interface. UI "
    "results apply only to the supplied reference and coordinate mapping."
)


def number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} must be <= {maximum}")
    return float(value)


def canvas(value, label):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must be [width,height]")
    result = [number(v, label) for v in value]
    if min(result) <= 0:
        raise ValueError(f"{label} dimensions must be positive")
    return result


def bbox(value, label):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"{label} must be [x0,y0,x1,y1]")
    result = [number(v, label) for v in value]
    if result[2] <= result[0] or result[3] <= result[1]:
        raise ValueError(f"{label} must have positive width and height")
    return result


def margins(box, size):
    return dict(zip(("left", "top", "right", "bottom"),
                    (box[0], box[1], size[0]-box[2], size[1]-box[3])))


def relationship(a, b):
    width = max(0.0, min(a[2], b[2])-max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3])-max(a[1], b[1]))
    x_gap = max(0.0, b[0]-a[2], a[0]-b[2])
    y_gap = max(0.0, b[1]-a[3], a[1]-b[3])
    return {
        "overlap_area_px2": width*height,
        "intersects": width > 0 and height > 0,
        "horizontal_signed_gap_px": x_gap if x_gap else -width,
        "vertical_signed_gap_px": y_gap if y_gap else -height,
        "separation_distance_px": math.hypot(x_gap, y_gap),
    }


def entries(items, label, roles=False):
    if not isinstance(items, list):
        raise ValueError(f"{label} must be an array")
    result, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"Each {label} item must be an object")
        name = item.get("id")
        if not isinstance(name, str) or not name.strip() or name in seen:
            raise ValueError(f"{label} ids must be nonempty and unique")
        seen.add(name)
        record = {"id": name, "bbox": bbox(item.get("bbox"), f"{label}.{name}.bbox")}
        if roles:
            if item.get("role") not in ("title", "signature"):
                raise ValueError(f"{label}.{name}.role must be title or signature")
            record["role"] = item["role"]
        result.append(record)
    return result


def check(config):
    if not isinstance(config, dict):
        raise ValueError("Configuration must be an object")
    size = canvas(config.get("canvas"), "canvas")
    elements = entries(config.get("elements"), "elements", roles=True)
    if not elements:
        raise ValueError("elements must contain at least one item")
    constraints = config.get("constraints", {})
    if not isinstance(constraints, dict):
        raise ValueError("constraints must be an object")
    allowed = {"equal_title_gaps_tolerance_px", "signature_bottom_ratio",
               "signature_bottom_tolerance_px", "signature_bottom_max_ratio"}
    unknown = set(constraints)-allowed
    if unknown:
        raise ValueError("Unknown constraints: " + ", ".join(sorted(unknown)))
    limits = {key: number(value, f"constraints.{key}", minimum=0,
                          maximum=1 if key in ("signature_bottom_ratio", "signature_bottom_max_ratio") else None)
              for key, value in constraints.items()}
    if "signature_bottom_tolerance_px" in limits and "signature_bottom_ratio" not in limits:
        raise ValueError("signature_bottom_tolerance_px requires signature_bottom_ratio")
    errors = []
    report = {"status": "failed", "canvas": size, "limitations": LIMITATION,
              "elements": [], "element_pairs": [], "title_gaps": [],
              "signatures": [], "signature_constraints": {}, "ui_pairs": [], "errors": errors}
    if "signature_bottom_ratio" in limits:
        report["signature_constraints"]["strict_target"] = {
            "ratio": limits["signature_bottom_ratio"],
            "tolerance_px": limits.get("signature_bottom_tolerance_px", 0),
            "meaning": "Two-sided alignment lock: moving up or down outside tolerance fails.",
        }
    if "signature_bottom_max_ratio" in limits:
        report["signature_constraints"]["maximum_bottom"] = {
            "ratio": limits["signature_bottom_max_ratio"],
            "meaning": "One-sided safety limit: bottom may be at or above this boundary; no target tolerance applies.",
        }
    for item in elements:
        edge = margins(item["bbox"], size)
        report["elements"].append({**item, "margins_px": edge})
        if min(edge.values()) < 0:
            errors.append(f"{item['id']}: bounding box extends outside canvas")
    for a, b in itertools.combinations(elements, 2):
        relation = relationship(a["bbox"], b["bbox"])
        report["element_pairs"].append({"a": a["id"], "b": b["id"], **relation})
        if relation["intersects"]:
            errors.append(f"{a['id']} intersects {b['id']}")
    titles = sorted((e for e in elements if e["role"] == "title"),
                    key=lambda e: (e["bbox"][1], e["bbox"][0]))
    for a, b in zip(titles, titles[1:]):
        report["title_gaps"].append({"above": a["id"], "below": b["id"],
                                     "gap_px": b["bbox"][1]-a["bbox"][3]})
    gaps = [record["gap_px"] for record in report["title_gaps"]]
    spread = max(gaps)-min(gaps) if gaps else 0.0
    report["title_gap_spread_px"] = spread
    if "equal_title_gaps_tolerance_px" in limits and spread > limits["equal_title_gaps_tolerance_px"]:
        errors.append(f"Title gap spread {spread:g}px exceeds tolerance")
    for item in (e for e in elements if e["role"] == "signature"):
        result = {"id": item["id"], "bottom_ratio": item["bbox"][3]/size[1]}
        if "signature_bottom_ratio" in limits:
            target = limits["signature_bottom_ratio"]*size[1]
            delta = item["bbox"][3]-target
            result.update(target_bottom_px=target, bottom_delta_px=delta)
            if abs(delta) > limits.get("signature_bottom_tolerance_px", 0):
                errors.append(f"{item['id']}: bottom differs from strict alignment target by {delta:g}px")
        if "signature_bottom_max_ratio" in limits:
            maximum = limits["signature_bottom_max_ratio"]*size[1]
            remaining = maximum-item["bbox"][3]
            result.update(max_bottom_px=maximum, remaining_bottom_clearance_px=remaining)
            if remaining < 0:
                errors.append(f"{item['id']}: bottom exceeds safety maximum by {-remaining:g}px")
        report["signatures"].append(result)
    if report["signature_constraints"] and not report["signatures"]:
        errors.append("Signature bottom constraint supplied but no signature element exists")

    if "ui_reference" in config:
        ref = config["ui_reference"]
        if not isinstance(ref, dict):
            raise ValueError("ui_reference must be an object")
        ref_size = canvas(ref.get("canvas"), "ui_reference.canvas")
        verified = ref.get("mapping_verified", False)
        if not isinstance(verified, bool):
            raise ValueError("ui_reference.mapping_verified must be boolean")
        zones = entries(ref.get("zones"), "ui_reference.zones")
        if any(min(margins(zone["bbox"], ref_size).values()) < 0 for zone in zones):
            raise ValueError("UI zone extends outside the reference canvas")
        difference = abs((size[0]/size[1])/(ref_size[0]/ref_size[1])-1)
        sx, sy = size[0]/ref_size[0], size[1]/ref_size[1]
        trusted = difference <= .01
        report["ui_mapping"] = {
            "reference_canvas": ref_size, "scale_x": sx, "scale_y": sy,
            "aspect_ratio_difference_fraction": difference,
            "mapping_verified_by_caller": verified, "mapping_check_passed": trusted,
            "mode": ("identity_final_canvas" if ref_size == size else "proportional_full_frame") if trusted else "rejected",
            "note": "mapping_verified is informational only and never bypasses aspect checks. Cropped UI must be pre-mapped into final-canvas coordinates with ui_reference.canvas equal to canvas; matching aspect ratios alone do not prove an uncropped view.",
        }
        if not trusted:
            errors.append("UI aspect ratios differ by more than 1%; pre-map UI bboxes into final-canvas coordinates and set ui_reference.canvas equal to canvas. mapping_verified=true cannot bypass this rejection.")
        for zone in zones if trusted else []:
            x0, y0, x1, y1 = zone["bbox"]
            mapped = [x0*sx, y0*sy, x1*sx, y1*sy]
            for item in elements:
                relation = relationship(item["bbox"], mapped)
                report["ui_pairs"].append({"element": item["id"], "zone": zone["id"],
                                            "mapped_zone_bbox": mapped,
                                            "mapping_check_passed": trusted, **relation})
                if relation["intersects"]:
                    errors.append(f"{item['id']} intersects UI zone {zone['id']}")
    report["status"] = "passed" if not errors else "failed"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", type=Path, help="Input JSON layout configuration")
    parser.add_argument("--output", type=Path, help="Optional JSON report path; input/images remain unchanged")
    args = parser.parse_args()
    if args.output and args.output.resolve() == args.config.resolve():
        print("Report path must differ from the input configuration", file=sys.stderr)
        return 2
    try:
        report = check(json.loads(args.config.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        report = {"status": "failed", "limitations": LIMITATION, "errors": [str(exc)]}
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n"
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"Cannot write report: {exc}", file=sys.stderr)
            return 2
    sys.stdout.write(text)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
