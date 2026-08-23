#!/usr/bin/env python3
"""
mediafetch (mf) - High-Performance Profile-Based Media Downloader & Tagging Pipeline

Converts videos, music, audio, podcasts, shorts, and archives using yt-dlp, aria2c, ffmpeg,
and LRCLIB lyrics tag embedding.
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ANSI Color Codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Mutagen import for audio metadata & lyrics tagging
try:
    from mutagen.id3 import ID3, USLT, TIT2, TPE1, TALB, Encoding, ID3NoHeaderError
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

# Default configuration paths
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
    "sub_langs": "en.*"
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
    deps = ["yt-dlp", "ffmpeg"]
    missing = [dep for dep in deps if not shutil.which(dep)]
    
    if missing:
        print(f"\n{RED}{BOLD}Error: Missing required system dependencies: {', '.join(missing)}{RESET}\n")
        for m in missing:
            if m == "yt-dlp":
                print("  Arch Linux:    sudo pacman -S yt-dlp")
                print("  Debian/Ubuntu: sudo apt install yt-dlp")
            elif m == "ffmpeg":
                print("  Arch Linux:    sudo pacman -S ffmpeg")
                print("  Debian/Ubuntu: sudo apt install ffmpeg")
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


def cleanup_directory(target_dir_str: str = None):
    """Recursively removes YouTube video IDs and title clutter from filenames and .lrc sidecars."""
    if not target_dir_str:
        target_dir = Path.home() / "Music"
    else:
        target_dir = Path(target_dir_str).expanduser().resolve()

    if not target_dir.exists() or not target_dir.is_dir():
        print(f"{RED}[cleanup] Error: Directory not found: {target_dir}{RESET}", file=sys.stderr)
        return False

    print(f"\n{BOLD}{CYAN}🧹 Filename Cleanup Engine: Scanning {target_dir} ...{RESET}\n")

    valid_extensions = {".mp3", ".flac", ".m4a", ".ogg", ".wav", ".lrc", ".webp", ".png", ".jpg"}
    all_files = sorted([
        f for f in target_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in valid_extensions
    ])

    if not all_files:
        print(f"{YELLOW}[cleanup] No matching media or lyrics files found in: {target_dir}{RESET}\n")
        return True

    renamed_count = 0
    for file_path in all_files:
        old_stem = file_path.stem
        cleaned_stem = clean_title(old_stem)
        
        if cleaned_stem and cleaned_stem != old_stem:
            new_file_path = file_path.with_name(cleaned_stem + file_path.suffix)
            if new_file_path.exists() and new_file_path != file_path:
                print(f"  {YELLOW}⚠️  Skipped (Target exists): {file_path.name} -> {new_file_path.name}{RESET}")
                continue
            
            try:
                file_path.rename(new_file_path)
                renamed_count += 1
                print(f"  {GREEN}✔ Renamed:{RESET} {BOLD}{file_path.name}{RESET}\n    {CYAN}➜ {new_file_path.name}{RESET}")
            except Exception as e:
                print(f"  {RED}✖ Error renaming {file_path.name}: {e}{RESET}")

    print(f"\n{BOLD}{GREEN}✨ Cleanup Complete! Renamed {renamed_count} file(s) in {target_dir}.{RESET}\n")
    return True


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
    """Retrieves artist, title, and album from ID3 / FLAC tags or filename."""
    artist, title, album = "", "", ""
    
    if MUTAGEN_AVAILABLE:
        ext = filepath.suffix.lower()
        if ext == ".mp3":
            try:
                tags = ID3(filepath)
                if "TIT2" in tags: title = str(tags["TIT2"])
                if "TPE1" in tags: artist = str(tags["TPE1"])
                if "TALB" in tags: album = str(tags["TALB"])
            except Exception:
                pass
        elif ext == ".flac":
            try:
                tags = FLAC(filepath)
                if "title" in tags: title = tags["title"][0]
                if "artist" in tags: artist = tags["artist"][0]
                if "album" in tags: album = tags["album"][0]
            except Exception:
                pass

    if not title or not artist:
        fn_artist, fn_title = parse_filename_metadata(filepath)
        if not title: title = fn_title
        if not artist: artist = fn_artist

    return clean_title(artist), clean_title(title), clean_title(album)


def query_lrclib(title: str, artist: str = "", album: str = "", duration: float = 0.0):
    """Queries LRCLIB API for synced & unsynced lyrics."""
    headers = {"User-Agent": "mediafetch/2.0 (https://github.com/rehamfarhan/scripts)"}
    
    # 1. Try exact match if title & artist are present
    if title and artist:
        params = {"track_name": title, "artist_name": artist}
        if album: params["album_name"] = album
        if duration > 0: params["duration"] = int(duration)
            
        url = f"https://lrclib.net/api/get?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("syncedLyrics") or data.get("plainLyrics"):
                        return data
        except Exception:
            pass

    # 2. Fallback to general search query
    query_str = f"{artist} {title}".strip()
    if not query_str:
        return None

    search_url = f"https://lrclib.net/api/search?{urllib.parse.urlencode({'q': query_str})}"
    req = urllib.request.Request(search_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                results = json.loads(resp.read().decode("utf-8"))
                if results and isinstance(results, list):
                    for item in results:
                        if item.get("syncedLyrics") or item.get("plainLyrics"):
                            return item
    except Exception:
        pass

    return None


def has_embedded_lyrics(filepath: Path) -> bool:
    """Checks if an audio file already has embedded lyrics in ID3 USLT or FLAC tags."""
    if not MUTAGEN_AVAILABLE or not filepath.is_file():
        return False
    ext = filepath.suffix.lower()
    if ext == ".mp3":
        try:
            tags = ID3(filepath)
            return "USLT" in tags or len(tags.getall("USLT")) > 0
        except Exception:
            return False
    elif ext == ".flac":
        try:
            tags = FLAC(filepath)
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
            c_pid = target_client.get("pid")
            ws_name = target_client.get("workspace", {}).get("name")
            subprocess.run(["hyprctl", "dispatch", "focuswindow", f"pid:{c_pid}"], capture_output=True)
            if ws_name:
                subprocess.run(["hyprctl", "dispatch", "workspace", str(ws_name)], capture_output=True)
    except Exception:
        pass


def select_with_fzf(items: list, prompt: str, timeout_sec: int = None) -> str:
    """Invokes fzf in a terminal subprocess with custom prompt and optional timeout."""
    if not items or not shutil.which("fzf"):
        return None

    # Automatically focus Hyprland terminal window & workspace
    focus_hyprland_terminal()

    try:
        cmd = ["fzf", "--prompt", f"{prompt} > ", "--height", "40%", "--border", "--ansi"]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        stdout, _ = proc.communicate(input="\n".join(items), timeout=timeout_sec)
        if proc.returncode == 0 and stdout:
            res = stdout.strip()
            if res.startswith("[Skip") or res == "":
                return None
            return res
    except subprocess.TimeoutExpired:
        proc.kill()
        print(f"\n{YELLOW}[fzf] Selection timed out ({timeout_sec}s). Skipping.{RESET}")
    except Exception:
        pass
    return None


def attach_unsynced_lyrics_from_lrc(audio_path: Path, lrc_path: Path) -> bool:
    """Reads lrc file, strips timestamps, and embeds unsynchronized lyrics into metadata ONLY (no sidecar)."""
    try:
        with open(lrc_path, "r", encoding="utf-8", errors="ignore") as f:
            raw_content = f.read()
        
        clean_text = strip_lrc_timestamps(raw_content)
        if not clean_text:
            print(f"{YELLOW}[attach] Warning: No readable lyrics text in {lrc_path.name}{RESET}", file=sys.stderr)
            return False

        if MUTAGEN_AVAILABLE:
            ext = audio_path.suffix.lower()
            if ext == ".mp3":
                try:
                    try:
                        audio = ID3(audio_path)
                    except ID3NoHeaderError:
                        audio = ID3()
                    audio.delall("USLT")
                    audio.add(USLT(encoding=Encoding.UTF8, lang="eng", desc="", text=clean_text))
                    audio.save(audio_path)
                    print(f"{GREEN}✔ Successfully attached unsynchronized lyrics into ID3 tag for: {audio_path.name}{RESET}")
                    return True
                except Exception as e:
                    print(f"{RED}[attach] Error embedding ID3 tag: {e}{RESET}", file=sys.stderr)
            elif ext == ".flac":
                try:
                    audio = FLAC(audio_path)
                    audio["LYRICS"] = clean_text
                    audio["UNSYNCEDLYRICS"] = clean_text
                    audio.save()
                    print(f"{GREEN}✔ Successfully attached unsynchronized lyrics into FLAC tag for: {audio_path.name}{RESET}")
                    return True
                except Exception as e:
                    print(f"{RED}[attach] Error embedding FLAC tags: {e}{RESET}", file=sys.stderr)
    except Exception as e:
        print(f"{RED}[attach] Error reading LRC file: {e}{RESET}", file=sys.stderr)
    return False


def attach_lyrics_interactive(target_dir_str: str = None):
    """Two-step interactive fzf lyrics attachment menu (only shows untagged audio files)."""
    if not target_dir_str:
        target_dir = Path.home() / "Music"
    else:
        target_dir = Path(target_dir_str).expanduser().resolve()

    if not target_dir.exists() or not target_dir.is_dir():
        print(f"{RED}[attach] Error: Directory not found: {target_dir}{RESET}", file=sys.stderr)
        return False

    print(f"\n{BOLD}{CYAN}📎 Interactive Lyrics Attachment: Scanning {target_dir} ...{RESET}\n")

    audio_exts = {".mp3", ".flac", ".m4a", ".ogg", ".wav"}
    all_audio = sorted([
        f for f in target_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in audio_exts
    ])

    # Step 1: Filter for untagged audio files (files without embedded lyrics)
    untagged_audio = [f for f in all_audio if not has_embedded_lyrics(f)]
    if not untagged_audio:
        print(f"{GREEN}✔ All {len(all_audio)} audio file(s) in {target_dir} already have embedded lyrics!{RESET}\n")
        return True

    # Build relative paths for fzf menu display
    rel_audio_map = {str(f.relative_to(target_dir)): f for f in untagged_audio}
    audio_choices = sorted(list(rel_audio_map.keys()))

    print(f"{CYAN}Step 1: Select untagged audio file ({len(untagged_audio)} untagged / {len(all_audio)} total)...{RESET}")
    selected_rel_audio = select_with_fzf(audio_choices, "Step 1: Choose Audio Track to Attach Lyrics To")
    if not selected_rel_audio:
        print(f"{YELLOW}No audio file selected. Exiting.{RESET}")
        return False

    target_audio = rel_audio_map[selected_rel_audio]

    # Step 2: Select local .lrc file
    lrc_files = sorted([
        f for f in target_dir.rglob("*.lrc")
        if f.is_file()
    ])
    if not lrc_files:
        print(f"{YELLOW}[attach] No local .lrc files found in library {target_dir}{RESET}")
        return False

    rel_lrc_map = {str(f.relative_to(target_dir)): f for f in lrc_files}
    lrc_choices = sorted(list(rel_lrc_map.keys()))

    print(f"{CYAN}Step 2: Select local .lrc file to attach to {target_audio.name}...{RESET}")
    selected_rel_lrc = select_with_fzf(lrc_choices, f"Step 2: Choose .lrc File for '{target_audio.name}'")
    if not selected_rel_lrc:
        print(f"{YELLOW}No lyrics file selected. Exiting.{RESET}")
        return False

    target_lrc = rel_lrc_map[selected_rel_lrc]
    return attach_unsynced_lyrics_from_lrc(target_audio, target_lrc)


def embed_lyrics_in_file(filepath: Path, plain_lyrics: str, synced_lyrics: str):
    """Embeds lyrics into audio metadata (ID3 USLT / FLAC tags) & generates .lrc sidecar."""
    lyrics_content = synced_lyrics if synced_lyrics else plain_lyrics
    
    # 1. Create .lrc companion file for terminal music players (kew, cmus, etc.)
    if lyrics_content:
        lrc_path = filepath.with_suffix(".lrc")
        try:
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.write(lyrics_content.strip() + "\n")
        except Exception as e:
            print(f"  {YELLOW}[lyrics] Warning: Could not write .lrc file: {e}{RESET}", file=sys.stderr)

    # 2. Embed into metadata frames for universal media player compatibility (VLC, Lollypop, Amberol, etc.)
    if MUTAGEN_AVAILABLE:
        ext = filepath.suffix.lower()
        lyrics_text = plain_lyrics if plain_lyrics else synced_lyrics
        if not lyrics_text:
            return True

        if ext == ".mp3":
            try:
                try:
                    audio = ID3(filepath)
                except ID3NoHeaderError:
                    audio = ID3()

                audio.delall("USLT")
                audio.add(USLT(
                    encoding=Encoding.UTF8,
                    lang="eng",
                    desc="",
                    text=lyrics_text
                ))
                audio.save(filepath)
                return True
            except Exception as e:
                print(f"  {YELLOW}[lyrics] Warning: Could not embed ID3 USLT tag: {e}{RESET}", file=sys.stderr)
        elif ext == ".flac":
            try:
                audio = FLAC(filepath)
                audio["LYRICS"] = lyrics_text
                audio["UNSYNCEDLYRICS"] = lyrics_text
                if synced_lyrics:
                    audio["SYNCEDLYRICS"] = synced_lyrics
                audio.save()
                return True
            except Exception as e:
                print(f"  {YELLOW}[lyrics] Warning: Could not embed FLAC lyrics tags: {e}{RESET}", file=sys.stderr)

    return True


def _process_single_audio_file(filepath: Path, current_idx: int = 0, total_files: int = 0):
    """Processes lyrics fetching and embedding for a single resolved audio file Path."""
    artist, title, album = get_audio_metadata(filepath)
    if not title:
        print(f"{YELLOW}[lyrics] Could not determine track title for {filepath.name}{RESET}", file=sys.stderr)
        return False

    display_name = f"{artist} - {title}" if artist else title
    counter_str = f"[{current_idx}/{total_files}] " if total_files > 1 else ""
    print(f"\n{CYAN}🎤 {counter_str}Fetching lyrics for: {BOLD}{display_name}{RESET} ({filepath.name}) ...")

    duration = 0.0
    if MUTAGEN_AVAILABLE and filepath.suffix.lower() == ".mp3":
        try:
            mp3_info = MP3(filepath)
            duration = mp3_info.info.length
        except Exception:
            pass

    data = query_lrclib(title, artist, album, duration)
    if not data:
        print(f"{YELLOW}[lyrics] No online lyrics found on LRCLIB for: {display_name}{RESET}")
        
        # Local .lrc fallback selector via fzf
        music_library_dir = Path.home() / "Music"
        search_dir = filepath.parent if filepath.parent.exists() else music_library_dir
        lrc_files = sorted([f for f in search_dir.rglob("*.lrc") if f.is_file()])
        if not lrc_files and music_library_dir.exists():
            lrc_files = sorted([f for f in music_library_dir.rglob("*.lrc") if f.is_file()])

        if lrc_files and shutil.which("fzf"):
            rel_map = {}
            for f in lrc_files:
                try:
                    rel_map[str(f.relative_to(music_library_dir))] = f
                except Exception:
                    rel_map[str(f.name)] = f
            
            choices = ["[Skip / No Lyrics]"] + sorted(list(rel_map.keys()))
            print(f"{CYAN}💡 Opening local .lrc fallback picker for '{filepath.name}' (auto-skips in 5s)...{RESET}")
            sel = select_with_fzf(choices, f"Attach Local .lrc to '{filepath.name}'", timeout_sec=5)
            if sel and sel in rel_map:
                chosen_lrc = rel_map[sel]
                return attach_unsynced_lyrics_from_lrc(filepath, chosen_lrc)

        return False

    synced = data.get("syncedLyrics") or ""
    plain = data.get("plainLyrics") or ""

    embed_lyrics_in_file(filepath, plain, synced)
    lyric_type = "synchronized (.lrc + ID3/FLAC)" if synced else "plain text (ID3/FLAC)"
    print(f"{GREEN}✔ Successfully embedded {lyric_type} for: {display_name}{RESET}")
    return True


def process_lyrics_target(file_str: str):
    """Processes lyrics fetching for a single audio file OR recursively for an entire directory."""
    filepath = Path(file_str).resolve()
    if not filepath.exists():
        print(f"{RED}[lyrics] Error: Path not found: {file_str}{RESET}", file=sys.stderr)
        return False

    if filepath.is_dir():
        audio_extensions = {".mp3", ".flac", ".m4a", ".ogg", ".wav"}
        audio_files = sorted([
            f for f in filepath.rglob("*")
            if f.is_file() and f.suffix.lower() in audio_extensions
        ])

        if not audio_files:
            print(f"{YELLOW}[lyrics] No audio files found in directory: {filepath}{RESET}")
            return False

        print(f"\n{BOLD}{CYAN}🎵 Batch Lyrics Engine: Found {len(audio_files)} audio track(s) in {filepath}{RESET}")
        success_count = 0
        total_count = len(audio_files)

        # Process batch concurrently with thread pool for faster performance
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_file = {
                executor.submit(_process_single_audio_file, song_file, idx, total_count): song_file
                for idx, song_file in enumerate(audio_files, 1)
            }
            for future in as_completed(future_to_file):
                try:
                    if future.result():
                        success_count += 1
                except Exception as e:
                    print(f"{RED}[lyrics] Error processing track: {e}{RESET}", file=sys.stderr)

        print(f"\n{BOLD}{GREEN}✨ Batch Complete! Successfully fetched & embedded lyrics for {success_count}/{total_count} track(s).{RESET}\n")
        return True

    return _process_single_audio_file(filepath)


# ==============================================================================
# Execution Profiles & Download Engine
# ==============================================================================

PROFILES = {
    "video": {
        "desc": "1080p H.265 MKV video with English subtitles",
        "type": "video",
        "format": "bv*[height<=1080]+ba/best[height<=1080]",
        "flags": [
            "--embed-thumbnail",
            "--convert-thumbnails", "png",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs", "en.*",
            "--embed-subs",
            "--recode-video", "mkv"
        ]
    },
    "music": {
        "desc": "High-quality MP3 with square album art & embedded lyrics",
        "type": "music",
        "format": "bestaudio",
        "flags": [
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--embed-thumbnail",
            "--convert-thumbnails", "png",
            "--embed-metadata",
            "--ppa", "ThumbnailsConvertor:-vf crop=ih:ih",
            "--exec", f'post_process:python3 "{SCRIPT_PATH}" --embed-lyrics-file {{}}'
        ]
    },
    "flac": {
        "desc": "Lossless FLAC audio with square album art & embedded lyrics",
        "type": "music",
        "format": "bestaudio",
        "flags": [
            "--extract-audio",
            "--audio-format", "flac",
            "--embed-thumbnail",
            "--convert-thumbnails", "png",
            "--embed-metadata",
            "--ppa", "ThumbnailsConvertor:-vf crop=ih:ih",
            "--exec", f'post_process:python3 "{SCRIPT_PATH}" --embed-lyrics-file {{}}'
        ]
    },
    "shorts": {
        "desc": "1080p MP4 optimized for vertical video (Shorts, Reels, TikTok)",
        "type": "video",
        "format": "bv*[height<=1080]+ba/best[height<=1080]",
        "flags": [
            "--embed-thumbnail",
            "--convert-thumbnails", "png",
            "--recode-video", "mp4"
        ]
    },
    "podcast": {
        "desc": "Audio-only Opus format with embedded metadata & thumbnail",
        "type": "music",
        "format": "bestaudio",
        "flags": [
            "--extract-audio",
            "--audio-format", "opus",
            "--embed-thumbnail",
            "--embed-metadata"
        ]
    },
    "archive": {
        "desc": "Maximum quality video & audio preservation with all subtitles",
        "type": "video",
        "format": "bv*+ba/b",
        "flags": [
            "--embed-thumbnail",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs", "all",
            "--embed-subs"
        ]
    }
}

# Profile Aliases (e.g. 'audio' maps to 'music')
PROFILE_ALIASES = {
    "audio": "music"
}


def resolve_profile_name(name: str) -> str:
    """Resolves profile aliases to canonical profile keys."""
    if not name:
        return "video"
    return PROFILE_ALIASES.get(name.lower(), name.lower())


def interactive_menu(config, clipboard_url=None):
    """Interactive TUI menu when run without arguments."""
    print(f"\n{BOLD}{CYAN}=== 📥 Media Fetcher (mf) Interactive ==={RESET}\n")
    
    if clipboard_url:
        print(f"{GREEN}📋 Clipboard URL detected: {BOLD}{clipboard_url}{RESET}\n")
    
    print(f"{BOLD}Select Download Profile:{RESET}")
    profile_keys = list(PROFILES.keys())
    for idx, key in enumerate(profile_keys, 1):
        prof = PROFILES[key]
        alias_str = " (alias: audio)" if key == "music" else ""
        print(f"  [{idx}] {BOLD}{key:<8}{RESET}{alias_str} - {prof['desc']}")
    
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
        print(f"{RED}No URL provided. Exiting.{RESET}")
        sys.exit(1)
        
    urls = url_input.split()
    return selected_profile, urls, None


def main():
    check_dependencies()
    config = load_config()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(
        description="Media Fetcher (mf) - Robust profile-based yt-dlp wrapper & tagger",
        add_help=False
    )
    
    parser.add_argument("profile_or_url", nargs="?", help="Profile name (video, music, audio, etc.) or URL")
    parser.add_argument("urls", nargs="*", help="Additional URLs")
    parser.add_argument("--list", action="store_true", help="Inspect available video/audio streams (-F)")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive menu")
    parser.add_argument("-o", "--output-dir", help="Override output directory")
    parser.add_argument("--embed-lyrics-file", help="Internal/Standalone trigger for embedding lyrics")
    parser.add_argument("--update", action="store_true", help="Update yt-dlp executable")
    parser.add_argument("-h", "--help", action="store_true", help="Show help menu")
    
    args, unknown = parser.parse_known_args()

    # Handle internal/standalone lyrics trigger
    if args.embed_lyrics_file:
        process_lyrics_target(args.embed_lyrics_file)
        sys.exit(0)

    # Handle standalone 'attach' subcommand (e.g., mf attach or mf attach ~/Music)
    if args.profile_or_url == "attach":
        target = args.urls[0] if args.urls else None
        attach_lyrics_interactive(target)
        sys.exit(0)

    # Handle standalone 'cleanup' subcommand (e.g., mf cleanup or mf cleanup ~/Music/Downloads)
    if args.profile_or_url == "cleanup":
        target = args.urls[0] if args.urls else None
        cleanup_directory(target)
        sys.exit(0)

    # Handle standalone 'lyrics' subcommand (e.g., mf lyrics song.mp3 or mf lyrics ~/Music)
    if args.profile_or_url == "lyrics":
        targets = args.urls
        if not targets:
            print(f"{RED}Usage: mf lyrics <file1.mp3> [dir_or_file2 ...]{RESET}")
            sys.exit(1)
        for t in targets:
            process_lyrics_target(t)
        sys.exit(0)

    # Handle yt-dlp updater
    if args.update:
        print(f"\n{CYAN}Checking for yt-dlp updates...{RESET}")
        try:
            subprocess.run(["yt-dlp", "-U"])
        except Exception as e:
            print(f"{RED}Update failed: {e}{RESET}")
        sys.exit(0)

    # Handle Help
    if args.help:
        print(f"\n{BOLD}{CYAN}📥 Media Fetcher (mf){RESET}")
        print(f"\n{BOLD}Usage:{RESET}")
        print("  mf [PROFILE] <URL...>")
        print("  mf [OPTIONS]")
        print(f"\n{BOLD}Profiles:{RESET}")
        for k, v in PROFILES.items():
            alias_str = " (or 'audio')" if k == "music" else ""
            print(f"  {BOLD}{k:<10}{RESET}{alias_str:<12} {v['desc']}")
        print(f"\n{BOLD}Options:{RESET}")
        print("  -i, --interactive       Launch interactive prompt")
        print("  --list <URL>            Inspect available stream formats")
        print("  -o, --output-dir <PATH> Custom output directory (Defaults to ~/Downloads)")
        print("  attach [DIR]            Interactive fzf picker to attach lyrics to untagged audio")
        print("  cleanup [DIR]           Remove YouTube IDs & clutter from filenames (Defaults to ~/Music)")
        print("  lyrics <FILE/DIR...>    Fetch & embed lyrics into local audio files or folder")
        print("  --update                Update yt-dlp")
        print("  -h, --help              Show this help banner")
        print()
        sys.exit(0)

    # Resolve potential profile alias (e.g. 'audio' -> 'music')
    raw_profile = args.profile_or_url or ""
    resolved_profile = resolve_profile_name(raw_profile)

    # Handle Format Stream List (--list)
    if args.list:
        target_url = raw_profile or (args.urls[0] if args.urls else None)
        if not target_url or raw_profile in PROFILES or raw_profile in PROFILE_ALIASES:
            target_url = args.urls[0] if args.urls else None
        if not target_url:
            clip_url = get_clipboard_url()
            if clip_url:
                target_url = clip_url
        if not target_url:
            print(f"{RED}Error: Please specify a URL to inspect format streams.{RESET}")
            sys.exit(1)
        subprocess.run(["yt-dlp", "-F", target_url])
        sys.exit(0)

    # Determine Profile, URLs, and Target Directory
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
                print(f"{GREEN}📋 Auto-detected URL from clipboard: {BOLD}{clip_url}{RESET}")
                urls = [clip_url]
            else:
                print(f"{RED}Error: Profile '{raw_profile}' specified but no URL provided or found in clipboard.{RESET}")
                sys.exit(1)
    else:
        # User passed URL directly without specifying profile: e.g. mf "https://..."
        profile_name = "video"
        urls = [raw_profile] + args.urls

    profile = PROFILES[profile_name]

    # Destination directory routing
    if custom_out_dir:
        target_dir = Path(custom_out_dir).expanduser().resolve()
    else:
        if profile["type"] == "music":
            target_dir = Path(config.get("music_dir", DEFAULT_MUSIC_DIR)).expanduser().resolve()
        else:
            target_dir = Path(config.get("video_dir", DEFAULT_VIDEO_DIR)).expanduser().resolve()

    target_dir.mkdir(parents=True, exist_ok=True)

    # Build yt-dlp Command Flags
    out_template = str(target_dir / "%(title)s [%(id)s].%(ext)s")
    
    cmd = [
        "yt-dlp",
        "--newline",
        "-f", profile["format"],
        "-o", out_template
    ]

    # Add aria2c downloader if available
    if shutil.which("aria2c"):
        aria_conns = str(config.get("aria2_connections", 8))
        cmd.extend([
            "--downloader", "aria2c",
            "--downloader-args", f"aria2c:-x {aria_conns} -s {aria_conns}"
        ])

    cmd.extend(profile["flags"])
    cmd.extend(unknown)
    cmd.extend(urls)

    print(f"\n{BOLD}{CYAN}📥 Media Fetcher (mf){RESET}")
    print(f"  {BOLD}Profile   :{RESET} {profile_name} ({profile['desc']})")
    print(f"  {BOLD}Target Dir:{RESET} {target_dir}")
    print(f"  {BOLD}Targets   :{RESET} {len(urls)} URL(s)\n")

    res = subprocess.run(cmd)
    sys.exit(res.returncode)


if __name__ == "__main__":
    main()
