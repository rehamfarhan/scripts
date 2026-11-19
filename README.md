# scripts

A pile of small tools I use on Linux/Wayland, mostly for the terminal. Each one lives in its own folder with the source and a README that explains what it is for and how to use it.

They're not a framework and they don't share a library. The idea is that any folder here can be read, copied or deleted on its own.

## What's in here

| Folder | Command | Language | What it does |
| --- | --- | --- | --- |
| [`money/`](money/) | `money` | Python | Ledger for daily spending, income, reservations and month closures. |
| [`mediafetch/`](mediafetch/) | `mediafetch`, `mf` | Rust | Downloads video and audio with `yt-dlp` using fixed presets, plus lyrics tagging. |
| [`deprecated-mediafetch/`](deprecated-mediafetch/) | — | Python | The old Python version of mediafetch. Kept for reference, not maintained. |
| [`run/`](run/) | `run` | Rust | Launches games with per-game settings, keyboard patches and playtime tracking. |
| [`modfetch/`](modfetch/) | `modfetch` | Python | Installs Minecraft mods, modpacks, resource packs and shaders from Modrinth. |
| [`ddlclauncher/`](ddlclauncher/) | `ddlclauncher` | Bash | Scans for DDLC mods, writes launchers for them and runs them from a menu. |
| [`keydmgr/`](keydmgr/) | `keydmgr` | Python | Adds, changes and removes `keyd` bindings without editing the config by hand. |
| [`mkrofi/`](mkrofi/) | `mkrofi` | Bash | Creates `.desktop` entries so commands appear in rofi, dmenu or app menus. |
| [`scrlink/`](scrlink/) | `scrlink` | Bash | Puts a script in `/usr/local/bin` and moves loose scripts into folders. |
| [`cngtf/`](cngtf/) | `cngtf` | Python | Changes the system font and emoji font across GTK, Qt, terminal and Wayland apps. |
| [`barr/`](barr/) | `barr` | Bash | Restarts waybar after config changes. |
| [`raminfo/`](raminfo/) | `raminfo` | Bash | Prints RAM and swap usage with bars and a full `/proc/meminfo` breakdown. |
| [`rng/`](rng/) | `rng` | Python | Random number generator with configurable bounds and live re-rolling. |
| [`rngname/`](rngname/) | `rngname` | Python | Renames image files to random names, without collisions. |
| [`morsegen/`](morsegen/) | `morsegen` | Python | Encodes text to Morse and decodes it back, with custom symbols. |

`neovimconf/` is my Neovim config (an NvChad setup), not a command, so it isn't in the list.

## Installing

The scripts are used straight out of this directory. `scrlink` creates the symlinks in `/usr/local/bin`, so there's only ever one copy of each file.

```bash
# link scrlink itself first
sudo ./scrlink/scrlink.sh scrlink/scrlink.sh scrlink

# pick a script from the fzf menu
scrlink

# or name one directly
scrlink money
scrlink mediafetch mf
```

After that the command name works from anywhere. Editing the file in this repo changes the command immediately.

## Adding a new script

Drop the file in the repo root and run `scrlink` on it:

```bash
scrlink myscript.py
```

It will move it to `myscript/myscript.py`, create a starter README if one doesn't exist, and link `/usr/local/bin/myscript`. Then fill in the README and add a row to the table above.

## Requirements

Bash and Python 3 cover most of the repo. Individual tools also want:

- `git` and `fzf` for `scrlink`, `keydmgr`, `rng` menus and `ddlclauncher`
- `cargo` / Rust for `run` and `mediafetch`
- `yt-dlp`, `ffmpeg`, and optionally `aria2c` for `mediafetch`
- `wine` for Windows DDLC mods in `ddlclauncher`
- `waybar` and Hyprland for `barr`
- `keyd` for `keydmgr`
