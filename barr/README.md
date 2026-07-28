# 📊 Waybar Restarter (`barr.sh`)

A simple helper script to cleanly terminate and restart Waybar. Ideal for applying Wayland / Hyprland / Sway status bar configuration changes without restarting your session.

---

## 📋 Technical Overview

- **Language**: Bash (`#!/usr/bin/env bash`)
- **Dependencies**: `waybar`, `killall`, `pgrep`
- **System Location**: `barr/barr.sh`
- **Target Command**: `barr`

---

## ✨ Features

- **Clean Process Termination**: Kills active `waybar` instances safely.
- **Process Loop Guard**: Waits until all instances are fully shut down before restarting.
- **Background Relaunch**: Launches a fresh `waybar` instance in the background.

---

## 🚀 Setup & Installation

Link the script to `/usr/local/bin` using `scrlink`:

```bash
sudo ../scrlink/scrlink.sh barr/barr.sh barr
# or using scrlink helper:
sudo scrlink barr
```

---

## 📖 Usage

```bash
# Restart Waybar status bar
barr
```
