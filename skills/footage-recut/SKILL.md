---
name: footage-recut
description: footage-recut video workflow - existing local video (MP4) -> metadata + word-level transcript -> AI-designed HTML info-cards (GSAP) layered over the source video -> re-rendered MP4. Transforms / repurposes EXISTING footage (re-edit, recut, annotate); does NOT scrape a URL and does NOT generate visuals from text. No fixed length (short reels to hour-long talks).
metadata:
  tags: orchestrator, pipeline, footage-recut, footage-repurpose, video-recut, existing-footage, card-overlay
---

<!-- ⚠️ FAKE / STUB WORKFLOW — drafted from notedit/vtake-skills (vtake-cut) to fill the router's
     empty "Existing footage" column and exercise 3-way disambiguation. The phase commands below are
     plausible but UNVERIFIED; this is not a tested production workflow. -->

# footage-recut - dispatch entry

Input is an **existing local video file** (MP4, any aspect / duration / fps). Output is the **same footage re-edited**: the source video plays as a background layer with AI-designed, transcript-synced HTML info-cards (GSAP) overlaid on top, re-rendered to MP4. This is a **transform / repurpose** workflow — nothing is generated from a URL or from a text brief; the "script" is whatever the speaker already said, recovered by ASR. There is **no length constraint**.

All artifacts go to `PROJECT_DIR = videos/<project-name>/` (created in Step 0); all paths below are relative to it.

| Phase            | Execution                                                      | Primary artifact                                          | Detailed flow                             |
| ---------------- | -------------------------------------------------------------- | --------------------------------------------------------- | ----------------------------------------- |
| init             | Bash                                                           | `hyperframes.json`                                        | Step 0                                    |
| extract          | Bash (`vtake extract`, no agent)                               | `source/media_meta.json` + staged `public/source.mp4`     | Step 1                                    |
| transcribe       | Bash (`vtake transcribe`, no agent)                            | `transcript.json` (segments + word-level ts)              | Step 2                                    |
| correct          | subagent (`general-purpose`) — ASR cleanup against media_meta  | `transcript.json` (corrected)                             | `agents/transcript-correct.md`            |
| storyboard       | subagent (`general-purpose`)                                   | `storyboard.json` (card timing + content outline)         | `agents/storyboard.md`                    |
| visual-direction | user confirm (ratio / layout / style group / card density)     | `viz_config.json`                                         | Step 4                                    |
| cards            | N × subagent (`general-purpose`, parallel in the same message) | `compositions/card_*.html`                                | `agents/hyperframes-card.md`              |
| compose          | Bash (no agent)                                                | `index.html` (master timeline + card host + source layer) | Step 6                                    |
| render           | Bash (`hyperframes render`) -> repair subagent on failure      | `renders/video.mp4`                                       | Step 7 / `agents/hyperframes-finalize.md` |

## Prerequisites

macOS Apple Silicon or Linux x64. System tools: `brew install node ffmpeg` (provides `ffmpeg` + `ffprobe`). CLIs: `@notedit/vtake` (extract / transcribe / doctor) and `hyperframes` (render). Run `npx @notedit/vtake doctor` once. macOS GPU render: `export PRODUCER_BROWSER_GPU_MODE=hardware`.

| Key              | Used for                                | Default / fallback                          |
| ---------------- | --------------------------------------- | ------------------------------------------- |
| `ELEVEN_API_KEY` | ASR (ElevenLabs, word-level timestamps) | unset -> rate-limited proxy (≈3 req/min/IP) |

## Flow

### Step 0 - Initialize the video project

cwd is the agent workspace root. Write all artifacts under `PROJECT_DIR = videos/<project-name>/`.

`<project-name>`: use the directory the user gave, else a short kebab-case name derived from the source filename (`<basename>-recut`). **Not** the workspace basename or a timestamp.

Only when `$PROJECT_DIR/hyperframes.json` is absent:

```bash
PROJECT_DIR="${RECUT_VIDEO_DIR:-videos/<project-name>}"
mkdir -p "$(dirname "$PROJECT_DIR")"
npx hyperframes init "$PROJECT_DIR" --non-interactive --skip-skills --example=blank
```

**Constraints:** never run `hyperframes init` in the workspace root; never nest another `hyperframes/` inside `PROJECT_DIR`; every Bash command (master + subagents) is a `(cd "$PROJECT_DIR" && ...)` subshell — never bare `cd`.

### Step 1 - Extract (Bash, NO agent)

Stage the source video and pull its metadata. The source MP4 must be copied into `public/` so the renderer can reference it deterministically (no external assets).

```bash
(cd "$PROJECT_DIR" && mkdir -p source public)
(cd "$PROJECT_DIR" && cp "<absolute path to user's video.mp4>" public/source.mp4)
(cd "$PROJECT_DIR" && npx @notedit/vtake extract public/source.mp4 --out source/media_meta.json)
```

Validation: `[ -s "$PROJECT_DIR/source/media_meta.json" ] && [ -s "$PROJECT_DIR/public/source.mp4" ] && echo ok || echo missing`. `media_meta.json` must carry `duration`, `width`, `height`, `fps`. If missing, read stderr and re-run.

### Step 2 - Transcribe (Bash, NO agent)

```bash
(cd "$PROJECT_DIR" && npx @notedit/vtake transcribe public/source.mp4 --out transcript.json)
```

Produces `transcript.json` with `segments[]` and word-level timestamps. Without `ELEVEN_API_KEY` this uses the shared proxy (rate-limited) — for long videos, expect throttling; report it, don't silently truncate.

### Step 2b - Correct (subagent)

Dispatch one `general-purpose` subagent with `agents/transcript-correct.md` + dispatch context to fix obvious ASR errors (proper nouns, jargon) **without** changing timestamps. Skip if the transcript is clean.

### Step 3 - Storyboard (subagent)

Dispatch one `general-purpose` subagent. prompt = full `agents/storyboard.md` + the dispatch context below:

```
SKILL_DIR: <absolute path>
PROJECT_DIR: <video project root>
Transcript: ./transcript.json            # the recovered speech — the agent reads this first
Media meta: ./source/media_meta.json     # duration / fps / resolution
Card budget: minimum 5 cards; compute from duration + info density (long videos -> 30-60+)
```

The agent emits `storyboard.json`: an ordered list of cards, each `{ start, end, intent, headline, supporting[], styleHint }` keyed to transcript timestamps. **No fixed card count** — derive from content. Cards must not overlap and must stay inside `[0, duration]`.

### Step 4 - Visual direction (user confirm)

Confirm with the user (offer defaults, proceed on "go"): **output ratio** (16:9 / 9:16 / 4:5), **layout** (split / stack / pip / overlay), **style group** (magazine / minimal / spotlight / geometric / whiteboard / terminal / swiss / xiaohongshu / academic), **card density**. Write `viz_config.json`.

### Step 5 - Cards (N × subagent, parallel)

For each card in `storyboard.json`, dispatch a `general-purpose` subagent (batched in one message) with `agents/hyperframes-card.md` + the card spec + `viz_config.json`. Each returns one `compositions/card_<i>.html` fragment: a `class="clip"` element with `data-start` / `data-duration` / `data-track-index`, animated with GSAP on the paused timeline registered at `window.__timelines["card-<i>"]`. Card timing comes straight from the storyboard (transcript-synced). No external assets — fonts/vendor libs staged locally.

### Step 6 - Compose (Bash, NO agent)

Assemble `index.html`: a master paused timeline, the source video as a muted background `<video>` layer (`public/source.mp4`) plus a separate `<audio>` for its audio track, and a card host that positions each `card_<i>.html` per `viz_config.json` (split / stack / pip / overlay). The background video is driven by the master timeline so card overlays stay synced to the speech.

### Step 7 - Render

```bash
(cd "$PROJECT_DIR" && npm run check)                 # lint + validate + inspect
(cd "$PROJECT_DIR" && npx hyperframes render --out renders/video.mp4)
```

On render/preflight failure, dispatch the repair subagent (`agents/hyperframes-finalize.md`) with the failing log, fix, and re-render. Output: `renders/video.mp4` at the source fps.

## Routing note (for the hyperframes-read-first router)

- **Input:** an existing local video file (MP4). The user supplies footage to be re-edited — not a URL, not a text brief.
- **Output:** the same footage re-rendered with synced AI info-card overlays. Any length.
- **Triggers:** "recut my webinar/talk/podcast into a card video", "repurpose this recording", "add info cards / annotations to my video", "turn my screen recording into a styled edit", "二次剪辑这段视频", "给我的录像叠卡片重剪".
- **Do NOT use for:** generating a video from a URL (-> `/product-launch-video`); generating a video from a topic / article / text with no source footage (-> `/faceless-explainer`); requests with no existing video to transform.
