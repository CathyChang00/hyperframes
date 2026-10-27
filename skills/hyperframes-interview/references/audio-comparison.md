# 争议音频三段对照

当用户指出截词、异响、变速后不自然，先定位有句前、句后上下文的同一句，运行 `scripts/make_audio_comparison.py`，输出原速原声、当前处理、最终倍率三个短 WAV 和本地播放页。不要据此自动降噪、猜词、合成词尾或声称听审通过。

## 输入与运行

先确认原片是 1×，当前处理片的倍率已烘焙。选 10–30 秒左右上下文，最长 120 秒。通常两段应包含相同、连续的内容，没有内部删句；若要诊断当前版本已经截词或删句的错误，保留原片完整源句与当前版实际内容，用下述诊断模式明确差异，不补入别句伪装完整对照。

时间参数是各文件所选音轨首个解码样本起的秒数，使用半开区间 `[start, end)`，不是剪辑工程的全局时码。工具记录音轨和容器起始 PTS；音视频起点不同的素材，要先把用户的成片时码换算到对应音轨时间。`--original-audio-stream 0` 表示第一条音轨 `0:a:0`，不是第一个声道；双领夹的声道选择另行确认，本工具保持原有声道。

以下命令从 skill 目录运行；先替换两个输入路径和已确认的区间。示例原片 12 秒、当前片 10 秒，当前已烘焙 1.2×，最终目标 1.3×：

```bash
python3 scripts/make_audio_comparison.py \
  --original /absolute/path/raw.mp4 --original-start 100 --original-end 112 \
  --processed /absolute/path/current.mp4 --processed-start 70 --processed-end 80 \
  --processed-baked-speed 1.2 --target-speed 1.3 \
  --same-content-confirmed --label "完整原句与关门声对照" \
  --output /absolute/path/work/audio-comparison-v1
```

`--same-content-confirmed` 只记录操作者已完成内容定位，不是程序认证原话。严格模式的区间时长必须满足 `processed_duration ≈ original_duration / baked_speed`，允许 0.05 秒边界误差；不符就回查倍率和区间。需要逐词比较时，内部有删句的区间应拆成连续片段。

当前版已经截掉尾词、存在内部删句时，用 `--diagnostic-difference "当前版尾词 background 被截断"` 替换 `--same-content-confirmed`，两参数互斥。诊断模式允许时长不匹配，播放页与记录明确标记“未对齐诊断”；时长刚好一致也不视为内容一致。第三段仍只把当前错误版按 `target / baked` 变速，不自动补词、补静音或恢复原声。这用于调查差异，不能当作同一完整原句的处理质量证明。

## 输出与核查

需要 Python 3、`ffmpeg`、`ffprobe`。输出目录必须是新目录，原文件只读。工具生成 `01-original.wav`、`02-current.wav`、`03-final-speed.wav`、`index.html` 与 `comparison.json`。原声和当前处理仅解码成 48 kHz / 24-bit PCM；不调音量、不混声道、不加淡化。最终段从当前处理段应用 `target_speed / processed_baked_speed` 的保音调变速；例如已烘焙 1.2× 到目标 1.3×，只额外应用约 1.08333×，不是再乘 1.3×。目标与当前相同则直接复制 WAV。

记录包括输入文件 SHA-256、音轨、时间基准、倍率、执行命令、输出 SHA-256 与实际时长。读取完整输入计算 hash 可能需要时间；工具不会上传。播放页播放器保持 1×。变速长度只允许编码/算法小幅误差，不静默补齐或裁尾；失败目录可能保留部分 WAV，不作为完成结果交付。

这份对照用于定位和听审，不自动认定哪段更好；原词、尾音、噪声来源、接点自然度均保持待确认。若要比较降噪优劣，另做已记录增益的同响度对照，不覆盖这组三段保真参考。用户确认原话后按[原声完整性规则](podcast-production.md#截词漏词与异常声音)记录人类证据。
