# 🎲 Random Number Generator (`rng.py`)

An interactive terminal-based random number generator supporting custom bounds, precision control, inclusion/exclusion rules, and single-keypress rolling with ANSI terminal formatting.

---

## 📋 Technical Overview

- **Language**: Python 3
- **Dependencies**: Python standard library (`random`, `sys`, `tty`, `termios`)
- **System Location**: `rng/rng.py`
- **Target Command**: `rng`

---

## ✨ Features

- **Flexible Bounds**: Prompts for lower and upper limits, automatically swapping them if entered in reverse.
- **Inclusion Modes**: Choose between inclusive (include limits) or exclusive (exclude limits) generation.
- **Number Types**: Supports both whole numbers (integers) and floating-point decimal numbers with configurable decimal precision (0-10 places).
- **Single Keypress Rolling**: Configures limits once, then rolls new numbers instantly on any keypress using raw terminal input mode.
- **Clean Terminal UI**: Utilizes carriage returns (`\r`) to overwrite the active line, maintaining a clean, un-cluttered terminal view.

---

## 🚀 Setup & Installation

Link the script to `/usr/local/bin` using `scrlink`:

```bash
sudo ../scrlink/scrlink.sh rng/rng.py rng
# or using scrlink helper:
sudo scrlink rng
```

---

## 📖 Usage

### 1. Interactive Setup Mode (Wizard)
Run without arguments to configure via step-by-step prompts:
```bash
python3 rng.py
# or if symlinked:
rng
```

#### Steps:
1. Enter lower and upper limits.
2. Select inclusion mode (`1` for Inclusive, `2` for Exclusive).
3. Select number type (`1` for Whole numbers, `2` for Decimals).
4. (If Decimal selected) Enter desired decimal precision (1-10).
5. Generator starts — press **ANY KEY** (e.g. `Enter` or `Space`) to roll new numbers in place.
6. Press `q`, `Q`, or `Ctrl+C` to quit cleanly.

---

### 2. Direct CLI Mode (Skip Setup Prompts)
Pass arguments on the command line to skip all prompts and launch directly into the live generator loop:
```bash
rng <lower-limit> <upper-limit> [inclusion] [type] [decimals]
```

#### Arguments & Options:
| Parameter | Required / Default | Description |
| :--- | :--- | :--- |
| `<lower-limit>` | **Required** | Lower numeric boundary |
| `<upper-limit>` | **Required** | Upper numeric boundary |
| `[inclusion]` | Optional (default: `1`) | `1` = Inclusive `[min, max]`, `2` = Exclusive `(min, max)` |
| `[type]` | Optional (default: `1`) | `1` = Whole numbers (Integers), `2` = Decimals (Floats) |
| `[decimals]` | Optional (default: `2`) | Decimal precision (when `type` = `2`) |

#### Examples:
```bash
# Roll integers between 1 and 4 on every keypress
rng 1 4

# Roll exclusive integers between 1 and 10 (returns 2 to 9)
rng 1 10 2 1

# Roll decimals with default 2 decimal places (e.g. 6.38)
rng 1 10 1 2

# Roll decimals with 4 decimal places (e.g. 8.9202)
rng 1 10 1 2 4
```
