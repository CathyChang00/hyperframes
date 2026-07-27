---
name: hyperframes-media
description: HyperFrames 素材预处理技能，覆盖本地文字转语音、音视频转写、访谈/口播素材的论题/论点/论据梳理、纸面剪辑方案、嘉宾回答重组、去主持人音频、剪映文稿匹配稿、保留 iPhone 竖屏/HDR 原始观感的裁切导出、已有成片加字幕默认 3:4 竖屏画布、短视频封面/thumbnail 文案修改，以及透明背景抠像。用户要生成旁白、转写字幕、剪访谈、重组街采/口播、只保留嘉宾、去掉主持人、按 transcript 规划剪辑、保持原片色彩和比例、给成片加中文字幕并嵌入 3:4 竖屏画布、修改封面标题/字幕/上下虚化区文案、或做 TTS → 转写 → 字幕链路时使用。
---

# HyperFrames Media Preprocessing

Three CLI commands that produce assets for compositions: `tts` (speech), `transcribe` (timestamps), and `remove-background` (transparent video). Each downloads a model on first run and caches it under `~/.cache/hyperframes/`. Drop the output into the project, then reference it from the composition HTML — see the `hyperframes` skill for the audio/video element conventions.

When Cathy asks to revise a cover, thumbnail, title image, top/bottom blurred text area, or a cover screenshot, read `references/cover-thumbnail.md` before editing. The default is to preserve the latest approved cover composition and only change the named text elements.

When Cathy asks to add subtitles/captions to an existing video, default to a 3:4 vertical canvas export, not a direct same-as-source horizontal burn-in. Use a 1080x1440 Bryan/Corgi-style layout: the 16:9 source footage centered, blurred/extended background filling the canvas, and Chinese captions in the established lower safe area. Only keep the original aspect ratio when she explicitly asks to preserve the horizontal source dimensions.

## Text-to-Speech (`tts`)

Generate speech audio locally with Kokoro-82M. No API key.

```bash
npx hyperframes tts "Text here" --voice af_nova --output narration.wav
npx hyperframes tts script.txt --voice bf_emma --output narration.wav
npx hyperframes tts --list                       # all 54 voices
```

### Voice Selection

Match voice to content. Default is `af_heart`.

| Content type      | Voice                 | Why                           |
| ----------------- | --------------------- | ----------------------------- |
| Product demo      | `af_heart`/`af_nova`  | Warm, professional            |
| Tutorial / how-to | `am_adam`/`bf_emma`   | Neutral, easy to follow       |
| Marketing / promo | `af_sky`/`am_michael` | Energetic or authoritative    |
| Documentation     | `bf_emma`/`bm_george` | Clear British English, formal |
| Casual / social   | `af_heart`/`af_sky`   | Approachable, natural         |

### Multilingual

Voice IDs encode language in the first letter: `a`=American English, `b`=British English, `e`=Spanish, `f`=French, `h`=Hindi, `i`=Italian, `j`=Japanese, `p`=Brazilian Portuguese, `z`=Mandarin. The CLI auto-detects the phonemizer locale from the prefix — no `--lang` needed when the voice matches the text.

```bash
npx hyperframes tts "La reunión empieza a las nueve" --voice ef_dora --output es.wav
npx hyperframes tts "今日はいい天気ですね" --voice jf_alpha --output ja.wav
```

Use `--lang` only to override auto-detection (stylized accents). Valid codes: `en-us`, `en-gb`, `es`, `fr-fr`, `hi`, `it`, `pt-br`, `ja`, `zh`. Non-English phonemization requires `espeak-ng` system-wide (`brew install espeak-ng` / `apt-get install espeak-ng`).

### Speed

- `0.7-0.8` — tutorial, complex content, accessibility
- `1.0` — natural pace (default)
- `1.1-1.2` — intros, transitions, upbeat content
- `1.5+` — rarely appropriate; test carefully

### Long Scripts

For more than a few paragraphs, write to a `.txt` file and pass the path. Inputs over ~5 minutes of speech may benefit from splitting into segments.

### Requirements

Python 3.8+ with `kokoro-onnx` and `soundfile` (`pip install kokoro-onnx soundfile`). Model downloads on first use (~311 MB + ~27 MB voices, cached in `~/.cache/hyperframes/tts/`).

## Transcription (`transcribe`)

Produce a normalized `transcript.json` with word-level timestamps.

```bash
npx hyperframes transcribe audio.mp3
npx hyperframes transcribe video.mp4 --model small --language es
npx hyperframes transcribe subtitles.srt          # import existing
npx hyperframes transcribe subtitles.vtt
npx hyperframes transcribe openai-response.json
```

### Language Rule (Non-Negotiable)

**Never use `.en` models unless the user explicitly states the audio is English.** `.en` models (`small.en`, `medium.en`) **translate** non-English audio into English instead of transcribing it. This silently destroys the original language.

1. Language known and non-English → `--model small --language <code>` (no `.en` suffix)
2. Language known and English → `--model small.en`
3. Language unknown → `--model small` (no `.en`, no `--language`) — whisper auto-detects

**Default model is `small`, not `small.en`.**

### Model Sizes

| Model      | Size   | Speed    | When to use                           |
| ---------- | ------ | -------- | ------------------------------------- |
| `tiny`     | 75 MB  | Fastest  | Quick previews, testing pipeline      |
| `base`     | 142 MB | Fast     | Short clips, clear audio              |
| `small`    | 466 MB | Moderate | **Default** — most content            |
| `medium`   | 1.5 GB | Slow     | Important content, noisy audio, music |
| `large-v3` | 3.1 GB | Slowest  | Production quality                    |

Music with vocals: start at `medium` minimum; produced tracks often need manual SRT/VTT import. For caption-quality checks (mandatory after every transcription), the cleaning JS, retry rules, and the OpenAI/Groq API import path, see [hyperframes/references/transcript-guide.md](../hyperframes/references/transcript-guide.md).

### Output Shape

Compositions consume a flat array of word objects. The `id` field (`w0`, `w1`, ...) is added during normalization for stable references in caption overrides; it's optional for backwards compatibility.

```json
[
  { "id": "w0", "text": "Hello", "start": 0.0, "end": 0.5 },
  { "id": "w1", "text": "world.", "start": 0.6, "end": 1.2 }
]
```

### 访谈 / 口播重剪流程

当用户给原始访谈、街采、podcast、真人口播素材，并且想按观点逻辑重剪，而不是简单按时间裁切时，用这套流程。

1. **先转写，再规划。** 不要直接导出剪辑版。先做带时间戳的可读转写稿，标出说话人，并说明转写稿是机器转写还是已经人工校正过。
2. **即使最后删掉主持人，也要先找主持人的主线。** 访谈里经常是主持人在维持问题结构。最终成片可以完全裁掉主持人，但剪辑前必须先用主持人的问题判断真正要回答的问题是什么。
3. **把嘉宾按句子级别拆开。** 不要把 Whisper 分段或转写稿大段当成剪辑单位。把嘉宾回答拆成句子级/观点级片段：结论、论据、例外、案例、补充、口水词、跑题转向。
4. **先还原原片论证，再决定是否重排。** 不要为了“剪得更短”把原片本来完整的论题、论点、论据拆散。先写出：主持人实际追问的问题、嘉宾的核心回答、每个支撑细节的功能；如果原片已经有清楚结构，优先保留原结构，只做删主持人、删口水词、删跑题段。
5. **围绕一个主论点重组。** 开头先放最直接的回答，再接最强的直接理由。常见结构是：结论 → 个人证据 → 为什么头衔/履历不稀缺 → 真正重要的是什么 → 例子/例外 → 可执行结论。增长类访谈常见结构是：为什么选这个话题 → 为什么此时/此平台做 → 平台机制解释 → 支撑细节 → 人物态度/结尾金句。
6. **先讲具体对象，再讲抽象方法论。** 如果视频题目是某个公司动作、岗位或活动，例如 Café Cursor、DevRel、ABG CMO，开头必须先解释这个对象为什么值得讲，再接方法论。不要用 Twitter 方法论、平台机制、内容辅导这类泛化段落开场；用户说“可以删掉，或者放后面”时，默认先删掉，除非它能明确支撑主论点。
7. **删口水词要看功能，不是只看词本身。** 例如 "again I don't think" 如果没有新增信息就删；但如果一句话虽然不完美，却承载了必要含义或转场，就保留。删气口、重复词和未完成半句时，不要剪掉句子的语义收尾。
8. **案例和支撑细节只有服务主线才留。** 具名案例、平台对比、情绪铺垫都有用，但必须说明它支撑哪一个论点。如果一个细节会把视频带到另一个话题，就删掉或另做一条视频。
9. **涉及逻辑重排时，必须先让用户审批。** 先给纸面剪辑方案：精确原片时间段、建议顺序、保留/删除理由、可选结尾。等用户确认关键句和顺序后，再导出视频。
10. **主持人音频默认不进成片。** Cathy 常会自己录旁白垫音轨；除非用户明确要求保留主持人一句短问题，否则剪辑版默认只保留嘉宾声音。导出后必须用转写稿或听感确认没有主持人问题、笑声尾巴、“thank you” 这类结尾杂音。
11. **导出后必须做技术检查。** 检查时长、分辨率、codec/audio，跑一遍 decode pass；如果原片有横竖屏旋转信息，必须抽帧确认人物没有被拉伸。
12. **剪辑不等于调色。** 默认保持原片色彩路径，不要擅自加 `eq`、亮度、对比度、饱和度、gamma、色调映射或 SDR 转换。iPhone HDR/HLG/Dolby Vision 源片优先保持 10-bit HEVC 与原始色彩元数据（常见为 `bt2020nc / arib-std-b67 / bt2020`）；只有用户明确要求 SDR 交付、压暗、校色或平台兼容版时，才另出 SDR 版本，并把参数写进说明文件。
13. **给剪映文稿匹配要另出干净文稿。** 用户要“文稿匹配”或“完整 transcript”时，输出不带时间轴、不带说话人、不带段落标题的文稿。若用户提供片头旁白，把旁白放在最前面，再接最终剪辑里的嘉宾台词；只做必要语法修正，例如把 "over a thousand Café Cursor" 改成 "over a thousand Café Cursor events"，不要重写用户已确认的表达。

### Cathy 成片加字幕默认规则

当用户给的是“我剪完的版本”“直接用这个视频”“基于这个 vX 版本继续改”，把该文件当作 source of truth。不要回到更早的原素材、旧导出或之前下载的 B-roll，除非用户明确要求替换素材。

1. **“加字幕”默认交付 3:4 竖屏画布。** Cathy 说“加字幕”“加中文字幕”“把字幕加到视频上”时，默认导出 `1080x1440`，不是在原横屏文件上直接烧字幕。原 16:9 主画面要居中嵌入，上下用虚化或延展背景填充，中文字幕放在既定底部安全区；只有她明确说“保持横屏原尺寸”时才输出原比例。
2. **指定源视频优先。** 如果指定视频里已经有英文字幕、name card、章节 title、品牌特效字，默认全部保留；只在用户明确要求删除或重做时才覆盖。不要因为可以重新生成就做重复 name card、重复标题或重复字幕。
3. **中文 script 是字幕真值。** 机器转写或英文台词只用于对齐时间，不用于改写中文内容；中文和英文略有不一致时，字幕仍严格按用户给的中文 script 走。
4. **中英文字幕要共存。** 当源视频已经有英文字幕时，只加中文字幕。中文放在与英文有清楚间距的位置，不遮住英文；半透明黑底可以保留，厚黑描边不要加。
5. **长句分页，不要强行两行。** 用户说“一句话一次只出现一行”时，长句拆成多个 caption card；同一个 card 内不要折成两行。最后只剩一两个英文词时，优先略微拉宽或缩小字号，而不是把单词单独掉到下一行。
6. **统一字号和基线。** 同一条视频内字幕字号固定；Corgi、Higgsfield、PayPal 等品牌词可用品牌色或字形，但必须和当前字幕文字以底端 baseline 对齐，不要漂浮或下沉。
7. **3:4 居中要数学确认。** 用户说“正居中”时，不是凭肉眼上移或下移，而是计算主画面前景框：`foreground_y + foreground_h / 2 == canvas_h / 2`。导出后抽帧确认人物和字幕间距，不要让主画面偏上。
8. **每次导出都要技术和视觉检查。** 至少跑 `ffprobe`、完整 decode pass，并抽开头、普通字幕、长字幕、章节边界和结尾附近截图。最终回复只说源文件、输出文件、尺寸/时长和关键检查结果。
9. **字幕音频错位要局部返工，不要只整体重渲。** 用户指出“字幕和音频不匹配”“中间有一段错位”“挂空档”时，立刻回到最终成片，不要继续相信上一版 cue 表。先锁定用户指出位置前后至少 `10-15s` 的窗口，导出该窗口的字幕 cue，按音频关键词逐句 retime；字幕开始不能早于对应英文/中文语音的起点，结束也不能抢到下一句话。不要整条时间线粗暴平移，因为常见问题是中段某几句提前、漏翻或空了一句。长句要拆成最小语义 card，例如 `meme / 客户找来 / VC brand / hook / Hyperspell 是什么` 这类连续句必须一张卡对应一句话或半句话。重渲后必须抽这个局部窗口的带字幕 contact sheet；如果用户指出的是“中间一段”，最终回复要明确说修了哪几个 cue，而不是只说“已重新对齐”。

Cathy 的访谈口播剪辑默认交互流程：

1. 转写稿。
2. 主持人的隐藏问题线。
3. 原片论题、论点、论据梳理。
4. 嘉宾逐句观点拆分。
5. 建议保留/删除/重排方案。
6. 用户审批。
7. 导出剪辑版。
8. 技术检查 + 简短说明文件。
9. 剪映文稿匹配版转写稿（如用户需要）。

例子：VC 经历这段的开头顺序应该是：

```text
I don't think the VC experience was that helpful.
Nobody tried to approach me because I was once working at a VC firm.
Not a lot of people.
I think the title doesn't really do much.
There's so many people doing that.
So many people have worked at a VC firm.
I still feel like it's more important what you did at those roles, at those experiences, instead of the title or the firm.
```

这组顺序成立，是因为 "So many people have worked at a VC firm" 是在解释为什么 "the title doesn't really do much"。它应该贴在 title 那句后面，而不是放到后面当成一个新 topic。

例子：ABG CMO / Twitter viral 访谈应该先解释为什么选这个 topic，再解释为什么从 LinkedIn 切到 Twitter，然后说明 Twitter 与 Instagram 的算法差异，最后用 hate comments 做人物态度和 algorithm 回扣。不要一上来先讲算法，否则视频会变成抽象分析，丢掉原片“选题为什么成立”的上下文。

例子：DevRel 访谈的顺序应是：DevRel 到底是什么 → 为什么 B2B 公司需要 DevRel → 为什么 AI 时代 DevRel 变重要 → 怎么衡量 DevRel 是否有效 → X / LinkedIn / YouTube 等平台分工。不要把 "how to measure success" 放在定义之前；如果主持人问题被剪掉，仍然要按这个隐藏问题线组织嘉宾回答。

例子：Cursor / Café Cursor 访谈如果主线是 community-led growth，应直接从 Café Cursor 的具体起源开始，再接 community-led growth 与 PLG / SLG 如何一起工作，最后落到 NPS、见客户/潜在客户、收集反馈、工程团队直接见用户。Twitter 内容方法论这类段落会把视频带到个人内容增长，用户说“删掉或放后面”时，优先删掉。

例子：如果原片是 iPhone HLG/HDR 口播，最终剪辑版应默认保持 `hevc / yuv420p10le / bt2020nc / arib-std-b67 / bt2020` 这类原始色彩路径。生成 SDR 预览版可以作为备选，但不能覆盖用户要的主剪辑版；说明文件里必须写明是否做了 SDR 转换或任何亮暗/饱和度调整。

## Background Removal (`remove-background`)

Remove the background from a video or image so the subject (typically a person — avatar, presenter, talking head) sits as a transparent overlay in a composition.

```bash
npx hyperframes remove-background subject.mp4 -o transparent.webm  # default: VP9 alpha WebM
npx hyperframes remove-background subject.mp4 -o transparent.mov   # ProRes 4444 (editing)
npx hyperframes remove-background portrait.jpg -o cutout.png       # single-image cutout
npx hyperframes remove-background subject.mp4 -o subject.webm \
  --background-output plate.webm                                   # both layers in one pass
npx hyperframes remove-background subject.mp4 -o transparent.webm --device cpu
npx hyperframes remove-background --info                           # detected providers
```

Uses `u2net_human_seg` (MIT). First run downloads ~168 MB of weights to `~/.cache/hyperframes/background-removal/models/`.

### Layer separation (`--background-output`)

Pass `--background-output` (or `-b`) to emit a **second** transparent video alongside the cutout: same source RGB, alpha is `255 − mask` instead of `mask`. The cutout is the subject with a transparent background; the plate is the original surroundings with a transparent hole where the subject was.

| File                             | Alpha is…                                                 | Use it for                                                      |
| -------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------- |
| `-o subject.webm`                | The mask — subject opaque, background transparent         | Foreground layer, place on top                                  |
| `--background-output plate.webm` | Inverse — surroundings opaque, subject region transparent | Bottom layer; put text or graphics between this and the subject |

Both outputs share the same `--quality` preset and run from a single inference pass — encode cost roughly doubles, segmentation cost stays the same. Only valid for video inputs and `.webm`/`.mov` outputs.

**Hole-cut plate, not an inpainted clean plate.** The subject region in `plate.webm` is fully transparent — composite something opaque under it to fill the hole. The single test for whether `--background-output` is the right tool: _will anything ever be visible through the subject's silhouette where the subject used to be?_

| Use case                                                                            | Right tool                                                                         |
| ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Text/graphics between the cutout and the plate (this command's reason for existing) | **Hole-cut** (`--background-output`)                                               |
| Subject onto an unrelated scene                                                     | Just `subject.webm`; ignore the plate                                              |
| Show the room _without_ the person, alone over no other content                     | **Clean plate** — needs an inpainter (LaMa, ProPainter, E2FGVI). Not this command. |
| Replace the subject with a different subject                                        | **Clean plate** — same as above                                                    |

If a user asks for "the room with the person removed" and intends to display it standalone, do **not** reach for `--background-output`. Tell them they need an inpainter.

Typical layered composition (the canonical hole-cut use case):

```html
<!-- z=1 the inverse-alpha plate fills everything except the subject region -->
<video
  src="plate.webm"
  data-start="0"
  data-duration="6"
  data-track-index="0"
  muted
  playsinline
></video>

<!-- z=2 graphics / text live between the two layers -->
<h1 id="headline" style="z-index:2; ...">MAKE IT IN HYPERFRAMES</h1>

<!-- z=3 the cutout floats the subject back over the headline -->
<div class="cutout-wrap" style="position:absolute;inset:0;z-index:3">
  <video
    src="subject.webm"
    data-start="0"
    data-duration="6"
    data-track-index="1"
    muted
    playsinline
  ></video>
</div>
```

This is functionally equivalent to the text-behind-subject pattern below, but you don't need the original `presenter.mp4` in the project — the plate replaces it. Useful when you want to ship just the two transparent layers and let the user drop arbitrary content between them.

### Output Format

| Format                | When                                                          |
| --------------------- | ------------------------------------------------------------- |
| `.webm` (VP9 + alpha) | Default. Compositions play this directly via `<video>`.       |
| `.mov` (ProRes 4444)  | Editing in DaVinci/Premiere/FCP. Large files.                 |
| `.png`                | Single-image cutout (still subject, layered over a backdrop). |

Chrome decodes VP9 alpha natively, so the `.webm` plugs into a composition like any other muted-autoplay video — see the `hyperframes` skill for the `<video>` track conventions.

### Quality presets

`--quality fast|balanced|best` controls only the VP9 encoder's CRF — segmentation quality is fixed.

| Preset     | CRF | When                                                  |
| ---------- | --- | ----------------------------------------------------- |
| `fast`     | 30  | Iterating, smaller file, looser color match           |
| `balanced` | 18  | Default. Visually identical for most uses             |
| `best`     | 12  | Master / final delivery. Largest file, tightest match |

### Compositing patterns — pick the right one

The cutout webm is a **re-encoded copy** of the source mp4's RGB. That choice has consequences depending on what you put behind it:

| Pattern                                                  | What's behind the cutout                   | Result                                                                                                                                                                                                                            |
| -------------------------------------------------------- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Cutout over a different scene** (most common)          | Static image, gradient, or unrelated video | Looks great. The cutout's RGB is the only source of the subject — no doubling, no edge halo. This is what `remove-background` is built for.                                                                                       |
| **Cutout over its own source mp4** (text-behind-subject) | Same mp4 the cutout was generated from     | Two RGB sources for the same person. At default `--quality balanced` (crf 18) the doubling is barely visible; at `--quality fast` (crf 30) you'll see a faint color shift / edge halo. Use `--quality best` (crf 12) for masters. |
| **Cutout over a _different_ take of the same person**    | Footage of the same subject                | Will look like two separate people overlapping. Don't do this.                                                                                                                                                                    |

**Text-behind-subject** (headline behind a presenter):

```html
<video
  src="presenter.mp4"
  id="bg"
  data-start="0"
  data-duration="6"
  data-track-index="0"
  muted
  playsinline
></video>
<h1 id="headline" style="z-index:2; ...">MAKE IT IN HYPERFRAMES</h1>
<div class="cutout-wrap" style="position:absolute;inset:0;z-index:3;opacity:0">
  <video
    src="presenter.webm"
    data-start="0"
    data-duration="6"
    data-track-index="1"
    muted
    playsinline
  ></video>
</div>
```

Two key rules:

1. **Wrap the cutout video in a non-timed `<div>`** and animate the wrapper's opacity, not the video element's. The framework forces opacity:1 on active clips (any element with `data-start`/`data-duration`), so animating the video's opacity directly is silently overridden. The wrapper has no `data-*` attributes, so it's owned by your CSS/GSAP.
2. **Both videos use `data-start="0"` and `data-media-start="0"`** so the framework decodes them in sync from t=0. Late-mounting the cutout (`data-start=3.3`) introduces a seek + warm-up that lands a frame off the base mp4 — visible as one frame of misalignment at the cut.

Then GSAP-flip the wrapper opacity at the cut: `tl.set(cutoutWrap, { opacity: 1 }, 3.3)`.

## TTS → Transcribe → Captions

When there's no pre-recorded voiceover, generate one and transcribe it back to get word-level timestamps for captions:

```bash
npx hyperframes tts script.txt --voice af_heart --output narration.wav
npx hyperframes transcribe narration.wav   # → transcript.json
```

Whisper extracts precise word boundaries from the generated audio, so caption timing matches delivery without hand-tuning.
