# rng

An interactive random number generator for the terminal.

Sometimes you need a random number and don't want to open Python, a website, or remember `shuf` syntax. This asks for the range once, then rolls a new number every time you press a key, without redrawing the whole screen or scrolling your terminal.

## What it does

- Takes a lower and upper bound, swapping them if entered backwards.
- Inclusive or exclusive bounds.
- Integers or decimals, with 0–10 decimal places.
- After setup, any keypress rolls again in place (raw terminal mode, carriage return overwrite).
- `q` or `Ctrl+C` quits and restores the terminal.

## Install

```bash
sudo ../scrlink/scrlink.sh rng/rng.py rng
# or
sudo scrlink rng
```

## Usage

Run it bare and answer the prompts:

```bash
rng
```

Or pass everything on the command line to skip the prompts:

```bash
rng <lower> <upper> [inclusion] [type] [decimals]
```

| Argument | Default | Meaning |
| --- | --- | --- |
| `lower` | required | Lower bound |
| `upper` | required | Upper bound |
| `inclusion` | `1` | `1` inclusive `[min, max]`, `2` exclusive `(min, max)` |
| `type` | `1` | `1` integers, `2` decimals |
| `decimals` | `2` | Decimal places when `type` is `2` |

Examples:

```bash
rng 1 4          # integers 1-4
rng 1 10 2 1     # exclusive: 2-9
rng 1 10 1 2     # decimals, 2 places
rng 1 10 1 2 4   # decimals, 4 places
```

## Requirements

Python 3, plus a POSIX terminal (it uses `termios` and `tty`).
