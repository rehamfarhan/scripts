# 🚀 Rofi Entry Creator (`mkrofi.sh`)

Quickly generate standard-compliant desktop launcher configuration files (`.desktop`) to make custom commands and scripts searchable and launchable in Rofi, dmenu, or desktop application menus.

---

## 📋 Technical Overview

- **Language**: Bash (`#!/usr/bin/env bash`)
- **Dependencies**: `bash`, `coreutils`
- **System Location**: `mkrofi/mkrofi.sh`
- **Target Command**: `mkrofi`
- **Target Desktop Location**: `~/.local/share/applications/`

---

## ✨ Features

- **Guided Configuration**: Prompts interactively for Application Name, Command path/arguments, Description, Icon path or name, Terminal execution mode (`y/n`), and Categories.
- **Standards Compliant**: Generates compliant FreeDesktop `.desktop` files.
- **Auto-Registration**: Saves entries directly to `~/.local/share/applications/` and makes them executable for immediate menu indexing.

---

## 🚀 Setup & Installation

Link the script to `/usr/local/bin` using `scrlink`:

```bash
sudo ../scrlink/scrlink.sh mkrofi/mkrofi.sh mkrofi
# or using scrlink helper:
sudo scrlink mkrofi
```

---

## 📖 Usage

```bash
# Run interactive desktop entry generator
mkrofi
```

Follow the interactive prompts to create your `.desktop` launcher.
