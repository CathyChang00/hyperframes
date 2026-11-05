#!/usr/bin/env python3
"""Locate interview feedback and check version-bound delivery evidence.

Python standard library; ffprobe is needed for init/media checks. This tool
never edits media and never certifies listening, appearance or meaning.
"""
import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path


DIMENSIONS = ("subject", "scope", "negation", "causality", "reference")
SENSITIVE_WORDS = {
    "not", "never", "no", "only", "some", "many", "most", "all", "always",
    "might", "may", "could", "because", "if", "unless", "they", "it", "those",
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_json(command):
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def probe(path):
    return run_json(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])


def number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a timestamp or rate")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Timestamp/rate must be finite")
    return result


def frame_rate(value):
    """Accept existing numeric fps and exact rates such as '30000/1001'."""
    if isinstance(value, bool):
        raise ValueError("Boolean is not a frame rate")
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError("Frame rate must be a positive number or rational string") from error
    if result <= 0:
        raise ValueError("Frame rate must be positive")
    return result


def material_frame_limits(policy, fps):
    """Keep legacy fullscreen-only caps; typed caps distinguish stills from video."""
    if policy is None:
        return None
    if not isinstance(policy, dict):
        raise ValueError("materials_policy must be an object")
    typed = ("static_fullscreen_max_seconds", "video_max_seconds")
    if "fullscreen_max_seconds" in policy:
        if any(key in policy for key in typed):
            raise ValueError("Do not mix legacy fullscreen_max_seconds with typed material limits")
        fields = {"legacy": "fullscreen_max_seconds"}
    else:
        if not all(key in policy for key in typed):
            raise ValueError("Typed materials_policy needs static_fullscreen_max_seconds and video_max_seconds")
        fields = dict(zip(("static", "video"), typed))
    limits = {}
    for kind, key in fields.items():
        limit = number(policy[key])
        if limit <= 0:
            raise ValueError(f"{key} must be positive")
        frames = math.floor(Fraction(str(limit)) * fps)
        if frames < 1:
            raise ValueError(f"{key} allows no whole display frame")
        limits[kind] = frames
    return limits


def material_frames(item, fps):
    """Validate optional exact frames, otherwise quantize seconds to nearest frames."""
    start, end = interval(item["output_range"])
    frames = item.get("output_frames")
    if frames is not None:
        if (not isinstance(frames, list) or len(frames) != 2
                or any(isinstance(v, bool) or not isinstance(v, int) for v in frames)
                or frames[0] < 0 or frames[1] <= frames[0]):
            raise ValueError("output_frames must be integer [in_frame, out_frame), with 0 <= in < out")
        if any(abs(float(Fraction(f, 1) / fps) - t) > 0.001001
               for f, t in zip(frames, (start, end))):
            raise ValueError("output_frames and output_range disagree by more than 1 ms")
        return tuple(frames)
    result = tuple(math.floor(Fraction(str(t)) * fps + Fraction(1, 2)) for t in (start, end))
    if result[1] <= result[0]:
        raise ValueError("Material window rounds to no displayed frames")
    return result


def material_timing(item, spans):
    """Check temporal association, not whether an image proves the spoken claim."""
    start, end = interval(item["output_range"])
    linked = [interval(spans[s]["output_range"]) for s in item["span_ids"]]
    exception = item.get("timing_exception")
    allowed = None
    if exception is not None:
        if (not isinstance(exception, dict) or not isinstance(exception.get("reason"), str)
                or not exception["reason"].strip()):
            raise ValueError("timing_exception needs a concrete reason")
        allowed = number(exception["max_offset_seconds"])
        if allowed < 0:
            raise ValueError("timing_exception max_offset_seconds must be nonnegative")
    if any(start < source_end and end > source_start for source_start, source_end in linked):
        return
    gap = min(max(source_start - end, start - source_end, 0) for source_start, source_end in linked)
    if allowed is None or gap > allowed + 1e-9:
        raise ValueError("Material does not overlap its linked spoken spans; record a justified timing_exception for intentional lead/lag")


def continuous_material_errors(windows, limit_frames, presentation="fullscreen"):
    """Same-source continuations share a cap; a one-frame seam does not reset it."""
    grouped = {}
    for key, start, end, identifier in windows:
        grouped.setdefault(key, []).append((start, end, identifier))
    errors = []
    for entries in grouped.values():
        chain = None
        for start, end, identifier in sorted(entries):
            if chain is None:
                chain = [start, end, [identifier]]
            elif start <= chain[1] + 1:
                chain[1] = max(chain[1], end)
                chain[2].append(identifier)
            else:
                if len(chain[2]) > 1 and chain[1] - chain[0] > limit_frames:
                    errors.append(f"materials {', '.join(chain[2])}: continuous {presentation} presentation exceeds {limit_frames} frames; splitting IDs does not reset the cap")
                chain = [start, end, [identifier]]
        if chain is not None and len(chain[2]) > 1 and chain[1] - chain[0] > limit_frames:
            errors.append(f"materials {', '.join(chain[2])}: continuous {presentation} presentation exceeds {limit_frames} frames; splitting IDs does not reset the cap")
    return list(dict.fromkeys(errors))


def time_seconds(value):
    parts = str(value).split(":")
    if len(parts) > 3:
        raise ValueError("Use seconds, MM:SS or HH:MM:SS")
    values = [number(part) for part in parts]
    if any(v < 0 for v in values) or (len(values) > 1 and any(v >= 60 for v in values[1:])):
        raise ValueError("Invalid timecode")
    return sum(v * 60 ** i for i, v in enumerate(reversed(values)))


def interval(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("Range must be [in_seconds, out_seconds]")
    start, end = map(number, value)
    if start < 0 or end <= start:
        raise ValueError("Range must have 0 <= in < out")
    return start, end


def load_state(path):
    data = read_json(path)
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported schema_version")
    if not isinstance(data.get("versions"), dict) or data.get("active_version") not in data["versions"]:
        raise ValueError("active_version must exist in versions")
    for name in ("spans", "checks", "feedback", "materials", "semantic_reviews"):
        if not isinstance(data.get(name), list):
            raise ValueError(f"{name} must be an array")
        ids = [item.get("id") for item in data[name]]
        if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise ValueError(f"{name} IDs must be nonempty and unique")
    return data


def resolve(base, path):
    return (base / path).resolve()


def artifact(base, item, cache):
    path = resolve(base, item["path"])
    if not path.is_file():
        raise ValueError(f"Missing file: {path}")
    wanted = item.get("sha256", "")
    if not re.fullmatch(r"[a-f0-9]{64}", wanted):
        raise ValueError(f"Missing/invalid SHA-256: {path}")
    key = str(path)
    if key not in cache:
        cache[key] = sha256(path)
    if cache[key] != wanted:
        raise ValueError(f"File identity changed: {path}")
    return path


def get_pointer(data, pointer):
    if pointer == "":
        return data
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must start with /")
    for part in pointer[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def packet_identity(path):
    data = run_json([
        "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_streams",
        "-show_packets", "-show_data_hash", "sha256", "-show_entries",
        "stream=codec_name,sample_rate,channels,channel_layout,time_base,extradata_hash:"
        "packet=pts,dts,duration,data_hash,side_data_list", "-of", "json", str(path),
    ])
    if not data.get("streams") or not data.get("packets"):
        raise ValueError("No audio stream/packets for identity check")
    return data


def review_record(base, record, version, cache):
    if record.get("video_sha256") != version["video"]["sha256"]:
        raise ValueError("Review belongs to another video version")
    reviewer = record.get("reviewer", {})
    if reviewer.get("kind") not in {"user", "human", "agent"} or not reviewer.get("name"):
        raise ValueError("Record reviewer kind and identity; do not invent human review")
    if not record.get("observed_at") or not record.get("method"):
        raise ValueError("Review needs observed_at and actual method")
    if record.get("verdict") != "accepted":
        raise ValueError("Review is pending, uncertain or rejected")
    evidence = record.get("evidence", [])
    if not evidence:
        raise ValueError("Review needs evidence artifacts")
    for item in evidence:
        artifact(base, item, cache)


def validate_mapping(span, versions):
    if span["version"] not in versions or not span.get("utterance_id"):
        raise ValueError("Missing version or stable utterance_id")
    version = versions[span["version"]]
    if span.get("video_sha256") != version["video"]["sha256"]:
        raise ValueError("Stale timeline binding")
    start, end = interval(span["output_range"])
    source_start, source_end = interval(span["source_range"])
    rate, fps = number(span["rate"]), float(frame_rate(version["fps"]))
    if rate <= 0 or fps <= 0:
        raise ValueError("Rate/fps must be positive")
    tolerance = max(1 / fps, 0.002)
    if end > number(version["duration_seconds"]) + tolerance:
        raise ValueError("Span exceeds version duration")
    if abs((source_end - source_start) / rate - (end - start)) > tolerance:
        raise ValueError("Source/output mapping disagrees with rate; split non-affine edits")
    return start, end, source_start, rate


def locate(data, version_id, position=None, feedback_id=None, base=None):
    if feedback_id:
        match = next((f for f in data["feedback"] if f["id"] == feedback_id), None)
        if not match:
            raise ValueError("Unknown feedback ID")
        version_id, position = match["observed_version"], number(match["at"])
    if version_id not in data["versions"]:
        raise ValueError("Choose the version the user actually watched")
    position = time_seconds(position)
    cache = {}
    if base is not None:
        artifact(base, data["versions"][version_id]["video"], cache)
    if position >= number(data["versions"][version_id]["duration_seconds"]):
        raise ValueError("Time is outside watched video")
    hits = []
    for span in data["spans"]:
        if span["version"] != version_id:
            continue
        start, end, source_start, rate = validate_mapping(span, data["versions"])
        if start <= position < end:
            if base is not None:
                artifact(base, span["source"], cache)
            hits.append({**span, "source_second": source_start + (position - start) * rate})
    utterances = {s["utterance_id"] for s in hits}
    occurrences = [{"span_id": s["id"], "version": s["version"], "output_range": s["output_range"]}
                   for s in data["spans"] if s["utterance_id"] in utterances]
    return {"version": version_id, "output_second": position, "matches": hits,
            "all_occurrences": occurrences, "note": "No match means unmapped, not absent from the video."}


def check_state(data, base, media=False, stage="delivery"):
    cache, errors, results, pending, risks = {}, [], [], [], []
    active = data["active_version"]
    version = data["versions"][active]
    try:
        artifact(base, version["video"], cache)
        duration = number(version["duration_seconds"])
        exact_fps = frame_rate(version["fps"])
        fps = float(exact_fps)
        if duration <= 0 or fps <= 0:
            raise ValueError("Duration/fps must be positive")
        material_policy = version.get("materials_policy")
        material_limits = material_frame_limits(material_policy, exact_fps)
    except (ValueError, KeyError, TypeError, OSError) as error:
        return {"status": "fail", "errors": [str(error)], "checks": [], "pending": [], "risks": []}
    spans = {s["id"]: s for s in data["spans"]}
    for span in data["spans"]:
        try:
            validate_mapping(span, data["versions"])
            if span["version"] == active:
                artifact(base, span["source"], cache)
        except (ValueError, KeyError, TypeError, OSError) as error:
            errors.append(f"span {span['id']}: {error}")
    selected_checks = [c for c in data["checks"] if c.get("version") == active]
    if not selected_checks:
        pending.append("No active-version acceptance checks recorded")
    for item in selected_checks:
        result = {"id": item["id"], "kind": item.get("kind"), "scope": item.get("scope"), "status": "fail"}
        try:
            if not item.get("scope"):
                raise ValueError("State the actual check scope")
            if item.get("video_sha256") != version["video"]["sha256"]:
                raise ValueError("Check belongs to another video version")
            kind = item["kind"]
            if kind == "file_sha256":
                artifact(base, item["artifact"], cache)
            elif kind == "text":
                text = artifact(base, item["artifact"], cache).read_text(encoding="utf-8")
                required, forbidden = item.get("contains", []), item.get("excludes", [])
                if not required and not forbidden:
                    raise ValueError("Text check must contain at least one assertion")
                if any(t not in text for t in required) or any(t in text for t in forbidden):
                    raise ValueError("Exact text assertion failed")
            elif kind == "json_value":
                value = read_json(artifact(base, item["artifact"], cache))
                if get_pointer(value, item["pointer"]) != item["equals"]:
                    raise ValueError("JSON value does not match approved setting")
            elif kind in {"media_duration", "audio_identity"}:
                if not media:
                    result["status"] = "pending"
                    result["detail"] = "Run with --media to execute this check"
                    results.append(result)
                    continue
                video_path = artifact(base, version["video"], cache)
                if kind == "media_duration":
                    actual = number(probe(video_path)["format"]["duration"])
                    if abs(actual - number(item["expected_seconds"])) > number(item.get("tolerance_seconds", 0.05)):
                        raise ValueError("Media duration differs from approved duration")
                else:
                    baseline = artifact(base, item["baseline"], cache)
                    if packet_identity(baseline) != packet_identity(video_path):
                        raise ValueError("Audio packets, codec or timestamps changed")
            elif kind == "review":
                review_record(base, item["review"], version, cache)
                result["status"] = "review_recorded"
                result["detail"] = "Record and file binding checked; tool did not perform this review"
            else:
                raise ValueError(f"Unsupported check kind: {kind}")
            if kind != "review":
                result["status"] = "pass"
        except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
            result["detail"] = str(error)
        results.append(result)
    check_results = {r["id"]: r for r in results}
    for item in data["feedback"]:
        try:
            if item["observed_version"] not in data["versions"]:
                raise ValueError("Unknown observed version")
            at = number(item["at"])
            if not 0 <= at < number(data["versions"][item["observed_version"]]["duration_seconds"]):
                raise ValueError("Feedback timestamp outside observed video")
            if not item.get("request") or not item.get("span_ids"):
                raise ValueError("Feedback needs request and mapped span_ids")
            if any(s not in spans for s in item["span_ids"]):
                raise ValueError("Unknown mapped span")
            observed = [spans[s] for s in item["span_ids"] if spans[s]["version"] == item["observed_version"]]
            if not any(interval(s["output_range"])[0] <= at < interval(s["output_range"])[1] for s in observed):
                raise ValueError("Feedback time is not inside its watched-version mapped spans")
            status = item.get("status")
            if status not in {"open", "located", "applied", "verified", "superseded"}:
                raise ValueError("Invalid feedback status")
            if status == "superseded":
                if not item.get("reason"):
                    raise ValueError("Superseded feedback needs reason")
            elif status == "verified":
                if item.get("resolved_version") != active:
                    pending.append(f"feedback {item['id']}: carry forward or recheck for {active}")
                else:
                    ids = item.get("check_ids", [])
                    if not ids or any(check_results.get(i, {}).get("status") not in {"pass", "review_recorded"} for i in ids):
                        raise ValueError("Verified feedback needs successful current-version checks")
                    acceptance = item.get("acceptance", "rendered")
                    if acceptance not in {"artifact", "rendered"}:
                        raise ValueError("Acceptance must be artifact or rendered")
                    if acceptance == "rendered" and not any(check_results[i]["kind"] == "review" for i in ids):
                        raise ValueError("Rendered feedback needs actual-output review; text/config pass is insufficient")
            else:
                pending.append(f"feedback {item['id']}: {status}")
        except (ValueError, KeyError, TypeError) as error:
            errors.append(f"feedback {item['id']}: {error}")
    semantic_by_span = {}
    for item in data["semantic_reviews"]:
        if item.get("version") != active:
            continue
        try:
            ids = item.get("span_ids", [])
            if not ids or any(i not in spans or spans[i]["version"] != active for i in ids):
                raise ValueError("Semantic review must reference current spans")
            before, after = item["before"], item["after"]
            if not before.strip() or not after.strip():
                raise ValueError("Need original context and actual retained words")
            removed = (set(re.findall(r"[a-z]+", before.lower())) - set(re.findall(r"[a-z]+", after.lower()))) & SENSITIVE_WORDS
            if removed:
                risks.append({"id": item["id"], "removed_sensitive_words": sorted(removed), "meaning": "heuristic only; absence of flags does not prove fidelity"})
            before_tokens = re.findall(r"\w+", before.lower())
            after_tokens = re.findall(r"\w+", after.lower())
            source_words = iter(before_tokens)
            if not all(any(word == candidate for candidate in source_words) for word in after_tokens):
                risks.append({"id": item["id"], "retained_word_order_changed": True,
                              "meaning": "After text is not a deletion-only subsequence; verify all actual sources and do not substitute paraphrase"})
            for dimension in DIMENSIONS:
                review = item["dimensions"][dimension]
                if review.get("verdict") not in {"preserved", "changed_with_authorization"} or not review.get("note"):
                    raise ValueError(f"Unresolved semantic dimension: {dimension}")
                if review["verdict"] == "changed_with_authorization" and not review.get("authorization"):
                    raise ValueError("Semantic change needs concrete authorization")
            review_record(base, item["review"], version, cache)
            for span_id in ids:
                semantic_by_span[span_id] = item["id"]
        except (ValueError, KeyError, TypeError, OSError) as error:
            errors.append(f"semantic {item['id']}: {error}")
    for span in data["spans"]:
        if span["version"] == active and span.get("semantic_review_required") and span["id"] not in semantic_by_span:
            pending.append(f"span {span['id']}: semantic review missing")
    material_windows = {}
    material_kinds = {}
    placed_materials = 0
    for item in data["materials"]:
        if item.get("version") != active:
            continue
        try:
            if not all(item.get(k) for k in ("topic", "purpose", "span_ids")):
                raise ValueError("Need topic, editorial purpose and source spans")
            if any(s not in spans or spans[s]["version"] != active for s in item["span_ids"]):
                raise ValueError("Unknown/current-version material span")
            if item.get("status") == "placed":
                placed_materials += 1
                for key in ("source_url", "author", "observed_at", "semantic_limits"):
                    if not item.get(key):
                        raise ValueError(f"Placed material missing {key}")
                artifact(base, item["asset"], cache)
                artifact(base, item["source_evidence"], cache)
                start, end = interval(item["output_range"])
                if end > duration:
                    raise ValueError("Material exceeds video duration")
                mode = item.get("display_mode")
                if (mode is not None or material_policy is not None) and mode not in {"fullscreen", "overlay"}:
                    raise ValueError("Placed material needs display_mode fullscreen or overlay when a materials_policy is active")
                if "continuity_id" in item and (not isinstance(item["continuity_id"], str) or not item["continuity_id"].strip()):
                    raise ValueError("continuity_id must be a nonempty string")
                identities = [("asset", item["asset"]["sha256"])]
                if item.get("continuity_id"):
                    identities.append(("continuity", item["continuity_id"]))
                limit_kind = None
                if material_limits is not None:
                    if "legacy" in material_limits:
                        limit_kind = "legacy" if mode == "fullscreen" else None
                    else:
                        kind = item.get("asset_type")
                        if kind not in {"static", "video"}:
                            raise ValueError("Typed material limits require asset_type static or video; classify the content, not the file extension")
                        for identity in identities:
                            if identity in material_kinds and material_kinds[identity] != kind:
                                raise ValueError("The same asset or continuity_id cannot use conflicting asset_type values")
                            material_kinds[identity] = kind
                        if kind == "video" or mode == "fullscreen":
                            limit_kind = kind
                limit_frames = material_limits[limit_kind] if limit_kind else None
                if item.get("output_frames") is not None or limit_frames is not None:
                    start_frame, end_frame = material_frames(item, exact_fps)
                material_timing(item, spans)
                if limit_frames is not None:
                    if end_frame - start_frame > limit_frames:
                        raise ValueError(f"Material uses {end_frame - start_frame} frames; policy allows {limit_frames}")
                    for identity in identities:
                        material_windows.setdefault(limit_kind, []).append((identity, start_frame, end_frame, item["id"]))
                metric = item.get("metric")
                if metric:
                    if not all(metric.get(k) for k in ("kind", "display_value", "source_url", "observed_at")):
                        raise ValueError("Metric missing kind/display/source/date")
                    artifact(base, metric["evidence"], cache)
                    if metric["kind"] == "views" and metric["source_url"] != item["source_url"]:
                        raise ValueError("Views must belong to this same post")
            elif item.get("status") == "excluded":
                if not item.get("reason"):
                    raise ValueError("Excluded material needs reason")
            elif item.get("status") not in {"planned", "found"}:
                raise ValueError("Unknown material status")
            if stage == "delivery" and item.get("required") and item.get("status") != "placed":
                pending.append(f"material {item['id']}: requested material not placed")
            if stage == "delivery" and item.get("required") and item.get("status") == "placed":
                ids = item.get("export_check_ids", [])
                if not ids or any(check_results.get(i, {}).get("status") != "review_recorded" for i in ids):
                    pending.append(f"material {item['id']}: actual exported window review missing")
        except (ValueError, KeyError, TypeError, OSError) as error:
            errors.append(f"material {item['id']}: {error}")
    if material_limits is not None:
        for kind, windows in material_windows.items():
            presentation = "video" if kind == "video" else "fullscreen"
            errors.extend(continuous_material_errors(windows, material_limits[kind], presentation))
    elif placed_materials:
        risks.append({"materials_policy_missing": True,
                      "meaning": "No fullscreen duration cap was enforced. Set this version's materials_policy for an explicit project limit; no Cathy default is assumed."})
    errors.extend(f"check {r['id']}: {r.get('detail')}" for r in results if r["status"] == "fail")
    pending.extend(f"check {r['id']}: {r.get('detail')}" for r in results if r["status"] == "pending")
    return {"status": "fail" if errors else "pending" if pending else "checked",
            "version": active, "video_sha256": version["video"]["sha256"], "stage": stage,
            "errors": errors, "pending": pending, "checks": results, "risks": risks,
            "semantic_review_records": semantic_by_span,
            "boundary": "Only specified mechanical checks and evidence bindings were checked. Text/config checks do not prove burned-in pixels; review_recorded does not mean the tool listened, watched or certified meaning."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a version-bound state from an existing video")
    init.add_argument("--video", required=True)
    init.add_argument("--version", required=True)
    init.add_argument("--project", required=True)
    init.add_argument("--out", required=True)
    init.add_argument("--preset", help="Copy only material duration limits from this explicit project/style preset")
    lookup = commands.add_parser("locate", help="Map watched-version time to source and every reused occurrence")
    lookup.add_argument("state")
    lookup.add_argument("--version")
    group = lookup.add_mutually_exclusive_group(required=True)
    group.add_argument("--time")
    group.add_argument("--feedback")
    check = commands.add_parser("check", help="Check declared requirements, mappings and evidence")
    check.add_argument("state")
    check.add_argument("--media", action="store_true", help="Also execute ffprobe duration/audio packet checks")
    check.add_argument("--stage", choices=("plan", "delivery"), default="delivery")
    check.add_argument("--out")
    args = parser.parse_args()
    try:
        if args.command == "init":
            target = Path(args.out)
            if target.exists():
                raise ValueError("State already exists; preserve it and add a new version explicitly")
            video = Path(args.video).resolve()
            info = probe(video)
            stream = next(s for s in info["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic"))
            exact_fps = frame_rate(stream["avg_frame_rate"])
            version = {"video": {"path": str(video), "sha256": sha256(video)},
                       "fps": str(exact_fps), "duration_seconds": number(info["format"]["duration"])}
            if args.preset:
                preset_path = Path(args.preset).resolve()
                preset = read_json(preset_path)
                if (not isinstance(preset, dict) or not isinstance(preset.get("id"), str)
                        or not preset["id"].strip()):
                    raise ValueError("Preset needs a nonempty id for provenance")
                materials = preset["materials"]
                if not isinstance(materials, dict):
                    raise ValueError("Preset materials must be an object")
                keys = ("fullscreen_max_seconds", "static_fullscreen_max_seconds", "video_max_seconds")
                policy = {key: number(materials[key]) for key in keys if key in materials}
                material_frame_limits(policy, exact_fps)
                version["materials_policy"] = policy
                version["materials_policy_source"] = {
                    "preset_id": preset["id"],
                    "preset": {"path": str(preset_path), "sha256": sha256(preset_path)},
                }
            data = {"schema_version": 1, "project": args.project, "active_version": args.version,
                    "versions": {args.version: version}, "spans": [], "checks": [], "feedback": [],
                    "materials": [], "semantic_reviews": []}
            write_json(target, data)
            print(json.dumps({"created": str(target.resolve()), "acceptance": "Not checked; add relevant mappings and acceptance conditions"}, ensure_ascii=False))
            return 0
        data = load_state(args.state)
        if args.command == "locate":
            if args.time is not None and not args.version:
                raise ValueError("--time requires --version; do not guess which version the user watched")
            result = locate(data, args.version, args.time, args.feedback, Path(args.state).resolve().parent)
        else:
            result = check_state(data, Path(args.state).resolve().parent, args.media, args.stage)
            if args.out:
                if Path(args.out).resolve() == Path(args.state).resolve():
                    raise ValueError("Report must not overwrite state")
                write_json(args.out, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if args.command == "locate" or result["status"] == "checked" else 2
    except (ValueError, KeyError, TypeError, StopIteration, OSError, ZeroDivisionError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
