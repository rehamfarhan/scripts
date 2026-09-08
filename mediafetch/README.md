# 📥 MediaFetch (`mediafetch` / `mf`)

A blazing-fast, zero-overhead terminal media fetcher and `yt-dlp` wrapper built with **Rust** and **Ratatui**.

Features an instant (<3ms) launch, full-screen alternate buffer interactive dashboard, curated smart presets, automated LRCLIB lyrics tagging (`.lrc` sidecars + ID3 `USLT` frames), clipboard auto-detection, and a pixel-perfect nerdy summary card with real-time stats pills upon download completion.

---

## 📋 Technical Overview

- **Language**: Rust (Edition 2021)
- **UI Engine**: [Ratatui](https://github.com/ratatui/ratatui) + [Crossterm](https://github.com/crossterm-rs/crossterm)
- **Async Runtime**: [Tokio](https://tokio.rs/)
- **Core CLI Engine**: `yt-dlp` (native subprocess streaming with `--progress-template`)
- **Metadata & Lyrics**: [LRCLIB REST API](https://lrclib.net/) + [id3](https://crates.io/crates/id3) crate
- **Startup Latency**: **< 3ms** (native compiled binary, zero interpreter overhead)
- **Default Destinations**:
  - 🎬 Videos (`video`, `shorts`, `archive`): `~/Videos/Downloads`
  - 🎵 Music & Audio (`music`, `flac`, `podcast`): `~/Music/Downloads`

---

## 🧱 Architecture

The Rust codebase is structured into clean, modular components inside [`src/`](src/):

| Module | Responsibility |
| :--- | :--- |
| [**`src/main.rs`**](src/main.rs) | CLI argument parser, Wayland (`wl-paste`) & X11 clipboard auto-detector, event loop runner, desktop notifications, and pixel-perfect summary table printer. |
| [**`src/ui.rs`**](src/ui.rs) | Full-screen Ratatui alternate buffer renderer, rounded borders, media header card, presets selector, preset inspector, progress gauge, and URL input modal. |
| [**`src/presets.rs`**](src/presets.rs) | Definitions for all 6 curated presets, destinations, format flags, and post-processing steps. |
| [**`src/downloader.rs`**](src/downloader.rs) | Multi-threaded async supervisor driving `yt-dlp`, parsing `--progress-template` for live speed/ETA/percentage, and fallbacks for title extraction. |
| [**`src/lyrics.rs`**](src/lyrics.rs) | LRCLIB client with exact and fuzzy search, ID3v2 `USLT` frame tagger, and `.lrc` companion sidecar file generator. |
| [**`src/metadata.rs`**](src/metadata.rs) | Fast async JSON stream inspector querying creator, duration, views, and upload date. |

---

## 🎯 Smart Presets

MediaFetch eliminates guesswork with 6 curated presets designed for immediate, "no-thinking" execution:

| Key | Preset | Format Spec | Destination | Features & Extras |
| :---: | :--- | :--- | :--- | :--- |
| `[1]` | **Video** *(Default)* | 1080p H.265 MKV | `~/Videos/Downloads` | Merged English subtitles (`en.*`), embedded high-res thumbnail |
| `[2]` | **Music (MP3)** | 320k MP3 | `~/Music/Downloads` | Square album art, LRCLIB synced lyrics (`.lrc`) & ID3 `USLT` tags |
| `[3]` | **FLAC** | Lossless FLAC | `~/Music/Downloads` | Lossless audio extraction, square album art, embedded lyrics & `.lrc` companion |
| `[4]` | **Shorts** | 9:16 Vertical MP4 | `~/Videos/Downloads` | Optimized for vertical video formats (Shorts, Reels, TikTok) |
| `[5]` | **Podcast** | Opus Audio | `~/Music/Downloads` | High-efficiency audio-only Opus format with embedded metadata |
| `[6]` | **Archive** | Max Quality Video | `~/Videos/Downloads` | Maximum quality preservation with all available subtitles |

---

## ✨ Features

- **⚡ Instant Launch (<3ms)**: Starts immediately without Python interpreter lag or cold-start freezes.
- **🎨 Full-Screen Alternate Buffer TUI**: Runs in private terminal buffer mode (`EnterAlternateScreen`), keeping your shell scrollback clean and restoring your prompt cleanly on exit.
- **📋 Smart Clipboard Auto-Detect**: Running `mediafetch` without arguments automatically inspects your clipboard (`wl-paste` on Wayland or `xclip` on X11) and loads valid media links instantly.
- **🎤 Automated LRCLIB Lyrics Tagging**:
  - Automatically fetches synced and unsynced lyrics from LRCLIB.
  - Embeds unsynced lyrics directly into MP3 ID3v2 `USLT` frames.
  - Generates synchronized `.lrc` companion files right alongside the audio file for players like `kew`, `cmus`, or `vlc`.
- **📊 Nerdy Pixel-Perfect Ending Screen**:
  - Automatically exits the alternate screen buffer when complete and renders an aligned, high-contrast table card in your shell scrollback:
  ```text
  ╭── 📥 Download Complete • 1 Video ──────────────────────────────────────────────────────────╮
  │                                                                                            │
  │   #     Video Title                                Format         Size          Status     │
  │  ────────────────────────────────────────────────────────────────────────────────────────  │
  │   01    what is love?                              1080p H.265    5.6 MB        ✓ Saved    │
  │                                                                                            │
  ╰────────────── ⏱ 00:22 │ 📦 5.6 MB │ 🚀 0.3 MB/s │ ✅ 1/1 Saved │ 📁 ~/Videos/Downloads ────╯
  ```
- **📐 Mathematical Unicode Alignment**: Uses [`unicode_width`](https://crates.io/crates/unicode-width) to guarantee zero border drift or offset issues regardless of emojis, Japanese/CJK text, or special characters.

---

## ⌨️ Keybindings in TUI

| Key | Action |
| :--- | :--- |
| **`Enter`** | Start download with selected preset |
| **`1` – `6`** | Jump directly to preset by number |
| **`j` / `k`** or **`↓` / `↑`** | Navigate through presets list |
| **`u`** | Open URL input / paste modal |
| **`q`** / **`Esc`** / **`Ctrl+C`** | Abort and cleanly restore terminal |

---

## 🚀 Installation & Build

### 1. Build from Source

Ensure you have Rust and Cargo installed:

```bash
cd mediafetch
cargo build --release
```

The optimized binary will be created at `target/release/mediafetch`.

### 2. Install to PATH

Copy or symlink the compiled binary into your local bin directory:

```bash
cp target/release/mediafetch ~/.local/bin/mediafetch
chmod +x ~/.local/bin/mediafetch

# Optional shorthand alias:
ln -sf ~/.local/bin/mediafetch ~/.local/bin/mf
```

---

## 📖 Usage Examples

```bash
# 1. Clipboard Auto-Detect (Copy a YouTube/media link, then run bare)
mediafetch

# 2. Direct URL Download (Opens TUI with default 1080p Video preset)
mediafetch "https://www.youtube.com/watch?v=..."

# 3. Pre-select a Preset (Opens TUI with preset focused)
mediafetch music "https://www.youtube.com/watch?v=..."
mediafetch flac "https://www.youtube.com/watch?v=..."
mediafetch shorts "https://www.youtube.com/watch?v=..."

# 4. View Help & Presets List
mediafetch --help
```
