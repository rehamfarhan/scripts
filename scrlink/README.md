# scrlink

Links scripts into `/usr/local/bin` and keeps them in folders.

Running `~/scripts/money/money.py` from anywhere means typing the path or setting up aliases. `scrlink` makes a symlink in `/usr/local/bin` instead, so the command is just `money` and the file stays in the repo where it can be edited and versioned.

It also handles the case where a new script was dropped into the repo root: it moves it into its own folder and creates a starter README.

## What it does

- With no arguments, opens an `fzf` list of scripts in the repo.
- Resolves the script whether you give a path (`money/money.py`), a bare filename (`money.py`), or a folder name (`money`).
- Uses the filename without its extension as the command name unless you pass one.
- For a loose script in the root, creates `<name>/`, moves the file in (with `git mv` if it's tracked), writes a starter `README.md`, then links it.
- If the move fails, warns and links the script where it currently is.

## Install

```bash
sudo ./scrlink/scrlink.sh scrlink/scrlink.sh scrlink
```

## Usage

```bash
scrlink                          # fzf menu
scrlink money.py                 # link, moving it into money/ first
scrlink money/money.py money     # explicit source and command name
scrlink ytvideo                  # folder name
scrlink mediafetch mf            # give mediafetch the name mf
```

## Changing or removing a link

The symlinks live in `/usr/local/bin` and point back into this repo. Re-run `scrlink` after moving a file; remove a command with `sudo rm /usr/local/bin/<name>`.

## Requirements

- Bash
- `fzf` for the interactive menu (optional if you always pass arguments)
- `git` for `git mv` (optional)
- write access to `/usr/local/bin`, usually through `sudo`
