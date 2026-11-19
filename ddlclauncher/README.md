# ddlclauncher

A menu for Doki Doki Literature Club mods.

DDLC mods usually ship as a folder with a renamed executable, sometimes a `.exe` that needs Wine, sometimes a shell script or a Python entry point. Keeping track of which binary in which folder starts which mod gets old fast. This script scans the mods folder, works out what to run, and keeps a launcher for each mod in one menu.

## How it works

- Looks through `~/DDLC Mods` for mod folders.
- Finds a likely entry point inside each one: `.sh`, `.py`, or `.exe` (run through `wine`).
- Asks where to point, then writes a small launcher script to `~/DDLC Mods/.launchers/`.
- Records the result in `mod_database.txt` so the menu doesn't rescan every time.
- Runs the chosen mod detached with `setsid`, so closing the terminal doesn't kill the game.

The menu is `fzf`, with random DDLC-themed symbols in the labels. Press `Tab` on an entry to delete its launcher and clear the database entry.

## Install

```bash
sudo ../scrlink/scrlink.sh ddlclauncher/ddlclauncher.sh ddlclauncher
# or
sudo scrlink ddlclauncher
```

## Usage

```bash
ddlclauncher
```

- `Enter` starts the selected mod.
- `Tab` removes its launcher.
- `Esc` or `Ctrl+C` exits.

## Requirements

- `fzf`
- `python3` for `.py` mods
- `wine` for `.exe` mods

Mods are expected in `~/DDLC Mods`. Launchers and the database are kept in that folder too.
