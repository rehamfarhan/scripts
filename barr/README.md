# barr

Restarts waybar.

Waybar doesn't always pick up changes to its config or style file, and killing it by hand can leave you with no bar at all if the restart fails. This script kills the running instance and starts a fresh one in one step, which is what you usually want after editing the bar's config.

## What it does

```bash
pkill waybar
hyprctl dispatch 'hl.dsp.exec_cmd("/home/directpass/user_scripts/waybar/waybar_toggle.sh --on")'
```

`pkill` stops any running waybar, then Hyprland runs the waybar toggle script with `--on`. The toggle script handles starting the bar.

The path to `waybar_toggle.sh` is hardcoded. If you move that script, edit `barr.sh` to match.

## Install

```bash
sudo ../scrlink/scrlink.sh barr/barr.sh barr
# or
sudo scrlink barr
```

## Usage

```bash
barr
```

No output on success. Run it after editing `~/.config/waybar/config` or `style.css`.

## Requirements

- Hyprland (uses `hyprctl`)
- `pgrep`/`pkill` from procps
- waybar, plus the `waybar_toggle.sh` script referenced above
