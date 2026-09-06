#!/usr/bin/env python3
"""
mediafetch (mf) - High-Performance Profile-Based Media Downloader & Tagging Pipeline

Features:
  - Modular superfile-style multi-pane dashboard with real-time stats
  - Automated non-interactive execution (zero hanging or prompts on missing lyrics)
  - Separated two-phase pipeline: fast parallel downloads first, batch lyrics second
  - Profile-based presets: music/audio (MP3 320k + square art), flac, video (1080p MKV), shorts, podcast, archive
  - LRCLIB lyrics tagger (embedded ID3v2 USLT / FLAC tags + synced .lrc sidecars for kew/cmus)
  - Deduplicated playlist & album extraction
  - Standalone utility subcommands: cleanup, attach, lyrics
"""

import sys
import os
import re
import json
import shutil
import argparse
import subprocess
import urllib.request
import urllib.parse
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ANSI Fallback Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

PRINT_LOCK = threading.Lock()


def safe_print(*args, **kwargs):
    """Thread-safe print to avoid clobbering console lines."""
    with PRINT_LOCK:
        print(*args, **kwargs)


# ==============================================================================
# Lazy-Loaded Module Getters (Keeps startup latency < 0.05s)
# ==============================================================================

_MUTAGEN_AVAILABLE = None

def get_mutagen():
    """Lazily loads Mutagen classes."""
    global _MUTAGEN_AVAILABLE
    if _MUTAGEN_AVAILABLE is False:
        return None
    try:
        from mutagen.id3 import ID3, USLT, TIT2, TPE1, TALB, Encoding, ID3NoHeaderError
        from mutagen.mp3 import MP3
        from mutagen.flac import FLAC
        _MUTAGEN_AVAILABLE = True
        return {
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
    except ImportError:
        _MUTAGEN_AVAILABLE = False
        return None


def get_console():
    """Lazily loads Rich Console."""
    from rich.console import Console
    return Console()


# ==============================================================================
# Configuration & Paths
# ==============================================================================

SCRIPT_PATH = Path(__file__).resolve()
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

# Pre-compiled Regex Patterns for Title Sanitization
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


def load_config():
    """Loads config.json or initializes defaults if not present."""
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
        except Exception:
            pass
        return DEFAULT_CONFIG

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception:
        return DEFAULT_CONFIG


def get_clipboard_url():
    """Detects valid HTTP/HTTPS URL from system clipboard (wl-paste, xclip, pbpaste)."""
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


def check_dependencies():
    """Verifies system dependencies for running mediafetch."""
    deps = ["ffmpeg"]
    missing = [dep for dep in deps if not shutil.which(dep)]

    if missing:
        safe_print(f"\n{RED}{BOLD}Error: Missing required system dependencies: {', '.join(missing)}{RESET}\n")
        safe_print("  Arch Linux:    sudo pacman -S ffmpeg")
        safe_print("  Debian/Ubuntu: sudo apt install ffmpeg")
        sys.exit(1)


# ==============================================================================
# Lyrics Processing & Metadata Module (LRCLIB Integration)
# ==============================================================================

def clean_title(title: str) -> str:
    """Removes noise and clutter common in YouTube video titles using pre-compiled regex."""
    title = YOUTUBE_ID_PATTERN.sub('', title)
    for p in CLUTTER_PATTERNS:
        title = p.sub('', title)
    return title.strip()


def parse_filename_metadata(filepath: Path):
    """Extracts fallback artist and title from filename."""
    stem = filepath.stem
    stem = YOUTUBE_ID_PATTERN.sub('', stem)

    if " - " in stem:
        parts = stem.split(" - ", 1)
        artist = clean_title(parts[0])
        title = clean_title(parts[1])
        return artist, title

    return "", clean_title(stem)


def get_audio_metadata(filepath: Path):
    """Retrieves artist, title, and album from audio tags with fallback to filename."""
    artist, title, album = "", "", ""
    mut = get_mutagen()

    if mut and filepath.exists():
        ext = filepath.suffix.lower()
        if ext == ".mp3":
            try:
                audio = mut["MP3"](filepath)
                if audio.tags:
                    if "TIT2" in audio.tags:
                        title = str(audio.tags["TIT2"])
                    if "TPE1" in audio.tags:
                        artist = str(audio.tags["TPE1"])
                    if "TALB" in audio.tags:
                        album = str(audio.tags["TALB"])
            except Exception:
                pass
        elif ext == ".flac":
            try:
                audio = mut["FLAC"](filepath)
                if audio:
                    title = audio.get("title", [""])[0]
                    artist = audio.get("artist", [""])[0]
                    album = audio.get("album", [""])[0]
            except Exception:
                pass

    if not title:
        fn_artist, fn_title = parse_filename_metadata(filepath)
        title = fn_title
        if not artist:
            artist = fn_artist

    return clean_title(artist), clean_title(title), album


def query_lrclib(track_name: str, artist_name: str = "", album_name: str = "", duration: float = 0.0):
    """Queries the LRCLIB API for synchronized and plain lyrics."""
    clean_t = clean_title(track_name)
    clean_a = clean_title(artist_name)

    # 1. Exact GET request
    params = {"track_name": clean_t}
    if clean_a:
        params["artist_name"] = clean_a
    if album_name:
        params["album_name"] = album_name
    if duration > 0:
        params["duration"] = str(int(duration))

    headers = {"User-Agent": "MediaFetch/3.0 (https://github.com/rehamfarhan/scripts)"}
    url = f"https://lrclib.net/api/get?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("syncedLyrics") or data.get("plainLyrics"):
                    return data
    except Exception:
        pass

    # 2. Fallback Search request
    search_query = f"{clean_a} {clean_t}".strip() if clean_a else clean_t
    search_url = f"https://lrclib.net/api/search?{urllib.parse.urlencode({'q': search_query})}"

    try:
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                results = json.loads(response.read().decode("utf-8"))
                if results and isinstance(results, list):
                    for item in results:
                        if item.get("syncedLyrics"):
                            return item
                    for item in results:
                        if item.get("plainLyrics"):
                            return item
    except Exception:
        pass

    return None


def has_embedded_lyrics(filepath: Path) -> bool:
    """Checks if an audio file already has embedded lyrics in ID3 USLT or FLAC tags."""
    mut = get_mutagen()
    if not mut or not filepath.is_file():
        return False
    ext = filepath.suffix.lower()
    if ext == ".mp3":
        try:
            tags = mut["ID3"](filepath)
            return "USLT" in tags or len(tags.getall("USLT")) > 0
        except Exception:
            return False
    elif ext == ".flac":
        try:
            tags = mut["FLAC"](filepath)
            return "LYRICS" in tags or "UNSYNCEDLYRICS" in tags
        except Exception:
            return False
    return False


def strip_lrc_timestamps(lrc_text: str) -> str:
    """Strips [mm:ss.xx] timestamps and metadata tags from LRC content."""
    lines = lrc_text.splitlines()
    clean_lines = []
    for line in lines:
        if re.match(r'^\s*\[[a-zA-Z]+:', line):
            continue
        cleaned = re.sub(r'\[\d{2,}:\d{2}(?:\.\d{1,3})?\]', '', line).strip()
        if cleaned:
            clean_lines.append(cleaned)
    return "\n".join(clean_lines)


def focus_hyprland_terminal():
    """Brings the Hyprland terminal window into focus by switching to its workspace."""
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
                    stat_content = f.read()
                    parts = stat_content.split(")")
                    if len(parts) >= 2:
                        stat_fields = parts[-1].split()
                        curr_pid = int(stat_fields[1])
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


def embed_lyrics_in_file(filepath: Path, plain_lyrics: str, synced_lyrics: str):
    """Embeds lyrics into audio metadata (ID3 USLT / FLAC tags) & generates .lrc sidecar."""
    lyrics_content = synced_lyrics if synced_lyrics else plain_lyrics
    mut = get_mutagen()

    # 1. Create .lrc companion file for terminal music players (kew, cmus, etc.) if synced
    if synced_lyrics:
        lrc_path = filepath.with_suffix(".lrc")
        try:
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.write(synced_lyrics.strip() + "\n")
        except Exception:
            pass

    # 2. Embed into metadata frames for universal media players
    if mut:
        ext = filepath.suffix.lower()
        lyrics_text = plain_lyrics if plain_lyrics else synced_lyrics
        if not lyrics_text:
            return True

        if ext == ".mp3":
            try:
                try:
                    audio = mut["ID3"](filepath)
                except mut["ID3NoHeaderError"]:
                    audio = mut["ID3"]()

                audio.delall("USLT")
                audio.add(mut["USLT"](
                    encoding=mut["Encoding"].UTF8,
                    lang="eng",
                    desc="",
                    text=lyrics_text
                ))
                audio.save(filepath)
                return True
            except Exception:
                pass
        elif ext == ".flac":
            try:
                audio = mut["FLAC"](filepath)
                audio["LYRICS"] = lyrics_text
                audio["UNSYNCEDLYRICS"] = lyrics_text
                if synced_lyrics:
                    audio["SYNCEDLYRICS"] = synced_lyrics
                audio.save()
                return True
            except Exception:
                pass

    return True


def process_lyrics_for_file(filepath: Path) -> str:
    """Fetches and embeds lyrics for a single track. Returns status string."""
    artist, title, album = get_audio_metadata(filepath)
    if not title:
        return "[dim]No title[/]"

    duration = 0.0
    mut = get_mutagen()
    if mut and filepath.suffix.lower() == ".mp3":
        try:
            mp3_info = mut["MP3"](filepath)
            duration = mp3_info.info.length
        except Exception:
            pass

    data = query_lrclib(title, artist, album, duration)
    if not data:
        # Non-interactive: Simply skip if not found online
        return "[dim yellow]✗ Skipped[/]"

    synced = data.get("syncedLyrics") or ""
    plain = data.get("plainLyrics") or ""

    if not synced and not plain:
        return "[dim yellow]✗ Skipped[/]"

    embed_lyrics_in_file(filepath, plain, synced)
    return "[bold green]✓ Synced (.lrc)[/]" if synced else "[green]✓ Plain[/]"


# ==============================================================================
# Standalone Subcommands (.mfignore, attach, cleanup, batch lyrics)
# ==============================================================================

def get_mfignore_path(base_dir: Path = None) -> Path:
    """Returns the path to .mfignore (defaults to ~/Music/.mfignore)."""
    music_dir = Path.home() / "Music"
    if base_dir and base_dir.is_dir() and (base_dir / ".mfignore").exists():
        return base_dir / ".mfignore"
    if music_dir.exists():
        return music_dir / ".mfignore"
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
    """Checks if a given Path is matched by .mfignore."""
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


def select_with_fzf(items: list, prompt: str, allow_tab: bool = True) -> tuple:
    """Invokes fzf in a terminal subprocess with custom prompt and Tab support."""
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


def attach_unsynced_lyrics_from_lrc(audio_path: Path, lrc_path: Path) -> bool:
    """Embeds unsynchronized lyrics from an LRC file into metadata ONLY."""
    try:
        with open(lrc_path, "r", encoding="utf-8", errors="ignore") as f:
            raw_content = f.read()

        clean_text = strip_lrc_timestamps(raw_content)
        if not clean_text:
            safe_print(f"{YELLOW}[attach] Warning: No readable lyrics text in {lrc_path.name}{RESET}", file=sys.stderr)
            return False

        mut = get_mutagen()
        if mut:
            ext = audio_path.suffix.lower()
            if ext == ".mp3":
                try:
                    try:
                        audio = mut["ID3"](audio_path)
                    except mut["ID3NoHeaderError"]:
                        audio = mut["ID3"]()
                    audio.delall("USLT")
                    audio.add(mut["USLT"](encoding=mut["Encoding"].UTF8, lang="eng", desc="", text=clean_text))
                    audio.save(audio_path)
                    safe_print(f"{GREEN}✔ Successfully attached unsynchronized lyrics into ID3 tag for: {audio_path.name}{RESET}")
                    return True
                except Exception as e:
                    safe_print(f"{RED}[attach] Error embedding ID3 tag: {e}{RESET}", file=sys.stderr)
            elif ext == ".flac":
                try:
                    audio = mut["FLAC"](audio_path)
                    audio["LYRICS"] = clean_text
                    audio["UNSYNCEDLYRICS"] = clean_text
                    audio.save()
                    safe_print(f"{GREEN}✔ Successfully attached unsynchronized lyrics into FLAC tag for: {audio_path.name}{RESET}")
                    return True
                except Exception as e:
                    safe_print(f"{RED}[attach] Error embedding FLAC tags: {e}{RESET}", file=sys.stderr)
    except Exception as e:
        safe_print(f"{RED}[attach] Error reading LRC file: {e}{RESET}", file=sys.stderr)
    return False


def attach_lyrics_interactive(target_dir_str: str = None):
    """Interactive 2-step fzf lyrics attachment menu."""
    if not target_dir_str:
        target_dir = Path.home() / "Music"
    else:
        target_dir = Path(target_dir_str).expanduser().resolve()

    if not target_dir.exists() or not target_dir.is_dir():
        safe_print(f"{RED}[attach] Error: Directory not found: {target_dir}{RESET}", file=sys.stderr)
        return False

    safe_print(f"\n{BOLD}{CYAN}📎 Interactive Lyrics Attachment: Scanning {target_dir} ...{RESET}\n")

    audio_exts = {".mp3", ".flac", ".m4a", ".ogg", ".wav"}
    all_audio = sorted([
        f for f in target_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in audio_exts
    ])

    ignore_set = load_mfignore(target_dir)
    untagged_audio = [
        f for f in all_audio
        if not is_ignored(f, ignore_set, target_dir) and not has_embedded_lyrics(f)
    ]

    if not untagged_audio:
        safe_print(f"{GREEN}✔ All available audio file(s) already have lyrics or are in .mfignore!{RESET}\n")
        return True

    rel_audio_map = {str(f.relative_to(target_dir)): f for f in untagged_audio}
    audio_choices = sorted(list(rel_audio_map.keys()))

    while audio_choices:
        key, selected_rel_audio = select_with_fzf(audio_choices, "Step 1: Choose Track ([Tab] to hide to .mfignore)")
        if not selected_rel_audio:
            safe_print(f"{YELLOW}No audio file selected. Exiting.{RESET}")
            return False

        if key == "tab":
            add_to_mfignore(selected_rel_audio, target_dir)
            audio_choices.remove(selected_rel_audio)
            continue

        target_audio = rel_audio_map[selected_rel_audio]
        break

    lrc_files = sorted([f for f in target_dir.rglob("*.lrc") if f.is_file()])
    if not lrc_files:
        safe_print(f"{YELLOW}[attach] No local .lrc files found in library {target_dir}{RESET}")
        return False

    rel_lrc_map = {str(f.relative_to(target_dir)): f for f in lrc_files}
    lrc_choices = sorted(list(rel_lrc_map.keys()))

    _, selected_rel_lrc = select_with_fzf(lrc_choices, f"Step 2: Choose .lrc for '{target_audio.name}'", allow_tab=False)
    if not selected_rel_lrc:
        safe_print(f"{YELLOW}No lyrics file selected. Exiting.{RESET}")
        return False

    target_lrc = rel_lrc_map[selected_rel_lrc]
    return attach_unsynced_lyrics_from_lrc(target_audio, target_lrc)


def cleanup_directory(target_dir_str: str = None):
    """Recursively removes YouTube video IDs and title clutter from filenames."""
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


# ==============================================================================
# Superfile-Style Modular TUI Architecture & Dashboard
# ==============================================================================

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
    """Resolves profile aliases to canonical profile keys."""
    if not name:
        return "video"
    return PROFILE_ALIASES.get(name.lower(), name.lower())


class TrackItem:
    """Represents a single track in the download queue."""
    def __init__(self, idx: int, url: str, title: str, item_id: str = ""):
        self.idx = idx
        self.url = url
        self.title = title
        self.item_id = item_id
        self.status = "queued"  # "queued", "downloading", "processing", "done", "error"
        self.stage_text = "Queued"
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.speed = 0
        self.eta = 0
        self.percent = 0.0
        self.final_size_str = ""
        self.file_path = None
        self.artist = ""
        self.album = ""
        self.lyrics_status = ""  # "✓ Synced", "✓ Plain", "✗ Skipped"
        self.error_msg = ""


class DashboardState:
    """Thread-safe state store for the live dashboard."""
    def __init__(self, profile_name: str, target_dir: Path, items: list):
        self.lock = threading.Lock()
        self.profile_name = profile_name
        self.target_dir = target_dir
        self.items = items
        self.active_idx = 0
        self.total_speed = 0
        self.completed_count = 0
        self.synced_lyrics_count = 0
        self.skipped_lyrics_count = 0
        self.start_time = time.time()
        self.phase = "Downloading"  # "Downloading", "Lyrics", "Complete"


class QuietLogger:
    """Mutes noisy yt-dlp stdout/stderr to prevent breaking the live dashboard."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def format_bytes(num_bytes: int) -> str:
    """Formats byte counts into human-readable strings."""
    if not num_bytes or num_bytes <= 0:
        return ""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def render_dashboard(state: DashboardState, max_queue_rows: int = 10):
    """Renders the superfile-style modular multi-pane dashboard."""
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich import box

    with state.lock:
        items = list(state.items)
        active_idx = state.active_idx
        completed = state.completed_count
        total = len(items)
        prof_info = PROFILES.get(state.profile_name, {})
        format_desc = prof_info.get("format_desc", state.profile_name.upper())

        # Aggregate download speed
        total_speed = sum(it.speed for it in items if it.status == "downloading")
        speed_str = f"{total_speed / 1048576:.1f} MB/s" if total_speed > 0 else "Idle"

        # Active item for inspector
        inspect_item = items[active_idx] if 0 <= active_idx < len(items) else (items[0] if items else None)

    # 1. Root Layout
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3)
    )
    layout["main"].split_row(
        Layout(name="queue", ratio=2),
        Layout(name="details", ratio=1)
    )

    # 2. Header Panel
    target_short = str(state.target_dir).replace(str(Path.home()), "~")
    header_content = (
        f"[bold cyan]📥 Media Fetcher (mf)[/] [dim]•[/] "
        f"[bold white]{state.profile_name.upper()}[/] [dim]({format_desc})[/] [dim]➔[/] "
        f"[cyan]{target_short}[/] [dim]•[/] [bold white]{total} Track{'s' if total != 1 else ''}[/]"
    )
    layout["header"].update(Panel(header_content, box=box.ROUNDED, border_style="cyan"))

    # 3. Queue Table (Windowed to fit comfortably without vertical scrolling)
    if len(items) <= max_queue_rows:
        start_idx = 0
        end_idx = len(items)
    else:
        half = max_queue_rows // 2
        start_idx = max(0, min(active_idx - half, len(items) - max_queue_rows))
        end_idx = min(len(items), start_idx + max_queue_rows)

    visible_items = items[start_idx:end_idx]

    q_table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    q_table.add_column("num", width=6, style="dim")
    q_table.add_column("name", ratio=3, no_wrap=True)
    q_table.add_column("status", ratio=2, justify="right", no_wrap=True)

    for it in visible_items:
        idx_str = f"[{it.idx+1:02d}]"
        clean_name = it.title[:36]

        if it.status == "done":
            name_cell = f"[green]✓ {clean_name}[/]"
            status_cell = f"[dim]{it.final_size_str or 'Done'}[/] [green]✓[/]"
        elif it.status == "downloading":
            name_cell = f"[bold cyan]⠋ {clean_name}[/]"
            speed_txt = f"{it.speed/1048576:.1f}M/s" if it.speed else ""
            status_cell = f"[cyan]{it.percent:>3.0f}% {speed_txt}[/]"
        elif it.status == "processing":
            name_cell = f"[magenta]⚡ {clean_name}[/]"
            status_cell = f"[magenta]{it.stage_text}[/]"
        elif it.status == "error":
            name_cell = f"[red]✗ {clean_name}[/]"
            status_cell = "[red]Error[/]"
        else:
            name_cell = f"[dim]· {clean_name}[/]"
            status_cell = "[dim]Queued[/]"

        q_table.add_row(idx_str, name_cell, status_cell)

    window_label = f"Showing {start_idx+1}-{end_idx} of {total}" if total > max_queue_rows else f"{total} Item{'s' if total != 1 else ''}"
    layout["queue"].update(Panel(
        q_table,
        title=f"[bold cyan]📋 Download Queue [dim]({window_label})[/][/]",
        box=box.ROUNDED,
        border_style="blue"
    ))

    # 4. Inspector Panel (Active Item Metadata & Batch Gauge)
    d_table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    d_table.add_column("label", style="bold cyan", width=9)
    d_table.add_column("value", no_wrap=True)

    if inspect_item:
        d_table.add_row("Track:", f"[bold white]{inspect_item.title[:24]}[/]")
        d_table.add_row("Artist:", f"{inspect_item.artist[:24] or '[dim]Unknown[/]'}")
        d_table.add_row("Album:", f"{inspect_item.album[:24] or '[dim]Unknown[/]'}")
        d_table.add_row("Format:", f"[green]{format_desc}[/]")
        stage_style = "[magenta]" if inspect_item.status == "processing" else "[cyan]"
        d_table.add_row("Stage:", f"{stage_style}{inspect_item.stage_text}[/]")
    else:
        d_table.add_row("Status:", "[dim]Ready[/]")

    # Overall Batch Progress Bar
    pct_complete = (completed / total * 100) if total > 0 else 0
    filled = int(pct_complete / 10)
    bar_str = f"[green]{'━' * filled}[/][dim]{'━' * (10 - filled)}[/] {pct_complete:>3.0f}%"

    d_table.add_row("", "")
    d_table.add_row("Progress:", f"{completed}/{total} ({bar_str})")

    layout["details"].update(Panel(
        d_table,
        title="[bold cyan]ℹ️ Active Inspector[/]",
        box=box.ROUNDED,
        border_style="magenta"
    ))

    # 5. Footer Panel (Overall Metrics & Lyrics Summary)
    lyrics_txt = f"[bold green]{state.synced_lyrics_count} Synced[/] [dim]│[/] [dim yellow]{state.skipped_lyrics_count} Skipped[/]"
    footer_content = (
        f"[dim]🚀 Speed:[/] [bold green]{speed_str}[/] [dim]│[/] "
        f"[dim]Phase:[/] [bold cyan]{state.phase}[/] [dim]│[/] "
        f"[dim]🎵 Lyrics:[/] {lyrics_txt} [dim]│[/] "
        f"[dim]Completed:[/] [bold white]{completed}/{total}[/]"
    )
    layout["footer"].update(Panel(footer_content, box=box.ROUNDED, border_style="dim"))

    return layout


def build_ydl_options(profile_name: str, target_dir: Path, config: dict):
    """Builds native yt_dlp options dictionary corresponding to profile."""
    out_template = str(target_dir / "%(title)s [%(id)s].%(ext)s")

    opts = {
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": QuietLogger(),
    }

    # External aria2c downloader if available
    if shutil.which("aria2c"):
        aria_conns = str(config.get("aria2_connections", 8))
        opts["external_downloader"] = "aria2c"
        opts["external_downloader_args"] = [
            "-x", aria_conns,
            "-s", aria_conns,
            "-k", "1M"
        ]

    if profile_name in ("music", "audio"):
        opts.update({
            "format": "bestaudio/best",
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"},
                {"key": "FFmpegThumbnailsConvertor", "format": "png", "when": "before_dl"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ],
            "postprocessor_args": {
                "ThumbnailsConvertor": ["-vf", "crop=ih:ih"]
            }
        })
    elif profile_name == "flac":
        opts.update({
            "format": "bestaudio/best",
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "flac"},
                {"key": "FFmpegThumbnailsConvertor", "format": "png", "when": "before_dl"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ],
            "postprocessor_args": {
                "ThumbnailsConvertor": ["-vf", "crop=ih:ih"]
            }
        })
    elif profile_name == "podcast":
        opts.update({
            "format": "bestaudio/best",
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "opus"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ]
        })
    elif profile_name == "shorts":
        opts.update({
            "format": "bv*[height<=1080]+ba/best[height<=1080]",
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ]
        })
    elif profile_name == "archive":
        opts.update({
            "format": "bv*+ba/b",
            "writethumbnail": True,
            "writesubtitles": True,
            "allsubtitles": True,
            "postprocessors": [
                {"key": "FFmpegEmbedSubtitle"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ]
        })
    else:  # default: video
        opts.update({
            "format": "bv*[height<=1080]+ba/best[height<=1080]",
            "writethumbnail": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en.*"],
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mkv"},
                {"key": "FFmpegEmbedSubtitle"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ]
        })

    return opts


def download_track_worker(item: TrackItem, base_opts: dict, state: DashboardState):
    """Worker function to execute download and update state in real-time."""
    import yt_dlp

    ydl_opts = dict(base_opts)

    def progress_hook(d):
        status = d.get("status")
        if status == "downloading":
            item.status = "downloading"
            item.downloaded_bytes = d.get("downloaded_bytes") or 0
            item.total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            item.speed = d.get("speed") or 0
            if item.total_bytes > 0:
                item.percent = min(100.0, (item.downloaded_bytes / item.total_bytes) * 100)
            item.stage_text = "Downloading"
            with state.lock:
                state.active_idx = item.idx
        elif status == "finished":
            item.status = "processing"
            item.stage_text = "Processing..."

    def postprocessor_hook(d):
        item.status = "processing"
        pp = d.get("postprocessor", "")
        if pp == "ExtractAudio":
            item.stage_text = "Extracting Audio"
        elif pp == "FFmpegThumbnailsConvertor":
            item.stage_text = "Cropping Cover Art"
        elif pp == "EmbedThumbnail":
            item.stage_text = "Embedding Cover Art"
        elif pp == "FFmpegMetadata":
            item.stage_text = "Embedding Metadata"
        elif pp == "FFmpegVideoConvertor":
            item.stage_text = "Converting Video"

    ydl_opts["progress_hooks"] = [progress_hook]
    ydl_opts["postprocessor_hooks"] = [postprocessor_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(item.url, download=True)
            if not info:
                item.status = "error"
                item.stage_text = "Failed"
                return

            item.title = clean_title(info.get("title") or item.title)

            # Locate downloaded file path
            file_found = None
            if "requested_downloads" in info:
                for req in info["requested_downloads"]:
                    if "filepath" in req and os.path.exists(req["filepath"]):
                        file_found = Path(req["filepath"])
                        break

            if not file_found:
                prep_path = Path(ydl.prepare_filename(info))
                if prep_path.exists():
                    file_found = prep_path

            if file_found:
                item.file_path = file_found
                item.final_size_str = format_bytes(os.path.getsize(file_found))
                artist, title, album = get_audio_metadata(file_found)
                item.artist = artist
                item.album = album

            item.status = "done"
            item.stage_text = "Done"
            with state.lock:
                state.completed_count += 1

    except Exception as e:
        item.status = "error"
        item.stage_text = "Error"
        item.error_msg = str(e)


def render_final_summary_panel(state: DashboardState, console):
    """Renders the finalized, pristine superfile summary card."""
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE_HEAVY, expand=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Track Title", style="bold white", min_width=32)
    table.add_column("Size", style="cyan", width=10, justify="right")
    table.add_column("Status / Lyrics", style="green", width=18, justify="right")

    for idx, item in enumerate(state.items, 1):
        clean_name = item.title[:45]
        status_disp = item.lyrics_status or ("[green]✓ Saved[/]" if item.status == "done" else "[red]✗ Failed[/]")
        table.add_row(f"{idx:02d}", clean_name, item.final_size_str or "-", status_disp)

    target_short = str(state.target_dir).replace(str(Path.home()), "~")
    summary_panel = Panel(
        table,
        title=f"[bold cyan]📥 Download Complete [dim]• {len(state.items)} Track{'s' if len(state.items) != 1 else ''} ➔ {target_short}[/][/]",
        box=box.ROUNDED,
        border_style="cyan"
    )
    console.print()
    console.print(summary_panel)
    console.print()


def run_pipeline(profile_name: str, urls: list, target_dir: Path, config: dict):
    """Executes the superfile-style parallel dashboard download & lyrics pipeline."""
    import yt_dlp
    from rich.live import Live
    console = get_console()

    # Step 1: Pre-scan URLs & deduplicate playlist/album entries
    expanded_items = []
    seen_ids = set()

    with console.status("[bold cyan]🔍 Inspecting media streams & expanding playlists...[/]", spinner="dots"):
        ydl_flat_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "logger": QuietLogger()
        }
        with yt_dlp.YoutubeDL(ydl_flat_opts) as ydl:
            for url in urls:
                try:
                    info = ydl.extract_info(url, download=False)
                    if "entries" in info:
                        for entry in info["entries"]:
                            if not entry:
                                continue
                            eid = entry.get("id")
                            if eid and eid in seen_ids:
                                continue
                            if eid:
                                seen_ids.add(eid)

                            e_url = entry.get("url") or (f"https://www.youtube.com/watch?v={eid}" if eid else "")
                            e_title = clean_title(entry.get("title") or "Track")
                            if e_url:
                                expanded_items.append({
                                    "url": e_url,
                                    "id": eid or "",
                                    "title": e_title
                                })
                    else:
                        eid = info.get("id")
                        if eid and eid in seen_ids:
                            continue
                        if eid:
                            seen_ids.add(eid)
                        expanded_items.append({
                            "url": url,
                            "id": eid or "",
                            "title": clean_title(info.get("title") or "Media Item")
                        })
                except Exception:
                    expanded_items.append({
                        "url": url,
                        "id": "",
                        "title": "Media Item"
                    })

    if not expanded_items:
        console.print("[red]Error: No valid media items found to download.[/]")
        return 1

    # Initialize Dashboard State
    track_items = [
        TrackItem(idx, it["url"], it["title"], it.get("id", ""))
        for idx, it in enumerate(expanded_items)
    ]
    state = DashboardState(profile_name, target_dir, track_items)
    base_opts = build_ydl_options(profile_name, target_dir, config)
    max_workers = min(len(track_items), int(config.get("parallel_downloads", 3)))

    # Step 2: Phase 1 - Parallel Downloads with Live Dashboard
    stop_event = threading.Event()

    def ui_refresh_loop(live):
        while not stop_event.is_set():
            try:
                live.update(render_dashboard(state))
            except Exception:
                pass
            time.sleep(0.12)

    with Live(render_dashboard(state), console=console, refresh_per_second=8, screen=False) as live:
        refresher = threading.Thread(target=ui_refresh_loop, args=(live,), daemon=True)
        refresher.start()

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(download_track_worker, item, base_opts, state)
                    for item in track_items
                ]
                for f in as_completed(futures):
                    try:
                        f.result()
                    except Exception:
                        pass

            # Step 3: Phase 2 - Lyrics Processing (Completely Non-Interactive)
            profile_type = PROFILES.get(profile_name, {}).get("type", "video")
            if profile_type == "music":
                with state.lock:
                    state.phase = "Lyrics Tagging"

                for item in track_items:
                    if item.status == "done" and item.file_path:
                        with state.lock:
                            state.active_idx = item.idx
                            item.stage_text = "Fetching Lyrics"

                        # Non-interactive query
                        res = process_lyrics_for_file(item.file_path)
                        with state.lock:
                            item.lyrics_status = res
                            if "Synced" in res:
                                state.synced_lyrics_count += 1
                            elif "Skipped" in res:
                                state.skipped_lyrics_count += 1

            with state.lock:
                state.phase = "Complete"

        finally:
            stop_event.set()
            refresher.join(timeout=1.0)
            live.update(render_dashboard(state))

    # Step 4: Render Final Clean Summary
    render_final_summary_panel(state, console)
    return 0


# ==============================================================================
# Batch Local Lyrics Command (mf lyrics <DIR>)
# ==============================================================================

def process_local_lyrics_batch(target_path_str: str):
    """Processes lyrics fetching for a local directory using the Rich TUI."""
    target_path = Path(target_path_str).resolve()
    if not target_path.exists():
        safe_print(f"{RED}[lyrics] Error: Path not found: {target_path_str}{RESET}", file=sys.stderr)
        return False

    console = get_console()
    audio_extensions = {".mp3", ".flac", ".m4a", ".ogg", ".wav"}

    if target_path.is_file():
        audio_files = [target_path] if target_path.suffix.lower() in audio_extensions else []
    else:
        audio_files = sorted([
            f for f in target_path.rglob("*")
            if f.is_file() and f.suffix.lower() in audio_extensions
        ])

    if not audio_files:
        console.print(f"[yellow]No audio files found in: {target_path}[/]")
        return False

    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    console.print(f"\n[bold cyan]🎵 Lyrics Tagger:[/] Found {len(audio_files)} track(s) in [cyan]{target_path}[/]\n")
    results = []

    with Progress(
        SpinnerColumn("dots"),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=25),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Processing lyrics...", total=len(audio_files))
        for song_file in audio_files:
            status = process_lyrics_for_file(song_file)
            results.append((song_file.name, status))
            progress.advance(task)

    # Render Results Summary Table
    table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE_HEAVY, expand=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Track Title", style="bold white", min_width=32)
    table.add_column("Lyrics Status", justify="right")

    for idx, (filename, status) in enumerate(results, 1):
        table.add_row(f"{idx:02d}", filename[:45], status)

    console.print()
    console.print(Panel(table, title=f"[bold cyan]🎵 Lyrics Tagging Complete [dim]• {len(results)} Track{'s' if len(results) != 1 else ''}[/][/]", box=box.ROUNDED, border_style="cyan"))
    console.print()
    return True


# ==============================================================================
# Interactive Prompt & CLI Parsing
# ==============================================================================

def interactive_menu(config, clipboard_url=None):
    """Interactive TUI menu when run without arguments."""
    safe_print(f"\n{BOLD}{CYAN}=== 📥 Media Fetcher (mf) Interactive ==={RESET}\n")

    if clipboard_url:
        safe_print(f"{GREEN}📋 Clipboard URL detected: {BOLD}{clipboard_url}{RESET}\n")

    safe_print(f"{BOLD}Select Download Profile:{RESET}")
    profile_keys = list(PROFILES.keys())
    for idx, key in enumerate(profile_keys, 1):
        prof = PROFILES[key]
        alias_str = " (alias: audio)" if key == "music" else ""
        safe_print(f"  [{idx}] {BOLD}{key:<8}{RESET}{alias_str} - {prof['desc']}")

    choice = input(f"\n{BOLD}Choose profile (1-{len(profile_keys)}, default=1): {RESET}").strip()
    selected_profile = profile_keys[0]
    if choice.isdigit() and 1 <= int(choice) <= len(profile_keys):
        selected_profile = profile_keys[int(choice) - 1]

    if clipboard_url:
        use_clip = input(f"{BOLD}Use clipboard URL? (Y/n): {RESET}").strip().lower()
        if use_clip not in ['n', 'no']:
            return selected_profile, [clipboard_url], None

    url_input = input(f"{BOLD}Enter Media URL(s) (space-separated): {RESET}").strip()
    if not url_input:
        safe_print(f"{RED}No URL provided. Exiting.{RESET}")
        sys.exit(1)

    urls = url_input.split()
    return selected_profile, urls, None


def main():
    check_dependencies()
    config = load_config()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(
        description="Media Fetcher (mf) - Superfile-style modular TUI media downloader & tagger",
        add_help=False
    )

    parser.add_argument("profile_or_url", nargs="?", help="Profile name (video, music, audio, etc.) or URL")
    parser.add_argument("urls", nargs="*", help="Additional URLs")
    parser.add_argument("--list", action="store_true", help="Inspect available video/audio streams (-F)")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive menu")
    parser.add_argument("-o", "--output-dir", help="Override output directory")
    parser.add_argument("--update", action="store_true", help="Update yt-dlp executable")
    parser.add_argument("-h", "--help", action="store_true", help="Show help menu")

    args, unknown = parser.parse_known_args()

    # Subcommand: attach
    if args.profile_or_url == "attach":
        target = args.urls[0] if args.urls else None
        attach_lyrics_interactive(target)
        sys.exit(0)

    # Subcommand: cleanup
    if args.profile_or_url == "cleanup":
        target = args.urls[0] if args.urls else None
        cleanup_directory(target)
        sys.exit(0)

    # Subcommand: lyrics (batch process local files)
    if args.profile_or_url == "lyrics":
        targets = args.urls
        if not targets:
            safe_print(f"{RED}Usage: mf lyrics <file1.mp3> [dir_or_file2 ...]{RESET}")
            sys.exit(1)
        for t in targets:
            process_local_lyrics_batch(t)
        sys.exit(0)

    # Subcommand: update
    if args.update:
        safe_print(f"\n{CYAN}Checking for yt-dlp updates...{RESET}")
        try:
            subprocess.run(["yt-dlp", "-U"])
        except Exception as e:
            safe_print(f"{RED}Update failed: {e}{RESET}")
        sys.exit(0)

    # Subcommand: help
    if args.help:
        safe_print(f"\n{BOLD}{CYAN}📥 Media Fetcher (mf){RESET}")
        safe_print(f"\n{BOLD}Usage:{RESET}")
        safe_print("  mf [PROFILE] <URL...>")
        safe_print("  mf [OPTIONS]")
        safe_print(f"\n{BOLD}Profiles:{RESET}")
        for k, v in PROFILES.items():
            alias_str = " (or 'audio')" if k == "music" else ""
            safe_print(f"  {BOLD}{k:<10}{RESET}{alias_str:<12} {v['desc']}")
        safe_print(f"\n{BOLD}Options:{RESET}")
        safe_print("  -i, --interactive       Launch interactive prompt")
        safe_print("  --list <URL>            Inspect available stream formats")
        safe_print("  -o, --output-dir <PATH> Custom output directory")
        safe_print("  attach [DIR]            Interactive fzf picker to attach lyrics to untagged audio")
        safe_print("  cleanup [DIR]           Remove YouTube IDs & clutter from filenames (Defaults to ~/Music)")
        safe_print("  lyrics <FILE/DIR...>    Fetch & embed lyrics into local audio files or folder")
        safe_print("  --update                Update yt-dlp")
        safe_print("  -h, --help              Show this help banner")
        safe_print()
        sys.exit(0)

    raw_profile = args.profile_or_url or ""
    resolved_profile = resolve_profile_name(raw_profile)

    # Format stream list (--list)
    if args.list:
        target_url = raw_profile or (args.urls[0] if args.urls else None)
        if not target_url or raw_profile in PROFILES or raw_profile in PROFILE_ALIASES:
            target_url = args.urls[0] if args.urls else None
        if not target_url:
            clip_url = get_clipboard_url()
            if clip_url:
                target_url = clip_url
        if not target_url:
            safe_print(f"{RED}Error: Please specify a URL to inspect format streams.{RESET}")
            sys.exit(1)
        subprocess.run(["yt-dlp", "-F", target_url])
        sys.exit(0)

    # Profile & URL Resolution
    profile_name = "video"
    urls = []
    custom_out_dir = args.output_dir

    if args.interactive or (not args.profile_or_url and not args.urls):
        clip_url = get_clipboard_url()
        profile_name, urls, custom_out_dir = interactive_menu(config, clip_url)
    elif raw_profile in PROFILES or raw_profile in PROFILE_ALIASES:
        profile_name = resolved_profile
        urls = args.urls
        if not urls:
            clip_url = get_clipboard_url()
            if clip_url:
                safe_print(f"{GREEN}📋 Auto-detected URL from clipboard: {BOLD}{clip_url}{RESET}")
                urls = [clip_url]
            else:
                safe_print(f"{RED}Error: Profile '{raw_profile}' specified but no URL provided or found in clipboard.{RESET}")
                sys.exit(1)
    else:
        # Direct URL passed without profile: defaults to video
        profile_name = "video"
        urls = [raw_profile] + args.urls

    # Target directory routing
    profile = PROFILES[profile_name]
    if custom_out_dir:
        target_dir = Path(custom_out_dir).expanduser().resolve()
    else:
        if profile["type"] == "music":
            target_dir = Path(config.get("music_dir", DEFAULT_MUSIC_DIR)).expanduser().resolve()
        else:
            target_dir = Path(config.get("video_dir", DEFAULT_VIDEO_DIR)).expanduser().resolve()

    target_dir.mkdir(parents=True, exist_ok=True)

    # Execute superfile-style pipeline
    ret = run_pipeline(profile_name, urls, target_dir, config)
    sys.exit(ret)


if __name__ == "__main__":
    main()
