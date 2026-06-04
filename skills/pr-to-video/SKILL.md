---
name: pr-to-video
description: pr-to-video workflow - a GitHub pull request (URL like github.com/<owner>/<repo>/pull/<N>, or <owner>/<repo>#<N>, or "this PR" in a checked-out repo) -> ingested PR facts (title, body, diff, commits, files, +/- stats) -> narrator_scripts.json + audio (voice + BGM) + section_plan.md -> code-diff / before-after / impact explainer video. Input is a CODE CHANGE. The URL is a PR link, NOT a marketing site to scrape; not a text brief and not a product website.
metadata:
  tags: orchestrator, pipeline, pr-to-video, changelog, dev-rel, code-explainer, release-notes
---

<!-- ⚠️ FAKE / STUB WORKFLOW — drafted to (a) exercise the router's URL-disambiguation (PR URL vs
     product-site URL) and (b) prototype the `video-core` plan: this workflow owns only INGEST +
     STORY-DESIGN + CONFIG; downstream phases (audio / visual-design / scenes / finalize) reuse the
     shared engine (FE-derived today, hyperframes-video-core once extracted). Commands are plausible
     but UNVERIFIED; not a tested production workflow. -->

# pr-to-video - dispatch entry

Input is a **GitHub pull request** (a code change), supplied as a PR URL, an `<owner>/<repo>#<N>` ref, or "this PR" while a repo with an open PR is checked out. Output is a **code-change explainer**: what shipped, why, and how it works — rendered from the diff/commits as before-after, diff-highlight, file-tree, and impact scenes. Default length **30-90s** (changelog / feature-reveal register). There is **no website scrape and no headless Chrome** — ingest is the `gh` CLI.

Per the `video-core` plan this workflow authors only the PR-specific front (**ingest + story-design + config**); the marked phases below **reuse the shared engine** unchanged.

All artifacts go to `PROJECT_DIR = videos/<project-name>/` (created in Step 0); all paths below are relative to it.

| Phase                  | Execution                                                      | Primary artifact                                                                              | Detailed flow                           |
| ---------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | --------------------------------------- |
| init                   | Bash                                                           | `hyperframes.json`                                                                            | Step 0                                  |
| **ingest** (own)       | Bash (`gh` CLI, no agent, NO scrape)                           | `capture/pr.json` + `capture/diff.patch` + `capture/extracted/{tokens.json,visible-text.txt}` | Step 1                                  |
| design-system (config) | Bash (deterministic, code-centric preset)                      | `design-system/design.html` + `chunks/`                                                       | Step 1b                                 |
| **story-design** (own) | subagent (`general-purpose`)                                   | `narrator_scripts.json`                                                                       | `agents/story-design.md`                |
| audio (shared)         | `audio.mjs` in Bash                                            | `audio_meta.json`                                                                             | shared engine                           |
| visual-design (shared) | subagent (`general-purpose`)                                   | `section_plan.md`                                                                             | `agents/visual-design.md`               |
| scenes (shared)        | N × subagent (`general-purpose`, parallel in the same message) | `compositions/scene_*.html`                                                                   | shared `agents/hyperframes-scene.md`    |
| finalize (shared)      | Bash prelude (assemble + verify) -> repair subagent            | `renders/video.mp4`                                                                           | shared `agents/hyperframes-finalize.md` |

## Prerequisites

macOS Apple Silicon or Linux x64. System tools: `brew install node ffmpeg`. CLIs: **`gh`** (GitHub CLI, authenticated via `gh auth status`) and `hyperframes`. Optional cloud keys for TTS/BGM follow the shared engine's defaults (HeyGen / ElevenLabs / local Kokoro; Lyria / local MusicGen).

| Requirement         | Used for                                 | Default / fallback                      |
| ------------------- | ---------------------------------------- | --------------------------------------- |
| `gh auth status` OK | Reading the PR (public or private repos) | required — fail fast with the auth hint |
| TTS / BGM keys      | shared audio phase                       | local fallbacks (see shared engine)     |

## Flow

### Step 0 - Initialize the video project

cwd is the agent workspace root. `<project-name>`: directory the user gave, else `<repo>-pr-<N>` derived from the PR. Only when `$PROJECT_DIR/hyperframes.json` is absent:

```bash
PROJECT_DIR="${PR_VIDEO_DIR:-videos/<project-name>}"
mkdir -p "$(dirname "$PROJECT_DIR")"
npx hyperframes init "$PROJECT_DIR" --non-interactive --skip-skills --example=blank
```

**Constraints:** never `hyperframes init` in the workspace root; never nest another `hyperframes/`; every Bash command is a `(cd "$PROJECT_DIR" && ...)` subshell — never bare `cd`.

### Step 1 - Ingest (Bash, NO agent, NO scrape)

Resolve the PR ref (`PR="<url | owner/repo#N | N>"`) and pull structured facts with `gh`. No headless Chrome, no asset scraping.

```bash
(cd "$PROJECT_DIR" && mkdir -p capture/extracted capture/assets)
(cd "$PROJECT_DIR" && gh pr view "$PR" \
  --json number,title,body,author,url,baseRefName,headRefName,commits,files,additions,deletions,changedFiles,labels \
  > capture/pr.json)
(cd "$PROJECT_DIR" && gh pr diff "$PR" > capture/diff.patch)
```

Then synthesize the package the shared backend expects (mirrors FE's no-scrape scaffold): `tokens.json` with `colors:[]` (so the code-centric preset's native palette is used), and `visible-text.txt` = a plain-text brief assembled from the PR (title + body + changed-file list + the most significant diff hunks, truncated). `capture/assets/` stays empty.

```bash
[ -s "$PROJECT_DIR/capture/pr.json" ] && \
[ -s "$PROJECT_DIR/capture/diff.patch" ] && \
[ -s "$PROJECT_DIR/capture/extracted/visible-text.txt" ] && echo ok || echo missing
```

If `gh` errors (auth / not found / private), report the exact stderr and stop — do not fabricate PR contents.

### Step 1b - Design system (Bash, deterministic, code-centric preset)

Run the shared `build-design` + `emit-chunks` against the synthetic input with a code/terminal-leaning style preset (e.g. `--style terminal` or `--style swiss`), producing `design-system/design.html` + `chunks/`. Validation identical to the shared engine.

### Step 2 - Story-design (subagent) — OWN

Dispatch one `general-purpose` subagent. prompt = full `agents/story-design.md` + dispatch context:

```
SKILL_DIR: <absolute path>
PROJECT_DIR: <video project root>
PR facts: ./capture/pr.json            # title, body, commits, files, +/- stats — read first
Diff: ./capture/diff.patch             # the actual change; pull 2-4 representative hunks
Brief: ./capture/extracted/visible-text.txt
Schema validator: <SKILL_DIR>/scripts/validate.mjs narrator
Script style: concise, dev-facing — 1-2 sentences/scene, ≤20 words; name the change, the why, the impact
```

The agent picks `narrativeArchetype` from `changelog` / `feature-reveal` / `fix-explainer` / `refactor-walkthrough` (or `"<outer> with <inner>"`), then emits `narrator_scripts.json` (runs the validator before returning). `continuity` drives worker grouping (`continue` = same worker, run of up to 3; `break` = new worker; scene 1 always `break`). Scenes should map to: hook (what shipped) → the change (diff / before-after) → why / impact → close. `assetCandidates` is `[]` (no scraped assets; visuals are code/typography/diagram).

### Step 3 - Audio — SHARED

After `narrator_scripts.json` exists, run the shared `audio.mjs` exactly as FE/PLV do. → `audio_meta.json`.

### Step 4 - Visual-design (subagent) — SHARED

Shared `agents/visual-design.md`. Visual vocabulary leans on the diff: syntax-highlighted code blocks, before/after splits, file-tree reveals, `+`/`-` stat counters, arch diagrams. → `section_plan.md`.

### Step 5 - Scenes (N × subagent, parallel) — SHARED

Shared `agents/hyperframes-scene.md`. Each scene is a `class="clip"` element on the paused timeline registered at `window.__timelines[...]`, animated with GSAP. → `compositions/scene_*.html`.

### Step 6 - Finalize — SHARED

Shared assemble + preflight + repair, then render. → `renders/video.mp4`.

## Routing note (for the hyperframes-read-first router)

- **Input:** a **GitHub PR** — a code change (PR URL, `owner/repo#N`, or "this PR"). A URL, but **a `github.com/.../pull/N` link, not a product/marketing website**.
- **Output:** 30-90s code-change explainer (changelog / feature-reveal / fix / refactor walkthrough).
- **Triggers:** "make a video about this PR", "turn PR #1187 into a changelog video", "explain what this pull request does as a video", "release-notes video from github.com/org/repo/pull/123", "把这个 PR 做成视频".
- **Do NOT use for:** a product/marketing website URL (-> `/product-launch-video`); a topic/article/text with no PR (-> `/faceless-explainer`); existing video footage (-> `/footage-recut`); a whole-repo tour or multi-PR release (no workflow yet -> 通用).
