# ⌨️ `keydmgr` — Streamlined `fzf` Keyd Configurator

`keydmgr` is a fast, terminal-centric remapping manager and configurator for [keyd](https://github.com/rvaiya/keyd). Built around interactive `fzf` popup menus, it lets you modify, browse, edit, and create key remappings without memorizing keyd codes or manually opening raw config files.

---

## ✨ Features

- **Interactive `fzf` UI**:
  - Main menu, layer selection, searchable key picker, target action builder, and binding submenus all rendered in rounded `fzf` frames.
- **Active Bindings Submenu**:
  - Browse your active bindings in `fzf` and press **Enter** on any mapping to open its context menu:
    - ✏️ **Edit / Change Action** (rebind on the fly)
    - 🗑️ **Delete / Remove Binding** (safely unbind key)
    - 🔍 **Inspect Key** (check all layers)
    - 📋 **Print Line** (stdout formatted syntax)
- **Smart Key & Modifier Alias Resolver**:
  - Automatically resolves aliases like `caps`, `ctrl`, `super`, `win`, `ret`, `esc`, `semi`, `quote`, `bs`, `del`, `space`.
  - Translates `ctrl`/`control` → `C-`, `super`/`win`/`meta` → `M-`, `alt`/`opt` → `A-`, `shift` → `S-`.
- **Natural Language Shortcut Assistant**:
  - Converts `ctrl+c` → `C-c`, `super+shift+w` → `M-S-w`, `ctrl+alt+del` → `C-A-delete`, `ctrl+backspace` → `C-backspace`.
- **In-Place Section Updater**:
  - Inserts or updates bindings directly under the matching `[layer]` section in `/etc/keyd/default.conf` while preserving 100% of existing comments and structure.
- **Print Mode (`-p` / `--print`)**:
  - Stdouts the formatted configuration line without touching any files.
- **Privileged Live Reloading**:
  - Uses `sudo` to safely update `/etc/keyd/default.conf` and immediately reloads `keyd` daemon (`sudo keyd reload`).
- **Live Key Sniffer**:
  - Built-in `keyd monitor` wrapper to discover hardware key codes while typing.

---

## 🚀 Interactive Usage

Run `keydmgr` to open the main `fzf` menu:

```bash
keydmgr
# or
python3 ~/scripts/keydmgr/keydmgr.py
```

### Main Menu Options:
1. **➕ Bind / Remap Key**: Interactive layer picker, key selector, and shortcut builder.
2. **📋 Browse Active Bindings**: Search all active bindings. Press **Enter** on any mapping to open its **Edit / Delete / Inspect** submenu.
3. **🔍 Inspect Key Across Layers**: View all mappings for a specific key across layers.
4. **🎧 Live Key Sniffer**: Runs `keyd monitor` to identify hardware keys in real time.
5. **💾 Reload keyd Daemon**: Executes `sudo keyd reload`.

---

## 💻 CLI & Print Mode

You can also run `keydmgr` non-interactively or in print-only mode:

### 1. Print Mode (`-p`)
Outputs the formatted keyd configuration line to stdout without modifying files:
```bash
keydmgr capslock "ctrl+c" -p
# Output: capslock = C-c

keydmgr j down -l alt -p
# Output:
# [alt]
# j = down

keydmgr capslock "overload(meta, esc)" -p
# Output: capslock = overload(meta, esc)
```

### 2. Direct Write & Reload Mode
Directly updates `/etc/keyd/default.conf` and reloads `keyd`:
```bash
# Update capslock in [main] layer
keydmgr capslock "overload(meta, esc)" -l main

# Update j in [alt] layer
keydmgr j down -l alt
```

---

## 📂 Configuration Paths

- **Config Path**: `/etc/keyd/default.conf` (customizable via `-c /path/to/file.conf`)
- **Automatic Backups**: `~/.local/share/keyd/backups/`
