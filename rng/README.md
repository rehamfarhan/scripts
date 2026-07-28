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

Run the generator:
```bash
python3 rng.py
# or if symlinked:
rng
```

### Interactive Steps:
1. Enter the lower and upper limits.
2. Select inclusion mode:
   - `1` (Inclusive - default)
   - `2` (Exclusive)
3. Select number type:
   - `1` (Whole numbers / Integers)
   - `2` (Decimals / Floats)
4. (If Decimal selected) Enter desired decimal precision (1-10).
5. Press **ANY KEY** to roll a new random number.
6. Press `q`, `Q`, or `Ctrl+C` to quit cleanly.
