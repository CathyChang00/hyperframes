#!/usr/bin/env python3
"""Make three local audio comparisons; never infer words or certify listening."""

import argparse
from fractions import Fraction
import hashlib
import html
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f"Command failed ({command[0]}): {result.stderr[-4000:]}")
    return result.stdout


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(path, audio_stream):
    data = json.loads(run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ]))
    streams = [s for s in data["streams"] if s["codec_type"] == "audio"]
    if audio_stream < 0 or audio_stream >= len(streams):
        raise ValueError(f"No audio stream a:{audio_stream} in {path}")
    stream = streams[audio_stream]
    duration = stream.get("duration")
    # A container duration is not necessarily the selected audio duration.
    return {
        "audio_stream": audio_stream,
        "sample_rate": int(stream["sample_rate"]),
        "channels": stream["channels"],
        "stream_start_time": stream.get("start_time"),
        "container_start_time": data.get("format", {}).get("start_time"),
        "reported_audio_duration": float(duration) if duration else None,
    }


def wav_duration(path):
    # ffmpeg writes extensible PCM headers that older Python wave cannot read.
    data = json.loads(run([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=duration_ts,time_base", "-of", "json", str(path),
    ]))["streams"][0]
    return float(int(data["duration_ts"]) * Fraction(data["time_base"]))


def atempo_filters(ratio):
    factors = []
    while ratio > 2:
        factors.append(2.0)
        ratio /= 2
    while ratio < 0.5:
        factors.append(0.5)
        ratio /= 0.5
    factors.append(ratio)
    return ",".join(f"atempo={factor:.12g}" for factor in factors)


def extract(path, stream, start, end, sample_rate, output):
    # Sample offsets make the reference explicit even when a stream has a
    # non-zero initial PTS. No gain, noise reduction, fades, or channel mixing.
    first = round(start * sample_rate)
    last = round(end * sample_rate)
    command = [
        "ffmpeg", "-nostdin", "-v", "error", "-n", "-i", str(path),
        "-map", f"0:a:{stream}", "-vn", "-sn", "-dn", "-af",
        f"atrim=start_sample={first}:end_sample={last},asetpts=PTS-STARTPTS",
        "-c:a", "pcm_s24le", "-ar", "48000", str(output),
    ]
    run(command)
    return command


def check_duration(path, expected, tolerance):
    actual = wav_duration(path)
    if abs(actual - expected) > tolerance:
        raise ValueError(
            f"{path.name}: expected {expected:.6f}s, got {actual:.6f}s "
            f"(tolerance {tolerance:.6f}s). No padding or tail trimming applied."
        )
    return {"expected_seconds": expected, "actual_seconds": actual,
            "tolerance_seconds": tolerance, "sha256": sha256(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for kind in ("original", "processed"):
        parser.add_argument(f"--{kind}", required=True, type=Path)
        parser.add_argument(f"--{kind}-start", required=True, type=float,
                            help="Seconds from the first decoded sample of selected audio")
        parser.add_argument(f"--{kind}-end", required=True, type=float)
        parser.add_argument(f"--{kind}-audio-stream", type=int, default=0,
                            help="Audio stream ordinal, e.g. 0 means 0:a:0")
    parser.add_argument("--processed-baked-speed", required=True, type=float)
    parser.add_argument("--target-speed", required=True, type=float)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--same-content-confirmed", action="store_true",
                      help="Both intervals contain the same continuous words/context; no internal cuts")
    mode.add_argument("--diagnostic-difference", metavar="DESCRIPTION",
                      help="Explicit content difference, e.g. current version has a cut tail; not aligned evidence")
    parser.add_argument("--label", default="争议音频对照")
    parser.add_argument("--output", required=True, type=Path,
                        help="New directory; existing directories are never overwritten")
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        diagnostic = args.diagnostic_difference is not None
        if diagnostic and not args.diagnostic_difference.strip():
            raise ValueError("Diagnostic mode requires a non-empty description of the content difference")
        if output.exists():
            raise ValueError(f"Output already exists; choose a new directory: {output}")
        for tool in ("ffmpeg", "ffprobe"):
            if not shutil.which(tool):
                raise ValueError(f"Missing executable: {tool}")
        for speed in (args.processed_baked_speed, args.target_speed):
            if not math.isfinite(speed) or not 0.125 <= speed <= 8:
                raise ValueError("Speeds must be finite and between 0.125 and 8")
        sources = {}
        for kind in ("original", "processed"):
            path = getattr(args, kind).resolve()
            start, end = (getattr(args, f"{kind}_{edge}") for edge in ("start", "end"))
            if not path.is_file():
                raise ValueError(f"Input is not a file: {path}")
            if not all(math.isfinite(t) for t in (start, end)) or not 0 <= start < end:
                raise ValueError(f"{kind}: require finite 0 <= start < end")
            if end - start > 120:
                raise ValueError(f"{kind}: choose a short context window of at most 120 seconds")
            info = probe(path, getattr(args, f"{kind}_audio_stream"))
            duration = info["reported_audio_duration"]
            if duration is not None and end > duration + 1 / info["sample_rate"]:
                raise ValueError(f"{kind}: end exceeds selected audio duration {duration}")
            stat = path.stat()
            sources[kind] = dict(info, path=str(path), start_seconds=start,
                                 end_seconds=end, bytes=stat.st_size,
                                 mtime_ns=stat.st_mtime_ns)
        raw_length = args.original_end - args.original_start
        current_length = args.processed_end - args.processed_start
        expected_current = raw_length / args.processed_baked_speed
        duration_mapping_matches = abs(current_length - expected_current) <= 0.05
        if not diagnostic and not duration_mapping_matches:
            raise ValueError(
                "Intervals do not map to the same continuous context: "
                f"processed must be {expected_current:.6f}s at "
                f"{args.processed_baked_speed:g}x (tolerance 0.05s). "
                "Verify timestamps and baked speed, or declare the actual content difference "
                "with --diagnostic-difference instead of --same-content-confirmed."
            )
        for source in sources.values():
            source["sha256"] = sha256(Path(source["path"]))
        output.mkdir(parents=True)
        files = [output / name for name in
                 ("01-original.wav", "02-current.wav", "03-final-speed.wav")]
        commands = []
        for kind, path in zip(("original", "processed"), files):
            source = sources[kind]
            commands.append(extract(source["path"], source["audio_stream"],
                                    source["start_seconds"], source["end_seconds"],
                                    source["sample_rate"], path))
        checks = [check_duration(files[0], raw_length, 0.005),
                  check_duration(files[1], current_length, 0.005)]
        ratio = args.target_speed / args.processed_baked_speed
        if math.isclose(ratio, 1, rel_tol=0, abs_tol=1e-12):
            shutil.copyfile(files[1], files[2])
        else:
            command = ["ffmpeg", "-nostdin", "-v", "error", "-n",
                       "-i", str(files[1]), "-af", atempo_filters(ratio),
                       "-c:a", "pcm_s24le", str(files[2])]
            run(command)
            commands.append(command)
        expected_final = current_length / ratio
        checks.append(check_duration(files[2], expected_final,
                                     max(0.08, expected_final * 0.005)))
        for source in sources.values():
            stat = Path(source["path"]).stat()
            if (stat.st_size, stat.st_mtime_ns) != (source["bytes"], source["mtime_ns"]):
                raise ValueError("Input changed during rendering; discard this comparison")
        titles = ["原速原声 · 1×", f"当前处理 · 已烘焙 {args.processed_baked_speed:g}×",
                  f"最终倍率 · {args.target_speed:g}×"]
        report = {
            "schema_version": 1, "label": args.label,
            "comparison_mode": "diagnostic_difference" if diagnostic else "same_content",
            "diagnostic_difference": args.diagnostic_difference,
            "timebase": "elapsed decoded audio samples from selected stream start; not video/container PTS",
            "intervals": "half-open [start, end); sample boundaries rounded to nearest, ties to even",
            "same_continuous_content": "not_asserted_unaligned_diagnostic" if diagnostic else "operator_asserted_not_machine_verified",
            "duration_mapping": {"expected_processed_seconds_if_same_content": expected_current,
                                 "actual_processed_seconds": current_length,
                                 "within_0_05_seconds": duration_mapping_matches,
                                 "word_alignment": "not_verified"},
            "sources": sources, "original_speed": 1,
            "processed_baked_speed": args.processed_baked_speed,
            "target_speed": args.target_speed, "additional_tempo_ratio": ratio,
            "processing": "PCM 24-bit / 48 kHz; original channel count; no gain or denoise; final uses pitch-preserving atempo only",
            "outputs": [dict(check, file=path.name, title=title)
                        for path, title, check in zip(files, titles, checks)],
            "commands": commands, "technical_status": "duration_and_identity_checks_passed",
            "human_review": {"status": "pending", "words": "not_determined",
                             "tail_integrity": "not_certified", "sound_quality": "not_certified"},
        }
        (output / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        cards = "".join(
            f'<section><h2>{html.escape(title)}</h2><audio controls preload="metadata" '
            f'src="{path.name}"></audio><p>{check["actual_seconds"]:.3f} 秒</p></section>'
            for path, title, check in zip(files, titles, checks)
        )
        comparison_note = (
            "未对齐诊断：" + html.escape(args.diagnostic_difference) +
            "。原片与当前片有已声明的内容差异，不是逐词对齐证据。第三段只变速当前片，未补词或修复缺失。"
            if diagnostic else "三段均使用操作者已定位的同一连续上下文；程序未认证逐词对齐。"
        )
        page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(args.label)}</title>
<style>body{{font:18px/1.6 system-ui;margin:48px auto;max-width:820px;padding:0 24px;background:#f5f5f3;color:#202421}}h1{{font-size:28px}}h2{{font-size:20px}}section{{background:white;padding:20px 24px;margin:20px 0;border-radius:12px}}audio{{width:100%}}p{{color:#545a55}}</style>
<h1>{html.escape(args.label)}</h1><p>{comparison_note}</p><p>当前版本的倍率已烘焙，播放器请保持 1×；第三段仅再应用 {ratio:.6g}×，最终为 {args.target_speed:g}×。</p>
{cards}<p>仅完成文件、时长及倍率检查，尚未听审；未判断原词、词尾完整性或音质优劣。保留原有声道和响度，不做自动降噪或音量归一化。</p>
<p>时间均从各文件所选音轨的首个解码样本计起。原片 [{args.original_start:g}, {args.original_end:g}) 秒；当前片 [{args.processed_start:g}, {args.processed_end:g}) 秒。</p>
<a href="comparison.json">查看来源、时间映射与 SHA-256 记录</a></html>'''
        (output / "index.html").write_text(page, encoding="utf-8")
        print(json.dumps({"comparison": str(output / "index.html"),
                          "record": str(output / "comparison.json"),
                          "mode": report["comparison_mode"],
                          "human_review": "pending"}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
