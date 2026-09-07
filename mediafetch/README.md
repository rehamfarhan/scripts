# 📥 Media Fetcher (`mediafetch.py` / `mf`)

A robust, high-performance standalone Python wrapper for `yt-dlp` featuring a full-screen alternate-buffer TUI dashboard inspired by `superfile` and Dusky TUIs, multi-threaded downloads (`aria2c`), clipboard URL auto-pasting, smart destination directory routing (defaults to `~/Videos/Downloads` and `~/Music/Downloads`), preset profiles, multithreaded non-interactive LRCLIB lyrics tagging, and custom configuration support.

---

## 📋 Technical Overview

- **Language**: Python 3 (`#!/usr/bin/env python3`)
- **Dependencies**: `ffmpeg`, `yt-dlp`, `aria2c` (optional), `rich`, `python-mutagen` (optional)
- **System Location**: `mediafetch/mediafetch.py`
- **Target Command / Shorthand**: `mf`
- **Default Destinations**:
  - 🎵 Music & Audio (`music`, `audio`, `flac`, `podcast`): `~/Music/Downloads`
  - 🎬 Videos (`video`, `shorts`, `archive`): `~/Videos/Downloads`
- **Configuration File**: `~/.config/mediafetch/config.json`

---

## 🧱 Modular Architecture

`mediafetch` is split into dedicated subscripts inside `mediafetch/`:
- **`mediafetch.py`**: Lightweight CLI dispatcher, argument parser, and pipeline orchestrator.
- **`tui.py`**: Full-screen alternate screen buffer renderer (`Live(screen=True)`), cut-in rounded panels (`box.ROUNDED`), track inspector, full-width block progress gauge, and non-blocking keyboard listener.
- **`downloader.py`**: Native `yt_dlp` thread pool engine, instant stream resolution, progress hooks with `DownloadCancelled` handlers, and `.part` file cleanup.
- **`lyrics.py`**: LRCLIB API client, ID3v2 `USLT` & FLAC Vorbis comment embedding, non-interactive batch pipeline, and interactive `fzf` attachment.
- **`utils.py`**: Title sanitization regex, clipboard reader, `.mfignore` engine, Hyprland window focus, and configuration loader.

---

## ✨ Features

- **🎨 Full-Screen Alternate-Buffer TUI (`Live(screen=True)`)**: Takes over the terminal in private buffer mode (`\033[?1049h`). Eliminates stdout spam and frame redraw scrolling; cleanly restores the terminal and cursor upon exit or cancellation.
- **⚡ Full-Width Progress Gauge**: Dedicated full-width rounded gauge panel displaying high-contrast block characters (`████░░`) indicating exact batch and single-stream progress.
- **🚀 Instant (<0.1s) Download Startup**: Single media URLs bypass blocking metadata pre-extraction and stream straight into the download engine with zero startup lag.
- **🛑 Graceful Single-Press `Ctrl+C`**: One `Ctrl+C` or pressing `q` triggers a unified cancellation event, raises `yt_dlp.utils.DownloadCancelled`, halts active child processes (`aria2c`, `ffmpeg`), wipes incomplete `.part` files, and restores the terminal without tracebacks.
- **⚡ 100% Non-Interactive Execution**: Downloads never freeze waiting for user input. If LRCLIB has no online lyrics for a track, it logs `✗ Skipped` and immediately continues.
- **🐛 Deduplicated Playlists & Albums**: Fast flat playlist extraction prevents duplicate tracks.
- **⏳ Two-Phase Pipeline**: Downloads all media in parallel first; once all downloads are verified, batch-tags lyrics and writes `.lrc` companion sidecars in phase two.
- **📋 Smart Clipboard Auto-Paste**: Running `mf music`, `mf audio`, `mf video`, etc. without entering a URL automatically detects media links from your clipboard (`wl-paste`, `xclip`, `pbpaste`).
- **📁 Default Downloads Folders**: Videos route to `~/Videos/Downloads` and audio/music to `~/Music/Downloads` (customizable via `-o` / `--output-dir` or `config.json`).
- **Smart Presets & Aliases**:
  - `video` (Default): 1080p H.265 MKV video, embeds PNG thumbnail, merges English subtitles (`en.*`).
  - `music` (alias: `audio`): High quality MP3 (320k), 1:1 square-cropped album art metadata, automated LRCLIB lyrics tagging (ID3 `USLT` tags), and `.lrc` companion sidecar file generation.
  - `flac`: Lossless FLAC audio extraction, square album art, embedded lyrics, and `.lrc` sidecar file generation.
  - `shorts`: 1080p MP4 optimized for 9:16 vertical video formats (YouTube Shorts, Instagram Reels, TikTok).
  - `podcast`: Audio-only Opus format, embeds metadata and thumbnail.
  - `archive`: Maximum quality video/audio preservation with all available subtitles.
- **🎤 LRCLIB Lyrics Tagging & `kew` Player Integration**:
  - Embeds unsynchronized lyrics directly into MP3 ID3v2 `USLT` frames and FLAC Vorbis comments for universal player compatibility (VLC, Amberol, Lollypop, etc.).
  - Generates synchronized `.lrc` sidecar files for terminal players (`kew`, `cmus`).
- **🎵 Folder & File Lyrics Tagging**: Command `mf lyrics ~/Music` or `mf lyrics track.mp3` to fetch and embed lyrics for local files or whole directories.
- **📎 Interactive Lyrics Attachment**: Standalone `mf attach` utility launches an interactive 2-step `fzf` picker to attach local `.lrc` files to untagged audio tracks with `.mfignore` support.
- **🧹 Filename Cleanup Engine**: Command `mf cleanup` or `mf cleanup /path/to/dir` recursively strips YouTube ID tags (e.g. `[kohSdJPaWLA]`) and video clutter (`[Official Lyric Video]`, `[HD]`, `[4K]`) from all audio files and `.lrc` sidecars.
- **High-Speed Multi-Threaded Engine**: Uses `aria2c` with 8 concurrent connections (`-x 8 -s 8`) for maximum download speeds.

---

## ⌨️ Interactive Controls

During live dashboard execution:
- `q` / `Q` / `Ctrl+C`: Abort immediately, purge partial `.part` files, and restore the terminal.
- `c` / `C`: Toggle hide/show of completed items from the active queue table.

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

# Download music without fetching or embedding lyrics
mf music --nolyrics "https://www.youtube.com/watch?v=..."

# Download Lossless FLAC + lyrics
mf flac "https://www.youtube.com/watch?v=..."

# Download 1080p MKV Video with English subtitles
mf video "https://www.youtube.com/watch?v=..."

# Download 1080p Vertical Video (YouTube Shorts / Reels)
mf shorts "https://www.youtube.com/watch?v=..."

# Download Podcast (Opus audio)
mf podcast "https://www.youtube.com/watch?v=..."

# Interactively attach local .lrc lyrics to untagged songs
mf attach
mf attach ~/Music

# Clean YouTube IDs & clutter from filenames & .lrc sidecars
mf cleanup
mf cleanup ~/Music/Downloads

# Launch Interactive TUI Menu
mf -i

# Embed lyrics into existing local audio file or entire folder recursively
# Automatically skips tracks with existing .lrc sidecars or embedded metadata (use -f / --force to overwrite)
mf lyrics
mf lyrics /path/to/song.mp3
mf lyrics ~/Music
mf lyrics -f ~/Music

# Download age-restricted videos using cookies
mf video -c ~/.config/mediafetch/cookies.txt "https://www.youtube.com/watch?v=..."
# (Or place cookies.txt in ~/.config/mediafetch/cookies.txt for automatic on-demand retry)

# Inspect available stream formats only
mf --list "https://www.youtube.com/watch?v=..."
```

---

## 🍪 Cookies & Age-Restricted Content

YouTube requires sign-in authentication to access age-restricted videos. `mediafetch` includes a zero-risk **Smart Cookie Fallback**:
- Normal downloads run anonymously without cookies to protect your Google account from session rotation or bot-flagging.
- If an age-restricted video is encountered, `mediafetch` automatically retries using your `cookies.txt` and displays `Retrying (Cookies)`.
- If cookies are expired or missing, `mediafetch` reports `Age-Restricted` or `Expired Cookies` with guidance on updating your cookies.

### Providing Cookies
You can provide a Netscape-formatted `cookies.txt` via:
1. **Standard location**: Save to `~/.config/mediafetch/cookies.txt` (or in the `mediafetch/` folder).
2. **CLI flag**: `mf -c /path/to/cookies.txt <URL>` or `mf --cookies /path/to/cookies.txt <URL>`.
3. **Configuration**: Set `"cookie_file": "/path/to/cookies.txt"` and optionally `"cookies_mode": "always"` in `~/.config/mediafetch/config.json`.

