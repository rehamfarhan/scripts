#!/usr/bin/env python3
"""
mediafetch.utils - Core Utilities, Config, Sanitization, and System Integrations
"""

import sys
import os
import re
import json
import shutil
import subprocess
import threading
from pathlib import Path

# ANSI Fallback Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

PRINT_LOCK = threading.Lock()


def safe_print(*args, **kwargs):
    """Thread-safe print to avoid clobbering console lines."""
    with PRINT_LOCK:
        print(*args, **kwargs)


# ==============================================================================
# Configuration & Directory Defaults
# ==============================================================================

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "mediafetch"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "mediafetch"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_VIDEO_DIR = Path.home() / "Videos" / "Downloads"
DEFAULT_MUSIC_DIR = Path.home() / "Music" / "Downloads"

DEFAULT_CONFIG = {
    "aria2_connections": 8,
    "video_dir": str(DEFAULT_VIDEO_DIR),
    "music_dir": str(DEFAULT_MUSIC_DIR),
    "embed_lyrics": True,
    "sub_langs": "en.*",
    "parallel_downloads": 3
}


def load_config() -> dict:
    """Loads config.json or creates it with defaults if not present."""
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
        except Exception:
            pass
        return dict(DEFAULT_CONFIG)

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            updated = False
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
                    updated = True
            if updated:
                try:
                    with open(CONFIG_FILE, "w", encoding="utf-8") as fw:
                        json.dump(cfg, fw, indent=2)
                except Exception:
                    pass
            return cfg
    except Exception:
        return dict(DEFAULT_CONFIG)


# ==============================================================================
# Title Sanitization & Formatting
# ==============================================================================

YOUTUBE_ID_PATTERN = re.compile(r'\s*\[[a-zA-Z0-9_-]{11}\]$')
CLUTTER_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\s*[\(\[](official\s*(music\s*)?(video|audio|visualizer|lyric\s*video|hd|4k|4k\s*remaster)?|lyrics?|audio|remastered|remaster\s*\d*|video)[\)\]]',
        r'\s*[\(\[]ft\.?|\s*feat\.?.*[\)\]]',
        r'\s*[\(\[]HD[\)\]]',
        r'\s*[\(\[]HQ[\)\]]',
        r'\s*[\(\[]4K[\)\]]',
    ]
]


def clean_title(title: str) -> str:
    """Removes video IDs and promotional clutter from track titles."""
    if not title:
        return ""
    title = YOUTUBE_ID_PATTERN.sub('', title)
    for p in CLUTTER_PATTERNS:
        title = p.sub('', title)
    return title.strip()


def format_bytes(num_bytes: int) -> str:
    """Formats raw byte counts into human-readable strings (e.g. 4.2 MB)."""
    if not num_bytes or num_bytes <= 0:
        return ""
    val = float(num_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if val < 1024.0:
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} TB"


# ==============================================================================
# Lazy-Loaded Module Helpers (keeps CLI startup < 0.04s)
# ==============================================================================

_MUTAGEN_CACHE = None
_MUTAGEN_TRIED = False


def get_mutagen():
    """Lazily loads Mutagen classes for metadata tagging."""
    global _MUTAGEN_CACHE, _MUTAGEN_TRIED
    if _MUTAGEN_TRIED:
        return _MUTAGEN_CACHE

    _MUTAGEN_TRIED = True
    try:
        from mutagen import File
        from mutagen.id3 import ID3, USLT, TIT2, TPE1, TALB, Encoding, ID3NoHeaderError
        from mutagen.mp3 import MP3
        from mutagen.flac import FLAC
        _MUTAGEN_CACHE = {
            "File": File,
            "ID3": ID3,
            "USLT": USLT,
            "TIT2": TIT2,
            "TPE1": TPE1,
            "TALB": TALB,
            "Encoding": Encoding,
            "ID3NoHeaderError": ID3NoHeaderError,
            "MP3": MP3,
            "FLAC": FLAC
        }
        return _MUTAGEN_CACHE
    except ImportError:
        _MUTAGEN_CACHE = None
        return None


def get_console():
    """Lazily loads Rich Console."""
    from rich.console import Console
    return Console()


# ==============================================================================
# System Dependencies & Clipboard
# ==============================================================================

def check_dependencies():
    """Verifies that required external binaries are installed."""
    deps = ["ffmpeg"]
    missing = [dep for dep in deps if not shutil.which(dep)]

    if missing:
        safe_print(f"\n{RED}{BOLD}Error: Missing required system dependencies: {', '.join(missing)}{RESET}\n")
        safe_print("  Arch Linux:    sudo pacman -S ffmpeg")
        safe_print("  Debian/Ubuntu: sudo apt install ffmpeg")
        sys.exit(1)


def get_clipboard_url() -> str | None:
    """Extracts valid HTTP/HTTPS URL from system clipboard."""
    commands = []
    if shutil.which("wl-paste"):
        commands.append(["wl-paste", "--no-newline"])
    if shutil.which("xclip"):
        commands.append(["xclip", "-o", "-selection", "clipboard"])
    if shutil.which("pbpaste"):
        commands.append(["pbpaste"])

    for cmd in commands:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout:
                text = res.stdout.strip()
                url_match = re.search(r'https?://[^\s"\'>]+', text)
                if url_match:
                    return url_match.group(0)
        except Exception:
            continue
    return None


def focus_hyprland_terminal():
    """Focuses the active Hyprland terminal workspace if running on Hyprland."""
    if not shutil.which("hyprctl"):
        return
    try:
        res = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=2)
        if res.returncode != 0 or not res.stdout:
            return

        clients = json.loads(res.stdout)
        client_pids = {c.get("pid"): c for c in clients if c.get("pid")}

        curr_pid = os.getpid()
        target_client = None

        while curr_pid and curr_pid > 1:
            if curr_pid in client_pids:
                target_client = client_pids[curr_pid]
                break
            try:
                with open(f"/proc/{curr_pid}/stat", "r") as f:
                    parts = f.read().split(")")
                    if len(parts) >= 2:
                        curr_pid = int(parts[-1].split()[1])
                    else:
                        break
            except Exception:
                break

        if target_client:
            address = target_client.get("address")
            c_pid = target_client.get("pid")
            ws_name = target_client.get("workspace", {}).get("name")
            if ws_name is not None:
                subprocess.run(["hyprctl", "dispatch", "workspace", str(ws_name)], capture_output=True)
            if address:
                subprocess.run(["hyprctl", "dispatch", "focuswindow", f"address:{address}"], capture_output=True)
            elif c_pid:
                subprocess.run(["hyprctl", "dispatch", "focuswindow", f"pid:{c_pid}"], capture_output=True)
    except Exception:
        pass


def select_with_fzf(items: list, prompt: str, allow_tab: bool = True) -> tuple:
    """Spawns an interactive fzf picker."""
    if not items or not shutil.which("fzf"):
        return None, None

    focus_hyprland_terminal()

    try:
        cmd = [
            "fzf",
            "--prompt", f"{prompt} > ",
            "--height", "40%",
            "--border",
            "--ansi"
        ]
        if allow_tab:
            cmd.extend([
                "--header", "[Tab] Hide to .mfignore | [Enter] Select | [Esc] Cancel",
                "--expect=tab"
            ])

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        stdout, _ = proc.communicate(input="\n".join(items))
        if proc.returncode == 0 and stdout:
            if allow_tab:
                lines = stdout.splitlines()
                if len(lines) >= 2:
                    key = lines[0].strip()
                    res = lines[1].strip()
                elif len(lines) == 1:
                    key = ""
                    res = lines[0].strip()
                else:
                    return None, None
            else:
                key = ""
                res = stdout.strip()

            if res.startswith("[Skip") or res == "":
                return None, None
            return key, res
    except Exception:
        pass
    return None, None


# ==============================================================================
# .mfignore Engine
# ==============================================================================

def get_mfignore_path(base_dir: Path = None) -> Path:
    """Returns the .mfignore path (defaults to ~/Music/.mfignore)."""
    music_dir = Path.home() / "Music"
    if base_dir and base_dir.is_dir() and (base_dir / ".mfignore").exists():
        return base_dir / ".mfignore"
    return music_dir / ".mfignore"


def load_mfignore(base_dir: Path = None) -> set:
    """Loads ignored patterns from .mfignore."""
    ignored = set()
    paths_to_check = [Path.home() / "Music" / ".mfignore"]
    if base_dir and base_dir.is_dir():
        paths_to_check.append(base_dir / ".mfignore")

    for p in paths_to_check:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            ignored.add(line)
                            ignored.add(Path(line).name)
                            ignored.add(Path(line).stem)
            except Exception:
                pass
    return ignored


def add_to_mfignore(item_str: str, base_dir: Path = None) -> bool:
    """Appends an entry to .mfignore."""
    ignore_file = get_mfignore_path(base_dir)
    try:
        ignore_file.parent.mkdir(parents=True, exist_ok=True)
        with open(ignore_file, "a", encoding="utf-8") as f:
            f.write(f"{item_str}\n")
        safe_print(f"  {GREEN}🙈 Added to .mfignore:{RESET} {BOLD}{item_str}{RESET} ({ignore_file})")
        return True
    except Exception as e:
        safe_print(f"  {RED}[ignore] Error writing to .mfignore: {e}{RESET}", file=sys.stderr)
        return False


def is_ignored(file_path: Path, ignore_set: set, base_dir: Path = None) -> bool:
    """Checks whether a given path is matched in .mfignore."""
    if not ignore_set:
        return False
    if file_path.name in ignore_set or file_path.stem in ignore_set or str(file_path) in ignore_set:
        return True
    if base_dir:
        try:
            rel = str(file_path.relative_to(base_dir))
            if rel in ignore_set:
                return True
        except Exception:
            pass
    return False


# ==============================================================================
# Directory Cleanup Engine
# ==============================================================================

def cleanup_directory(target_dir_str: str = None) -> bool:
    """Recursively removes YouTube video IDs and title clutter from media filenames."""
    if not target_dir_str:
        target_dir = Path.home() / "Music"
    else:
        target_dir = Path(target_dir_str).expanduser().resolve()

    if not target_dir.exists() or not target_dir.is_dir():
        safe_print(f"{RED}[cleanup] Error: Directory not found: {target_dir}{RESET}", file=sys.stderr)
        return False

    safe_print(f"\n{BOLD}{CYAN}🧹 Filename Cleanup Engine: Scanning {target_dir} ...{RESET}\n")

    valid_extensions = {".mp3", ".flac", ".m4a", ".ogg", ".wav", ".lrc", ".webp", ".png", ".jpg"}
    all_files = sorted([
        f for f in target_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in valid_extensions
    ])

    if not all_files:
        safe_print(f"{YELLOW}[cleanup] No matching media or lyrics files found in: {target_dir}{RESET}\n")
        return True

    renamed_count = 0
    for file_path in all_files:
        old_stem = file_path.stem
        cleaned_stem = clean_title(old_stem)

        if cleaned_stem and cleaned_stem != old_stem:
            new_file_path = file_path.with_name(cleaned_stem + file_path.suffix)
            if new_file_path.exists() and new_file_path != file_path:
                safe_print(f"  {YELLOW}⚠️  Skipped (Target exists): {file_path.name} -> {new_file_path.name}{RESET}")
                continue

            try:
                file_path.rename(new_file_path)
                renamed_count += 1
                safe_print(f"  {GREEN}✔ Renamed:{RESET} {BOLD}{file_path.name}{RESET}\n    {CYAN}➜ {new_file_path.name}{RESET}")
            except Exception as e:
                safe_print(f"  {RED}✖ Error renaming {file_path.name}: {e}{RESET}")

    safe_print(f"\n{BOLD}{GREEN}✨ Cleanup Complete! Renamed {renamed_count} file(s) in {target_dir}.{RESET}\n")
    return True

# Supported Profiles
PROFILES = {
    "video": {
        "desc": "1080p H.265 MKV video with English subtitles",
        "type": "video",
        "format_desc": "MKV 1080p H.265"
    },
    "music": {
        "desc": "High-quality MP3 (320k) with square album art & embedded lyrics",
        "type": "music",
        "format_desc": "MP3 320k (VBR 0)"
    },
    "flac": {
        "desc": "Lossless FLAC audio with square album art & embedded lyrics",
        "type": "music",
        "format_desc": "FLAC Lossless"
    },
    "shorts": {
        "desc": "1080p MP4 optimized for vertical video (Shorts, Reels, TikTok)",
        "type": "video",
        "format_desc": "MP4 1080p Vertical"
    },
    "podcast": {
        "desc": "Audio-only Opus format with embedded metadata & thumbnail",
        "type": "music",
        "format_desc": "Opus Audio"
    },
    "archive": {
        "desc": "Maximum quality video & audio preservation with all subtitles",
        "type": "video",
        "format_desc": "Archive (Max Quality)"
    }
}

PROFILE_ALIASES = {
    "audio": "music"
}


def resolve_profile_name(name: str) -> str:
    """Resolves profile aliases to canonical profile names."""
    if not name:
        return "video"
    return PROFILE_ALIASES.get(name.lower(), name.lower())
