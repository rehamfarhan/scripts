# 📥 YouTube Downloader (`ytvideo.sh`)

A robust, high-performance wrapper for `yt-dlp` configured with multi-threaded downloads (`aria2c`), preset profiles, thumbnail embedding, subtitle integration, and download archive tracking.

---

## 📋 Technical Overview

- **Language**: Bash (`#!/usr/bin/env bash`)
- **Dependencies**: `yt-dlp`, `aria2c`, `ffmpeg`
- **System Location**: `ytvideo/ytvideo.sh`
- **Target Command**: `ytvideo`
- **Archive Location**: `~/.cache/ytvideo/archive.txt`

---

## ✨ Features

- **High-Speed Multi-Threaded Engine**: Uses `aria2c` with 8 concurrent connections (`-x 8 -s 8`) for fast downloads.
- **Smart Presets**:
  - `video` (Default): 1080p H.265 MKV video, embeds PNG thumbnail, merges English subtitles.
  - `music`: High quality MP3 (VBR quality 0), square-cropped album artwork metadata.
  - `podcast`: Audio-only Opus format, embeds metadata and thumbnail.
  - `archive`: Maximum quality video/audio preservation with all available subtitles.
- **Format Selection Helper**: `--list` flag to inspect available streams/formats.
- **Duplicate Prevention**: Keeps track of downloaded video IDs in `~/.cache/ytvideo/archive.txt`.

---

## 🚀 Setup & Installation

Link the script to `/usr/local/bin` using `scrlink`:

```bash
sudo ../scrlink/scrlink.sh ytvideo/ytvideo.sh ytvideo
# or using scrlink helper:
sudo scrlink ytvideo
```

---

## 📖 Usage Examples

```bash
# Download video in 1080p (default video profile)
ytvideo "https://www.youtube.com/watch?v=..."

# Download high-quality audio / music MP3
ytvideo music "https://www.youtube.com/watch?v=..."

# Download podcast (Opus audio format)
ytvideo podcast "https://www.youtube.com/watch?v=..."

# Download maximum quality video with all subtitles
ytvideo archive "https://www.youtube.com/watch?v=..."

# Inspect available formats only
ytvideo --list "https://www.youtube.com/watch?v=..."
```
