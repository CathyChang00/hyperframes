---
name: hyperframes-interview
description: 剪辑和修订真人访谈、长播客、cold open与teaser，处理多机位、原声、字幕、资料、封面及发布包装；按任务调用对应子技能。
---

# HyperFrames Interview

要成片就交实际视频；只要执行稿或预览时按该范围交付。复用项目运行时；需要转写时用hyperframes-media，实际渲染时读取可用的hyperframes及对应音频、CLI技能。

## 本轮范围

从最近采用版继续，记录观看版本、反馈时码、允许修改层和必留项。当前指令优先；局部修改保护其他已确认内容，先候选／静帧时不替换主片。

相关话题可以合并，但保留独有论据、必要问题和主持人介绍。未规定硬时长时，按信息增量和完整问答决定长度。以后默认的调整只用于新项目。

## Cathy默认样式

新建节目按[Cathy固定样式](references/cathy-style.md)及JSON预设：teaser和正文默认1.2×；字幕每种语言各一行；固定标题字体、水印尺寸和底色。双语转画幅的中文位置按[中文字幕技能](../interview-subtitles-zh/SKILL.md)，已有项目保留采用的速度与例外。

配低音量、无歌词的背景音乐，teaser可取同曲更有起伏的节选。全屏静态资料每段≤4秒并带轻微滚动；用户提供或指定视频每段≤15秒，按完整动作选段。滚动截图导成MP4仍属静态资料，限时不等于必须凑满。

## 剪辑顺序

先核对逐字稿、人物身份和原片定位，再决定主线与删剪。首次内容编辑看全稿；只改图形时复用现有内容审阅。结论、机制、案例和边界优先于同义重复，资料需求随内容一起安排。

先接顺主音轨，再安排机位和B-roll。保留产品介绍、主题问题、必要追问及转折；删无效附和、重复问法和口癖，两位说话人都精修。换镜头不重复拼声音，缩短资料窗口不删下方对白。

原话、编辑概括、字幕纠错分开。原片或用户亲听纠错保留来源，未确定处标VERIFY；不凭声纹猜身份。默认现场原声，新增VO需用户要求。跨段摘句保留源时码，不能当作连续原话。

cold open、跨句拼接和句内微删检查主语、范围、否定、因果及指代，保住词尾和自然呼吸。音频争议先回原片定位，再做原速／处理／最终倍率对照，不反复猜词滤波。

## 按任务读取

只读取当前任务需要的资料。

| 任务                                 | 入口                                                                                                                                              |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| 完整节目、合并话题、累计删剪账       | [长片](../hyperframes-interview-longform/SKILL.md)                                                                                                |
| cold open、独立teaser                | [开场与teaser](../hyperframes-interview-teaser/SKILL.md)                                                                                          |
| 完整版另出≤15分钟LinkedIn版          | [LinkedIn剪辑](../hyperframes-interview-linkedin-cut/SKILL.md)                                                                                    |
| 4–6分钟主题切片、3:4包装、VO         | [短切片](references/shortform-editorial.md)                                                                                                       |
| 多轮反馈、版本映射、验收状态         | [修订](references/revision-workflow.md)；scripts/interview_project.py                                                                             |
| 多机位、尾词、变速、混音、验证       | [制作与原声](references/podcast-production.md)；争议词读[音频对照](references/audio-comparison.md)                                                |
| 查资料、原帖指标、字幕、姓名卡、滚动 | [画面与资料](references/visual-evidence.md)                                                                                                       |
| launch／demo素材、静音和选段         | [视频B-roll](references/video-broll.md)                                                                                                           |
| 关系动效、组合Logo、局部背衬         | [图形构图](references/graphic-composition.md)                                                                                                     |
| 封面                                 | [英文](references/cover-workflow.md)、[中文](../interview-cover-zh/SKILL.md)；[三画幅](../interview-cover-zh/references/three-format-delivery.md) |
| 中文字幕、双语及转画幅               | [中文字幕](../interview-subtitles-zh/SKILL.md)                                                                                                    |
| 发布标题、正文、标签、章节           | [小红书](references/rednote-publishing.md)、[X／LinkedIn](references/social-publishing.md)                                                        |
| 指定飞书／Notion／Google Doc         | [在线文档](references/document-delivery.md)                                                                                                       |

## 封面与发布

完整封面默认英文横16:9、中文竖3:4、中文横4:3，单版修改只更新指定项。封面先给钩子，副标题给答案线索，发布标题补行动或转折；英文已定后中文版保留主题与承诺。默认给一个推荐标题，用户要候选再给指定数量。

发布文案复用最终成片和逐字稿，不重启剪辑。小红书原生章节默认≤6个，正文不重复时间轴；X／LinkedIn按各自发布流程处理。写稿、填页和正式发布沿用本轮授权。

## 核验与交付

反馈时码绑定用户观看版本，原词回查未剪原片；同句在片头与正文复用时，定位所有出现，再按本轮范围修改。实际导出后检查改动、接点和受影响部分，配置通过不等于成片通过。

纯视觉修改保护整条采用音轨、倍率与尾词；输入、时间映射和数据未变才继承验证。新全片编码完整解码；局部替换／纯封装按[制作参考](references/podcast-production.md#局部修订与验证复用)检查。默认不额外调色或转SDR。

视频交MP4及最终SRT，执行稿交完整问答、原片定位和删剪决定；保留上一版，确认播放器、封面和下载指向当前文件。资料来源表和标题显示时码从最终时间线生成。交付说明只写改了什么、验证范围、待解决项和结果链接。
