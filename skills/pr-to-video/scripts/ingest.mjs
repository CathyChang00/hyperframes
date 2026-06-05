#!/usr/bin/env node
// Phase 1 — PR ingest (deterministic; no subagent; NO network).
//
// Pure transform. The orchestrator (SKILL.md Step 1) runs `gh` itself so auth /
// not-found / private-repo errors surface with gh's own stderr; THIS script never
// touches the network. It only folds the two gh artifacts into the synthetic
// capture package the shared backend (build-design / prep) expects — exactly the
// shape faceless-explainer's scaffold writes, so the whole downstream runs unchanged.
//
// Reads:
//   --pr-json <path>   gh pr view --json number,title,body,author,url,baseRefName,
//                      headRefName,commits,files,additions,deletions,changedFiles,labels
//   --diff <path>      gh pr diff (raw unified diff)  [optional — brief still builds without it]
// Writes (under --out-dir, default ./capture/extracted):
//   tokens.json        synthetic design tokens (colors:[] → claude native palette)
//   visible-text.txt   the narrative SOURCE: a readable plain-text brief assembled
//                      from title + meta + body + commits + changed files + a
//                      budget-bounded selection of representative diff hunks.
//
// The story-design subagent reads visible-text.txt for the narrative AND gets the
// full diff.patch separately for deep hunk selection — so this brief is curated,
// not exhaustive: noisy files (lockfiles / dist / maps) are deprioritised so real
// source hunks win the char budget.
//
// Usage:
//   node ingest.mjs --pr-json ./capture/pr.json --diff ./capture/diff.patch \
//                   --out-dir ./capture/extracted
//
// Exit 0 = tokens.json + visible-text.txt written + summary on stdout.
// Exit 1 = pr.json missing / unparseable (orchestrator should stop).

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve, join } from "node:path";

// ---------- argv ----------
const argv = process.argv.slice(2);
const flag = (name, def) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && i + 1 < argv.length ? argv[i + 1] : def;
};
function die(msg) {
  console.error(`✗ ingest.mjs: ${msg}`);
  process.exit(1);
}

const prJsonPath = resolve(flag("pr-json", "./capture/pr.json"));
const diffPath = flag("diff") ? resolve(flag("diff")) : resolve("./capture/diff.patch");
const outDir = resolve(flag("out-dir", "./capture/extracted"));

// Budgets — keep visible-text.txt readable and bounded for the story-design agent.
const MAX_BODY_CHARS = parseInt(flag("max-body-chars", "2600"), 10);
const MAX_DIFF_CHARS = parseInt(flag("max-diff-chars", "4800"), 10);
const MAX_HUNK_LINES = parseInt(flag("max-hunk-lines", "22"), 10); // per hunk, post-context-trim
const MAX_COMMITS = parseInt(flag("max-commits", "12"), 10);
const MAX_FILES_LISTED = parseInt(flag("max-files-listed", "40"), 10);

// Noisy paths whose diff bodies rarely teach anything — deprioritised in hunk
// selection (still listed in "Files changed" with their stats).
const NOISE_RX =
  /(^|\/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|npm-shrinkwrap\.json|go\.sum|Cargo\.lock|composer\.lock|Gemfile\.lock|poetry\.lock)$|\.(min\.js|min\.css|map|snap)$|(^|\/)(dist|build|out|vendor|node_modules|\.next|coverage)\//;

// ---------- read pr.json ----------
if (!existsSync(prJsonPath)) die(`pr.json not found at ${prJsonPath} (run gh pr view first)`);
let pr;
try {
  pr = JSON.parse(readFileSync(prJsonPath, "utf8"));
} catch (e) {
  die(`pr.json is not valid JSON (${e.message}) — check the gh pr view output`);
}

// ---------- read diff (optional) ----------
let diffRaw = "";
if (existsSync(diffPath)) {
  try {
    diffRaw = readFileSync(diffPath, "utf8");
  } catch {
    diffRaw = "";
  }
}

// ---------- derive scalars ----------
const number = pr.number ?? "?";
const title = (pr.title || `Pull request #${number}`).trim();
const url = pr.url || "";
const repo = (() => {
  const m = /github\.com\/([^/]+\/[^/]+)\/pull\//.exec(url);
  if (m) return m[1];
  if (pr.headRepository?.nameWithOwner) return pr.headRepository.nameWithOwner;
  return "";
})();
const author = pr.author?.login || pr.author?.name || "unknown";
const baseRef = pr.baseRefName || "base";
const headRef = pr.headRefName || "head";
const additions = pr.additions ?? 0;
const deletions = pr.deletions ?? 0;
const changedFiles = pr.changedFiles ?? (Array.isArray(pr.files) ? pr.files.length : 0);
const labels = Array.isArray(pr.labels)
  ? pr.labels.map((l) => (typeof l === "string" ? l : l?.name)).filter(Boolean)
  : [];

// ---------- clean body ----------
function cleanBody(raw) {
  if (!raw || typeof raw !== "string") return "";
  let t = raw
    .replace(/<!--[\s\S]*?-->/g, "") // strip HTML comments (PR templates)
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (t.length > MAX_BODY_CHARS) {
    t = t.slice(0, MAX_BODY_CHARS).replace(/\s+\S*$/, "") + "\n…(description truncated)";
  }
  return t;
}
const body = cleanBody(pr.body);

// ---------- commits ----------
const commits = Array.isArray(pr.commits) ? pr.commits : [];
const commitLines = commits
  .map(
    (c) =>
      c?.messageHeadline || (c?.messageBody || "").split("\n")[0] || (c?.oid || "").slice(0, 7),
  )
  .filter(Boolean);

// ---------- files (from pr.json) ----------
const files = (Array.isArray(pr.files) ? pr.files : []).map((f) => ({
  path: f.path || f.filename || "",
  additions: f.additions ?? 0,
  deletions: f.deletions ?? 0,
}));

// ---------- parse the unified diff into per-file hunks ----------
function parseDiff(raw) {
  if (!raw) return new Map();
  const lines = raw.split("\n");
  const byPath = new Map(); // path -> { hunks: string[][] }
  let curPath = null;
  let curHunk = null;
  const ensure = (p) => {
    if (!byPath.has(p)) byPath.set(p, { hunks: [] });
    return byPath.get(p);
  };
  for (const line of lines) {
    if (line.startsWith("diff --git ")) {
      // new file block; provisional path from "b/<path>" (refined by +++ below)
      const m = /^diff --git a\/(.+?) b\/(.+)$/.exec(line);
      curPath = m ? m[2] : null;
      curHunk = null;
      if (curPath) ensure(curPath);
      continue;
    }
    if (line.startsWith("+++ ")) {
      // authoritative new path ("+++ b/path" or "+++ /dev/null" for deletions)
      const p = line.slice(4).replace(/^b\//, "").trim();
      if (p && p !== "/dev/null") {
        curPath = p;
        ensure(curPath);
      }
      continue;
    }
    if (line.startsWith("--- ")) continue;
    if (line.startsWith("@@")) {
      if (!curPath) continue;
      curHunk = [line];
      ensure(curPath).hunks.push(curHunk);
      continue;
    }
    if (curHunk && curPath) {
      // body line of the current hunk (context / + / -); ignore the trailing
      // "\ No newline at end of file" sentinel
      if (line.startsWith("\\")) continue;
      curHunk.push(line);
    }
  }
  return byPath;
}
const diffByPath = parseDiff(diffRaw);

// Render a single hunk, trimmed: keep the @@ header + all +/- lines, but cap
// surrounding context to keep signal high and stay inside the line budget.
function renderHunk(hunk) {
  const header = hunk[0];
  const bodyLines = hunk.slice(1);
  const kept = [];
  for (const l of bodyLines) {
    if (l.startsWith("+") || l.startsWith("-")) kept.push(l);
    else if (kept.length && kept[kept.length - 1] !== "  ⋯") {
      // collapse runs of context into a single marker (only between changes)
      if (kept.some((k) => k.startsWith("+") || k.startsWith("-"))) kept.push("  ⋯");
    }
  }
  // drop a trailing context marker
  while (kept.length && kept[kept.length - 1] === "  ⋯") kept.pop();
  let out = [header.replace(/\s*$/, "")];
  out = out.concat(kept.slice(0, MAX_HUNK_LINES));
  if (kept.length > MAX_HUNK_LINES)
    out.push(`  …(+${kept.length - MAX_HUNK_LINES} more changed lines)`);
  return out.join("\n");
}

// ---------- rank files for the representative-diff section ----------
// real source first (non-noise, by total churn desc), noisy files last.
const ranked = [...files]
  .filter((f) => f.path && diffByPath.has(f.path))
  .sort((a, b) => {
    const an = NOISE_RX.test(a.path) ? 1 : 0;
    const bn = NOISE_RX.test(b.path) ? 1 : 0;
    if (an !== bn) return an - bn;
    return b.additions + b.deletions - (a.additions + a.deletions);
  });
// include any diffed paths missing from files[] (rare; e.g. renames) at the tail
for (const p of diffByPath.keys()) {
  if (!ranked.find((f) => f.path === p)) ranked.push({ path: p, additions: 0, deletions: 0 });
}

// ---------- build the representative-diff section under the char budget ----------
const diffSections = [];
let diffChars = 0;
let filesShown = 0;
let filesOmitted = 0;
for (const f of ranked) {
  const entry = diffByPath.get(f.path);
  if (!entry || !entry.hunks.length) continue;
  const head = `### ${f.path}  (+${f.additions} / -${f.deletions})`;
  const rendered = entry.hunks.map(renderHunk).join("\n");
  const block = `${head}\n${rendered}`;
  if (diffChars + block.length > MAX_DIFF_CHARS && filesShown > 0) {
    filesOmitted++;
    continue;
  }
  diffSections.push(block);
  diffChars += block.length;
  filesShown++;
}

// ---------- assemble visible-text.txt ----------
const lines = [];
lines.push(`# ${title}`);
lines.push("");
const metaBits = [repo, `PR #${number}`, `by ${author}`].filter(Boolean);
lines.push(metaBits.join(" · "));
lines.push(
  `${baseRef} ← ${headRef} · +${additions} / -${deletions} across ${changedFiles} file(s)`,
);
if (labels.length) lines.push(`Labels: ${labels.join(", ")}`);
if (url) lines.push(`URL: ${url}`);
lines.push("");

lines.push("## What the PR says");
lines.push(body || "(no description provided)");
lines.push("");

if (commitLines.length) {
  lines.push(`## Commits (${commitLines.length})`);
  for (const c of commitLines.slice(0, MAX_COMMITS)) lines.push(`- ${c}`);
  if (commitLines.length > MAX_COMMITS)
    lines.push(`- …(+${commitLines.length - MAX_COMMITS} more)`);
  lines.push("");
}

if (files.length) {
  lines.push(`## Files changed (${files.length})`);
  const sortedFiles = [...files].sort(
    (a, b) => b.additions + b.deletions - (a.additions + a.deletions),
  );
  for (const f of sortedFiles.slice(0, MAX_FILES_LISTED)) {
    lines.push(`- ${f.path}  (+${f.additions} / -${f.deletions})`);
  }
  if (files.length > MAX_FILES_LISTED)
    lines.push(`- …(+${files.length - MAX_FILES_LISTED} more files)`);
  lines.push("");
}

if (diffSections.length) {
  lines.push("## Representative diff");
  lines.push("");
  lines.push(diffSections.join("\n\n"));
  if (filesOmitted > 0) {
    lines.push("");
    lines.push(
      `…(diff truncated to fit; ${filesOmitted} more changed file(s) omitted — see capture/diff.patch for the full change)`,
    );
  }
  lines.push("");
} else if (diffRaw) {
  lines.push("## Representative diff");
  lines.push("(diff present but no parseable hunks — see capture/diff.patch)");
  lines.push("");
}

const visibleText =
  lines
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim() + "\n";

// ---------- assemble tokens.json (FE scaffold shape; colors:[] → preset native palette) ----------
const oneLiner = (() => {
  const firstPara = body.split("\n").find((l) => l.trim().length > 0) || title;
  const s = `PR #${number}${repo ? ` in ${repo}` : ""}: ${firstPara}`.replace(/\s+/g, " ").trim();
  return s.length > 150 ? s.slice(0, 147).replace(/\s+\S*$/, "") + "…" : s;
})();
const tokens = {
  title,
  description: oneLiner,
  colors: [],
  fonts: [],
  headings: [],
  sections: [],
  ctas: [],
  svgs: [],
  cssVariables: {},
};

// ---------- write ----------
mkdirSync(outDir, { recursive: true });
const tokensOut = join(outDir, "tokens.json");
const textOut = join(outDir, "visible-text.txt");
writeFileSync(tokensOut, JSON.stringify(tokens, null, 2) + "\n");
writeFileSync(textOut, visibleText);

// ---------- summary ----------
console.log(
  [
    `✓ ingest: ${repo || "(repo?)"} PR #${number} — "${title}"`,
    `  +${additions} / -${deletions} across ${changedFiles} file(s); ${commitLines.length} commit(s)`,
    `  diff: ${filesShown} file(s) shown, ${filesOmitted} omitted (budget ${MAX_DIFF_CHARS} chars)`,
    `  wrote ${textOut} (${visibleText.length} chars) + ${tokensOut}`,
  ].join("\n"),
);
