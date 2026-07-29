# 🎮 Game Launcher (`run.py`)

An intelligent interactive game launcher and manager utilizing `fzf` to discover new game directories, run setup wizards, manage Windows `.exe` Wine prefixes, generate standalone runner scripts, create `.desktop` menu entries, and support instant quick-launching (`run <name>`).

---

## 📋 Technical Overview

- **Language**: Python 3 (`#!/usr/bin/env python3`)
- **Dependencies**: `fzf`, Python 3.8+
- **System Location**: `run/run.py`
- **Target Command**: `run`

---

## ✨ Features

- **Automated Game Discovery & Wizard**: Automatically detects unregistered subdirectories in `~/Games` and guides you through selecting main executables, setting display names, and configuring launcher wrappers.
- **Wine Prefix Manager**:
  - **Shared Wine Prefix**: Uses `$GAMES_ROOT/.wine` by default for Windows `.exe` games.
  - **Isolated Wine Prefix**: Allows setting up a per-game isolated prefix (`<GameDir>/.wine`).
- **Quick-Launch Mode (`run <name>`)**: Pass a game name query to immediately fuzzy-match and launch the game without opening the full menu.
- **Desktop Entry Creator (`.desktop`)**: Optionally creates `.desktop` menu shortcuts in `~/.local/share/applications/` for Rofi, Dmenu, and application menus.
- **Hidden Registry (`.run_registry.json`)**: Prevents re-scanning already configured folders.
- **Interactive `fzf` Menu**: Browse games with visual icons (`🐧` Linux native, `💻` Windows/Script).
- **Detached Execution**: Spawns games in clean background sessions (`start_new_session=True`), closing the terminal immediately.

---

## 🚀 Setup & Installation

Link the script to `/usr/local/bin` using `scrlink`:

```bash
sudo scrlink run
```

---

## 📖 Usage Examples

```bash
# Standard interactive launcher (scans new folders -> opens fzf menu)
run

# Quick-launch a game directly by name (fuzzy match)
run cyberpunk
run hollow

# Specify custom games directory
run --games-dir /path/to/custom/games
```

### Hotkeys in Menu
- **`ENTER`**: Launch selected game in background and exit terminal.
- **`TAB`**: Toggle ignore/hide status for selected game in registry.
- **`ESC` / `Ctrl+C`**: Exit menu.

