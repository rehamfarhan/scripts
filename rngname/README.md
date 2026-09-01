# 🎲 Random Picture Renamer (`rngname.py` / `rngname`)

A lightweight Python utility designed to rename wallpaper and picture files to randomized alphanumeric strings, preventing naming conflicts and cleaning up messy image directory filenames.

---

## 📋 Technical Overview

- **Language**: Python 3 (`#!/usr/bin/env python3`)
- **Dependencies**: None (Standard Library only: `argparse`, `random`, `pathlib`, `string`)
- **System Location**: `rngname/rngname.py`
- **Target Command / Shorthand**: `rngname`
- **Default Directory**: `~/Pictures/wallpapers`
- **Supported Formats**: `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, `.bmp`, `.avif`, `.svg`, `.heic`, `.jxl`, and more.

---

## ✨ Features

- **🛡️ Collision-Proof Renaming**: Pre-calculates unique randomized destination filenames and checks against both existing and planned names before renaming.
- **📁 Target Folder Flexibility**: Renames images in `~/Pictures/wallpapers` by default, or accepts any custom folder as an argument.
- **🔍 Dry-Run Simulation (`-n` / `--dry-run`)**: Preview proposed renames safely without modifying any files on disk.
- **📂 Recursive Scanning (`-r` / `--recursive`)**: Process nested subdirectories of images in a single pass.
- **📏 Customizable Length (`-l` / `--length`)**: Configure random string length (defaults to 12 characters).

---

## 🚀 Setup & Installation

Link the script to `/usr/local/bin` using `scrlink`:

```bash
sudo ../scrlink/scrlink.sh rngname/rngname.py rngname
# or using scrlink helper:
sudo scrlink rngname
```

---

## 📖 Usage Examples

```bash
# Rename images in default directory (~/Pictures/wallpapers)
rngname

# Rename images in a specific folder
rngname ~/Pictures/Screenshots
rngname /path/to/wallpapers

# Preview changes without modifying files (Dry Run)
rngname ~/Pictures/wallpapers --dry-run

# Recursively rename images including subfolders
rngname ~/Pictures/wallpapers -r

# Specify custom random string length (e.g. 16 characters)
rngname ~/Pictures/wallpapers -l 16
```
