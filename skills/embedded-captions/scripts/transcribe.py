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
import os, sys, json, subprocess, pathlib
from elevenlabs import ElevenLabs


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: transcribe.py <project-dir>")
    project = pathlib.Path(sys.argv[1]).resolve()
    src = project / "source.mp4"
    if not src.exists():
        sys.exit(f"[transcribe] not found: {src}")

    audio = project / "audio.mp3"
    if not audio.exists():
        subprocess.check_call([
            "ffmpeg", "-y", "-i", str(src),
            "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(audio)
        ], stderr=subprocess.DEVNULL)

    out_path = project / "transcript.json"
    if out_path.exists():
        # hyperframes init pre-writes a whisper-shaped transcript. Detect
        # it and replace with Scribe v2 — whisper schema has top-level
        # "systeminfo"/"transcription", Scribe has "words"/"language_code".
        try:
            existing = json.load(open(out_path))
        except Exception:
            existing = {}
        is_scribe = "words" in existing and "language_code" in existing
        if is_scribe:
            print(f"[transcribe] already have Scribe v2 transcript, skipping")
            return
        print(f"[transcribe] replacing whisper-shape transcript with Scribe v2")

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
