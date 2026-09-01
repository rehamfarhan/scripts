#!/usr/bin/env python3
"""keydmgr: A streamlined, fzf-driven keyd configuration manager.

Features:
- Fast interactive fzf selector menus for every step.
- Intelligent key & modifier alias resolver ('ctrl', 'win', 'ret', 'caps', 'semi', etc.).
- Natural shortcut translator ('ctrl+c' -> 'C-c', 'super+shift+w' -> 'M-S-w', 'overload(meta, esc)').
- In-place layer section updating in /etc/keyd/default.conf preserving all existing comments.
- Interactive Browse menu with submenu actions (Edit, Delete, Inspect, Print).
- Supports -p / --print flag to output formatted line to stdout without modifying files.
- Live daemon reloading with sudo keyd reload.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

DEFAULT_CONFIG_PATH = Path("/etc/keyd/default.conf")
BACKUP_DIR = Path.home() / ".local" / "share" / "keyd" / "backups"

# ANSI Colors
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_CYAN = "\033[36m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_MAGENTA = "\033[35m"
COLOR_RED = "\033[31m"
COLOR_DIM = "\033[2m"


# ==============================================================================
# FZF RUNNER HELPER
# ==============================================================================

def check_fzf() -> None:
    """Ensure fzf is installed and available in PATH."""
    if not shutil.which("fzf"):
        print(f"{COLOR_RED}Error: 'fzf' is required but not installed or not in PATH.{COLOR_RESET}", file=sys.stderr)
        sys.exit(1)


def run_fzf(
    items: List[str],
    prompt: str = "Select: ",
    header: str = "",
    expect_keys: Optional[List[str]] = None,
    with_nth: Optional[str] = None,
    delimiter: Optional[str] = None,
    border_label: str = "",
    preview_cmd: str = "",
    preview_window: str = "right:50%:wrap",
    print_query: bool = True,
    margin: str = "8%,8%",
) -> Tuple[Optional[str], str, str]:
    """Run fzf with given items and return (selected_item, key_pressed, query_string)."""
    check_fzf()
    cmd = [
        "fzf",
        f"--prompt={prompt}",
        "--height=40",
        f"--margin={margin}",
        "--border=rounded",
        "--pointer=▶ ",
        "--ansi",
    ]
    if print_query:
        cmd.append("--print-query")
    if border_label:
        cmd.append(f"--border-label= {border_label} ")
    if header:
        cmd.append(f"--header={header}")
    if expect_keys:
        cmd.append(f"--expect={','.join(expect_keys)}")
    if with_nth:
        cmd.append(f"--with-nth={with_nth}")
    if delimiter:
        cmd.append(f"--delimiter={delimiter}")
    if preview_cmd:
        cmd.append(f"--preview={preview_cmd}")
        cmd.append(f"--preview-window={preview_window}")

    input_bytes = "\n".join(items).encode("utf-8")
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out_bytes, _ = proc.communicate(input=input_bytes)

    if proc.returncode not in (0, 1, 130):
        return None, "", ""

    raw_lines = out_bytes.decode("utf-8", errors="replace").splitlines()
    if not raw_lines:
        return None, "", ""

    query = ""
    key = ""
    selected = None

    if print_query:
        query = raw_lines[0].strip()
        rest = raw_lines[1:]
    else:
        rest = raw_lines

    if expect_keys and len(rest) >= 2:
        key = rest[0].strip()
        selected = rest[1]
    elif expect_keys and len(rest) == 1:
        if rest[0] in expect_keys:
            key = rest[0]
        else:
            selected = rest[0]
    elif rest:
        selected = rest[0]

    return selected, key, query


# ==============================================================================
# KEY & MODIFIER KNOWLEDGE BASE
# ==============================================================================

MODIFIER_ALIASES: Dict[str, str] = {
    "c": "C-",
    "ctrl": "C-",
    "control": "C-",
    "ctl": "C-",
    "lctrl": "C-",
    "rctrl": "C-",
    "m": "M-",
    "meta": "M-",
    "super": "M-",
    "win": "M-",
    "windows": "M-",
    "cmd": "M-",
    "command": "M-",
    "a": "A-",
    "alt": "A-",
    "opt": "A-",
    "option": "A-",
    "lalt": "A-",
    "ralt": "A-",
    "s": "S-",
    "shift": "S-",
    "lshift": "S-",
    "rshift": "S-",
    "g": "G-",
    "altgr": "G-",
    "h": "H-",
    "hyper": "H-",
}

KEY_ALIASES: Dict[str, str] = {
    # Special & Whitespace
    "esc": "esc",
    "escape": "esc",
    "ret": "enter",
    "return": "enter",
    "enter": "enter",
    "space": "space",
    "spc": "space",
    "spacebar": "space",
    "tab": "tab",
    "backspace": "backspace",
    "bs": "backspace",
    "delete": "delete",
    "del": "delete",
    "caps": "capslock",
    "capslock": "capslock",
    "caps_lock": "capslock",
    # Standalone Modifiers
    "ctrl": "leftcontrol",
    "control": "leftcontrol",
    "leftcontrol": "leftcontrol",
    "rightcontrol": "rightcontrol",
    "alt": "leftalt",
    "leftalt": "leftalt",
    "rightalt": "rightalt",
    "meta": "leftmeta",
    "super": "leftmeta",
    "win": "leftmeta",
    "windows": "leftmeta",
    "leftmeta": "leftmeta",
    "rightmeta": "rightmeta",
    "shift": "leftshift",
    "leftshift": "leftshift",
    "rightshift": "rightshift",
    # Navigation
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pgup": "pageup",
    "pagedown": "pagedown",
    "pgdn": "pagedown",
    "insert": "insert",
    "ins": "insert",
    # Punctuations & Symbols
    "semi": "semicolon",
    "semicolon": "semicolon",
    ";": "semicolon",
    "quote": "apostrophe",
    "apostrophe": "apostrophe",
    "'": "apostrophe",
    "grave": "grave",
    "`": "grave",
    "minus": "minus",
    "-": "minus",
    "equal": "equal",
    "equals": "equal",
    "=": "equal",
    "slash": "slash",
    "/": "slash",
    "backslash": "backslash",
    "\\": "backslash",
    "comma": "comma",
    ",": "comma",
    "dot": "dot",
    "period": "dot",
    ".": "dot",
    "leftbrace": "leftbrace",
    "[": "leftbrace",
    "rightbrace": "rightbrace",
    "]": "rightbrace",
    # Media & Volume
    "play": "playpause",
    "playpause": "playpause",
    "pause": "pause",
    "next": "nextsong",
    "nextsong": "nextsong",
    "prev": "previoussong",
    "previoussong": "previoussong",
    "volup": "volumeup",
    "volumeup": "volumeup",
    "voldn": "volumedown",
    "voldown": "volumedown",
    "volumedown": "volumedown",
    "mute": "mute",
}

PUNCTUATION_EQUIVALENTS: Dict[str, str] = {
    ";": "semicolon",
    "semicolon": ";",
    "'": "apostrophe",
    "apostrophe": "'",
    "`": "grave",
    "grave": "`",
    "-": "minus",
    "minus": "-",
    "=": "equal",
    "equal": "=",
    "/": "slash",
    "slash": "/",
    "\\": "backslash",
    "backslash": "\\",
    ",": "comma",
    "comma": ",",
    ".": "dot",
    "dot": ".",
    "[": "leftbrace",
    "leftbrace": "[",
    "]": "rightbrace",
    "rightbrace": "]",
    "esc": "escape",
    "escape": "esc",
}

KEY_DESCRIPTIONS: Dict[str, str] = {
    "esc": "Escape key",
    "enter": "Enter / Return",
    "backspace": "Backspace (delete back)",
    "delete": "Delete (delete forward)",
    "space": "Space bar",
    "tab": "Tab key",
    "capslock": "Caps Lock key",
    "leftmeta": "Left Super / Windows key",
    "rightmeta": "Right Super / Windows key",
    "leftalt": "Left Alt / Option",
    "rightalt": "Right Alt / Option",
    "leftcontrol": "Left Control",
    "rightcontrol": "Right Control",
    "leftshift": "Left Shift",
    "rightshift": "Right Shift",
    "up": "Up Arrow",
    "down": "Down Arrow",
    "left": "Left Arrow",
    "right": "Right Arrow",
    "pageup": "Page Up",
    "pagedown": "Page Down",
    "home": "Home",
    "end": "End",
    "playpause": "Play / Pause media",
    "nextsong": "Next Track",
    "previoussong": "Previous Track",
    "volumeup": "Volume Up",
    "volumedown": "Volume Down",
    "mute": "Audio Mute",
    "semicolon": "Semicolon (;)",
    "apostrophe": "Single Quote / Apostrophe (')",
    "grave": "Backtick / Grave (`)",
    "backslash": "Backslash (\\)",
    "slash": "Forward Slash (/)",
    "comma": "Comma (,)",
    "dot": "Period / Dot (.)",
    "equal": "Equal sign (=)",
    "minus": "Minus / Hyphen (-)",
}


def get_canonical_keys() -> List[str]:
    """Retrieve list of valid keys from keyd or standard list."""
    try:
        res = subprocess.run(["keyd", "list-keys"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            keys = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            return sorted(list(set(keys)))
    except Exception:
        pass

    fallback = [
        "esc", "enter", "backspace", "tab", "space", "capslock",
        "leftcontrol", "rightcontrol", "leftshift", "rightshift", "leftalt", "rightalt",
        "leftmeta", "rightmeta", "up", "down", "left", "right",
        "home", "end", "pageup", "pagedown", "insert", "delete",
        "semicolon", "apostrophe", "grave", "slash", "backslash", "comma", "dot",
        "minus", "equal", "playpause", "nextsong", "previoussong", "volumeup", "volumedown", "mute"
    ]
    for c in "abcdefghijklmnopqrstuvwxyz0123456789":
        fallback.append(c)
    for i in range(1, 25):
        fallback.append(f"f{i}")
    return sorted(list(set(fallback)))


def resolve_key_name(query: str) -> str:
    """Normalize user input string to canonical keyd key name."""
    clean = query.strip().lower()
    if clean in KEY_ALIASES:
        return KEY_ALIASES[clean]
    return clean


def parse_human_combo(text: str) -> str:
    """Translate natural shortcut expressions into keyd action syntax.
    
    Examples:
        'ctrl+c' -> 'C-c'
        'ctrl+alt+t' -> 'C-A-t'
        'super+shift+w' -> 'M-S-w'
        'ctrl+backspace' -> 'C-backspace'
        'overload(meta, esc)' -> 'overload(meta, esc)'
    """
    raw = text.strip()
    if "(" in raw:
        return raw

    if "-" in raw:
        parts = raw.split("-")
        if len(parts) > 1 and all(p.upper() in ["C", "M", "A", "S", "G", "H"] for p in parts[:-1]):
            norm_key = resolve_key_name(parts[-1])
            mods = "-".join(p.upper() for p in parts[:-1])
            return f"{mods}-{norm_key}"
        return raw

    tokens = [t.strip() for t in re.split(r"[\+]+", raw) if t.strip()]
    if len(tokens) <= 1:
        tokens = [t.strip() for t in raw.split() if t.strip()]

    if not tokens:
        return ""

    if len(tokens) == 1:
        return resolve_key_name(tokens[0])

    mods = []
    for mod_tok in tokens[:-1]:
        m_lower = mod_tok.lower()
        if m_lower in MODIFIER_ALIASES:
            m_prefix = MODIFIER_ALIASES[m_lower].rstrip("-")
            if m_prefix not in mods:
                mods.append(m_prefix)
        else:
            mods.append(m_lower.upper())

    target_key = resolve_key_name(tokens[-1])
    if mods and target_key:
        return f"{'-'.join(mods)}-{target_key}"
    return raw


# ==============================================================================
# IN-PLACE SECTION CONFIG UPDATER (PRESERVES COMMENTS)
# ==============================================================================

def get_active_layers(config_path: Path = DEFAULT_CONFIG_PATH) -> List[str]:
    """Extract list of existing layer section names from config file."""
    if not config_path.exists():
        return ["main", "alt", "alt+shift"]

    layers = []
    try:
        with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_str = line.strip()
                if line_str.startswith("[") and line_str.endswith("]"):
                    sec = line_str[1:-1].strip().lower()
                    if sec not in ["global", "ids"] and sec not in layers:
                        layers.append(sec)
    except Exception:
        pass

    if not layers:
        layers = ["main"]
    return layers


def _write_and_reload_config(new_content: str, config_path: Path) -> Tuple[bool, str]:
    """Validate, write (handling sudo if necessary), and reload keyd."""
    with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as tf:
        tf.write(new_content)
        stage_path = tf.name

    try:
        check_proc = subprocess.run(["keyd", "check", stage_path], capture_output=True, text=True, timeout=5)
        raw_msg = (check_proc.stderr.strip() + "\n" + check_proc.stdout.strip()).strip()
        clean_err = raw_msg.replace(stage_path, "config")
        error_triggers = ["invalid key or action", "invalid binding", "failed to open", "unknown key", "syntax error"]
        if any(trig in clean_err.lower() for trig in error_triggers):
            return False, f"Syntax validation failed:\n{clean_err}"
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        pass

    # Create backup
    try:
        if config_path.exists():
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(config_path, BACKUP_DIR / f"{config_path.stem}_{timestamp}.conf")
    except Exception:
        pass

    # Determine write permissions
    is_user_writable = False
    if config_path.exists():
        is_user_writable = os.access(config_path, os.W_OK)
    else:
        is_user_writable = os.access(config_path.parent, os.W_OK)

    try:
        if os.geteuid() == 0 or is_user_writable:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            if os.geteuid() == 0:
                os.chmod(config_path, 0o644)
        else:
            cmd = ["sudo", "install", "-m", "644", stage_path, str(config_path)]
            res = subprocess.run(cmd)
            if res.returncode != 0:
                return False, f"Failed to write to {config_path} (sudo install failed)"

        # Reload daemon if default config
        if config_path.resolve() == DEFAULT_CONFIG_PATH.resolve():
            reload_cmd = ["sudo", "keyd", "reload"] if os.geteuid() != 0 else ["keyd", "reload"]
            subprocess.run(reload_cmd, capture_output=True, text=True, timeout=5)

        return True, "Config successfully updated and keyd reloaded!"
    except Exception as e:
        return False, f"Error saving configuration: {e}"
    finally:
        if os.path.exists(stage_path):
            os.remove(stage_path)


def update_config_file(
    layer: str,
    key: str,
    action: str,
    config_path: Path = DEFAULT_CONFIG_PATH
) -> Tuple[bool, str]:
    """Insert or update a key = action binding under [layer] in config_path, preserving all comments."""
    layer_clean = layer.strip().lower()
    key_clean = key.strip()
    action_clean = action.strip()
    formatted_line = f"{key_clean} = {action_clean}\n"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    else:
        lines = ["[global]\n\n", "[ids]\n*\n\n", "[main]\n"]

    layer_header_idx = -1
    next_section_idx = len(lines)

    for i, line in enumerate(lines):
        line_str = line.strip()
        if line_str.startswith("[") and line_str.endswith("]"):
            sec = line_str[1:-1].strip().lower()
            if sec == layer_clean:
                layer_header_idx = i
            elif layer_header_idx != -1 and i > layer_header_idx:
                next_section_idx = i
                break

    equiv_keys = {key_clean, resolve_key_name(key_clean)}
    if key_clean in PUNCTUATION_EQUIVALENTS:
        equiv_keys.add(PUNCTUATION_EQUIVALENTS[key_clean])

    updated = False
    if layer_header_idx != -1:
        for idx in range(layer_header_idx + 1, next_section_idx):
            line_str = lines[idx].strip()
            if line_str.startswith("#") or not line_str:
                continue
            if "=" in line_str:
                k, _ = line_str.split("=", 1)
                k_clean = k.strip()
                if k_clean in equiv_keys:
                    lines[idx] = formatted_line
                    updated = True
                    break

        if not updated:
            insert_pos = next_section_idx
            while insert_pos > layer_header_idx + 1 and lines[insert_pos - 1].strip() == "":
                insert_pos -= 1
            lines.insert(insert_pos, formatted_line)
            updated = True
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"\n[{layer_clean}]\n")
        lines.append(formatted_line)
        updated = True

    new_content = "".join(lines)
    success, msg = _write_and_reload_config(new_content, config_path)
    if success:
        return True, f"Successfully applied to [{layer_clean}] in {config_path} and reloaded keyd!"
    return False, msg


def remove_binding_from_file(
    layer: str,
    key: str,
    config_path: Path = DEFAULT_CONFIG_PATH
) -> Tuple[bool, str]:
    """Remove a key binding under [layer] in config_path, preserving all comments."""
    layer_clean = layer.strip().lower()
    key_clean = key.strip()

    if not config_path.exists():
        return False, f"Config file {config_path} not found."

    with open(config_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    layer_header_idx = -1
    next_section_idx = len(lines)

    for i, line in enumerate(lines):
        line_str = line.strip()
        if line_str.startswith("[") and line_str.endswith("]"):
            sec = line_str[1:-1].strip().lower()
            if sec == layer_clean:
                layer_header_idx = i
            elif layer_header_idx != -1 and i > layer_header_idx:
                next_section_idx = i
                break

    if layer_header_idx == -1:
        return False, f"Layer [{layer_clean}] not found in {config_path}."

    equiv_keys = {key_clean, resolve_key_name(key_clean)}
    if key_clean in PUNCTUATION_EQUIVALENTS:
        equiv_keys.add(PUNCTUATION_EQUIVALENTS[key_clean])

    found_idx = -1
    for idx in range(layer_header_idx + 1, next_section_idx):
        line_str = lines[idx].strip()
        if line_str.startswith("#") or not line_str:
            continue
        if "=" in line_str:
            k, _ = line_str.split("=", 1)
            if k.strip() in equiv_keys:
                found_idx = idx
                break

    if found_idx == -1:
        return False, f"Key '{key_clean}' not found in layer [{layer_clean}]."

    lines.pop(found_idx)
    new_content = "".join(lines)
    success, msg = _write_and_reload_config(new_content, config_path)
    if success:
        return True, f"Successfully removed '{key_clean}' from [{layer_clean}]!"
    return False, msg


# ==============================================================================
# FZF INTERACTIVE FLOWS
# ==============================================================================

def fzf_pick_layer(config_path: Path = DEFAULT_CONFIG_PATH) -> Optional[str]:
    """Prompt user to select or create a layer using fzf."""
    active_layers = get_active_layers(config_path)
    layer_items = [f"📂 [{l}]" for l in active_layers]
    layer_items.append("➕ Create / Type New Layer Name...")

    sel, _, query = run_fzf(
        layer_items,
        prompt="Select Layer: ",
        header="Select target layer or type custom layer name:",
        border_label="📂 Layer Selector",
    )

    if not sel:
        if query:
            return query.strip().lstrip("[").rstrip("]").lower()
        return None

    if "Create / Type" in sel:
        if query:
            return query.strip().lstrip("[").rstrip("]").lower()
        sub_sel, _, sub_q = run_fzf([], prompt="Enter New Layer Name: ", border_label="➕ New Layer Name")
        return sub_q.strip().lower() if sub_q else None

    m = re.search(r"\[([a-zA-Z0-9_\:\+\*\-\s]+)\]", sel)
    if m:
        return m.group(1).strip().lower()
    return sel.strip().lower()


def fzf_pick_key() -> Optional[str]:
    """Prompt user to select a key to modify using fzf with search and alias hints."""
    canonical_keys = get_canonical_keys()
    
    common_keys = [
        "capslock", "leftcontrol", "leftalt", "leftmeta", "leftshift",
        "esc", "enter", "space", "tab", "backspace", "delete",
        "semicolon", "apostrophe", "grave", "slash", "backslash",
        "up", "down", "left", "right"
    ]
    
    items = []
    seen = set()
    for k in common_keys:
        desc = KEY_DESCRIPTIONS.get(k, k)
        items.append(f"{k}\t{COLOR_CYAN}{k:<14}{COLOR_RESET} {COLOR_YELLOW}★ {desc}{COLOR_RESET}")
        seen.add(k)

    for k in canonical_keys:
        if k not in seen:
            desc = KEY_DESCRIPTIONS.get(k, "")
            desc_str = f" {COLOR_DIM}({desc}){COLOR_RESET}" if desc else ""
            items.append(f"{k}\t{k:<14}{desc_str}")
            seen.add(k)

    sel, _, query = run_fzf(
        items,
        prompt="Key to Modify: ",
        header="Type key name/alias (e.g. caps, ctrl, semi, ret, j) or select below:",
        border_label="⌨️  Key to Modify",
        delimiter="\t",
        with_nth="2",
    )

    if not sel:
        if query:
            return resolve_key_name(query)
        return None

    raw_key = sel.split("\t")[0].strip()
    return resolve_key_name(raw_key)


def fzf_pick_action(key_name: str, layer_name: str) -> Optional[str]:
    """Prompt user to choose or type target action expression using fzf."""
    presets = [
        ("⚡ Type Direct Shortcut", "Type in search box (e.g. ctrl+c, super+shift+w, down, enter, backspace)"),
        ("🔀 Overload (Tap / Hold)", "Tap for a key, Hold for a layer/modifier (e.g. tap=esc, hold=meta)"),
        ("📂 Layer Activate", "Momentarily activate layer while held (layer(layer_name))"),
        ("🔁 Layer Toggle", "Toggle persistent layer on key press (toggle(layer_name))"),
        ("🔄 Layer Swap", "Swap active layer (swap(layer_name))"),
        ("📜 Macro Sequence", "Play key sequence (macro(C-c 10ms C-v))"),
        ("🚫 Disable Key (noop)", "Disable key completely (noop)"),
    ]

    items = [f"{p[0]}\t{COLOR_BOLD}{p[0]:<28}{COLOR_RESET} {COLOR_DIM}{p[1]}{COLOR_RESET}" for p in presets]

    sel, _, query = run_fzf(
        items,
        prompt=f"Modify '{key_name}' in [{layer_name}] to: ",
        header=f"Target: [{layer_name}] {key_name} = ???\nType shortcut directly (e.g. 'ctrl+c') OR pick a preset:",
        border_label=f"🎯 Target Action ({key_name})",
        delimiter="\t",
        with_nth="2",
    )

    if query and (not sel or "Type Direct Shortcut" in sel):
        return parse_human_combo(query)

    if not sel:
        return None

    if "Overload" in sel:
        hold_sel, _, hold_q = run_fzf(
            ["meta (Super/Windows)", "control (Ctrl)", "alt (Alt)", "shift (Shift)", "nav", "sym"],
            prompt="Overload: Hold Action (Layer or Modifier): ",
            border_label="🔀 Overload - Hold Action",
        )
        hold_target = hold_q if not hold_sel else hold_sel.split()[0]

        tap_sel, _, tap_q = run_fzf(
            ["esc (Escape)", "enter (Return)", "space", "backspace", "tab"],
            prompt="Overload: Tap Action (Key): ",
            border_label="🔀 Overload - Tap Action",
        )
        tap_target = tap_q if not tap_sel else tap_sel.split()[0]

        if hold_target and tap_target:
            return f"overload({resolve_key_name(hold_target)}, {resolve_key_name(tap_target)})"
        return None

    if "Layer Activate" in sel:
        active_layers = get_active_layers()
        l_sel, _, l_q = run_fzf(active_layers, prompt="Layer to Activate: ", border_label="📂 layer(...)")
        target_layer = l_q if not l_sel else l_sel
        return f"layer({target_layer.strip().lower()})" if target_layer else None

    if "Layer Toggle" in sel:
        active_layers = get_active_layers()
        l_sel, _, l_q = run_fzf(active_layers, prompt="Layer to Toggle: ", border_label="🔁 toggle(...)")
        target_layer = l_q if not l_sel else l_sel
        return f"toggle({target_layer.strip().lower()})" if target_layer else None

    if "Layer Swap" in sel:
        active_layers = get_active_layers()
        l_sel, _, l_q = run_fzf(active_layers, prompt="Layer to Swap: ", border_label="🔄 swap(...)")
        target_layer = l_q if not l_sel else l_sel
        return f"swap({target_layer.strip().lower()})" if target_layer else None

    if "Macro Sequence" in sel:
        _, _, macro_q = run_fzf([], prompt="Macro Sequence (e.g. C-c 10ms C-v): ", border_label="📜 macro(...)")
        return f"macro({macro_q.strip()})" if macro_q else None

    if "Disable Key" in sel:
        return "noop"

    return parse_human_combo(query) if query else None


def fzf_bind_flow(print_only: bool = False, target_layer: Optional[str] = None, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Complete interactive fzf flow for binding a key."""
    layer = target_layer or fzf_pick_layer(config_path)
    if not layer:
        return

    key = fzf_pick_key()
    if not key:
        return

    action = fzf_pick_action(key, layer)
    if not action:
        return

    formatted_line = f"{key} = {action}"

    if print_only:
        if layer != "main":
            print(f"[{layer}]\n{formatted_line}")
        else:
            print(formatted_line)
        return

    print(f"\n{COLOR_CYAN}Adding binding:{COLOR_RESET} [{COLOR_MAGENTA}{layer}{COLOR_RESET}] {COLOR_BOLD}{key}{COLOR_RESET} = {COLOR_GREEN}{action}{COLOR_RESET}")
    success, msg = update_config_file(layer, key, action, config_path)
    if success:
        print(f"{COLOR_GREEN}✔ {msg}{COLOR_RESET}\n")
    else:
        print(f"{COLOR_RED}✖ {msg}{COLOR_RESET}\n", file=sys.stderr)
        sys.exit(1)


def fzf_binding_submenu(layer: str, key: str, action: str, config_path: Path = DEFAULT_CONFIG_PATH) -> bool:
    """Submenu triggered when pressing Enter on a binding in Browse Active Bindings.
    
    Returns True if the list should be refreshed.
    """
    header_text = f"Selected: [{layer}] {key} = {action}"
    options = [
        "✏️   Edit / Change Action",
        "🗑️   Delete / Remove Binding",
        "🔍  Inspect Key Across All Layers",
        "📋  Print Line (stdout)",
        "↩️   Back to Bindings List",
    ]

    sub_sel, _, _ = run_fzf(
        options,
        prompt="Action: ",
        header=header_text,
        border_label=f"⚙️  Manage: [{layer}] {key}",
        print_query=False,
    )

    if not sub_sel or "Back" in sub_sel:
        return False

    if "Edit" in sub_sel:
        new_action = fzf_pick_action(key, layer)
        if new_action:
            success, msg = update_config_file(layer, key, new_action, config_path)
            if success:
                print(f"\n{COLOR_GREEN}✔ Updated [{layer}] {key} = {new_action}{COLOR_RESET}\n")
            else:
                print(f"\n{COLOR_RED}✖ {msg}{COLOR_RESET}\n", file=sys.stderr)
            return True

    elif "Delete" in sub_sel:
        # Confirm removal
        conf_sel, _, _ = run_fzf(
            ["1) Yes (Remove this binding)", "2) No (Cancel)"],
            prompt=f"Confirm remove '{key}' from [{layer}]? ",
            border_label="⚠️ Confirm Deletion",
            print_query=False,
        )
        if conf_sel and "Yes" in conf_sel:
            success, msg = remove_binding_from_file(layer, key, config_path)
            if success:
                print(f"\n{COLOR_GREEN}✔ {msg}{COLOR_RESET}\n")
            else:
                print(f"\n{COLOR_RED}✖ {msg}{COLOR_RESET}\n", file=sys.stderr)
            return True

    elif "Inspect" in sub_sel:
        fzf_inspect_key_direct(key, config_path)
        input(f"\n{COLOR_DIM}Press Enter to return to menu...{COLOR_RESET}")

    elif "Print Line" in sub_sel:
        if layer != "main":
            print(f"\n[{layer}]\n{key} = {action}\n")
        else:
            print(f"\n{key} = {action}\n")
        input(f"{COLOR_DIM}Press Enter to return to menu...{COLOR_RESET}")

    return False


def fzf_browse_bindings(config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Browse existing bindings in fzf with an interactive submenu on selection."""
    while True:
        if not config_path.exists():
            print(f"{COLOR_YELLOW}Config file {config_path} not found.{COLOR_RESET}")
            return

        items = []
        current_layer = "main"
        with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_str = line.strip()
                if line_str.startswith("[") and line_str.endswith("]"):
                    current_layer = line_str[1:-1].strip().lower()
                    continue
                if line_str.startswith("#") or not line_str or "=" not in line_str:
                    continue
                k, v = line_str.split("=", 1)
                k_clean = k.strip()
                v_clean = v.strip()
                desc = KEY_DESCRIPTIONS.get(v_clean, "")
                desc_str = f" {COLOR_DIM}({desc}){COLOR_RESET}" if desc else ""
                row_display = f"[{COLOR_MAGENTA}{current_layer:<10}{COLOR_RESET}]  {COLOR_CYAN}{k_clean:<14}{COLOR_RESET} →  {COLOR_GREEN}{v_clean:<22}{COLOR_RESET}{desc_str}"
                items.append(f"{current_layer}\t{k_clean}\t{v_clean}\t{row_display}")

        if not items:
            print(f"{COLOR_YELLOW}No custom bindings found in {config_path}.{COLOR_RESET}")
            return

        sel, _, _ = run_fzf(
            items,
            prompt="Select Binding: ",
            header="Active Bindings in /etc/keyd/default.conf\n[ENTER] Open Submenu (Edit / Delete / Inspect) | [ESC] Return",
            border_label="📋 Active Keyd Bindings",
            delimiter="\t",
            with_nth="4",
            print_query=False,
        )

        if not sel:
            break

        parts = sel.split("\t")
        if len(parts) >= 3:
            layer = parts[0]
            key = parts[1]
            action = parts[2]
            fzf_binding_submenu(layer, key, action, config_path)


def fzf_inspect_key_direct(key: str, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Helper to inspect a key across all layers."""
    equivs = {key, resolve_key_name(key)}
    if key in PUNCTUATION_EQUIVALENTS:
        equivs.add(PUNCTUATION_EQUIVALENTS[key])

    matches = []
    if config_path.exists():
        current_layer = "main"
        with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_str = line.strip()
                if line_str.startswith("[") and line_str.endswith("]"):
                    current_layer = line_str[1:-1].strip().lower()
                    continue
                if line_str.startswith("#") or not line_str or "=" not in line_str:
                    continue
                k, v = line_str.split("=", 1)
                if k.strip() in equivs:
                    matches.append(f"[{COLOR_MAGENTA}{current_layer}{COLOR_RESET}]  {COLOR_CYAN}{k.strip()}{COLOR_RESET} = {COLOR_GREEN}{v.strip()}{COLOR_RESET}")

    if not matches:
        print(f"\n{COLOR_YELLOW}No custom bindings for '{key}' in any layer (default hardware behavior).{COLOR_RESET}")
    else:
        print(f"\n{COLOR_BOLD}Mappings for '{key}':{COLOR_RESET}")
        for m in matches:
            print(f"  {m}")


def fzf_inspect_key(config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Inspect a key across all active layers."""
    key = fzf_pick_key()
    if not key:
        return
    fzf_inspect_key_direct(key, config_path)
    print()


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="keydmgr - Streamlined fzf Keyd Configurator",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "key",
        nargs="?",
        help="Trigger key to modify (e.g. capslock, j, semi, ctrl)"
    )
    parser.add_argument(
        "action",
        nargs="?",
        help="Target action / shortcut (e.g. 'ctrl+c', 'C-c', 'down', 'overload(meta, esc)')"
    )
    parser.add_argument(
        "-l", "--layer",
        default=None,
        help="Target layer (default: main)"
    )
    parser.add_argument(
        "-p", "--print",
        action="store_true",
        help="Print the formatted keyd configuration line to stdout instead of modifying files"
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to keyd config file (default: {DEFAULT_CONFIG_PATH})"
    )

    args = parser.parse_args()

    # CLI Direct Mode: key and action supplied
    if args.key and args.action:
        layer = (args.layer or "main").strip().lower()
        key = resolve_key_name(args.key)
        action = parse_human_combo(args.action)
        formatted_line = f"{key} = {action}"

        if args.print:
            if layer != "main":
                print(f"[{layer}]\n{formatted_line}")
            else:
                print(formatted_line)
            return

        print(f"[{layer}] {key} = {action}")
        success, msg = update_config_file(layer, key, action, args.config)
        if success:
            print(f"{COLOR_GREEN}✔ {msg}{COLOR_RESET}")
        else:
            print(f"{COLOR_RED}✖ {msg}{COLOR_RESET}", file=sys.stderr)
            sys.exit(1)
        return

    # If -p is passed alone, run interactive bind flow in print-only mode
    if args.print:
        fzf_bind_flow(print_only=True, target_layer=args.layer, config_path=args.config)
        return

    # Interactive fzf Main Menu
    while True:
        menu_items = [
            "➕  Bind / Remap Key",
            "📋  Browse Active Bindings",
            "🔍  Inspect Key Across Layers",
            "🎧  Live Key Sniffer (keyd monitor)",
            "💾  Reload keyd Daemon (sudo keyd reload)",
            "🚪  Exit",
        ]

        sel, _, _ = run_fzf(
            menu_items,
            prompt="Select Option: ",
            border_label="⌨️  KEYDMGR (Keyd Manager)",
            print_query=False,
        )

        if not sel or "Exit" in sel:
            break

        if "Bind / Remap" in sel:
            fzf_bind_flow(print_only=False, target_layer=args.layer, config_path=args.config)
        elif "Browse" in sel:
            fzf_browse_bindings(args.config)
        elif "Inspect" in sel:
            fzf_inspect_key(args.config)
        elif "Live Key Sniffer" in sel:
            cmd = ["sudo", "keyd", "monitor"] if os.geteuid() != 0 else ["keyd", "monitor"]
            try:
                subprocess.run(cmd)
            except KeyboardInterrupt:
                pass
        elif "Reload keyd" in sel:
            cmd = ["sudo", "keyd", "reload"] if os.geteuid() != 0 else ["keyd", "reload"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                print(f"\n{COLOR_GREEN}✔ keyd daemon reloaded successfully!{COLOR_RESET}\n")
            else:
                print(f"\n{COLOR_RED}✖ keyd reload failed: {res.stderr.strip()}{COLOR_RESET}\n", file=sys.stderr)


if __name__ == "__main__":
    main()
