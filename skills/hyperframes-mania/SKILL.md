---
name: hyperframes-mania
description: HyperFrames Silicon Mania / Mania 科技新闻快剪后期生产线，覆盖最终成片校时、中文 reference 改写、3:4 竖版包装、中文字幕、0.25 秒 contact sheet 复核、可复现渲染文件和 Mania 固定封面模板。用户给 Mania、Silicon Mania、hyperspellmania 或同类科技周报成片，要求做中文多平台版本、修字幕错位、竖版包装或周报封面时使用；新闻 source references 的研究与文案使用 silicon-mania-references。
---

# HyperFrames Mania

只处理 Silicon Mania / Mania 科技新闻快剪的后期交付。新闻事实、X source 和 reference 文案优先使用 `silicon-mania-references`；通用转写命令使用 `hyperframes-media`。

## 时间轴与字幕

1. 最终成片是时间轴真值，reference 时间戳只用于规划；用户指出错位时立刻回最终视频抽帧。
2. 先从最终源视频抽 `fps=4`、每 0.25 秒带时间标记的 contact sheet，再按真实画面切点写 cue。
3. 中文字幕去掉 `references (n/m)`、时间戳、X handle 和 source-list 格式，形成一条连续时间线。
4. 用户改写优先于标准翻译；保留 `IMO奥赛`、`旧金山TechBro` 等用户确认的 meme 表达，不改成新闻稿。
5. 降低中文观众认知成本：不知名个人优先写公司/职位，知名或用户指定人物保留姓名；必要产品名和公司名可保留英文。
6. 1080x1440 字幕优先从 46px 左右开始，黑描边约 4px，半透明黑底，放在虚化区；长句按语义拆成 1–2 行。
7. 导出后用同样 `fps=4` 抽带字幕 contact sheet，检查开头 4 秒、长字幕、用户改词、最后一句和 outro；发现错位就改 cue 重渲。

## 3:4 竖版包装

1. 默认输出 1080x1440 的 3:4 竖画布；16:9 主视频保持原比例居中，不裁切、不拉伸，背景用同一视频放大铺满并虚化。
2. 用户口头说“4:3/3:4/竖着”同时强调“16:9 不要变”时，按上述布局执行并在交付中说明尺寸。
3. 保留字幕 cue 脚本、透明字幕 PNG、filter graph 和最终 mp4；文件名体现 `fixed`、`small`、`cn_subtitles` 等版本。

## Mania 固定封面

默认使用 Cathy 确认的 1080x1440、3:4 模板：

1. 同一帧做虚化暗背景，主画面保持核心事件和标题完整；顶部黄色圆角标题条约 `(78,118)-(1002,226)`，圆角约 20px，颜色约 `#FFDD23`，轻微黑色投影约下移 5px。
2. 标题优先类似 `硅谷 Twitter 周报 #1`，黑色粗体，字号上限约 86px；底部放约 3 条中文看点，每条使用半透明黑色圆角底。
3. 底部字幕从 48px 起按最长单行回退，白色粗体；只把用户点名的身份或对象词改成橘色 `#FF7E1C`，不要整句上色。
4. 不加白色边框、白色文字描边或大黑色底板；英文和中文之间保留用户文案中的空格。
5. 用户给已设计好的 16:9 横版/PDF 式封面并要求完整保留时，用 1080x1440 黑底等比缩放：`image_h = round(1080 * src_h / src_w)`，`image_y = (1440 - image_h) // 2`。
6. 此时标题黄条放在画布顶部和主封面上沿之间正中：单行高约 136px，`title_y = (image_y - 136) // 2`；关键词红色用 `#C41220`。

## 交付检查

1. 跑 `ffprobe` 和完整 decode pass。
2. 对照 source 检查每个新闻 beat 的字幕、画面和切点。
3. 抽查主画面比例、顶部标题、最长字幕、用户刚修改的词和 outro。
4. 最终只报告源文件、输出文件、尺寸、时长和实际检查结果。
