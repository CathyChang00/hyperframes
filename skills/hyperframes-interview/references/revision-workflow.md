# 反馈定位、当前配置与可检查的交付

多轮修订时维护版本、原片映射和验收状态；小改只登记相关字段。记录留在项目目录，不随通用skill上传私人素材。

## 反馈动作与批准继承

| 反馈                   | 执行边界                                           |
| ---------------------- | -------------------------------------------------- |
| 合并话题、背景后移     | 移动完整问答，删同义重复，保护独有证据与主持人介绍 |
| 删句、嘴瓢、附和       | 同步修改原声、字幕和画面接点                       |
| 删图、换Logo、缩短资料 | 只改覆盖层，保留下方对白和后文时间线               |
| 先静帧，合适再应用     | 标记待应用，确认后放入视频                         |
| 替换某品牌全部标识     | 查标题、角落、资料卡及teaser／正文中的全部使用     |
| 沿用参考某一属性       | 只继承指定字体、底色或尺寸                         |
| 全篇应用效果           | 迁移视觉规则，保留teaser／正文各自的姓名标签       |
| 以后按新规则做         | 更新默认，不重导已采用成片                         |

项目记录用`反馈｜观看版本/原话｜修改层｜范围｜采用参考｜保留项｜交付物｜状态`。以最近采用成片合入后来批准的静帧；回退某个视觉效果时，保留后续删词、纠错和声音。用户恢复的内容列为必留，被否决稿不作新基线。

先交用户正在等待的完整产物，内部短样不能代替完整teaser或成片。正文、teaser与待应用静帧分别标状态，播放器和下载指向同一交付版本。

## 一份当前配置，三种证据

`project-state.json`记录版本、spans、反馈、checks、materials和semantic_reviews；`active_version`指向真实MP4。姓名、水印、字幕和倍率沿用现有渲染配置，避免两套值。新Cathy项目从[固定样式](cathy-style.md)初始化并记录覆盖项；新版本绑定新SHA-256。

| 证据       | 有效范围                                             |
| ---------- | ---------------------------------------------------- |
| 文字／配置 | 源文件含指定文字或数值，不证明已烧入视频             |
| 媒体       | 文件身份、容器时长、音轨包和时间戳，不证明听感或语义 |
| review     | 指定版本、方法和范围的实际审阅；记录不是自动听审     |

映射优先由现有EDL导出。空验收清单不通过，撤销要求标`superseded`并留原因。

## 可运行工具

Python3标准库；`init`及`check --media`需要ffprobe。路径相对本skill：

```bash
python3 scripts/interview_project.py init --video /project/final-V1.mp4 --version V1 --project Cathy --preset assets/cathy-interview-16x9.json --out /project/project-state.json
python3 scripts/interview_project.py locate /project/project-state.json --version V1 --time 00:10
python3 scripts/interview_project.py locate /project/project-state.json --feedback F001
python3 scripts/interview_project.py check /project/project-state.json --stage plan --out /project/plan-check.json
python3 scripts/interview_project.py check /project/project-state.json --media --out /project/delivery-check.json
```

`init`不覆盖已有记录；非Cathy项目可不传preset。`locate`返回源时码及同句所有位置，无命中可能只是缺映射。`check`退出0表示登记条件的机械检查完成，2表示错误或待验收；不加`--media`时媒体条件pending。`review_recorded`仅表示记录与文件身份有效。

`init --preset`复制materials限时并保存`materials_policy_source: {preset_id, preset: {path, sha256}}`，不改变速度或渲染样式。新增版本显式继承有效policy；更新通用skill不改旧项目快照。

## 项目记录格式

`schema_version: 1`；路径相对状态文件或用绝对路径。时间是有限秒数，区间`[in,out)`；文件引用为`{"path":"...","sha256":"实际64位SHA-256"}`。

### versions 与 spans：精确定位

`versions[V1]`含`video`引用、`duration_seconds`和数值或有理字符串`fps`。新增版本追加记录并更新active_version，不覆盖旧内容后沿用旧SHA。

一个span对应连续、可线性映射的原声：

```json
{
  "id": "V2-coldopen-01",
  "utterance_id": "source-01",
  "version": "V2",
  "video_sha256": "本版视频SHA-256",
  "speaker": "已确认姓名",
  "source": { "path": "source.mp4", "sha256": "原片SHA-256" },
  "source_range": [120, 126.5],
  "output_range": [0, 5],
  "rate": 1.3,
  "text": "连续原话",
  "semantic_review_required": true
}
```

句内删除或倍率变化拆成多个span；复用原句保留utterance_id、另设id和输出位置。反馈时码始终绑定用户观看版本。

### feedback：定位、修改、验收

必填`id / request / observed_version / at / span_ids / status`；可用`change_type: new_direction/aesthetic_selection/correction`区分新方向、审美选择和修复。

状态`open → located → applied → verified`；撤销为`superseded + reason`。verified需`resolved_version / check_ids`指向真实新版本并通过。默认`acceptance: rendered`要求实际输出review；只验稿件或配置时用artifact。旧verified跨版本需继承有效证据或复查。

同句反馈用locate的`all_occurrences`定位，再按用户指定范围修改，不机械改所有出现。

### checks：已确认要求的自动检查

每项含`id / version / video_sha256 / kind / scope`，scope说明实际检查范围。

| kind           | 必填／作用                                          |
| -------------- | --------------------------------------------------- |
| file_sha256    | artifact；核对文件身份                              |
| text           | artifact＋非空contains或excludes数组；大小写敏感    |
| json_value     | artifact / pointer / equals；JSON Pointer定位配置   |
| media_duration | expected_seconds；可选tolerance_seconds，默认0.05秒 |
| audio_identity | baseline引用；比较首音轨包、编码信息和时间戳        |
| review         | 实际审阅对象                                        |

review含`video_sha256 / reviewer:{kind:user/human/agent,name} / observed_at / method / verdict:accepted/uncertain/rejected / evidence:[文件引用]`。准确记录局部试听、导出帧或用户亲听的范围；没有听审就不填“听过”。

### materials：先按谈话规划资料

必填`id / version / topic / purpose / span_ids / required / status`，状态`planned/found/placed/excluded`。内容剪辑时写明事件、素材需求、查询线索及作用，按[资料计划](visual-evidence.md#让资料跟着谈话走)查找。

placed还需`source_url / author / observed_at / semantic_limits / asset / source_evidence / output_range`。指标另存`metric:{kind,display_value,source_url,observed_at,evidence}`；views对应当前帖，followers对应主页。视频派生映射见[视频B-roll](video-broll.md#原片派生文件成片三层可回查)。

`check --stage plan`允许待找资料；delivery要求required资料placed并以`export_check_ids`关联实际导出review。找不到就pending，取消必需资料保留依据，excluded写reason。research_status可细记查找过程，不能代替placed。

### 资料限时与时序的机械检查

在`versions[ID]`配置`materials_policy:{static_fullscreen_max_seconds:4,video_max_seconds:15}`。placed资料声明`display_mode:fullscreen/overlay`、`asset_type:static/video`：静态仅全屏限4秒，视频两种展示均限15秒；滚动截图导成MP4仍属static，不能按后缀分类。

旧`{fullscreen_max_seconds:4}`表示所有全屏资料统一限时，与typed字段不能混用。迁移需显式更新policy和资料类型；无policy时报告未检查限时。两项typed限值都需有效，缺类型不能享受更长上限。

`output_range`为秒；可加最终半开整数帧区间`output_frames`，两者差≤1ms。仅秒数时按fps四舍五入到最近帧，上限`floor(limit_seconds×fps)`；30000/1001fps下4秒最多119帧、15秒449帧。hold、滚动和淡入淡出均计入显示窗口。

相邻或只隔1帧的同SHA资料合并计时；同帖不同裁图用共同`continuity_id`。换ID不重置时长，同资产或continuity_id不能标矛盾类型。脚本不自动识别相似图片。

所有placed资料须与关联的当前span有时间重叠；完全提前／延后或只碰边界时记`timing_exception:{reason,max_offset_seconds}`，offset是距最近关联span允许的空隙。该检查核对时序，不判断素材语义。

### semantic_reviews：关键剪口保义

高风险span标`semantic_review_required:true`。记录`id / version / span_ids / before / after / dimensions / review`；before含可回源上下文，after为实播原词。

dimensions逐项记`subject / scope / negation / causality / reference`，各含`verdict:preserved/changed_with_authorization/uncertain`及note。changed另附实际authorization，不把编辑同意当作伪造原话许可。英文删词初筛不能替代上下文判断；有问题恢复原声限定，不用改字幕掩盖。见[语义检查](podcast-production.md#关键剪口语义检查)。

## 滚动与配乐修订的证据

更新实际渲染源和完整有效资料清单，合并差异时保留其他窗口。新增素材、音乐来源及展示时码进入最终来源表。

窗口检查前、首、中、末、后一帧；内部跨源接缝另查。边界争议从已知起点解码后按精确帧号取图，快速seek可能给邻帧。滚动宽度、路径及固定图层分别看，hold内重复帧正常。

纯视觉修改复制已采用的完整混音（含配乐），核对音轨包和时间戳。改配乐后另验对白保护及新混音，不再声称整轨与旧版一致；未变且证据有效的部分可复用。

## 有用的交付说明

导航章节与大标题入画窗口分别维护。标题表输出`实际文案｜入画–出画｜时长｜teaser/正文`；来源表覆盖全片实际资料。片头或删词改变时间线后，从最终帧数重新生成。

交付只说明已改反馈、当前可打开版本和未落实项；检查日志留项目目录。
