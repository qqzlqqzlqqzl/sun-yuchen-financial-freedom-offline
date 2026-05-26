# 孙宇晨《财富自由革命之路》离线备份

这是一个个人离线备份整理仓库，内容来自公开页面和公开 RSS/音频源。

## 来源

- 官方页面: https://www.hejustinsun.com/zh/podcast
- 官方页面内的 Vimeo 清单: 157 条
- Wavlake RSS: https://wavlake.com/feed/show/c643fc93-e0a4-4898-adb0-456b48a1b829
- Wavlake 直链 MP3: 145 个，已离线并完成 `ffprobe` 可读性校验

## 仓库内容

- `metadata/official-vimeo-episodes.json`: 从官网 Framer CMS 提取的官方 Vimeo 剧集清单
- `metadata/official-vimeo-urls.txt`: 官网引用的 Vimeo 原始链接
- `metadata/wavlake-episodes.json`: Wavlake RSS 剧集清单
- `metadata/wavlake-files.tsv`: 已离线 MP3 文件名、大小、sha256
- `metadata/official-vimeo-partial-files.tsv`: 已离线的官方 Vimeo m4a 文件名、大小、sha256
- `wavlake-mp3/`: 145 个已离线 MP3 文件
- `official-vimeo-m4a-partial/`: 64 个已离线官网 Vimeo m4a 文件
- `checksums/*.sha256`: 音频文件校验和
- `transcriptions/`: 离线 Whisper large-v3 转写结果，包含原始 JSON、清洗 JSON、TXT、SRT、日志和转写 summary

## 当前离线状态

- `wavlake-mp3/`: 145 个 MP3，约 1.8GB，已通过 `ffprobe` 校验
- `official-vimeo-m4a-partial/`: 64 个官网 Vimeo m4a，约 1.0GB，作为补充来源
- `transcriptions/`: 209 个本地音频均已生成 `raw-json`、`clean-json`、`text`、`srt`
- `metadata/`: 官方与 RSS 元数据、URL、文件清单、校验和

## 转写说明

转写使用离线 `whisper.cpp` / `ggml-large-v3.bin`，`ftype=1/qntvr=0`，不是 int8/q8/q5/q4 量化模型。主批次参数为中文 `zh`、`beam_size=5`、`best_of=5`、4 workers、每 worker 3 threads。

原始模型返回保存在 `transcriptions/raw-json/`；可解析 UTF-8 JSON 在 `transcriptions/clean-json/`；普通文稿在 `transcriptions/text/`；字幕在 `transcriptions/srt/`。完整转写校验见 `transcriptions/metadata/transcription-summary.json`。

## 完整性说明

这不是官网 Vimeo 157 条音频的完整离线镜像。当前完整的是 Wavlake RSS 直链 MP3 集合；官网 Vimeo 来源只下载了 64 条。详见 `AUDIT-2026-05-26.md`。
