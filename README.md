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

## 当前离线状态

- `wavlake-mp3/`: 145 个 MP3，约 1.8GB，已通过 `ffprobe` 校验
- `official-vimeo-m4a-partial/`: 64 个官网 Vimeo m4a，约 1.0GB，作为补充来源
- `metadata/`: 官方与 RSS 元数据、URL、文件清单、校验和
