# 📥 Media Fetcher (`mediafetch.py` / `mf`)

A robust, high-performance standalone Python wrapper for `yt-dlp` configured with multi-threaded downloads (`aria2c`), clipboard URL auto-pasting, smart destination directory routing (defaults to `~/Downloads`), preset profiles for video, music/audio, FLAC, shorts, podcasts, and archives, multithreaded batch LRCLIB lyrics tagging, and custom configuration support.

---

## 📋 Technical Overview

- **Language**: Python 3 (`#!/usr/bin/env python3`)
- **Dependencies**: `yt-dlp`, `ffmpeg`, `aria2c` (optional), `python-mutagen` (optional)
- **System Location**: `mediafetch/mediafetch.py`
- **Target Command / Shorthand**: `mf`
- **Default Download Destination**: `~/Downloads` (auto-creates directory via `mkdir -p` if missing)
- **Configuration File**: `~/.config/mediafetch/config.json`

---

## ✨ Features

- **Standalone Single-Executable Architecture**: Unified CLI downloader, interactive prompt, and LRCLIB lyrics tagger combined into one clean Python script.
- **📋 Smart Clipboard Auto-Paste**: Running `mf music`, `mf audio`, `mf video`, etc. without entering a URL automatically reads media URLs from your system clipboard (`wl-paste`, `xclip`, `pbpaste`).
- **📁 Default Downloads Folder**: All media downloads route by default to `~/Downloads` (customizable via `-o` / `--output-dir` or `~/.config/mediafetch/config.json`).
- **Smart Presets & Aliases**:
  - `video` (Default): 1080p H.265 MKV video, embeds PNG thumbnail, merges English subtitles (`en.*`).
  - `music` (alias: `audio`): High quality MP3 (VBR 0), square-cropped album art metadata, automated LRCLIB lyrics tagging (ID3 `USLT` tags), and `.lrc` companion sidecar file generation.
  - `flac`: Lossless FLAC audio extraction, square album art, embedded lyrics, and `.lrc` sidecar file generation.
  - `shorts`: 1080p MP4 optimized for 9:16 vertical video formats (YouTube Shorts, Instagram Reels, TikTok).
  - `podcast`: Audio-only Opus format, embeds metadata and thumbnail.
  - `archive`: Maximum quality video/audio preservation with all available subtitles.
- **🎤 Multithreaded Batch Lyrics Tagging & `kew` Player Integration**:
  - Concurrent batch processor queries LRCLIB using clean track titles & artist tags.
  - Embeds unsynchronized lyrics directly into MP3 ID3v2 `USLT` frames and FLAC Vorbis comments for universal player compatibility (VLC, Lollypop, Amberol, Foobar2000, etc.).
  - Generates synchronized `.lrc` sidecar files for terminal players (`kew`, `cmus`).
- **🎵 Folder & File Lyrics Tagging**: Command `mf lyrics ~/Music` or `mf lyrics track.mp3` to fetch and embed lyrics for local files or whole directories concurrently.
- **High-Speed Multi-Threaded Engine**: Uses `aria2c` with 8 concurrent connections (`-x 8 -s 8`) for maximum speed.

---

## 🚀 Setup & Installation

Link the script to `/usr/local/bin` using `scrlink` under the shorthand `mf`:

```bash
sudo ../scrlink/scrlink.sh mediafetch/mediafetch.py mf
# or using scrlink helper:
sudo scrlink mediafetch/mediafetch.py mf
```

---

## 📖 Usage Examples

```bash
# Clipboard Download (Copy a link, then run without pasting!)
mf music
mf audio

# Direct URL Download (High quality MP3 + album art + lyrics)
mf audio "https://www.youtube.com/watch?v=..."
mf music "https://www.youtube.com/watch?v=..."

# Download Lossless FLAC + lyrics
mf flac "https://www.youtube.com/watch?v=..."

# Download 1080p MKV Video with English subtitles
mf video "https://www.youtube.com/watch?v=..."

# Download 1080p Vertical Video (YouTube Shorts / Reels)
mf shorts "https://www.youtube.com/watch?v=..."

# Download Podcast (Opus audio)
mf podcast "https://www.youtube.com/watch?v=..."

# Launch Interactive TUI Menu
mf -i

# Embed lyrics into existing local audio file or entire folder recursively
mf lyrics /path/to/song.mp3
mf lyrics ~/Music

# Inspect available stream formats only
mf --list "https://www.youtube.com/watch?v=..."
```
