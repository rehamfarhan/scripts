# keydmgr

A helper for editing `keyd` bindings.

`keyd` config is simple once you know the syntax, but the day-to-day loop is annoying: remember the key names, get the syntax right, edit a root-owned file, reload the daemon, and hope you didn't break the layer you were editing. `keydmgr` wraps that loop in `fzf` menus and a few CLI commands.

It reads and writes `/etc/keyd/default.conf`, changing only the line or section you asked for and leaving the rest of the file, including comments, alone.

## What it does

- Pick keys from a searchable list instead of typing keyd codes.
- Accepts normal shortcut notation and translates it: `ctrl+c` becomes `C-c`, `super+shift+w` becomes `M-S-w`, `ctrl+alt+del` becomes `C-A-delete`.
- Understands aliases like `caps`, `ctrl`, `super`, `win`, `ret`, `esc`, `semi`, `quote`, `bs`, `del`, `space`.
- Inserts a binding under the right `[layer]` section, or updates it if it already exists.
- Keeps a backup in `~/.local/share/keyd/backups/` before writing.
- Reloads `keyd` with `sudo keyd reload` after a change.
- Can print the resulting config line instead of writing anything.

## Install

```bash
sudo ../scrlink/scrlink.sh keydmgr/keydmgr.py keydmgr
# or
sudo scrlink keydmgr
```

## Interactive use

```bash
keydmgr
```

The main menu has five options:

1. Bind or remap a key (layer, key, action).
2. Browse active bindings. Selecting one opens a submenu to edit, delete, inspect, or print it.
3. Inspect a key across all layers.
4. Live key sniffer (`keyd monitor`), useful for finding the code of a key you don't know.
5. Reload the daemon.

## CLI use

Print the line without writing:

```bash
keydmgr capslock "ctrl+c" -p
# capslock = C-c

keydmgr j down -l alt -p
# [alt]
# j = down
```

Write and reload:

```bash
keydmgr capslock "overload(meta, esc)" -l main
keydmgr j down -l alt
```

## Options

| Flag | Meaning |
| --- | --- |
| `-p`, `--print` | Print the config line, don't write. |
| `-l`, `--layer` | Layer to edit (default `main`). |
| `-c`, `--config` | Use a different config file. |

## Files

- Config: `/etc/keyd/default.conf`
- Backups: `~/.local/share/keyd/backups/`

## Requirements

- Python 3
- `keyd`, installed and running
- `fzf` for the menus
- `sudo` rights for writes and reloads
