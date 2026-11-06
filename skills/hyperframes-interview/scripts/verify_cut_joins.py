#!/usr/bin/env python3
"""Place each cut of a shortened interview inside a real pause and prove it with ASR.

Subtitle timings lag speech and whisper.cpp word offsets drift, so neither is used as the cut
point. Every quiet run near the expected boundary is a candidate. A cut-in is accepted only when
the kept side (audio before it) ends with `keep_tail` AND the dropped side starts with
`drop_head`; a cut-out only when the dropped side ends with `drop_tail` AND the kept side starts
with `keep_head`. Kept pauses are capped at 150 ms. The joined audio is transcribed once more and
written to the output as evidence.

Start the ASR first, for example:
  whisper-server -m ~/.cache/hyperframes/whisper/models/ggml-large-v3.bin --port 8178 -l en

Joins JSON: a list of
  {"id": "C01", "est_in": 118.3, "est_out": 132.9,
   "keep_tail": "as a school", "drop_head": "and what",
   "drop_tail": "university more", "keep_head": "the responsibility",
   optional "alt_keep_tail" / "alt_drop_head" / "alt_drop_tail" / "alt_keep_head": [...],
   optional "max_in" / "max_out" (seconds the cut must not pass: material or title starts),
   optional "video_max_in" (picture stops there; the gap becomes held frames)}
Times are seconds on the timeline of the dialogue stem (no music)."""

import argparse
import io
import json
import re
import urllib.request
import uuid

import numpy as np
import soundfile as sf

QUIET_DB = -40.0
MIN_RUN = 0.03
CLIP = 3.5
KEEP_PAUSE = 0.15
GUARD = 0.015


def norm(text):
    return re.sub(r"[^a-z' ]+", ' ', text.lower().replace('-', ' ')).split()


def ends_with(words, phrase):
    p = norm(phrase)
    return len(words) >= len(p) and words[-len(p):] == p


def starts_with(words, phrase):
    p = norm(phrase)
    return bool(p) and words[:len(p)] == p


def envelope(mono, sr):
    hop, win = int(0.005 * sr), int(0.02 * sr)
    idx = np.arange((len(mono) - win) // hop) * hop
    c = np.concatenate([[0], np.cumsum(mono.astype(np.float64) ** 2)])
    return 20 * np.log10(np.maximum(np.sqrt((c[idx + win] - c[idx]) / win), 1e-9))


def quiet_runs(db, t0, t1, step=0.005, off=0.01, quiet=QUIET_DB, min_run=MIN_RUN):
    """Quiet stretches [a, b) in seconds; db[k] describes the 20 ms window starting at k*step."""
    k0, k1 = max(int((t0 - off) / step), 0), min(int((t1 - off) / step), len(db))
    q = db[k0:k1] < quiet
    out, start = [], None
    for k in range(len(q) + 1):
        v = q[k] if k < len(q) else False
        if v and start is None:
            start = k
        elif not v and start is not None:
            a, b = (k0 + start) * step + off, (k0 + k) * step + off
            if b - a >= min_run:
                out.append((a, b))
            start = None
    return out


class Asr:
    def __init__(self, url):
        self.url = url

    def __call__(self, samples, sr):
        buf = io.BytesIO()
        sf.write(buf, samples, sr, format='WAV', subtype='PCM_16')
        boundary = uuid.uuid4().hex
        body = b''.join([
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="c.wav"\r\n'
            'Content-Type: audio/wav\r\n\r\n'.encode(), buf.getvalue(), b'\r\n',
            f'--{boundary}\r\nContent-Disposition: form-data; name="response_format"\r\n\r\njson\r\n'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="temperature"\r\n\r\n0.0\r\n--{boundary}--\r\n'.encode()])
        req = urllib.request.Request(self.url, data=body,
                                     headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        return json.loads(urllib.request.urlopen(req, timeout=120).read())['text'].strip()


def solve(j, transcribe, db, fps):
    """transcribe(ranges) -> text of the audio made by joining the given (start, end) second ranges."""
    asr1 = lambda a, b: transcribe([(max(a, 0.0), b)])
    rec = dict(id=j['id'], tries_in=[], tries_out=[])
    tails = [j['keep_tail']] + j.get('alt_keep_tail', [])
    heads_drop = [j['drop_head']] + j.get('alt_drop_head', [])
    best_in = None
    for a, b in quiet_runs(db, j['est_in'] - 1.2, j['est_in'] + 1.4):
        p = a + min(KEEP_PAUSE, b - a - GUARD)
        kept, dropped = asr1(p - CLIP, p), asr1(p, p + CLIP)
        ok = any(ends_with(norm(kept), t) for t in tails) and any(starts_with(norm(dropped), h) for h in heads_drop)
        rec['tries_in'].append(dict(run=[round(a, 3), round(b, 3)], point=round(p, 3), kept=kept, dropped=dropped, ok=ok))
        if ok:
            best_in = (a, b, p)
            break
    heads = [j['keep_head']] + j.get('alt_keep_head', [])
    tails_drop = [j['drop_tail']] + j.get('alt_drop_tail', [])
    best_out = None
    for a, b in reversed(quiet_runs(db, j['est_out'] - 1.4, j['est_out'] + 1.2)):
        p = b - min(KEEP_PAUSE, b - a - GUARD)
        kept, dropped = asr1(p, p + CLIP), asr1(p - CLIP, p)
        ok = any(starts_with(norm(kept), h) for h in heads) and any(ends_with(norm(dropped), t) for t in tails_drop)
        rec['tries_out'].append(dict(run=[round(a, 3), round(b, 3)], point=round(p, 3), kept=kept, dropped=dropped, ok=ok))
        if ok:
            best_out = (a, b, p)
            break
    rec['ok'] = bool(best_in and best_out)
    if not rec['ok']:
        return rec
    t_in, t_out = best_in[2], best_out[2]
    if 'max_in' in j:
        t_in = min(t_in, j['max_in'] - 1 / fps)
        if t_in < best_in[0]:
            rec.update(ok=False, reason='material starts before the pause; use video_max_in')
            return rec
    if 'max_out' in j:
        t_out = min(t_out, j['max_out'])
        if t_out < best_out[0]:
            rec.update(ok=False, reason='title starts before the pause')
            return rec
    f_in, f_out = round(t_in * fps), round(t_out * fps)
    v_in = min(f_in, round(j['video_max_in'] * fps)) if 'video_max_in' in j else f_in
    rec.update(frame_in=f_in, frame_out=f_out, video_frame_in=v_in, hold_last_frame=f_in - v_in,
               pause_run_in=[round(v, 3) for v in best_in[:2]], pause_run_out=[round(v, 3) for v in best_out[:2]],
               joined_pause=round((f_in / fps - best_in[0]) + (best_out[1] - f_out / fps), 3))
    rec['joined_text'] = transcribe([(f_in / fps - CLIP, f_in / fps), (f_out / fps, f_out / fps + CLIP)])
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dialogue', help='dialogue-only stem (wav), on the timeline being cut')
    ap.add_argument('joins', help='joins JSON (see above)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--server', default='http://127.0.0.1:8178/inference')
    ap.add_argument('--fps', default='30000/1001')
    args = ap.parse_args()
    num, den = (int(x) for x in args.fps.split('/')) if '/' in args.fps else (float(args.fps), 1)
    fps = num / den
    audio, sr = sf.read(args.dialogue, dtype='float32', always_2d=True)
    db = envelope(audio.mean(1), sr)
    asr = Asr(args.server)
    transcribe = lambda ranges: asr(np.concatenate([audio[max(int(a * sr), 0):int(b * sr)] for a, b in ranges]), sr)
    result = [solve(j, transcribe, db, fps) for j in json.load(open(args.joins))]
    with open(args.out, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    for r in result:
        print(r['id'], 'OK' if r['ok'] else 'NO CLEAN PAUSE — keep this unit or pick another', r.get('frame_in'),
              r.get('frame_out'), 'hold', r.get('hold_last_frame'), '|', r.get('joined_text', r.get('reason', '')))
    removed = sum(r['frame_out'] - r['frame_in'] for r in result if r['ok'])
    print(f'removed {removed / fps:.2f} s across {sum(r["ok"] for r in result)} cuts')


if __name__ == '__main__':
    main()
