# 🎮 Game Launcher (`run.py`)

An intelligent, interactive game launcher and manager utilizing `fzf` to discover new game directories, run setup wizards with real-time binary inspector previews, manage Windows `.exe` Wine prefixes, track total playtime and star ratings, stream live verbose terminal logs, provide a comprehensive `TAB` item utilities menu, create `.desktop` application menu entries, and support instant quick-launching (`run <name>`).

---

## 📋 Technical Overview

- **Language**: Python 3 (`#!/usr/bin/env python3`)
- **Dependencies**: `fzf`, Python 3.8+
- **System Location**: `run/run.py`
- **Target Command**: `run`

---

## ✨ Features

- **Automated Game Discovery & Disk Folder Wizard**: Automatically detects unregistered subdirectories in `~/Games`, allows disk directory renaming to clean game names, and guides you through selecting main executables and launcher wrappers.
- **Centered `fzf` Interface**: Menu floats in the dead center of the terminal screen (X and Y axes) with rounded borders, title banners (`🏰 DirectPass's Game Dungeon 🎮`), and fixed-width column alignment for game names, star ratings, playtime counters, and relative timestamps.
- **Recently Played Menu Sorting**: Automatically sorts games in the main menu by `last_played` timestamp descending (most recently played games appear at the top).
- **TAB Item Utilities Sub-Menu (`⚙️ Utilities`)**: Pressing `TAB` on any game opens an interactive sub-menu:
  - ✏️ **Rename Game Entry**: Rename display name and update launcher wrappers & `.desktop` entries.
  - ⭐ **Rate Game**: Star rating picker (0 to 5 stars).
  - 🍷 **Configure Wine / Execution**: Custom Wine prefix setup, Virtual Desktop resolution (`1920x1080`, `2560x1440`, etc.), DXVK Vulkan HUD (`fps`, `full`), and Windows OS version (`win10`, `win7`).
  - 🛠️ **Change Main Executable Binary**: Re-scan game folder and pick a different main binary with live metadata preview.
  - 🖥️ **Create / Recreate Desktop Shortcut**: Generate system `.desktop` file.
  - 📁 **Open Game Folder**: Open game directory in file manager / terminal (`spf` / `xdg-open`).
  - 🙈 **Hide / Ignore Game**: Soft-hide game from menu.
  - 🗑️ **Delete Launcher Entry**: Un-register game profile completely.
- **Attached Execution & Live Verbose Logs**: Games launch attached in the foreground, streaming engine logs and `stdout`/`stderr` outputs directly to your terminal. When the game finishes, session playtime is measured and logged to `.run_stats.json`.
- **Forced `SDL_VIDEODRIVER=x11` Compatibility**: Unconditionally exports `export SDL_VIDEODRIVER=x11` in all `start_game.sh` wrapper scripts to prevent Wayland window creation crashes (e.g. for games like *Hacknet*).
- **Real-Time Binary Inspector & Preview Panel**: Displays file size, architecture type, modification date, script peeks, and `⭐ Recommended` / `⚠️ Utility` status badges in a live `fzf` preview panel.
- **Quick-Launch Mode (`run <name>`)**: Pass a game name query to immediately fuzzy-match and launch the game without opening the full menu.
- **Desktop Entry Creator (`.desktop`)**: Optionally creates `.desktop` menu shortcuts in `~/.local/share/applications/` for Rofi, Dmenu, and application menus.
- **Hidden Registry (`.run_registry.json`)**: Prevents re-scanning already configured folders.

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
run hacknet

# Specify custom games directory
run --games-dir /path/to/custom/games
```

### ⌨️ Hotkeys in Menu
- **`ENTER`**: Launch selected game attached in foreground.
- **`TAB`**: Open item utilities sub-menu for selected game (Rename, Rate, Wine config, Change binary, etc.).
- **`ESC` / `Ctrl+C`**: Exit menu.
