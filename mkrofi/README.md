# mkrofi

Creates `.desktop` entries for commands and scripts.

A script in your home directory isn't visible to rofi, dmenu or the app menu until there's a `.desktop` file for it, and writing one by hand means remembering the format, the icon name and the right directory. `mkrofi` asks a few questions and writes the file for you.

## What it does

Prompts for:

- application name
- command, with arguments
- description
- icon (path or theme icon name)
- whether it should open in a terminal
- categories

Then writes a standard FreeDesktop entry to `~/.local/share/applications/` and makes it executable, so launchers pick it up on their next index.

## Install

```bash
sudo ../scrlink/scrlink.sh mkrofi/mkrofi.sh mkrofi
# or
sudo scrlink mkrofi
```

## Usage

```bash
mkrofi
```

Answer the prompts. The new entry appears in rofi/dmenu once the launcher refreshes; if it doesn't show up immediately, reopen the launcher or log out and back in.

## Requirements

Bash and coreutils. Nothing else.
