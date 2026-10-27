# 反馈定位、当前配置与可检查的交付

用于多轮修订：用户报成片时码、同句在片头与正文复用、已经确认样式需要保护，或需要检查这轮是否真正改到成片。简单修改只登记相关字段，不为一处改字重建全项目；新建完整剪辑时随 EDL 一起维护。项目记录放工作目录，不写回通用 skill，也不把私人素材、听审记录或工程配置默认上传 GitHub。

## 一份当前配置，三种证据

`project-state.json` 保存版本、原声片段、反馈、验收条件、资料计划与语义审阅；`active_version` 指向本次交付的真实 MP4。姓名、handle、封面、水印、字幕样式与倍率等批准值放项目现有渲染配置，检查项引用配置或输出，不维护互相冲突的第二套文本。选择新版本时重新绑定文件 SHA-256；旧版保留可回查。未变音轨可以用包数据与时间戳一致性继承证据，不能只看总时长。

区分以下结论：

| 证据           | 能证明什么                                          | 不能证明什么                               |
| -------------- | --------------------------------------------------- | ------------------------------------------ |
| 文字或配置检查 | SRT/标签源/渲染配置有精确文字或值                   | 最终画面已烧入，水印每帧可见               |
| 媒体检查       | 文件身份、容器时长、指定音轨包与时间戳一致          | 听起来舒服、裁剪好看、语义保真             |
| 实际审阅记录   | 指定人或 agent 用指定方法检查了绑定版本，证据可打开 | 不能把填写记录当工具亲自听审或全片人工通过 |

先从项目现有 EDL 导出映射，避免手工再抄一套。一次改变先记基线文件、允许修改层及受影响检查；配置通过后仍检查真实导出画面。自动检查只覆盖明确登记的条件，空清单不能通过。被用户明确撤销的要求标 `superseded` 并留原因，不偷偷删除历史。

## 可运行工具

路径相对于本 skill。Python 3 标准库；`init` 和 `check --media` 需要可执行的 ffprobe。

```bash
python3 scripts/interview_project.py init --video /project/final-V1.mp4 --version V1 --project Interview --out /project/project-state.json
python3 scripts/interview_project.py locate /project/project-state.json --version V1 --time 00:10
python3 scripts/interview_project.py locate /project/project-state.json --feedback F001
python3 scripts/interview_project.py check /project/project-state.json --stage plan --out /project/plan-check.json
python3 scripts/interview_project.py check /project/project-state.json --media --out /project/delivery-check.json
```

`init` 读取真实视频并建立身份，不覆盖现有记录，也不自动宣称验收完成。`locate` 要求观看版本和时间，返回源文件秒数及同一句的所有使用位置；无命中说明尚未映射，不能断言素材里没有这句话。`check` 只读取媒体，退出 0 表示已登记条件的机械检查完成；退出 2 表示错误或仍有待验收项。未加 `--media` 的媒体条件保持 pending。`review_recorded` 表示审阅记录与文件身份有效，不是脚本完成了审美或听审。

## 项目记录格式

工具初始化 `schema_version: 1`、`project`、`active_version`、`versions` 及五个空数组。路径相对状态文件所在目录，也可用绝对路径；时间为有限的秒数，区间用 `[in, out)`，倍率记录素材实际烘焙速度。文件引用统一为 `{"path":"...","sha256":"实际64位SHA-256"}`，大文件 SHA 可用流式 `shasum -a 256` 获取。

### versions 与 spans：精确定位

`versions` 以 V1/V2 等稳定版本 ID 为键，每版保存 `video` 文件引用、`duration_seconds`、数值型 `fps`。注册新版本时追加记录，并显式更新 `active_version`；保留旧版本，不将原路径指向新内容后沿用旧 SHA。

每条 `spans` 记录一个可线性映射的连续原声区间：

```json
{
  "id": "V2-coldopen-crypto-01",
  "utterance_id": "source-crypto-01",
  "version": "V2",
  "video_sha256": "本版真实视频SHA-256",
  "speaker": "已确认的姓名",
  "source": { "path": "source.mp4", "sha256": "原文件SHA-256" },
  "source_range": [120, 126.5],
  "output_range": [0, 5],
  "rate": 1.3,
  "text": "对应连续原话",
  "semantic_review_required": true
}
```

这段示例将原片 6.5 秒按 1.3 倍变成成片 5 秒。句内删除或不同倍率必须拆成多个 span，不拿整句平均倍率估算。正文重复引用保留相同 `utterance_id`、不同 `id` 和输出位置。用户说第 10 秒时先确认当前页面实际版本，不把新版本的第 10 秒套回旧版。

### feedback：定位、修改、验收

每项保留 `id / request / observed_version / at / span_ids / status`。`at` 是用户看见的版本时间；`span_ids` 绑定已定位的原反馈片段。用 `change_type` 可选标记 `new_direction / aesthetic_selection / correction`，分别统计新增方向、审美选择、本可避免的修复，不能把版本数都算成失败。

状态为 `open → located → applied → verified`；明确撤销时用 `superseded + reason`。`applied` 只代表修改做了，不能冒充成片已验收。`verified` 还需要 `resolved_version` 和 `check_ids`；这些检查必须指向本次真实文件并成功。`acceptance` 默认 `rendered`，必须包含实际输出的 review，文字/配置检查不能单独关闭成片反馈；只要求稿件或配置本身时才显式设 `artifact`。旧版 verified 到新版本先继承或重新核对相关证据，不因 status 字符串还在就自动通过。

一项涉及重复原句的反馈，使用 `locate` 的 `all_occurrences` 找片头、正文等位置，再按本轮范围登记各处修复和对应检查。若用户只指定某一次出现，保留其范围，不机械改全部。

### checks：已确认要求的自动检查

每项有 `id / version / video_sha256 / kind / scope`；scope 写实际范围，例如“字幕文件”“两处姓名卡实际帧”“整轨包与时间戳”。检查只针对绑定版本。

| kind             | 必填内容                                             | 用法                                                                               |
| ---------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `file_sha256`    | `artifact`                                           | 批准封面文件或已验证交付身份未变                                                   |
| `text`           | `artifact`，非空 `contains` 或 `excludes` 字符串数组 | 精确姓名、handle；限定文稿中排除旧标签。匹配区分大小写                             |
| `json_value`     | `artifact / pointer / equals`                        | 用 JSON Pointer 核对渲染参数，例如 `/watermark/text`；仅证明配置                   |
| `media_duration` | `expected_seconds`，可选 `tolerance_seconds`         | 实际视频容器时长；默认允许 0.05 秒差异                                             |
| `audio_identity` | `baseline` 文件引用                                  | 当前第一个音轨与批准基线的音频包、编解码信息、时间戳完全一致；不同则不能继承此证据 |
| `review`         | 下述 `review` 对象                                   | 实际画面、听感、字幕词尾或平台 poster 的审阅证据                                   |

比如姓名卡的文字源检查与最终导出画面审阅分别登记；水印配置正确与实际覆盖也分别登记。不要把 `text` 检查标成“视频里无该词”，不要用自动时长检查替代词尾听审。

`review` 对象含 `video_sha256`、`reviewer: {kind: user/human/agent, name: 实际身份}`、`observed_at`、`method`、`verdict: accepted/uncertain/rejected`、`evidence` 文件引用数组。方法准确写明“用户亲听原片确认”“查看两处导出帧”或“局部试听”；不具备听审能力的 agent 不填写“听过”。证据可以是实际截图、对照片段或用户确认的文字记录，声明检查范围；工具核对记录，不认证其结论。

### materials：先按谈话规划资料

每项有 `id / version / topic / purpose / span_ids / required / status`，状态为 `planned / found / placed / excluded`。`planned` 阶段即写明具体事件、需要的图片/视频/数据、查询线索及叙事作用；它和内容选择一起形成，不等成片后补装饰。详见[画面与社媒证据](visual-evidence.md#让资料跟着谈话走)。

`placed` 还需 `source_url / author / observed_at / semantic_limits / asset / source_evidence / output_range`，日期、原帖内容与实际插入窗口可互查。涉及指标时另存 `metric: {kind, display_value, source_url, observed_at, evidence}`；views 的链接必须属于当前帖，followers 使用其主页证据，不互换。这里只校验证据字段和文件，原帖真实性仍需按视觉参考核验。

`check --stage plan` 允许资料待找；delivery 模式要求 `required: true` 的资料已 placed，并用 `export_check_ids` 关联实际导出窗口的 review。排入时间线不等于导出已确认。找不到则保留 pending，不能用无关素材或手动写 pass 补齐。明确取消必需资料时保留取消依据，再更新 required；排除资料需写 reason。更细的查找、核实、资产可用阶段可在行内 `research_status` 留记录；它不能替代 placed 和输出审阅。

### semantic_reviews：关键剪口保义

高风险 span 标 `semantic_review_required: true`。每条语义记录有 `id / version / span_ids / before / after / dimensions / review`；before 是可回源的完整上下文，after 是剪后实际保留原词，不是润色总结。

`dimensions` 必须分别记录 `subject / scope / negation / causality / reference`。每项有 `verdict: preserved/changed_with_authorization/uncertain` 与具体 `note`；有意改变原意必须另记 `authorization`，不能由 agent 自己填“允许”。记录用户批准编辑决定不等于允许伪造嘉宾原话。

工具对英文敏感词的删减给出初筛风险，并检查逐项审阅证据；没有风险标记不证明语义不变，中文、代词、上下文和讽刺仍需实际审阅。发现问题回原片恢复限定或完整句，不靠字幕改写掩盖。方法见[关键剪口语义审查](podcast-production.md)。

## 有用的交付说明

给用户实际结果：这轮改了哪些反馈、当前可打开版本、还有哪些未落实。机器日志留工作目录；不把技术检查清单变成额外审批，也不承诺以后固定几版完成。工具不会修改视频或自动上传项目数据。
