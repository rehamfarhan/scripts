# cngtf

Changes the system font.

On a Linux desktop the font is set in several unrelated places: GTK, Qt, Xresources, KDE's config, rofi, waybar, kitty, foot, Hyprland's appearance file, and fontconfig. Changing the font properly means editing all of them and then refreshing the font cache. `cngtf` does that from one command, with an `fzf` picker for the installed fonts.

## What it does

- Lists installed fonts with `fc-list` (or takes a name as an argument).
- Validates the name loosely: an exact `fc-list` match is used if there is one, otherwise it proceeds with what you typed and warns.
- Writes the font to:
  - fontconfig
  - GNOME/GTK settings and `gtk-3.0`/`gtk-4.0` config
  - Qt config
  - `~/.Xresources` / xsettingsd
  - `kdeglobals`
  - rofi
  - waybar
  - kitty
  - foot
  - `~/.config/hypr/source/appearance.lua`
- Backs up each file it edits as `<file>.bak` before writing.
- Refreshes the font cache and signals waybar and xsettingsd. Missing apps are skipped quietly.

There's also an emoji mode (`-e`) that changes the fontconfig emoji preference instead of the UI font.

## Install

```bash
sudo ../scrlink/scrlink.sh cngtf/cngtf.py cngtf
# or
sudo scrlink cngtf
```

## Usage

```bash
cngtf                          # pick a font from the fzf list
cngtf "JetBrainsMono Nerd Font" --size 12
cngtf -e                       # pick an emoji font
cngtf -e "Noto Color Emoji"
```

| Option | Meaning |
| --- | --- |
| `--size N` | Font size for the configs that take one (default 11) |
| `-e`, `--emoji` | Change the emoji font instead |

## Notes

- Hyprland changes are written to `~/.config/hypr/source/appearance.lua`, which matches this repo's Hyprland setup. On a different config layout that step is skipped.
- Most applications pick up the change immediately; some need a restart. Waybar is signalled automatically.
- If a font name doesn't appear in `fc-list`, it's still applied. That's useful for fonts installed after the cache was built, but it will also accept a typo.

## Requirements

- Python 3
- `fontconfig` (`fc-list`, `fc-cache`)
- `fzf` for the interactive picker
- The relevant desktop apps installed; absent ones are ignored
