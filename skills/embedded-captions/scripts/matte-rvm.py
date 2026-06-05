#!/usr/bin/env python3
"""
Foreground matting for the embedded-captions skill.

Uses RobustVideoMatting (RVM) MobileNetV3 ONNX with CPU fp32. CoreML is
avoided because the CoreML execution-provider partitions the graph and
introduces fp precision issues that show up as corrupted alpha inside
the subject's face (alpha ≈ 30 instead of 255).

Usage:
  python matte-rvm.py <project-dir>

Reads:
  <project-dir>/source.mp4  OR  <project-dir>/frames_bg/f_%04d.png
Writes:
  <project-dir>/frames_fg/f_%04d.png   (RGBA, subject opaque, bg transparent)
"""
import os, sys, glob, time, json, shutil, subprocess, pathlib
import numpy as np
import onnxruntime as ort
from PIL import Image

SCRIPT_DIR = pathlib.Path(__file__).parent
MODEL_PATH = SCRIPT_DIR.parent / "assets" / "rvm_mobilenetv3_fp32.onnx"
MODEL_URL  = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx"


def ensure_model():
    if MODEL_PATH.exists():
        return
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"[matte] downloading RVM weights (~14MB) to {MODEL_PATH}", flush=True)
    subprocess.check_call(["curl", "-fL", "-o", str(MODEL_PATH), MODEL_URL])


def downsample_for_height(h: int) -> float:
    # RVM recommendation: process at ~512 on shorter edge.
    return round(min(1.0, 512.0 / max(h, 1)), 3)


def ensure_source(project: pathlib.Path) -> pathlib.Path:
    """Resolve the input clip to <project>/source.mp4 (creating a symlink).

    `hyperframes init --video X.mp4` copies the clip under its own name, but the
    rest of the pipeline (this script, transcribe.py, and the rendered a-roll
    <video src="source.mp4">) expects source.mp4. Bridge that here so no manual
    rename is needed. Idempotent.
    """
    src = project / "source.mp4"
    if src.exists():
        return src
    EXCL = {"final", "bg_plus_caps", "fg_caps", "audio"}
    cands = []
    for ext in ("mp4", "mov", "webm", "mkv", "m4v"):
        cands += [pathlib.Path(x) for x in glob.glob(str(project / f"*.{ext}"))]
    cands = [c for c in cands if c.stem not in EXCL and not c.name.startswith("index")]
    found = None
    if cands:
        found = max(cands, key=lambda c: c.stat().st_size)   # largest = the source clip
    else:
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
        print(f"[matte] resolved source.mp4 -> {found.name}", flush=True)
    return src


def probe_fps(src: pathlib.Path) -> int:
    """Native integer fps of the source, so the matte stays frame-aligned with it
    (and with the hyperframes render, which reads the same value via matte.fps)."""
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "0", "-select_streams", "v:0", "-show_entries",
             "stream=r_frame_rate", "-of", "default=nk=1:nw=1", str(src)]
        ).decode().strip()
        num, den = (out.split("/") + ["1"])[:2]
        f = float(num) / float(den or 1)
        return max(1, round(f)) if f > 0 else 24
    except Exception:
        return 24


def extract_frames(src_mp4: str, dst_dir: str, fps: int = 24):
    os.makedirs(dst_dir, exist_ok=True)
    existing = sorted(glob.glob(os.path.join(dst_dir, "*.png")))
    if existing:
        return existing
    subprocess.check_call([
        "ffmpeg", "-y", "-i", src_mp4,
        "-vf", f"fps={fps}",
        os.path.join(dst_dir, "f_%04d.png"),
    ])
    return sorted(glob.glob(os.path.join(dst_dir, "*.png")))


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: matte-rvm.py <project-dir>")
    project = pathlib.Path(sys.argv[1]).resolve()
    src = ensure_source(project)
    frames_bg = project / "frames_bg"
    frames_fg = project / "frames_fg"

    if not src.exists() and not frames_bg.exists():
        sys.exit(f"[matte] no source video found in {project} "
                 f"(looked for source.mp4 / *.mp4 / hyperframes.json)")

    ensure_model()

    if src.exists() and not frames_bg.exists():
        fps = probe_fps(src)
        (project / "matte.fps").write_text(str(fps))
        print(f"[matte] source fps={fps} (native) → extracting frames_bg", flush=True)
        extract_frames(str(src), str(frames_bg), fps)
    elif not (project / "matte.fps").exists():
        # frames already present from a prior run — best-effort fps record
        (project / "matte.fps").write_text(str(probe_fps(src) if src.exists() else 24))

    files = sorted(glob.glob(str(frames_bg / "*.png")))
    if not files:
        sys.exit(f"[matte] no input frames found in {frames_bg}")

    frames_fg.mkdir(parents=True, exist_ok=True)

    # Probe first frame for size → downsample ratio
    probe = Image.open(files[0])
    W, H = probe.size
    downsample_ratio = np.array([downsample_for_height(H)], dtype=np.float32)

    sess = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    rec = [np.zeros([1, 1, 1, 1], dtype=np.float32) for _ in range(4)]

    print(f"[matte] {len(files)} frames, {W}x{H}, downsample={downsample_ratio[0]}", flush=True)
    t0 = time.time()
    for i, f in enumerate(files):
        img = Image.open(f).convert("RGB")
        arr = np.asarray(img, dtype=np.float32) / 255.0
        src_np = np.ascontiguousarray(np.transpose(arr, (2, 0, 1))[None])
        fgr, pha, *rec = sess.run(
            ["fgr", "pha", "r1o", "r2o", "r3o", "r4o"],
            {
                "src": src_np,
                "r1i": rec[0], "r2i": rec[1], "r3i": rec[2], "r4i": rec[3],
                "downsample_ratio": downsample_ratio,
            },
        )
        alpha = (pha[0, 0] * 255).clip(0, 255).astype(np.uint8)
        rgb = np.asarray(img, dtype=np.uint8)
        Image.fromarray(np.dstack([rgb, alpha]), mode="RGBA").save(
            frames_fg / os.path.basename(f)
        )
        if i % 30 == 0 or i == len(files) - 1:
            fps_now = (i + 1) / (time.time() - t0)
            print(f"  {i+1}/{len(files)} — {fps_now:.1f} fps", flush=True)

    print(f"[matte] done in {time.time()-t0:.1f}s → {frames_fg}")


if __name__ == "__main__":
    main()
