#!/usr/bin/env python3
"""Read actual cover files and verify the requested delivery set and aspect ratios.

Manifest: {"covers": [{"id": "en_16x9"|"zh_3x4"|"zh_4x3", "files": [
  {"path": "relative/to/manifest.png", "elements": [
    {"id": "title-or-face", "bbox": [x0,y0,x1,y1]}]}]}]}.
Elements are optional, caller-supplied visible bounds in that file's pixels.
Default checks all three variants. --only checks an explicitly requested local
revision, not the completeness of the full set. No source image is modified.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from PIL import Image

RATIOS = {"en_16x9": (16, 9), "zh_3x4": (3, 4), "zh_4x3": (4, 3)}
LIMITATION = (
    "Checks actual image files, ratios and supplied element bounds only; does not "
    "verify copy, detect faces, judge visual quality or confirm platform publication."
)


def check(manifest, base, only=None):
    required = [only] if only else list(RATIOS)
    if only and only not in RATIOS:
        raise ValueError("Unknown variant")
    errors = []
    report = {"status": "failed", "scope": "single_variant" if only else "full_set",
              "required_variants": required, "files": [], "errors": errors,
              "limitations": LIMITATION}
    if not isinstance(manifest, dict) or not isinstance(manifest.get("covers"), list):
        raise ValueError("Manifest must have a covers array")
    covers = {}
    for cover in manifest["covers"]:
        if not isinstance(cover, dict) or cover.get("id") not in RATIOS:
            raise ValueError("Each cover must use a known variant id")
        name = cover["id"]
        if name in covers:
            raise ValueError(f"Duplicate variant: {name}")
        covers[name] = cover
    for name in required:
        if name not in covers:
            errors.append(f"Missing required variant: {name}")
            continue
        files = covers[name].get("files")
        if not isinstance(files, list) or not files:
            errors.append(f"{name}: files must be a nonempty array")
            continue
        for item in files:
            record = {"variant": name, "status": "failed"}
            report["files"].append(record)
            try:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"].strip():
                    raise ValueError("Each file needs a nonempty path")
                path = Path(item["path"])
                if not path.is_absolute():
                    path = base / path
                record["path"] = str(path.resolve())
                with Image.open(path) as im:
                    im.verify()
                with Image.open(path) as im:
                    im.load()
                    w, h = im.size
                    fmt = im.format
                rw, rh = RATIOS[name]
                record.update(size=[w, h], expected_ratio=[rw, rh], format=fmt)
                if w * rh != h * rw:
                    raise ValueError(f"actual {w}x{h} is not {rw}:{rh}; do not relabel or stretch the image")
                if fmt not in ("PNG", "JPEG"):
                    raise ValueError("Publication cover must be PNG or JPEG")
                elements = item.get("elements", [])
                if not isinstance(elements, list):
                    raise ValueError("elements must be an array")
                names = set()
                for element in elements:
                    if not isinstance(element, dict) or not isinstance(element.get("id"), str) or not element["id"].strip():
                        raise ValueError("Each element needs a nonempty id")
                    if element["id"] in names:
                        raise ValueError("Element ids must be unique within a file")
                    names.add(element["id"])
                    b = element.get("bbox")
                    if not isinstance(b, list) or len(b) != 4 or not all(
                        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in b
                    ):
                        raise ValueError(f"{element['id']}: bbox must contain four finite numbers")
                    if not (0 <= b[0] < b[2] <= w and 0 <= b[1] < b[3] <= h):
                        raise ValueError(f"{element['id']}: bbox is invalid or clipped by final canvas")
                record.update(status="passed", supplied_elements_checked=len(elements),
                              sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            except (OSError, ValueError, TypeError, Image.DecompressionBombError) as exc:
                record["error"] = str(exc)
                errors.append(f"{name}: {exc}")
    report["status"] = "failed" if errors else "passed"
    return report


class OutputPathError(ValueError):
    """The report destination could replace a protected input."""


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
    except (OSError, RuntimeError) as exc:
        raise OutputPathError(f"Cannot verify report destination: {exc}") from exc
    if matches:
        raise OutputPathError(f"Report path must differ from the manifest and source images: {source}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--only", choices=RATIOS, help="Validate only the user-requested local revision")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        guard_report_output(args.output, args.manifest)
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        covers = manifest.get("covers", []) if isinstance(manifest, dict) else []
        for cover in covers if isinstance(covers, list) else []:
            files = cover.get("files", []) if isinstance(cover, dict) else []
            for item in files if isinstance(files, list) else []:
                if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"].strip():
                    guard_report_output(args.output, args.manifest.parent / item["path"])
        report = check(manifest, args.manifest.parent, args.only)
    except OutputPathError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError) as exc:
        report = {"status": "failed", "errors": [str(exc)], "limitations": LIMITATION}
    result = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    sys.stdout.write(result)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
