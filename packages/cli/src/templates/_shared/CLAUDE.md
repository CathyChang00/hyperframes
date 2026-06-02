# HyperFrames Composition Project

## Skills — USE THESE FIRST

**Always invoke the relevant skill before writing or modifying compositions.** Skills encode framework-specific patterns (e.g., `window.__timelines` registration, `data-*` attribute semantics, shader-compatible CSS rules) that are NOT in generic web docs. Skipping them produces broken compositions.

**Making a video?** Start at the router (`/video-workflows`) — it maps your request to the right workflow before you invoke a specific one.

| Skill                        | Command                  | When to use                                                                                                                                   |
| ---------------------------- | ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **video-workflows** (router) | `/video-workflows`       | **FIRST** stop for any "make me a video" intent — routes to the right workflow                                                                |
| **product-launch-video**     | `/product-launch-video`  | URL or product brief / script → 60-90s product launch / SaaS / promo video                                                                    |
| **faceless-explainer**       | `/faceless-explainer`    | Arbitrary text (topic / article / notes), **no URL, no website capture** → 60-90s faceless explainer                                          |
| **hyperframes-core**         | `/hyperframes-core`      | HTML composition contract: data attributes, clips, tracks, sub-compositions, variables, media, deterministic rules                            |
| **hyperframes-creative**     | `/hyperframes-creative`  | Creative direction: `design.md`, palettes, typography, narration, beat planning, audio-reactive, composition patterns                         |
| **hyperframes-animation**    | `/hyperframes-animation` | All motion: atomic rules, scene blueprints, transitions, and runtime adapters (GSAP default; Lottie, Three.js, Anime.js, CSS, WAAPI, TypeGPU) |
| **hyperframes-cli**          | `/hyperframes-cli`       | Dev-loop CLI: init, lint, validate, inspect, preview, render, doctor                                                                          |
| **hyperframes-media**        | `/hyperframes-media`     | Asset preprocessing: TTS, BGM, transcribe, remove-background, and caption authoring                                                           |
| **hyperframes-registry**     | `/hyperframes-registry`  | Installing registry blocks and components via `hyperframes add`                                                                               |

> **Tailwind v4 projects** (`hyperframes init --tailwind`): see `/hyperframes-core` → `references/tailwind.md`.

> **Skills not available?** Ask the user to run `npx hyperframes skills` and restart their
> agent session, or install manually: `npx skills add heygen-com/hyperframes`.

## Commands

```bash
npm run dev          # start the preview server (long-running — keep it alive in background)
npm run check        # lint + validate + inspect
npm run render       # render to MP4
npm run publish      # publish and get a shareable link
npx hyperframes lint --verbose  # include info-level findings
npx hyperframes lint --json     # machine-readable output for CI
npx hyperframes docs <topic> # reference docs in terminal
```

> **`npm run dev` is a long-running server, not a one-shot command.** It blocks until stopped.
> In Claude Code, always run it with `run_in_background: true`. Never run it as a foreground
> command — it will time out and the server will die, breaking the browser preview.

## Documentation

**For quick reference**, use the local CLI docs command (no network required):

```bash
npx hyperframes docs <topic>
```

Topics: `data-attributes`, `gsap`, `compositions`, `rendering`, `examples`, `troubleshooting`

**For full documentation**, discover pages via the machine-readable index — do NOT guess URLs:

```
https://hyperframes.heygen.com/llms.txt
```

## Project Structure

- `index.html` — main composition (root timeline)
- `compositions/` — sub-compositions referenced via `data-composition-src`
- `meta.json` — project metadata (id, name)
- `transcript.json` — whisper word-level transcript (if generated)

## Linting — ALWAYS RUN AFTER CHANGES

After creating or editing any `.html` composition, **always** run the full check before considering the task complete:

```bash
npm run check
```

Fix all errors before presenting the result. Inspect warnings should be reviewed before rendering.

## Key Rules

1. Every timed element needs `data-start`, `data-duration`, and `data-track-index`
2. Elements with timing **MUST** have `class="clip"` — the framework uses this for visibility control
3. Timelines must be paused and registered on `window.__timelines`:
   ```js
   window.__timelines = window.__timelines || {};
   window.__timelines["composition-id"] = gsap.timeline({ paused: true });
   ```
4. Videos use `muted` with a separate `<audio>` element for the audio track
5. Sub-compositions use `data-composition-src="compositions/file.html"` to reference other HTML files
6. Only deterministic logic — no `Date.now()`, no `Math.random()`, no network fetches
