#!/usr/bin/env node
/*
 * transcribe.cjs — word-level transcription via hyperframes' native Whisper
 * (replaces the Python ElevenLabs Scribe path; no Python, no API key).
 *
 *   node transcribe.cjs <project-dir> [model] [language]
 * Reads:  <project>/source.mp4 (audio track)
 * Writes: <project>/transcript.json  — { text, language_code, words:[{text,start,end,type}] }
 */
const path = require("path");
const fs = require("fs");
const os = require("os");
const cp = require("child_process");

function hfRoot() {
  const roots = [
    process.env.HYPERFRAMES_ROOT,
    path.resolve(__dirname, "..", "..", ".."),
    path.join(os.homedir(), "Downloads", "hyperframes"),
  ].filter(Boolean);
  for (const r of roots) if (fs.existsSync(path.join(r, "packages", "cli", "dist", "cli.js"))) return r;
  console.error("[transcribe] hyperframes CLI not found — set HYPERFRAMES_ROOT"); process.exit(3);
}
function ensureSource(project) {
  const src = path.join(project, "source.mp4");
  if (fs.existsSync(src)) return src;
  const EXCL = new Set(["final", "bg_plus_caps", "fg_caps", "audio"]);
  let cands = fs.readdirSync(project)
    .filter((f) => ["mp4", "mov", "webm", "mkv", "m4v"].includes(path.extname(f).slice(1).toLowerCase())
      && !EXCL.has(path.basename(f, path.extname(f))) && !f.startsWith("index"))
    .map((f) => path.join(project, f));
  let found = cands.sort((a, b) => fs.statSync(b).size - fs.statSync(a).size)[0];
  if (found) { try { fs.symlinkSync(path.basename(found), src); } catch { fs.copyFileSync(found, src); } }
  return src;
}

function main() {
  const project = path.resolve(process.argv[2] || "");
  if (!process.argv[2]) { console.error("usage: transcribe.cjs <project-dir> [model] [language]"); process.exit(1); }
  const model = process.argv[3] || process.env.WHISPER_MODEL || "small.en";
  const language = process.argv[4] || process.env.WHISPER_LANG || "";
  const out = path.join(project, "transcript.json");

  // already in our schema? skip.
  if (fs.existsSync(out)) {
    try {
      const d = JSON.parse(fs.readFileSync(out, "utf8"));
      if (d && d.words && d.language_code) { console.log("[transcribe] already normalized, skipping"); return; }
    } catch {}
  }

  const src = ensureSource(project);
  if (!fs.existsSync(src)) { console.error(`[transcribe] no source in ${project}`); process.exit(2); }
  const audio = path.join(project, "audio.mp3");
  if (!fs.existsSync(audio))
    cp.execFileSync("ffmpeg", ["-y", "-i", src, "-vn", "-acodec", "libmp3lame", "-q:a", "2", audio], { stdio: "ignore" });

  // run hyperframes Whisper → writes a flat word array to <dir>/transcript.json
  const cli = path.join(hfRoot(), "packages", "cli", "dist", "cli.js");
  const args = ["transcribe", audio, "-d", project, "--json", "--model", model];
  if (language) args.push("--language", language);
  let info = {};
  try {
    const so = cp.execFileSync("node", [cli, ...args], { encoding: "utf8" });
    const line = so.trim().split("\n").filter(Boolean).pop();
    info = JSON.parse(line);
  } catch (e) {
    console.error("[transcribe] hyperframes whisper failed:", e.message); process.exit(1);
  }
  const flatPath = info.transcriptPath || out;
  const flat = JSON.parse(fs.readFileSync(flatPath, "utf8"));
  const arr = Array.isArray(flat) ? flat : flat.words || [];

  // normalize to our schema
  const words = arr
    .filter((w) => (w.text ?? w.word) != null)
    .map((w) => ({ text: w.text ?? w.word, start: w.start ?? w.t0, end: w.end ?? w.t1, type: "word" }));
  const text = words.map((w) => w.text).join(" ").replace(/\s+([,.!?;:])/g, "$1").trim();
  fs.writeFileSync(out, JSON.stringify({ text, language_code: language || "en", words }, null, 2));
  console.log(`[transcribe] whisper(${model}) ${words.length} words → ${out}`);
  console.log(`[transcribe] text: ${text.slice(0, 160)}${text.length > 160 ? "…" : ""}`);
}
main();
