# 🛠️ Custom Scripts Collection

Welcome to my personal collection of custom utility scripts! This repository serves as a centralized hub for lightweight, terminal-centric tools built for system management, productivity, media handling, and entertainment on Linux/Wayland environments.

Each utility is organized into its own standalone directory containing the executable script and a dedicated `README.md`. When browsing this repository on GitHub or locally, clicking into any script folder displays the code alongside its full documentation.

---

## 🗂️ Script Directory Index

| Script / Folder | Command | Language | Description |
| :--- | :--- | :--- | :--- |
| [**`money/`**](money/) | `money` | Python 3 | Git-inspired terminal financial ledger with quick entry syntax, reservation system, and ASCII logging. |
| [**`mediafetch/`**](mediafetch/) | `mf` | Bash | High-speed multi-threaded media downloader wrapper around `yt-dlp` & `aria2c` with presets for video, music, and podcasts. |
| [**`run/`**](run/) | `run` | Bash | Interactive `fzf` launcher for native Linux games with `.runignore` management and automatic Wayland/X11 wrappers. |
| [**`ddlclauncher/`**](ddlclauncher/) | `ddlclauncher` | Bash | Interactive DDLC mod manager featuring thematic `fzf` UI, automatic scanner, launcher creator, and executable detection. |
| [**`morsegen/`**](morsegen/) | `morsegen` | Python 3 | Bi-directional Morse code encoder and decoder with custom symbol support and distinct character validation. |
| [**`rng/`**](rng/) | `rng` | Python 3 | Interactive terminal random number generator with bound inclusion/exclusion options, float precision, and live keypress rolling. |
| [**`mkrofi/`**](mkrofi/) | `mkrofi` | Bash | Interactive `.desktop` application entry creator to register custom terminal commands in Rofi / dmenu menus. |
| [**`barr/`**](barr/) | `barr` | Bash | Safe restarter script for Waybar to cleanly reload status bar configurations without disrupting desktop sessions. |
| [**`scrlink/`**](scrlink/) | `scrlink` | Bash | Intelligent helper tool to symlink scripts to `/usr/local/bin`, featuring `fzf` selection and automatic folder migration. |

---

## 🚀 Installation & System-Wide Setup

All scripts in this repository can be symlinked to `/usr/local/bin` using the included `scrlink` utility for system-wide execution.

```bash
# 1. Symlink scrlink itself first
sudo ./scrlink/scrlink.sh scrlink/scrlink.sh scrlink

# 2. Symlink any script interactively using fzf
scrlink

# 3. Or symlink a specific script directly:
scrlink money
scrlink mediafetch mf
```

---

## 🏗️ Repository Architecture & Workflow

To maintain clean and uncluttered documentation:

1. **Modular Directory Structure**: Every utility lives inside its own named subfolder (`<script_name>/`).
2. **Dedicated Documentation**: Each subfolder contains a standalone `README.md` detailing technical specifications, features, CLI references, and examples.
3. **Adding New Scripts**: Simply drop a new script (e.g. `myscript.py`) into the `scripts/` directory and run:
   ```bash
   scrlink myscript.py
   ```
   `scrlink` will automatically:
   - Create a standalone `myscript/` folder.
   - Move `myscript.py` into `myscript/myscript.py`.
   - Create a starter `README.md` in `myscript/`.
   - Register the `/usr/local/bin/myscript` symlink.

---

## ⚙️ Requirements & Dependencies

- **Shell**: Bash 4+
- **Python**: Python 3.8+
- **Core CLI Utilities**: `fzf`, `yt-dlp`, `aria2c`, `ffmpeg`, `waybar` (optional, for `barr`), `wine` (optional, for Windows DDLC mods).
