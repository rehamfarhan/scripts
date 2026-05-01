# GEMINI.md

## Project Overview
This repository is a curated collection of custom utility scripts used for system management, productivity, and entertainment. The scripts are primarily written in **Bash** and **Python** and are designed to be symlinked to `/usr/local/bin` for system-wide execution.

The project emphasizes terminal-centric workflows, speed, and minimal dependencies (primarily relying on common tools like `fzf`, `yt-dlp`, and `aria2c`).

## Building and Running

### Deployment
The primary way to "install" these scripts is by using the `scrlink.sh` utility, which creates a symlink in `/usr/local/bin`.

```bash
# General usage:
sudo ./scrlink.sh <script_file> <target_command_name>

# Examples:
sudo ./scrlink.sh money.py money
sudo ./scrlink.sh yt.sh yt
```

### Script-Specific Execution
- **Money Git CLI (`money.py`)**: Requires Python 3. Initialize with `money init`.
- **Morse Generator (`morsegen.py`)**: Requires Python 3.
- **Game Launcher (`run.sh`)**: Requires `fzf`. Run as `./run.sh`.
- **YouTube Downloader (`yt.sh`)**: Requires `yt-dlp` and optionally `aria2c`.
- **Waybar Restarter (`barr.sh`)**: Specific to Wayland/Waybar environments.

## Development Conventions

### Script Structure
- **Python**: Use `argparse` for command-line arguments and `main()` entry points. Maintain the `MoneyStore` patterns for any new local-storage utilities.
- **Bash**: Use `set -euo pipefail` where applicable for robustness. Ensure scripts are standalone and do not rely on external shell functions unless sourced.
- **Shebangs**: Always include proper shebangs (e.g., `#!/usr/bin/env python3` or `#!/usr/bin/env bash`).

### Documentation
- Every new script must be added to the `README.md` with its features and usage examples.
- Use emojis in headings within `README.md` to maintain the existing visual style.

### Git Workflow
- Changes should be committed with clear, descriptive messages.
- New scripts should be made executable (`chmod +x`) before being committed or linked.
