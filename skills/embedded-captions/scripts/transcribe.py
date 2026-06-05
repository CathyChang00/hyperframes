#!/usr/bin/env python3
"""
Word-level transcription via ElevenLabs Scribe v2.

Scribe gives tighter timing than Whisper and handles background music
reasonably; cost is low (one pass per video).

Usage:
  python transcribe.py <project-dir>

Reads:  <project-dir>/source.mp4 (audio track)
Writes: <project-dir>/transcript.json  — { text, language_code, words: [{text, start, end, type}] }

Requires env: ELEVENLABS_API_KEY
"""
import os, sys, json, glob, shutil, subprocess, pathlib


def ensure_source(project: pathlib.Path) -> pathlib.Path:
    """Resolve the input clip to <project>/source.mp4 (idempotent; mirrors matte-rvm.py)."""
    src = project / "source.mp4"
    if src.exists():
        return src
    EXCL = {"final", "bg_plus_caps", "fg_caps", "audio"}
    cands = []
    for ext in ("mp4", "mov", "webm", "mkv", "m4v"):
        cands += [pathlib.Path(x) for x in glob.glob(str(project / f"*.{ext}"))]
    cands = [c for c in cands if c.stem not in EXCL and not c.name.startswith("index")]
    found = max(cands, key=lambda c: c.stat().st_size) if cands else None
    if not found:
        hj = project / "hyperframes.json"
        if hj.exists():
            try:
                v = (json.load(open(hj)).get("video") or "")
                if v and (project / v).exists():
                    found = project / v
            except Exception:
                pass
    if found:
        try:
            src.symlink_to(found.name)
        except OSError:
            shutil.copy(found, src)
    return src


def _usable_words(d) -> bool:
    ws = d.get("words") if isinstance(d, dict) else None
    return isinstance(ws, list) and any(
        isinstance(w, dict) and "start" in w and "end" in w for w in ws
    )


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: transcribe.py <project-dir>")
    project = pathlib.Path(sys.argv[1]).resolve()
    src = ensure_source(project)

    out_path = project / "transcript.json"
    existing = {}
    if out_path.exists():
        try:
            existing = json.load(open(out_path))
        except Exception:
            existing = {}
    if "words" in existing and "language_code" in existing:
        print("[transcribe] already have Scribe v2 transcript, skipping")
        return

    # Scribe v2 is the primary engine, but the key is OPTIONAL: if it's unset,
    # fall back to any usable word-level transcript already in the project (one
    # hyperframes init wrote, or one the user dropped in) instead of hard-failing.
    if not os.environ.get("ELEVENLABS_API_KEY"):
        if _usable_words(existing):
            n = sum(1 for w in existing["words"] if isinstance(w, dict) and "start" in w)
            print(f"[transcribe] no ELEVENLABS_API_KEY — using existing transcript.json "
                  f"({n} word-level entries) as-is")
            return
        sys.exit("[transcribe] ELEVENLABS_API_KEY not set and no usable word-level "
                 "transcript.json found. Set the key, or drop a transcript.json with "
                 "words[].{text,start,end} into the project.")

    if not src.exists():
        sys.exit(f"[transcribe] no source audio/video found in {project}")
    audio = project / "audio.mp3"
    if not audio.exists():
        subprocess.check_call([
            "ffmpeg", "-y", "-i", str(src),
            "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(audio)
        ], stderr=subprocess.DEVNULL)
    if existing:
        print("[transcribe] replacing existing transcript with Scribe v2")

    from elevenlabs import ElevenLabs
    client = ElevenLabs()
    with open(audio, "rb") as f:
        r = client.speech_to_text.convert(
            file=f, model_id="scribe_v2", timestamps_granularity="word"
        )

    out = {
        "text": r.text,
        "language_code": r.language_code,
        "words": [
            {"text": w.text, "start": w.start, "end": w.end, "type": w.type}
            for w in r.words
        ],
    }
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    nword = sum(1 for w in out["words"] if w["type"] == "word")
    print(f"[transcribe] {nword} words, lang={out['language_code']} → {out_path}")
    print(f"[transcribe] text: {r.text[:160]}{'…' if len(r.text) > 160 else ''}")


if __name__ == "__main__":
    main()
