# deprecated-mediafetch

The old Python version of [mediafetch](../mediafetch/).

> **Deprecated.** This is no longer maintained. Use [`../mediafetch/`](../mediafetch/) instead; it's the Rust rewrite with the same presets and faster startup.

This version still works if you have its dependencies, so it's kept in the repo as a reference for the Python implementation.

## What it did

A `yt-dlp` wrapper with a `rich` full-screen TUI, multi-threaded downloads through `aria2c`, clipboard URL detection, preset profiles, and LRCLIB lyrics tagging.

The code is split into:

- `mediafetch.py`: argument parsing and pipeline
- `tui.py`: `rich` live display
- `downloader.py`: `yt-dlp` thread pool, progress hooks, partial-file cleanup
- `lyrics.py`: LRCLIB client and tag embedding
- `utils.py`: filename cleanup, clipboard, `.mfignore`, config loading

## If you still want to run it

```bash
sudo ../scrlink/scrlink.sh deprecated-mediafetch/mediafetch.py mf
```

Note that this uses the `mf` name, same as the current version. Link one or the other, not both.

## Requirements

`yt-dlp`, `ffmpeg`, `rich`, `python-mutagen`, optionally `aria2c`.
