---
name: hyperframes-interview
description: HyperFrames 长访谈内容生产线，覆盖多视频转写复核、从长访谈收敛 3–4 条核心视频、论题/论点/论据重组、topic/title/chapter 命名、两句话 VO question / POV、transcript-backed paper script、双机位与 Drive 文件命名、Google Doc 剪辑交付、剪映文稿匹配，以及访谈成片字幕与封面。用户要 review 访谈、重组嘉宾回答、把多个采访问题合并成 4–6 分钟切片、设计主持人补录问题，或把素材整理成剪辑师可执行文档时使用。
---

# HyperFrames Interview

把访谈从原始素材整理成可发布选题和可执行剪辑稿。转写、TTS 与抠像命令使用 `hyperframes-media`；本技能只负责访谈内容判断和交付。

## 默认工作流

1. 先做带时间戳、说话人和机器转写状态的 transcript；不要直接剪。
2. 还原主持人的隐藏问题线，即使最终删掉主持人声音。
3. 把嘉宾回答拆成句子级最小证据：结论、机制、案例、结果、边界、补充、口水词和跑题。
4. 先还原原片论证，再决定是否重排；原片结构清楚时只删主持人、口水词和跑题段。
5. 先给纸面剪辑方案和证据边界，涉及逻辑重排时等用户确认后再导出视频。
6. 导出后检查时长、分辨率、codec、audio、旋转信息和完整 decode；默认不调色、不做 SDR 转换。

## 从长访谈收敛成少数视频

### 选题方法

1. **问题不等于视频。** 把采访问题、回答和数据看成 evidence pool，不要把 10 个问题机械拆成 10 条视频。
2. **先定主线，再扫全稿。** 主线未确定时给最多 6 个 proposal，只写核心命题、证据链和边界；用户选定后重新逐句扫描所有 transcript。
3. **选题从可发布命题出发。** 人物经历、平台名、产品名或一次顺带提及不是 topic；每条视频必须有可复述的结论，并形成 `结论 → 机制 → 案例 → 边界 / 结果`。
4. **给每个 supporting detail 一个功能。** 标明它证明起点、机制、阶段变化、案例、结果、例外还是组织影响；无法说明作用就删除或放入备选库。
5. **不要把关键词当论据。** 一段只提到 performance ads、community 或 agent，却不能证明当前主论点，就不能作为 supporting evidence。
6. **机制依附型候选优先合并。** 候选 B 主要解释 A 为什么成立，而且会复用同一组起点、数据和结尾时合并；只有两条都有独立结论和独立 evidence pool 时才拆开。
7. **太短时扩大母题，不要填充。** 沿同一因果链向外扩一层，再反推 title、VO 和叙事顺序；证据只够 2–3 分钟时标为 optional short。
8. **写清素材所有权。** 同一句原声默认只归一条视频，避免四条视频换标题后重复使用。

### 标题与 chapter

1. Title 写结论、反差、状态变化或新的生产单位，不用人物履历和宽泛名词充当选题。
2. Subtitle 写机制：解释这个变化如何发生，而不是重复标题。
3. Chapter 写观众能理解的论证步骤，不用 `Hook`、`结尾`、`素材案例` 等内部剪辑标签。
4. 已验证的命名范式包括 `OPEN SOURCE IS A BETTER RESUME`、`COMFYUI IS NOT JUST A WORKFLOW LAYER`、`FROM ONE-OFF GENERATIONS TO AN AD CREATIVE FACTORY`、`ComfyUI’s Growth Playbook: From Community to PLG`；把它们当作“结论 / 转变 / 方法”的示例，不机械复用字面文案。
5. 把数字当标题前核验指标、单位、speaker 和时间范围；嘉宾自述数据标为 self-reported。

### Storytelling paraphrase 与原话

1. 先用大白话写 `结果或结论 → 起点或误解 → 动作与机制 → 转折 → payoff / what's next`，再回 transcript 找证据。
2. 固定分开四层：`topic thesis` 是编辑判断，`storytelling paraphrase` 是编辑叙事，`exact transcript evidence` 是可搜索原文，`subtitle correction` 是执行建议。
3. Paraphrase 可以综合多段原文、调整顺序和解释功能，但不能加引号、放进 quote block 或冒充嘉宾原话。
4. 每个 excerpt 必须是 source transcript 的连续原文；ASR 错误只写进字幕建议，不篡改原始 code block。
5. Diarization 或声纹不确定时标 `回原视频核对声纹`；核对前不能写成 CEO quote 或确定事实。

## Cathy 的 4–6 分钟访谈切片

### VO question / POV

1. 先区分 `纯 POV` 与 `VO question`：POV 是 on-screen text，不录音；VO question 才是 Cathy 补录口播。
2. VO 默认两句话、约 11–14 秒：第一句必须以疑问句提出核心问题，第二句加入一个具体观察、对比或追问，把回答引向第一组嘉宾原声。
3. VO 不负责概括完整 5–6 分钟，只负责在开头第 1–2 组回答、约前 50–100 个英文词内完成回收；后面可以继续展开机制、案例、边界和结果。
4. 不要把所有 chapter 塞进问题；删除原访谈中分散的主持人问题，让新 VO 后直接接最短、最明确的嘉宾回答。
5. 用户说 `纯 POV` 时不生成或插入音频；主持人声音默认不进成片。

### 时长估算

英文访谈按 130–150 words/minute 估算，再加 VO、停顿和 jump cut 缓冲。非母语或停顿多靠近 130，紧凑粗剪靠近 150；叙事完整后立即停，不为凑 5 分钟保留弱素材。

## Google Doc 剪辑交付

Live Google Doc 是 source of truth，本地 Markdown 只是中间层。按下面顺序写：

```text
Heading 1：剪辑素材（置顶）
外部参考链接
Heading 2：双机位素材说明（给剪辑师）
三组顺序 + 正/侧镜头链接 + 时间码基准 + 同步方法

Heading 1：Paper Script 标题
最终 topic 与时长总览

Heading 1：VIDEO N｜TOPIC TITLE
副标题
主持人补录问题（两句话）
VO 录音链接
问题回收范围
核心命题
Storytelling paraphrase

Heading 2：观众向 Chapter 标题
source timestamp + speaker
剪辑功能
exact transcript excerpt
剪辑边界
字幕 / 声纹风险
```

执行规则：

1. 文档最顶部固定放外部参考链接、双机位映射、内容顺序、转录源机位和 VO 文件。
2. 双机位文件优先命名为 `YYYYMMDD-company-partN-正镜头.ext` / `YYYYMMDD-company-partN-侧镜头.ext`。
3. Paper Script 标明 V1/V2/V3 的时间码基准，并提醒按波形、口型或同一句台词同步，不按文件头硬对齐。
4. 每条 VO 音频链接紧跟对应问题；每个 topic 用 Heading 1，每个观众向 chapter 用 Heading 2。
5. Title、VO、文件名或素材链接变化后同步本地稿与 Google Doc；用查找验证独特原句，并等待 `Saved to Drive`。

## 访谈成片继续加工

当用户说“我剪完的版本”“直接用这个视频”或指定 vX 时，把该文件当 source of truth，不回到旧素材，除非用户明确要求。

1. 保留已有英文字幕、name card、chapter title 和品牌特效字；不要重复制作。
2. 用户给的中文 script 是字幕真值，机器转写只用于时间对齐。
3. 已有英文字幕时只加中文；长句拆成多个单行 caption card，统一字号和 baseline。
4. 3:4 / 竖屏居中用公式确认：`foreground_y + foreground_h / 2 == canvas_h / 2`。
5. 章节截断检查边界前后帧；外部 B-roll 一旦承诺就必须实际切入。
6. 字幕中段错位时只返工用户指出位置前后 10–15 秒，逐句 retime，不整体平移时间线。
7. 封面先抽 contact sheet，选人物状态强且符合标题的帧；修改封面时读取 `../hyperframes-media/references/cover-thumbnail.md`。
8. 每次导出跑 `ffprobe`、完整 decode pass，并检查开头、品牌词、普通字幕、章节边界和结尾截图。

## 默认交互顺序

1. 转写稿。
2. 主持人的隐藏问题线。
3. 原片论题、论点、论据。
4. 嘉宾逐句证据拆分。
5. Topic proposal 与合并建议。
6. 用户确认。
7. Transcript-backed paper script 与 Google Doc。
8. 用户审批重排。
9. 导出、技术检查与剪映文稿匹配稿。

## 已验证的排序模式

- DevRel：定义 → B2B 为什么需要 → AI 时代为何更重要 → 如何衡量 → 平台分工。
- Café Cursor：活动起源 → community-led growth 与 PLG/SLG → NPS 和直接见用户；个人 Twitter 方法论默认删除。
- VC 经历：先回答 title 是否有用，再用“很多人都做过 VC”解释原因，最后落到真正做过什么。
- 增长访谈：为什么选这个 topic → 为什么此时/此平台 → 平台机制 → 证据 → 人物态度或结尾金句。
