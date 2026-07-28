# 📡 Morse Generator (`morsegen.py`)

A flexible, bi-directional Morse code encoder and decoder supporting custom symbols, distinct character validation, and clean CLI flags/subcommands.

---

## 📋 Technical Overview

- **Language**: Python 3
- **Dependencies**: Python standard library (`argparse`, `sys`)
- **System Location**: `morsegen/morsegen.py`
- **Target Command**: `morsegen`

---

## ✨ Features

- **Subcommand & Flag Modes**: Use either descriptive subcommands (`encode`, `decode`) or quick flags (`-e`, `-d`).
- **Bi-directional**: Easily convert plain text to Morse code or decode Morse code back to text.
- **Custom Symbols**: Configure custom characters for dots, dashes, and word separators.
- **Distinct Characters Validation**: Ensures the dot, dash, and separator symbols are distinct and do not overlap.

---

## 🚀 Setup & Installation

Link the script to `/usr/local/bin` using `scrlink`:

```bash
sudo ../scrlink/scrlink.sh morsegen/morsegen.py morsegen
# or using scrlink helper:
sudo scrlink morsegen
```

---

## 📖 Usage Examples

```bash
# Encode text using subcommand
python3 morsegen.py encode "HELLO WORLD"

# Decode Morse code using flags
python3 morsegen.py -d ".... . .-.. .-.. --- / .-- --- .-. .-.. -.."

# Encode text using custom symbols (dot: '.', dash: '_', sep: '/')
python3 morsegen.py encode "HELLO" --dot "." --dash "_" --sep "/"
```
