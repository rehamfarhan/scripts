# 🔗 Script Linker (`scrlink.sh`)

An intelligent helper script to package, organize, and symlink repository scripts into `/usr/local/bin` for system-wide CLI access. Supports interactive `fzf` selection and automatic folder migration.

---

## 📋 Technical Overview

- **Language**: Bash (`#!/usr/bin/env bash`)
- **Dependencies**: `bash`, `coreutils`, `fzf` (optional for interactive selection), `git` (optional for version control migration)
- **System Location**: `scrlink/scrlink.sh`
- **Target Command**: `scrlink`

---

## ✨ Features

- **Interactive `fzf` Selection**: Run `scrlink` with no arguments to launch an interactive menu for browsing and selecting any script in the repository.
- **Automatic Subfolder Migration**: When a new script is dropped directly into the `scripts/` root (e.g. `myscript.py`), running `scrlink myscript.py` automatically:
  1. Creates a standalone folder (`myscript/`).
  2. Moves `myscript.py` into `myscript/myscript.py` (via `git mv`).
  3. Generates a starter `README.md` in `myscript/` if one doesn't exist yet.
  4. Registers the symlink in `/usr/local/bin/myscript`.
- **Smart Target Defaults**: Automatically defaults target command name to the script's basename without extension if omitted (e.g., `money.py` $\rightarrow$ `money`).
- **Flexible Path Resolution**: Resolves paths whether specified by relative script path (`money/money.py`), bare filename (`money.py`), or directory name (`money`).

---

## 🚀 Setup & Installation

Symlink `scrlink` itself to `/usr/local/bin`:

```bash
sudo ./scrlink/scrlink.sh scrlink/scrlink.sh scrlink
```

---

## 📖 Usage Examples

```bash
# Launch interactive menu to select a script using fzf
scrlink

# Link a script by filename (auto-migrates to folder if in root)
scrlink money.py

# Link a script by subfolder path and specify target command name
scrlink money/money.py money

# Link using directory name
scrlink ytvideo
```
