# 📥 Media Fetcher (`mediafetch.sh` / `mf`)

A robust, high-performance wrapper for `yt-dlp` configured with multi-threaded downloads (`aria2c`), preset profiles for video, music, and podcasts, thumbnail embedding, subtitle integration, and download archive tracking.

---

## 📋 Technical Overview

- **Language**: Bash (`#!/usr/bin/env bash`)
- **Dependencies**: `yt-dlp`, `aria2c`, `ffmpeg`
- **System Location**: `mediafetch/mediafetch.sh`
- **Target Command / Shorthand**: `mf`
- **Archive Location**: `~/.cache/mediafetch/archive.txt`

---

## ✨ Features

- **High-Speed Multi-Threaded Engine**: Uses `aria2c` with 8 concurrent connections (`-x 8 -s 8`) for maximum bandwidth speed.
- **Smart Presets**:
  - `video` (Default): 1080p H.265 MKV video, embeds PNG thumbnail, merges English subtitles.
  - `music`: High quality MP3 (VBR quality 0), square-cropped album artwork metadata.
  - `podcast`: Audio-only Opus format, embeds metadata and thumbnail.
  - `archive`: Maximum quality video/audio preservation with all available subtitles.
- **Format Selection Helper**: `--list` flag to inspect available streams/formats.
- **Duplicate Prevention**: Keeps track of downloaded media IDs in `~/.cache/mediafetch/archive.txt`.

---

## 🚀 Setup & Installation

Link the script to `/usr/local/bin` using `scrlink` under the shorthand `mf`:

```bash
sudo ../scrlink/scrlink.sh mediafetch/mediafetch.sh mf
# or using scrlink helper:
sudo scrlink mediafetch mf
```

---

## 📖 Usage Examples

```bash
# Download video in 1080p (default video profile)
mf "https://www.youtube.com/watch?v=..."

# Download high-quality music MP3 with album art
mf music "https://www.youtube.com/watch?v=..."

# Download podcast (Opus audio format)
mf podcast "https://www.youtube.com/watch?v=..."

# Download maximum quality video with all subtitles
mf archive "https://www.youtube.com/watch?v=..."

# Inspect available formats only
mf --list "https://www.youtube.com/watch?v=..."
```
