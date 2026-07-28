# 🛠️ Custom Scripts Collection

A curated collection of custom utility scripts used for system management, productivity, and entertainment, tracked with Git and symlinked system-wide for easy access.

## 📖 Table of Contents
- [🚀 Setup & Installation](#-setup--installation)
- [💰 Money Git CLI (money.py)](#-money-git-cli-moneypy)
- [📡 Morse Generator (morsegen.py)](#-morse-generator-morsegenpy)
- [🎮 Game Launcher (run.sh)](#-game-launcher-runsh)
- [💔 DDLC Mod Launcher (ddlclauncher.sh)](#-ddlc-mod-launcher-ddlclaunchersh)
- [📥 YouTube Downloader (ytvideo.sh)](#-youtube-downloader-ytvideosh)
- [📊 Waybar Restarter (barr.sh)](#-waybar-restarter-barrsh)
- [🚀 Rofi Entry Creator (mkrofi.sh)](#-rofi-entry-creator-mkrofish)
- [🎲 Random Number Generator (rng.py)](#-random-number-generator-rngpy)
- [🔗 Script Linker (scrlink.sh)](#-script-linker-scrlinksh)

---

## 🚀 Setup & Installation

These scripts are intended to be stored locally and symlinked to `/usr/local/bin` using the included `scrlink.sh` utility for system-wide execution.

```bash
# Example: Link money.py to /usr/local/bin/money
sudo ./scrlink.sh money.py money
```

---

## 💰 Money Git CLI (`money.py`)

A **Git-inspired terminal ledger** to track your finances with speed, clarity, and discipline. It stores data locally in a hidden `.moneygit/` folder.

### Features
- **Shorthand Quick Entry**: Record transactions instantly with syntax like `money +500 Salary` or `money -90 Burger @cafe` (use `@` to separate optional notes from the source).
- **Reservation System**: Mentally lock/reserve funds (e.g., for rent, bills) to see your actual available balance.
- **Detailed Log**: View complete transaction history in a cleanly formatted ASCII table.
- **Search & Filter**: Search transactions by source, action, timestamp, or notes.
- **Undo & Delete**: Quickly remove the last transaction using `undo` or delete specific transactions via ID prefixes.

### Command Reference
```bash
money init                                     # Initialize a new ledger in the current directory
money status                                   # View total, reserved, and available balance
money balance                                  # Print current total balance value only
money log                                      # Display history of all transactions
money commit --source <src> --action <act> ... # Record transaction with specific flags
money commit "<source>, <action>, <amount>"    # Record transaction with legacy comma-separated text
money reserve <amount> <identifier>            # Lock funds under a specific label
money reserves                                 # List all active reservations
money settle <identifier>                      # Settle a reservation (converts to spend transaction)
money delete <id_prefix>                       # Delete transaction matching ID prefix
money undo                                     # Remove the last recorded transaction
money search <query>                           # Search ledger history
money config --currency <USD/BDT/etc>          # Configure display currency
```

### Quick Entry Usage Examples
```bash
money +1500 Freelance Pay       # Records BDT 1500 income
money -25 Coffee @coffeebar     # Records BDT 25 expense with note "coffeebar"
money reserve 1200 Rent         # Reserves BDT 1200 for Rent
money settle Rent               # Settles the reserve and logs BDT 1200 expense
```

---

## 📡 Morse Generator (`morsegen.py`)

A flexible, bi-directional Morse code encoder and decoder supporting custom symbols and distinct characters validation.

### Features
- **Subcommand & Flag Modes**: Use either descriptive subcommands or quick flags.
- **Bi-directional**: Easily convert plain text to Morse code or decode Morse code back to text.
- **Custom Symbols**: Configure custom characters for dots, dashes, and separators.
- **Distinct Characters Validation**: Ensures the dot, dash, and separator symbols are distinct and do not overlap.

### Usage
```bash
# Encode text (using subcommand)
python3 morsegen.py encode "HELLO WORLD"

# Decode Morse code (using flags)
python3 morsegen.py -d ".... . .-.. .-.. --- / .-- --- .-. .-.. -.."

# Encode text using custom symbols
python3 morsegen.py encode "HELLO" --dot "." --dash "_" --sep "/"
```

---

## 🎮 Game Launcher (`run.sh`)

An interactive game launcher utilizing `fzf` to browse, launch, and manage native games.

### Features
- **Interactive Search Menu**: Quickly browse and launch games inside your Games directory.
- **Ignore list support**: Press `TAB` to add any executable to a local `.runignore` file, hiding it from future launcher lists.
- **Automatic Compat/Wayland Fixes**: Detects if game requires custom wrappers. If a script starts with `# ICON: 💻`, it runs directly; otherwise, it forces X11 mode (`SDL_VIDEODRIVER=x11`) to ensure game engine compatibility on Wayland.

### Usage
```bash
# Launch interactive menu (defaults to ~/Games)
./run.sh

# Specifying custom games directory
./run.sh /path/to/my/games
```

---

## 💔 DDLC Mod Launcher (`ddlclauncher.sh`)

A thematic interactive manager for Doki Doki Literature Club mods, offering easy launcher creation and execution.

### Features
- **Mod Directory Scanning**: Automatically scans `~/DDLC Mods` for directories and identifies executable entry points (`.sh`, `.py`, `.exe` via Wine).
- **Auto-Generated Launchers**: Walks you through creating a permanent launcher config stored under `.launchers/`.
- **Polish UI**: Uses `fzf` with randomized thematic emojis (💔, 🩸, 🧠, 🌸, etc.) matching the DDLC aesthetic.
- **Mod Management**: Press `TAB` within the selection menu to instantly delete a mod launcher configuration.

### Usage
```bash
# Run scanning & interactive mod selection menu
./ddlclauncher.sh
```

---

## 📥 YouTube Downloader (`ytvideo.sh`)

A robust, high-performance wrapper for `yt-dlp` configured with sensible defaults and multi-threaded downloading.

### Features
- **High-Speed Downloads**: Uses `aria2c` under the hood with 8 split connections for maximum bandwidth usage.
- **Smart Profiles**:
  - `video` (Default): Downloads 1080p H.265 MKV video, embeds the PNG thumbnail, and merges English subtitles.
  - `music`: Extracts high-quality MP3 (quality level 0), crops album artwork to a square format, and embeds full metadata.
  - `podcast`: Extracts audio-only Opus format, embeds metadata and thumbnail.
  - `archive`: Downloads the maximum quality available and embeds all subtitles.
- **Format Selection Helper**: Use the `--list` command to quickly inspect all available formats for a video.
- **Duplicate Prevention**: Maintains a download archive at `~/.cache/ytvideo/archive.txt` to skip already-downloaded videos.

### Usage
```bash
# Download a video in 1080p (default video profile)
./ytvideo.sh "https://www.youtube.com/watch?v=..."

# Download high-quality audio / music
./ytvideo.sh music "https://www.youtube.com/watch?v=..."

# Download podcast (Opus audio format)
./ytvideo.sh podcast "https://www.youtube.com/watch?v=..."

# Download maximum quality video with all subtitles
./ytvideo.sh archive "https://www.youtube.com/watch?v=..."

# List formats only
./ytvideo.sh --list "https://www.youtube.com/watch?v=..."
```

---

## 📊 Waybar Restarter (`barr.sh`)

A simple helper script to cleanly terminate and restart Waybar. Ideal for applying Wayland configuration changes.

### Usage
```bash
./barr.sh
```

---

## 🚀 Rofi Entry Creator (`mkrofi.sh`)

Quickly generate compliant desktop launcher configuration files (`.desktop`) to make custom terminal commands searchable in application menus.

### Features
- **Guided Configuration**: Prompts you for App Name, command paths, icon choices, categories, and terminal execution preference.
- **Standard Compliant**: Automatically registers the entry in `~/.local/share/applications/` and marks it executable.

### Usage
```bash
./mkrofi.sh
```

---

## 🔗 Script Linker (`scrlink.sh`)

Utility tool to easily symlink any script in this collection to `/usr/local/bin` for system-wide command access.

### Usage
```bash
sudo ./scrlink.sh <script_file> <target_command_name>

# Example: Link ytvideo.sh as 'ytvideo'
sudo ./scrlink.sh ytvideo.sh ytvideo
```

---

## 🎲 Random Number Generator (`rng.py`)

An interactive terminal-based random number generator with custom bounds, precision, and inclusion/exclusion settings.

### Features
- **Flexible Bounds**: Prompts for lower and upper limits, automatically swapping them if entered in reverse order.
- **Inclusion Settings**: Choose between including (inclusive) or excluding (exclusive) the specified bounds.
- **Number Types**: Generates either whole numbers (integers) or decimal numbers (floats) with configurable decimal places (0-10).
- **Interactive Rolling**: Configures limits once, then rolls new numbers on any keypress.
- **Clean Interface**: Utilizes carriage returns to overwrite the same line, maintaining a clean and minimalist terminal view.
- **Cross-Platform Support**: Uses raw terminal manipulation to detect keypresses on Unix/Linux systems with a fallback for Windows systems.

### Usage
Run the script using Python:
```bash
python3 rng.py
```

Follow the interactive prompts:
1. Enter the lower and upper limits.
2. Select the inclusion mode:
   - `1` (Inclusive - default)
   - `2` (Exclusive)
3. Select the number type:
   - `1` (Whole numbers - default)
   - `2` (Decimals)
4. (If Decimal chosen) Enter the desired decimal places (1-10).
5. Press any key to roll a new random number, or press `q`, `Q`, or `Ctrl+C` to cleanly exit.

---

## 🛠️ Contribution & Maintenance

All scripts are tracked via Git. They are maintained to optimize personal productivity, system workflows, and terminal-centric gaming environments.
