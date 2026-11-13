# 争议音频三段对照

截词、异响、变速不自然时生成原速/当前处理/最终倍率三段，仅供定位和听审，不自动降噪、补词或认证质量；确认原话按[原声规则](podcast-production.md#截词漏词与异常声音)。

## 输入与运行

需 Python 3、`ffmpeg`、`ffprobe`；原文件只读，输出用新目录。确认原片 1×、当前倍率已烘焙；选句前后 10–30 秒，最长 120 秒。通常须同句连续内容，内部删句则拆段；调查截词/删句用诊断模式，不补别句。

时间从所选音轨首个解码样本起算秒数，区间 `[start, end)`；按音轨/容器起始 PTS 换算，非工程时码。`--original-audio-stream 0` 指音轨 `0:a:0`，非声道；保留原声道，双领夹归属另查。

从 skill 目录运行，替换路径/区间（原片 12 秒，当前 10 秒/1.2×，目标 1.3×）：

```bash
python3 scripts/make_audio_comparison.py \
  --original /path/raw.mp4 --original-start 100 --original-end 112 \
  --processed /path/current.mp4 --processed-start 70 --processed-end 80 \
  --processed-baked-speed 1.2 --target-speed 1.3 \
  --same-content-confirmed --label "尾词对照" --output /path/compare-v1
```

`--same-content-confirmed` 仅记录操作者定位；要求 `processed_duration ≈ original_duration / baked_speed`，容差 0.05 秒，不符回查。诊断改用互斥参数 `--diagnostic-difference "当前版截尾"`，允许时长不符并标“未对齐诊断”；等长也非同内容证明，第三段只变速当前错误版，不补词/静音，不作完整原句质量证据。

## 输出与核查

生成 `01-original.wav`、`02-current.wav`、`03-final-speed.wav`、`index.html`、`comparison.json`。前两段仅解码 48 kHz / 24-bit PCM，不调音量/混声道/淡化；第三段从当前段保音调按 `target_speed / processed_baked_speed`（1.2×→1.3× 约 1.08333×），同倍率复制。播放器 1×。

记录输入/输出 SHA-256、音轨、时间基准、倍率、命令和实际时长。只容许编码/算法的小幅长度误差，不补齐或裁尾；失败残留不交付。原词、尾音、噪声和接点仍待听审；降噪另做记录增益的同响度对照，不覆盖本组。
