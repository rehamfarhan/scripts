# 🎮 Game Launcher (`run.sh`)

An interactive game launcher utilizing `fzf` to browse, launch, and manage native Linux games with automatic Wayland compatibility wrapper detection and ignore lists.

---

## 📋 Technical Overview

- **Language**: Bash (`#!/usr/bin/env bash`)
- **Dependencies**: `fzf`, `coreutils` (`setsid`, `realpath`)
- **System Location**: `run/run.sh`
- **Target Command**: `run`

---

## ✨ Features

- **Interactive Search Menu**: Browse and launch games inside your `~/Games` directory (or a custom path).
- **Ignore List Support (`.runignore`)**: Press `TAB` on any item in the `fzf` menu to append it to `.runignore` and instantly hide it from future listings.
- **Automatic Wayland / X11 Compatibility Wrappers**:
  - Scripts containing `# ICON: 💻` run natively as `./executable`.
  - Standard native executables run with forced X11 driver mode (`env SDL_VIDEODRIVER=x11`) to prevent Wayland SDL initialization glitches.
- **Detached Execution**: Launches games via `setsid` in the background, closing the terminal cleanly without killing the game.

---

## 🚀 Setup & Installation

Link the script to `/usr/local/bin` using `scrlink`:

```bash
sudo ../scrlink/scrlink.sh run/run.sh run
# or using scrlink helper:
sudo scrlink run
```

---

## 📖 Usage Examples

```bash
# Launch interactive menu using default directory (~/Games)
./run.sh
# or if symlinked:
run

# Specify a custom games directory
run /path/to/my/games
```

### Hotkeys in Menu
- **`ENTER`**: Launch selected game.
- **`TAB`**: Add game to ignore list (`.runignore`) and dynamically remove it from menu.
- **`ESC` / `Ctrl+C`**: Exit menu.
