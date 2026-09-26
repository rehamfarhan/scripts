# `run` — Pre-Feature-Work Audit Findings

Audit date: 2026-09-26. State: all 15 tests pass; `cargo build` clean; the three
confirmed bugs (Execution Settings modal, `--games-dir` fallback, SDL-driver
labeling) are fixed with regression tests. Findings below are the open items
remaining before starting new feature work.

Status legend: `open` = not started · `in progress` = being worked · `done` = fixed.

---

## 1. Stale `start_game.sh` — binary & resolution changes silently no-op

- **Severity**: high (silent false-success on two daily-use features)
- **Files**: `src/scanner.rs` (`generate_frozen_lines`, `patch_env_block`,
  `create_launcher_script`), `src/ui/events.rs` (ChangeBinary Enter handler,
  Execution Settings cycle), `src/launcher.rs` (launch path)
- **Status**: **deferred** — flagged for later. User plans to replace Wine with a
  Proton fork, which will rewrite the launch-line logic anyway; re-assess then.

**Problem.** `create_launcher_script` only ever patches the managed env block on
existing scripts. The launch line (which embeds the binary path and, for wine,
the `/desktop=name,<res>` resolution) is generated only on *fresh* generation.

- `m` (Change Main Binary) → DB updated + "✓ Main binary set" toast, but the
  script keeps launching the **old binary**.
- Execution Settings resolution cycle → "✓ saved" toast, but the launch line
  keeps the **old resolution**.

Both only take real effect after a full `Ctrl+R` regeneration. The frozen-line
design was deliberate ("avoid re-opening the launch-line clobbering problem"),
but the UI claims success without doing anything.

**Candidate directions**
- A) Extend the marker system: wrap the launch line in its own managed block
  (`# >>> RUN-MANAGED:LAUNCH <<<`), patch binary + resolution through markers,
  preserve everything else, keep the corrupt-markers refusal + Ctrl+R escape
  hatch.
- B) Full regeneration whenever binary/resolution differ (destructive to any
  hand-edits outside the env block — same semantics as Ctrl+R).
- C) Keep the freeze, but detect the mismatch and warn "requires Ctrl+R" instead
  of toasting success (honesty fix, not a functional fix).

---

## 2. Ctrl+letter combos trigger bare hotkeys — Ctrl+X deletes the game

- **Severity**: high (destructive, no undo)
- **Files**: `src/ui/events.rs` (`handle_key_event` main dispatch), `src/ui/mod.rs`
  (raw mode enabled)
- **Status**: done (fixed in `ed3dc81`, regression-tested)

**Problem.** Raw mode is on and the main `match key.code` has no
`KeyModifiers::CONTROL` guard beyond a small intercept block
(`d/u/j/n/k/p/r`). Every other Ctrl+letter falls through to the bare hotkey:

- `Ctrl+X` → `Char('x')` arm → soft-deletes the selected game (no undo in UI)
- `Ctrl+C` → opens Execution Settings instead of quitting (no Ctrl+C exit path)
- `Ctrl+E/F/M/O/S` → edit script / toggle favorite / change binary / open folder / sort

**Candidate directions**
- A) Guard every bare-letter arm with `key.modifiers.is_empty()` (ctrl combos
  become no-ops or explicit handlers).
- B) Add a catch-all in the CONTROL block for the remaining letters (no-op) and
  map `Ctrl+C` to quit.
- C) Explicitly remap Ctrl+C to quit + guard only the destructive letters
  (x/d/m/e…).

---

## 3. Quick-launch never discovers new folders

- **Severity**: medium (confirmed-intended — quick-launch stays instant)
- **Files**: `src/main.rs` (quick-launch path), `src/ui/app.rs`
  (`check_unregistered_folders` only runs in `App::new`)
- **Status**: **wontfix** — confirmed-intended by maintainer (2026-09). Quick-launch
  is deliberately DB-only to stay instant; new folders are discovered on the next
  TUI launch. Documented in `AGENTS.md` (gotcha #3) and `README.md`
  (Quick-Launch Mode). Don't add a scan to the hot path.

**Problem.** `run <query>` fuzzy-matches only against the SQLite DB. A newly
added game folder is invisible to quick-launch until the TUI has been opened
once (which triggers the onboarding wizard / folder scan).

**Candidate directions**
- A) Confirm as intended, document it, leave as-is.
- B) Scan for unregistered folders in quick-launch too and bootstraps them
  (adopt the wizard's add/ignore semantics without the TUI).
- C) Add a `run scan` subcommand as a separate refresh entry point.

---

## 4. Clippy gate is red at baseline — 6 pre-existing errors

- **Severity**: medium (blocks the project's own "clippy clean" rule)
- **Files**: `src/model.rs` (81, 245, 249), `src/scanner.rs` (273),
  `src/ui/events.rs` (341), `src/ui/widgets/modals.rs` (440)
- **Status**: open

**Errors**
| Location | Clippy lint | Fix |
| :--- | :--- | :--- |
| `model.rs:81` | `derivable_impls` | derive `Default` on `GameStats` |
| `model.rs:245/249` | `single_char_pattern` | `push_str('🌟')` / `push('⬛')` |
| `scanner.rs:273` | `ptr_arg` | take `&[String]` instead of `&Vec<String>` |
| `events.rs:341` | `needless_sort_by` | `sort_by_key` with reverse |
| `modals.rs:440` | `too_many_arguments` | bundle wizard args into a struct |

---

## 5. Minor items (not blocking)

- `ChangeBinary` Enter handler ignores `ScriptGenerationResult::SkippedCorruptMarkers`
  → toasts success while the script stays corrupt.
- Inspector's `# CUSTOM_WRAPPER` content check is dead code — the marker is never
  emitted by the generator; `is_custom` relies solely on the DB flag.
- `launch_game_attached` records a session (play_count bump, 0s) even when the
  game crashes / fails to launch.
- `win_ver` stored-but-unused is documented and the UI now labels SDL-driver as
  inert under Wine — informational only, not a bug.