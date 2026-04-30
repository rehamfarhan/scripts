# 🛠️ Custom Scripts Collection

A collection of utility scripts for various tasks, tracked with Git and linked system-wide for easy access.

## 📖 Table of Contents
- [🚀 Setup & Installation](#-setup--installation)
- [💰 Money Git CLI (money.py)](#-money-git-cli-moneypy)
- [📡 Morse Generator (morsegen.py)](#-morse-generator-morsegenpy)
- [🎮 Game Launcher (run.sh)](#-game-launcher-runsh)
- [📥 YouTube Downloader (yt.sh)](#-youtube-downloader-ytsh)
- [📊 Waybar Restarter (barr.sh)](#-waybar-restarter-barrsh)
- [🔗 Script Linker (scrlink.sh)](#-script-linker-scrlinksh)

---

## 🚀 Setup & Installation

These scripts are intended to be stored in `~/scripts` and linked to `/usr/local/bin` using the included `scrlink.sh` utility.

```bash
# Example: Link money.py to /usr/local/bin/money
./scrlink.sh money.py money
```

---

## 💰 Money Git CLI (`money.py`)

A **Git-inspired terminal app** to track your money with speed, clarity, and discipline.

### Features
- **Lightning-Fast**: Log transactions with shorthand like `money +500 Salary` or `money -90 Burger @cafe`.
- **Reservation System**: Mentally "lock" money for specific purposes (e.g., `money reserve 1200 Rent`).
- **Status Overview**: Check your total, reserved, and available balance with `money status`.
- **Search & Log**: View history with `money log` or search specific entries with `money search query`.
- **Undo/Delete**: Easily correct mistakes with `money undo` or `money delete <id>`.

### Usage
```bash
money init          # Initialize a new ledger
money +1000 Salary  # Record income
money -50 Coffee    # Record expense
money status        # Show balance summary
```

---

## 📡 Morse Generator (`morsegen.py`)

A flexible Morse code encoder and decoder.

### Features
- **Custom Symbols**: Define your own symbols for dots, dashes, and separators.
- **Bi-directional**: Easily switch between encoding text and decoding Morse.

### Usage
```bash
# Encode text
python3 morsegen.py encode "HELLO WORLD"

# Decode Morse
python3 morsegen.py decode ".... . .-.. .-.. --- / .-- --- .-. .-.. -.."

# Custom symbols
python3 morsegen.py encode "HELLO" --dot "." --dash "_" --separator "/"
```

---

## 🎮 Game Launcher (`run.sh`)

An interactive game launcher using `fzf`.

### Features
- **Interactive Menu**: Quickly find and launch games from your Games directory.
- **Ignore List**: Press `TAB` to add executables to a `.runignore` file.
- **Compatibility**: Includes fixes for Wayland/X11 environment variables.

### Usage
```bash
./run.sh [path/to/games]
```

---

## 📥 YouTube Downloader (`yt.sh`)

A convenient wrapper for `yt-dlp` with sensible defaults.

### Features
- **Fast Downloads**: Uses `aria2c` for multi-threaded downloads.
- **Format Presets**: Flags for 720p, 1080p, and "best" quality.
- **Audio Mode**: Extract MP3s directly with `--mp3`.
- **Subtitles**: Embed English subtitles with `--subs`.

### Usage
```bash
yt --mp3 <url>
yt --1080 --subs <url>
```

---

## 📊 Waybar Restarter (`barr.sh`)

A simple script to cleanly restart Waybar. Useful after configuration changes.

### Usage
```bash
./barr.sh
```

---

## 🔗 Script Linker (`scrlink.sh`)

Utility to symlink scripts from this repository to `/usr/local/bin`.

### Usage
```bash
sudo ./scrlink.sh <script_name> <target_name>
```

---

## 🛠️ Contribution & Maintenance

I use Git to track changes in this repository. All scripts are maintained for personal efficiency and system-wide accessibility.
