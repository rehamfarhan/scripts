# 🎮 Game Launcher (`run`)

A blazing-fast, nerdy-cool TUI game launcher, telemetry inspector, and session tracker rewritten natively in **Rust** using **Ratatui** and **Crossterm**.

---

## 📋 Technical Overview

- **Language**: Rust (Edition 2021)
- **Framework**: [Ratatui](https://github.com/ratatui/ratatui) 0.30 + [Crossterm](https://github.com/crossterm-rs/crossterm) 0.29
- **Startup Latency**: <2 ms (compiled native ELF binary)
- **Target Command**: `run`
- **Storage**: SQLite at `~/Games/.run.db` (legacy `~/Games/.run_registry.json` and `.run_stats.json` are auto-migrated on first run, then renamed to `.bak`)

---

## ✨ Features

- **Dual-Pane Cyber-Dashboard**:
  - **Left Pane (Library)**: Clean, focused game list with platform icons (`🐧`/`💻`), titles, and real-time fuzzy search filtering (`/`).
  - **Right Top Pane (Telemetry & Specs Inspector)**: Showcases star ratings (`⭐⭐⭐⭐⬛ (8/10 • Great)`), cumulative playtime (`14.2h`), total session count (`Session #7`), last played timestamp (`2h ago`), game folder, executable path, file size, Wine/SDL drivers, and active `keyd` keyboard patch.
  - **Right Bottom Pane (Quick Actions & Hotkeys)**: Full keybinding cheatsheet and tips ticker.
- **In-Place Modal Dialogs**: No screen flickering or nested sub-shells. In-terminal modals for:
  - ⭐ **Rate Game**: 0 to 10 star rating selector (0 = Unrated).
  - ⌨️ **Keyboard Patches (keyd)**: Zero-sudo runtime key remapping (e.g. Left Shift -> Left Ctrl for broken Ctrl keys) with automatic cleanup traps on exit.
  - ⚙️ **Execution Settings**: Custom Wine prefix, Virtual Desktop resolution, DXVK Vulkan HUD, and SDL video driver overrides.
  - 🛠️ **Change Main Binary**: Heuristic binary scanner with recommended badges (`⭐ Recommended Main Binary`).
  - ✏️ **Rename Game**: Inline text editing with wrapper updates.
  - 🧙 **New Games Onboarding Wizard**: Multi-step guided walkthrough for newly added game directories in `~/Games`.
- **Zero-Sudo Keyboard Patches (`keyd`)**:
  - Automatically executes `keyd bind` in-memory before launching.
  - Injects cleanup traps in `start_game.sh` and launcher safety fallbacks so default keyboard bindings are always restored on exit.
- **Attached Process Execution & Session Tracking**:
  - Clean terminal handoff: streams game stdout/stderr directly to terminal.
  - Wall-clock session duration tracking saved automatically to `.run.db`.
- **Centered Post-Game Session Recap Screen**:
  - Color-coded recap card with rounded borders, sparkles (`✨`), duration, total playtime, rating, session end date, platform, and online stoic/gaming quotes (fetched with a short timeout and offline fallback).
- **Launcher Script Generation**:
  - `start_game.sh` is generated with a marked env section (between `RUN-MANAGED:ENV` comment markers) that settings changes patch in-place. Manual edits outside that section are preserved across patches. `Ctrl+R` is the full-reset escape hatch — it regenerates the script from scratch, discarding all manual edits.
- **Quick-Launch Mode (`run <query>`)**:
  - Instant direct launch (<5ms) without opening the TUI dashboard:
    ```bash
    run balatro
    run rerun
    ```

---

## 🚀 Building & Installation

Compile the release binary:

```bash
cargo build --release
```

Link the executable using `scrlink` or symlink directly:

```bash
ln -sf "$(pwd)/target/debug/run" ~/.local/bin/run
```

---

## ⌨️ Keybindings

| Key | Action |
| :--- | :--- |
| `Enter` | Launch selected game in foreground |
| `r` | Rate game (0 - 10 Stars modal) |
| `f` | Toggle favorite (pin to top) |
| `s` / `S` | Cycle sort field / toggle ascending-descending |
| `i` | Toggle the quick-actions panel |
| `p` / `P` | Keyboard Patch (keyd remap modal) |
| `c` | Execution & Video Driver settings |
| `e` | Edit launcher wrapper script in `$EDITOR` |
| `d` | Create system `.desktop` application shortcut |
| `o` | Open game directory in file manager (`spf` / `xdg-open`) |
| `m` | Change main executable binary |
| `n` | Rename game entry |
| `x` / `Delete` | Remove launcher entry (preserves playtime stats) |
| `Ctrl+R` | Reset launcher script (regenerates start_game.sh, with confirmation) |
| `/` | Focus real-time search filter |
| `q` / `Esc` | Quit |
