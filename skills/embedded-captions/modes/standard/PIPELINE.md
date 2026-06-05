# Standard mode — how this skill runs these templates

The 54 files in `templates/` (+ `_anatomy.md`, `_motion.md`) are the **design library** for Standard mode:
a flowing verbatim **rail** (their "flow") + one **embed** climax (their "climax"), matted speaker, one
paused seek-safe GSAP timeline. **This file is the one override you must read** — it adapts that library
to THIS skill's pipeline. Where this file and `_anatomy.md` disagree, **this file wins.**

## 3 things differ from `_anatomy.md` (read this, then use the library freely)

1. **Matte = RVM, not `remove-background`.** Ignore the `hyperframes remove-background` / `person.webm` /
   `.cut` layer in `_anatomy.md`. This skill mattes with `scripts/matte.cjs` (RVM → `frames_fg/*.png`) and
   composites the subject **in post** via `render-and-composite.sh`. **Never put the person in the HTML.**
2. **Contract = ours.** Not `.stage` / `window.__timelines['cap-{id}']`. Use `#root[data-composition-id="main"]`
   + `#a-roll` (the source video = their z0 background plate) + `#stage` + `#a-roll-audio` +
   `window.__timelines["main"]`. Same seek-safe rules (no `Math.random`/`Date.now`/CSS-keyframes/`repeat:-1`).
3. **Two files, not one** (this is how the rail ends up *in front* of the subject while the climax sits *behind*):
   - **`index.html`** — the source video + the **embed climax** in `#stage`. The RVM matte overlays this, so
     the subject occludes the climax (their z1 "behind the speaker").
   - **`rail.html`** — the **rail** (flow) only, transparent background, no video, no climax. Rendered to a
     transparent WebM and alpha-composited **on top of** the matte, so the rail is never occluded
     (their z6 "in front, lower third"). `render-and-composite.sh` does this automatically when `rail.html` exists.

Everything else in the library carries over **unchanged**: the per-template **style tokens**
(`--ff` / `--cfill` / `--cacc`, climax fill/stroke), the named **FLOW_*/CLIMAX_* motion recipes** in `_motion.md`,
`cqh` sizing, exit ≈ 75% of entry, **climax dwell ≥ 1 s**, and the restraint rule (effects only at the climax;
the rail stays clean + active-word accent).

## Pipeline (Standard)

```
1. hyperframes init <project> --non-interactive --video <video.mp4> --skip-skills
2. node scripts/matte.cjs <project>          # RVM → frames_fg/*.png  (KEEP RVM)
3. node scripts/transcribe.cjs <project>     # Whisper → transcript.json (verbatim word timings)
4. [AGENT] pick 3 templates by transcript fit (their `## Triggers`), read those 3 + the 2-3 motion
   recipes they name + this file; then author <project>/index.html (climax) + <project>/rail.html (rail)
5. bash scripts/render-and-composite.sh <project>   # renders both, RVM-mattes, alpha-overlays rail → final.mp4
```

## `index.html` — video + embed climax (matte puts it behind the subject)

```html
<!doctype html><html lang="en"><head><meta charset="UTF-8">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:{{W}}px;height:{{H}}px;overflow:hidden;background:#000}
  #a-roll{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center 12%;z-index:1}
  #stage{position:absolute;inset:0;z-index:2;container-type:size;pointer-events:none}   /* cqh works off this */
  /* CLIMAX — big, behind the subject (RVM matte occludes it in post). _anatomy §3 base + the template's tokens.
     ⚠ font-family MUST be the template's LITERAL name (hyperframes maps it to a bundled OFFLINE font). A CSS
     var (var(--ff)) is NOT resolved by the font compiler → it silently falls back to a generic sans and the
     whole look dies. Use a name from hyperframes' mapped list (oswald, inter, poppins, playfair display, …). */
  .climax{position:absolute;left:50%;top:37%;transform:translate(-50%,-50%);white-space:nowrap;
    font-family:'Oswald',sans-serif;          /* ← the template's font, LITERAL (never var()) */
    line-height:1.18;font-weight:900;font-size:44cqh;text-transform:uppercase;
    color:var(--cfill);text-shadow:0 2px 13px rgba(0,0,0,.6),0 0 48px rgba(0,0,0,.42);
    -webkit-text-stroke:1px rgba(0,0,0,.5);paint-order:stroke fill}     /* stroke for lit scenes (_anatomy §3) */
  .climax span{display:inline-block;opacity:0}
  .stage-tokens{--cfill:#e9e6dd;--cacc:#e3c06a}                         /* ← the template's fill/accent (colours only) */
</style></head><body class="stage-tokens">
  <div id="root" data-composition-id="main" data-start="0" data-duration="{{DUR}}" data-width="{{W}}" data-height="{{H}}">
    <video id="a-roll" src="source.mp4" muted playsinline data-duration="{{DUR}}" data-track-index="0" style="z-index:1"></video>
    <div id="stage"><div class="climax"><span>{{CLIMAX_WORD}}</span></div></div>
    <audio id="a-roll-audio" src="source.mp4" data-start="0" data-duration="{{DUR}}" data-track-index="3" data-volume="1"></audio>
  </div>
  <script>
    window.__timelines=window.__timelines||{};
    const tl=gsap.timeline({paused:true});
    const climax=document.querySelector('.climax span');
    const T={{CLIMAX_AT}}, HOLD={{CLIMAX_HOLD}};            // HOLD ≥ entranceDur + 1s
    tl.add(()=>{}, 0);                                       // ensure t=0 state
    tl.add(CLIMAX_IN(climax), T);                            // _motion.md recipe (e.g. deblur)
    tl.add(CLIMAX_OUT(climax), T+HOLD);                      // ends opacity:0
    window.__timelines["main"]=tl;
  </script>
</body></html>
```

## `rail.html` — the rail only, transparent (alpha-composited in front)

Same `#root`/timeline contract, but **transparent**, **no `#a-roll` video**, **no climax** — plus the `.grade`
vignette. Words injected from `transcript.json`, revealed at each word's `start`; the active word is recoloured to
`--cacc` via a `color` set (not a class — className isn't seek-safe). Lower third.

```html
<!doctype html><html lang="en"><head><meta charset="UTF-8">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:{{W}}px;height:{{H}}px;overflow:hidden;background:transparent}
  /* .grade — the anatomy's z5 vignette (depth + legibility). Composites over the matte, under the flow.
     KEEP IT — dropping it makes the result look flat/washed. A soft radial darken, NOT a full-frame solid bar. */
  .grade{position:absolute;inset:0;z-index:1;pointer-events:none;
    background:radial-gradient(130% 100% at 50% 28%, transparent 42%, rgba(0,0,0,.6))}
  #stage{position:absolute;inset:0;z-index:2;container-type:size}
  .flow{position:absolute;left:50%;bottom:9%;transform:translateX(-50%);width:90%;height:16%}
  .line{position:absolute;left:0;right:0;bottom:0;text-align:center;
    font-family:'Oswald',sans-serif;          /* ← the template's font, LITERAL (never var(); see climax note) */
    line-height:1.15;font-weight:700;font-size:6.4cqh;color:var(--cfill);
    text-shadow:0 2px 10px rgba(0,0,0,.65)}                 /* glyph-local scrim; NEVER a full-frame bar */
  .line .w{display:inline-block;opacity:0;margin:0 .12em;color:var(--cfill)}
  .stage-tokens{--cfill:#e9e6dd;--cacc:#e3c06a}             /* ← same fill/accent as index.html */
</style></head><body class="stage-tokens">
  <div id="root" data-composition-id="main" data-start="0" data-duration="{{DUR}}" data-width="{{W}}" data-height="{{H}}">
    <div class="grade"></div>
    <div id="stage"><div class="flow"></div></div>
  </div>
  <script>
    window.__timelines=window.__timelines||{};
    const tl=gsap.timeline({paused:true});
    const flow=document.querySelector('.flow');
    const _cs=getComputedStyle(document.body);
    const CFILL=(_cs.getPropertyValue('--cfill').trim()||'#fff'), CACC=(_cs.getPropertyValue('--cacc').trim()||'#10A37F');
    // WORDS = transcript grouped into lines [{words:[{text,start}], end}] in scene-local seconds
    // (2–4 words/line; non-overlapping windows — line.end ≤ next line's first word.start).
    const WORDS={{WORDS_JSON}};
    const FLOW_IN=(w)=>gsap.fromTo(w,{opacity:0,y:14},{opacity:1,y:0,duration:.42,ease:'power3.out'}); // _motion.md
    // Build EVERY line up-front as its own stacked container. Do NOT swap flow.innerHTML
    // per line — that runs synchronously at construction, leaving only the last line in the
    // DOM (earlier FLOW_IN tweens point at detached nodes). Separate containers = seek-safe.
    WORDS.forEach((line,li)=>{
      const div=document.createElement('div'); div.className='line';
      div.innerHTML=line.words.map((w,i)=>`<span class="w" data-i="${i}">${w.text}</span>`).join(' ');
      flow.appendChild(div);
      const spans=[...div.querySelectorAll('.w')];
      spans.forEach((el,i)=>{const w=line.words[i];
        tl.add(FLOW_IN(el), w.start);
        tl.set(spans,{color:CFILL}, w.start);   // reset prior active word — set COLOR, not className
        tl.set(el,{color:CACC}, w.start);});     // current word = accent (className sets aren't seek-safe)
      // Clear the line by fading its CONTAINER (not the spans). The container sits
      // at opacity 1 until here, so the tween can't degenerate into a 0→0 no-op the
      // way a span exit colliding with that span's own reveal would (which leaves a
      // word stuck on). Completes before the next line's first word → never two at once.
      const nextStart = WORDS[li+1] ? WORDS[li+1].words[0].start : null;
      const exitAt = nextStart!=null ? Math.max(line.words[0].start+0.1, nextStart-0.22) : line.end;
      tl.to(div,{opacity:0,duration:.22,ease:'power2.in'}, exitAt);             // line gone, stays gone
    });
    window.__timelines["main"]=tl;
  </script>
</body></html>
```

## Notes

- **No `plan.json` in Standard mode** → the template-mode gates (`check-timing`, `check-occlusion`) don't run.
  Self-check: rail words verbatim & on the beat (≤80ms), one embed per beat, climax holds ≥1s, exit ends at
  `opacity:0`. `check-overflow.js` still runs as a warning.
- **Rail legibility** is glyph-local only — a soft shadow or a text-box scrim. **Never grade/recolor the video**
  and never lay a full-frame bar (this skill's hard rule).
- **One embed at a time**, spaced ≥ a beat apart; the rail can briefly dim/clear under the embed if they'd collide.
- **⚠ Fonts are deterministic + must be LITERAL.** hyperframes ships the template fonts as OFFLINE fonts, but
  only applies one when `font-family` is a literal mapped name (`'Oswald'`, `'Inter'`, `'Poppins'`,
  `'Playfair Display'`, `'Anton'`, …). A CSS `var(--ff)` logs `No deterministic font mapping` and silently
  falls back to a generic sans — **the single biggest way a Standard render ends up looking nothing like the
  template.** Never put the font in a var; never rely on a Google-Fonts `<link>` (it's a flaky network dep).
- **Carry the template's design — don't sanitise it into generic defaults.** A small white Inter rail with a
  plain fade is NOT the template; next to the standalone it looks broken. The rail uses the **template's** font,
  size, palette (`--cfill`/`--cacc`) and `FLOW_IN`, and keeps the **`.grade`** vignette. Swap the rail font to a
  clean sans (Inter) ONLY for a truly decorative display face (Monoton / Press Start 2P / Special Elite / Arcade)
  that can't carry a running line — the climax keeps the display face.
- 16:9 climax base `44cqh`; long words bleed off-frame (intended cinematic); a 3-char climax behind a centred
  subject needs the stroke (above) so it peeks.
- **Keep the climax crisp.** A blur entrance (`deblur` / blur-in from `_motion.md`) leaves a big hero word soft
  for a large fraction of a short (~2s) dwell — it reads as a defect, not a move. Prefer a crisp scale/rise
  entrance unless the dwell is long. The settled hold must be sharp.
- **Rail lines must not overlap.** On continuous speech the next line's first word lands ~immediately after the
  previous line ends, so a line's exit has to *complete before* the next begins (the skeleton pre-empts it at
  `nextStart − dur`). Group at clause/breath boundaries to give the swap room; never let two lines co-exist.
