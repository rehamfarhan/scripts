# mediafetch

Downloads video and audio from YouTube and similar sites.

`yt-dlp` can do almost anything, but the flags for "1080p video with subtitles and a thumbnail" or "320k MP3 with cover art and synced lyrics" are long, easy to get wrong, and different every time. `mediafetch` puts those combinations behind fixed presets, shows the download in a full-screen TUI, and adds the lyrics step for music.

It's a Rust binary wrapping `yt-dlp`, so there's no interpreter startup lag.

## Presets

| Key | Preset | Format | Destination |
| --- | --- | --- | --- |
| `1` | Video | 1080p H.265 MKV, English subtitles, thumbnail | `~/Videos/Downloads` |
| `2` | Music | 320k MP3, square album art, lyrics | `~/Music/Downloads` |
| `3` | FLAC | Lossless FLAC, album art, lyrics | `~/Music/Downloads` |
| `4` | Shorts | 9:16 vertical MP4 | `~/Videos/Downloads` |
| `5` | Podcast | Opus audio with metadata | `~/Music/Downloads` |
| `6` | Archive | Best available video and all subtitles | `~/Videos/Downloads` |

## What it does

- Opens a full-screen alternate-buffer UI, so the download doesn't spam your scrollback. The terminal is restored on exit or cancel.
- Starts with the clipboard URL if you run it with no arguments (`wl-paste` on Wayland, `xclip` on X11).
- Streams progress out of `yt-dlp` and shows speed, ETA and percentage.
- For audio presets, looks up lyrics on LRCLIB, writes a `.lrc` file next to the track, and embeds unsynced lyrics in the file's tags (ID3 `USLT` for MP3, Vorbis comments for FLAC).
- Prints a summary table when the download finishes.

## Build

```bash
cargo build --release
cp target/release/mediafetch ~/.local/bin/mediafetch
ln -sf ~/.local/bin/mediafetch ~/.local/bin/mf
```

## Usage

```bash
mediafetch                                  # use the clipboard URL
mediafetch "https://youtube.com/watch?v=…"  # start with that URL
mediafetch music "https://…"                # preselect a preset
mediafetch flac "https://…"
mediafetch --help
```

### Keys

| Key | Action |
| --- | --- |
| `Enter` | Download with the selected preset |
| `1`–`6` | Select a preset |
| `j` / `k`, arrows | Move through presets |
| `u` | Enter or paste a URL |
| `q`, `Esc`, `Ctrl+C` | Quit and restore the terminal |

## Source layout

| File | Role |
| --- | --- |
| `src/main.rs` | Argument parsing, clipboard detection, event loop, notifications, summary output |
| `src/ui.rs` | Ratatui rendering: preset list, inspector, progress, URL modal |
| `src/presets.rs` | Preset definitions and their `yt-dlp` flags |
| `src/downloader.rs` | Runs `yt-dlp`, parses progress, handles errors |
| `src/lyrics.rs` | LRCLIB lookup, `.lrc` writer, tag embedding |
| `src/metadata.rs` | Fetches title, creator, duration, views and upload date |

## Requirements

- `yt-dlp` and `ffmpeg`
- `wl-clipboard` or `xclip` for clipboard detection
- `libnotify`/`notify-send` if you want desktop notifications
- A terminal with Unicode support (the summary table uses box drawing and emoji)

The older Python implementation is in [`../deprecated-mediafetch/`](../deprecated-mediafetch/) and is no longer maintained.
