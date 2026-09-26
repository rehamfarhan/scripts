# `run` — TUI Game Launcher (Rust)

Fast, single-binary TUI game launcher/session tracker. Ratatui + Crossterm UI, SQLite storage, generates per-game `start_game.sh` wrapper scripts.

## Build, test, lint

- Build: `cargo build` (dev) / `cargo build --release` (what actually ships — see `run.sh`, which auto-builds and execs `target/release/run`)
- `run` on PATH is `~/.local/bin/run`, symlinked to `run.sh` (which execs the **release** binary; `~/.local/bin` is on PATH). Re-run `ln -sf /home/directpass/scripts/run/run.sh ~/.local/bin/run` if the symlink is broken. For a dev build during development use `cargo run` or `./target/debug/run` directly — don't repoint the symlink at the debug binary.
- Test: `cargo test` — unit tests live inline in `#[cfg(test)] mod tests` at the bottom of `db.rs`, `scanner.rs`, `ui/events.rs`. They use `tempfile` for isolated dirs/DBs — never write a test that touches the real `~/Games` or `~/.config`.
- Lint: `cargo clippy --all-targets -- -D warnings` before considering any change done.
- Single test: `cargo test <test_name>`
- No `cargo fmt` config is committed; match existing style rather than running a blanket reformat.

## Architecture

- `main.rs` — arg parsing + dispatch. Two modes: quick-launch (`run <query>`, fuzzy-matches against the DB and exits, no TUI) and full TUI (`ui::run_tui`).
- `config.rs` — path/env helpers only (games dir, desktop dir, username). No business logic.
- `model.rs` — serde structs for the **legacy JSON format** (`GameRegistry`/`GameStats`) plus shared formatting helpers (`format_playtime`, `format_last_played`, `format_star_rating`). These JSON structs are read only once, during migration — current storage is SQLite via `db.rs`.
- `db.rs` — SQLite storage (`~/Games/.run.db`). `GameRecord` is the live in-memory/DB record type (distinct from `model::GameEntry`, which is JSON-only). One `games` table, one `sessions` table.
  - **Soft delete**: `remove_game` sets `hidden = 1`, never deletes rows. `get_all_games` filters `hidden = 0`; `get_all_dir_keys` does not — deliberately, so the New Game Wizard doesn't re-prompt for a folder the user hid.
  - **`upsert_game` is a full-row overwrite on conflict**, including `rating`/`playtime_seconds`/`play_count`/`last_played`, and forces `hidden = 0`. Every call site MUST start from an existing loaded `GameRecord` (`.clone()` it, mutate only the field(s) being changed) — never construct a bare `GameRecord { .. }` literal to update an existing game, or its stats get silently wiped. Bare literals are only correct for genuinely new rows (see the New Game Wizard's add/ignore handlers in `ui/events.rs`).
  - Session stats update additively via `record_session` (`playtime_seconds = playtime_seconds + ?`), not `upsert_game` — keep it that way.
- `scanner.rs` — binary discovery/scoring (`evaluate_binary_score`; it's covered by tests, tune with care) and `start_game.sh` generation/patching.
  - Generated scripts have a **marker-delimited managed block** (`# >>> RUN-MANAGED:ENV ... <<<`). Settings changes patch only between the markers via `patch_env_block`; everything else, including user hand-edits, is preserved byte-for-byte. If markers are missing/duplicated/misordered, the patch is refused (`ScriptGenerationResult::SkippedCorruptMarkers`) and the file is left untouched — don't "fix" this by force-overwriting. `Ctrl+R` in the UI is the deliberate full-reset escape hatch for that case.
- `launcher.rs` — spawns the game (`start_game.sh`) attached to the terminal, times the session, calls `record_session`, then `recap::render_post_game_recap`.
- `recap.rs` — post-game recap screen, plain ANSI (not ratatui — renders _after_ the TUI alt-screen is already torn down). `fetch_online_quote()` makes blocking HTTP calls (1.5s timeout, two providers tried sequentially). Keep it non-fatal-on-failure (always falls back to a local quote) and don't silently grow the worst-case blocking time.
- `ui/app.rs` — `App` struct (all mutable UI state) and `ActiveModal` enum (one variant per modal, carrying that modal's own state). `all_games` is an in-memory cache loaded via `reload_games()`; it is NOT auto-refreshed after a DB write — every handler that mutates the DB must call `app.reload_games()` afterward.
- `ui/events.rs` — all key handling, one large `match` on `ActiveModal`. When adding a modal or an option to an existing modal, the number of "positions" in the key handler (the `% N` wrap, the `Home`/`End` targets) **must exactly match** the number of rows the corresponding `widgets/modals.rs` renderer actually draws — see "Known gotchas" below, this already drifted once.
- `ui/widgets/*.rs` — pure rendering, split by panel (`game_list`, `inspector`, `hotkeys`, `modals`). Should not mutate `App`.
- `ui/theme.rs` / `ui/layout.rs` — color/style constants and the fixed pane-splitting layout.

## Data model conventions

- Rating is **0–10** internally, end to end (DB column, `format_star_rating`, the rate modal's 11 options). Don't reintroduce a 0–5 scale — the legacy JSON migration already accounts for old 0–5 data by multiplying by 2.
- `WineOpts.sdl_driver` only has an effect for **Linux-native** games (exported as `SDL_VIDEODRIVER` in the generated script). For Windows games it's presentational only right now — Wine doesn't consume it.
- `WineOpts.win_ver` is a stored-but-unused field (see its doc comment in `model.rs`). Don't assume it does anything at runtime.

## Known gotchas (found during audit — check current state before assuming these are still open)

1. **Windows Execution Settings modal state/render mismatch** — **FIXED** (2026-09, commit `84eb759`): the handler now cycles 3 categories (0..=2) matching the 3 rendered rows; regression test `windows_exec_settings_cycles_three_rows_in_place`. If this ever regresses: the Windows handler in `ui/events.rs` and `render_exec_modal` in `ui/widgets/modals.rs` MUST agree on row count.
2. `main.rs` / `config.rs`: `--games-dir <path>` is resolved via `config::resolve_games_dir()`, which creates the requested path **before** canonicalizing — **FIXED** (2026-09, commit `9c846e8`). A not-yet-existing custom path is created, never silently replaced by the default. Keep it that way: `create_dir_all` before `canonicalize`.
3. `run <query>` (quick-launch) deliberately does **not** scan for unregistered folders — confirmed-intended behavior as of 2026-09 (the command is meant to stay instant). A freshly added game directory isn't quick-launchable until the TUI has been opened once (which runs the folder scan / onboarding wizard). Don't add a folder scan to the quick-launch path; document instead.
4. **Reset keybinding is `Ctrl+R` — don't change it.** It was originally `Shift+R`, then `KeyCode::Char('R')`, then a guarded `Char('r')+SHIFT` arm — all failed in real terminals because crossterm reports Shift inconsistently on letter keys (sometimes uppercase char, sometimes lowercase+modifier, sometimes no modifier at all). `Ctrl+R` in the `KeyModifiers::CONTROL` block is the only binding that worked reliably.
5. **Markers must always be emitted on fresh generation**, even when the env block content is empty (no keyd, no sdl_driver, no windows opts). A previous `if !env_block.is_empty()` guard skipped them, which silently broke all future patches (`SkippedCorruptMarkers`). The test `test_markers_present_even_with_empty_env_block` in `scanner.rs` guards this — don't reintroduce the guard.
6. **`App::new()` sets `is_searching = true`** (fuzzy search mode on startup). In tests, set `app.is_searching = false` before dispatching hotkey events via `handle_key_event`, or they get swallowed by the search-bar input handler (`KeyCode::Char(c)` at the top of the function pushes into `search_query` and returns early).
7. **`recap.rs` receives the raw 0–10 DB rating.** Display must handle the full 0–10 range — a previous implementation matched only `1..=5`, showing "Unrated" for anything ≥6. `format_star_rating()` in `model.rs` is the canonical formatter; keep labels consistent with it.

## Testing conventions

- Use `tempfile::tempdir()` for anything touching the filesystem or DB.
- `db.rs` tests use a monotonically-increasing `AtomicU64` counter plus the PID to build unique temp DB paths — reuse that helper rather than hardcoding paths, to keep parallel `cargo test` runs from colliding.
- Add a regression test alongside any bug fix, in the same file's existing `#[cfg(test)] mod tests` block.

## Things NOT to do

- Don't touch `run_py_legacy.py` — kept only as historical reference for the pre-Rust implementation, not part of the build. Same for `run.py.deprecated` (renamed from `run.py`): the launcher entry point is `run.sh`, and `~/.local/bin/run` symlinks to it.
- Don't add a new persisted JSON format; SQLite (`db.rs`) is the only current storage. `model::GameRegistry`/`GameStats` exist solely to deserialize old files during one-time migration.
- Don't reformat files wholesale; keep diffs scoped to the change being made.
