# run

A game launcher for the terminal.

The problem it solves is mostly about the games that aren't in Steam: a folder in `~/Games`, maybe a Windows executable that needs a particular Wine prefix, maybe a broken Ctrl key that needs a remap for one game only, plus the question of how long you've actually played it. Doing that by hand means one shell script per game and no record of anything.

`run` keeps a library of those folders, generates a launcher script per game, and gives you one place to change the settings, rate the game and see the playtime.

## What it does

- Lists games from `~/Games` in a two-pane TUI: library on the left, details and actions on the right.
- Shows per-game playtime, session count, last played time, rating, executable, size, and the Wine/SDL settings currently in use.
- Runs games in the foreground and records the session length when they exit.
- Generates `start_game.sh` for each game. Settings written by `run` go inside marked blocks so manual edits elsewhere survive.
- Per-game settings: Wine prefix, virtual desktop resolution, DXVK HUD, SDL video driver, and the main executable.
- Optional `keyd` remapping before launch (for example, mapping left Shift to left Ctrl on a laptop with a dead key). Applied for the session and cleaned up afterwards.
- Quick launch: `run <query>` starts a matching game without opening the TUI.
- Creates a `.desktop` shortcut if you want the game in rofi or your app menu.

Quick launch only matches games already in the library. New folders in `~/Games` are picked up the next time the TUI is opened.

## Storage

Everything is kept in SQLite at `~/Games/.run.db`. The old `.run_registry.json` and `.run_stats.json` files are imported on first run and then renamed to `.bak`.

## Build and install

```bash
cargo build --release
ln -sf "$(pwd)/run.sh" ~/.local/bin/run
```

`run.sh` builds the binary if it's missing, then executes `target/release/run`.

## Usage

```bash
run          # open the library
run balatro  # quick launch
```

## Keybindings

| Key | Action |
| --- | --- |
| `Enter` | Launch the selected game |
| `r` | Rate (0–10) |
| `f` | Toggle favourite (pins to top) |
| `s` / `S` | Change sort field / direction |
| `i` | Toggle the actions panel |
| `p` | `keyd` keyboard patch |
| `c` | Execution and video driver settings |
| `e` | Edit the launcher script in `$EDITOR` |
| `d` | Create a `.desktop` shortcut |
| `o` | Open the game folder |
| `m` | Change the main executable |
| `n` | Rename the entry |
| `x` / `Delete` | Remove the entry (stats are kept) |
| `Ctrl+R` | Regenerate `start_game.sh` from scratch |
| `/` | Search |
| `q` / `Esc` | Quit |

## Requirements

- Rust and Cargo to build
- A terminal with Unicode support
- `wine` for Windows games
- `keyd` if you use keyboard patches
- `xdg-open` or `spf` for opening folders
