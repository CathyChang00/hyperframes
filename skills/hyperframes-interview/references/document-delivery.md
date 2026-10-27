# 飞书 / Notion / Google Doc 剪辑交付

用户指定平台时，使用对应可用工具或文档技能更新真实在线页面，本地 Markdown 只是中间层；不要自动另建 Google Doc 代替飞书。只读请求不授权编辑。写入请求按已确认内容执行，并回读标题、关键问题、首尾及选中开场。多选题/短切片交付可参考下面结构；完整长版采用 [longform 子技能](../../hyperframes-interview-longform/SKILL.md)的执行稿结构，用户指定顺序优先：

```text
Heading 1：选中的 cold open / teaser（用户要求时置于页面标题后第一部分）
本轮批准时长的时间轴 + speaker + source timestamp + exact transcript

Heading 1：剪辑素材
外部参考链接
Heading 2：机位与收音映射（给剪辑师）
素材组与分段文件 + 画面机位链接 + 主音轨/声道 + source 时间码基准 + 同步方法

Heading 1：Paper Script 标题
最终 topic 与时长总览

Heading 1：VIDEO N｜TOPIC TITLE
副标题
主持人问题（标注：原片问题 / 无声 chapter card；补录 VO 仅在用户明确要求时使用）
原片文件与时间码；若明确补录，再放 VO 录音链接
问题回收范围
核心命题
Storytelling paraphrase

Heading 2：观众向 Chapter 标题
source timestamp + speaker
原片问题 buffer（如有）：粗剪插入点 + 原素材时间码
剪辑功能
exact transcript excerpt
剪辑边界
字幕 / 说话人映射风险
```

执行规则：

1. 多选题/短切片文档若包含选中的开场，先放完整开场，再放参考链接、机位映射、内容顺序与转录来源；没有开场时以剪辑素材开头。完整长版的材料顺序依 longform 结构，明确要求补录时才放 VO 文件。
2. 多个 teaser 候选已完成取舍时，成品页只放用户最终选择的一条；其余候选留在工作稿，不与长版 Script 混在一起。
3. 新代理与交付文件可用 `YYYYMMDD-company-partN-机位.ext`；保留原始文件名及映射，不为命名习惯移动或重命名唯一原片。
4. Paper Script 标明 V1/V2/V3 的时间码基准，并提醒按波形、口型或同一句台词同步，不按文件头硬对齐。
5. 每条问题必须紧跟类型和素材位置：原片问题放文件与时间码，无声 chapter card 放 exact on-screen copy；只有用户明确要求补录时才写 VO 并放音频链接。每个 topic 用 Heading 1，每个观众向 chapter 用 Heading 2。
6. Title、VO、文件名或素材链接变化后同步本地稿与在线页面；Google Doc 等待 `Saved to Drive`。Notion 默认建在 Private，除非用户指定 teamspace 或共享范围；不要自行改权限。
7. 任一在线页面写入后回读，验证标题、选中开场的首尾、长版首个核心问题、关键案例与最后一节；未选候选不混入成品页。原话、问题或片头修正时，同步已纳入本次交付的剪辑稿、视频和字幕，分别核验，不能只更新一处。
