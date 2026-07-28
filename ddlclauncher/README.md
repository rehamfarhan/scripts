# 💔 DDLC Mod Launcher (`ddlclauncher.sh`)

A thematic interactive manager for Doki Doki Literature Club (DDLC) mods, offering automatic launcher creation, mod directory scanning, and execution.

---

## 📋 Technical Overview

- **Language**: Bash (`#!/usr/bin/env bash`)
- **Dependencies**: `fzf`, `bash`, `python3` (for `.py` mods), `wine` (for `.exe` mods)
- **System Location**: `ddlclauncher/ddlclauncher.sh`
- **Target Command**: `ddlclauncher`
- **Data Location**: `~/DDLC Mods/.launchers/` and `mod_database.txt`

---

## ✨ Features

- **Mod Directory Scanning**: Automatically scans `~/DDLC Mods` for new directories and identifies executable entry points (`.sh`, `.py`, `.exe` via Wine).
- **Auto-Generated Launchers**: Interactively creates launcher shell scripts stored in `~/DDLC Mods/.launchers/`.
- **Thematic Visual UI**: Uses `fzf` with randomized thematic emojis (💔, 🩸, 🧠, 🌸, 🎭, 🖤, 🕊️, etc.) matching the DDLC visual aesthetic.
- **Launcher Deletion (`TAB`)**: Press `TAB` within the selection menu to instantly remove a launcher script and reset its database entry.
- **Detached Execution**: Runs games in detached background processes (`setsid`).

---

## 🚀 Setup & Installation

Link the script to `/usr/local/bin` using `scrlink`:

```bash
sudo ../scrlink/scrlink.sh ddlclauncher/ddlclauncher.sh ddlclauncher
# or using scrlink helper:
sudo scrlink ddlclauncher
```

---

## 📖 Usage

```bash
# Run interactive scanner and launcher menu
./ddlclauncher.sh
# or if symlinked:
ddlclauncher
```

### Hotkeys in Menu
- **`ENTER`**: Launch selected DDLC Mod.
- **`TAB`**: Remove launcher configuration for selected mod.
- **`ESC` / `Ctrl+C`**: Exit menu.
