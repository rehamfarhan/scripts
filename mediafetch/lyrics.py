#!/usr/bin/env python3
"""
mediafetch.lyrics - LRCLIB Client, Metadata Extraction, ID3/FLAC Tagging, and Non-Interactive Pipeline
"""

import sys
import os
import re
import json
import urllib.request
import urllib.parse
from pathlib import Path

try:
    from .utils import (
        clean_title,
        get_mutagen,
        get_console,
        safe_print,
        select_with_fzf,
        load_mfignore,
        add_to_mfignore,
        is_ignored,
        CYAN,
        GREEN,
        YELLOW,
        RED,
        BOLD,
        RESET,
        YOUTUBE_ID_PATTERN,
    )
except ImportError:
    from utils import (
        clean_title,
        get_mutagen,
        get_console,
        safe_print,
        select_with_fzf,
        load_mfignore,
        add_to_mfignore,
        is_ignored,
        CYAN,
        GREEN,
        YELLOW,
        RED,
        BOLD,
        RESET,
        YOUTUBE_ID_PATTERN,
    )


def parse_filename_metadata(filepath: Path) -> tuple[str, str]:
    """Extracts fallback artist and title from filename."""
    stem = filepath.stem
    stem = YOUTUBE_ID_PATTERN.sub('', stem)

    if " - " in stem:
        parts = stem.split(" - ", 1)
        artist = clean_title(parts[0])
        title = clean_title(parts[1])
        return artist, title

    return "", clean_title(stem)


def get_audio_metadata(filepath: Path) -> tuple[str, str, str]:
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


def query_lrclib(track_name: str, artist_name: str = "", album_name: str = "", duration: float = 0.0) -> dict | None:
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


def embed_lyrics_in_file(filepath: Path, plain_lyrics: str, synced_lyrics: str) -> bool:
    """Embeds lyrics into audio metadata (ID3 USLT / FLAC tags) & generates .lrc sidecar."""
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
    """Fetches and embeds lyrics for a single track. 100% non-interactive."""
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


def attach_lyrics_interactive(target_dir_str: str = None) -> bool:
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

    target_audio = None
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

    if not target_audio:
        return False

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


def process_local_lyrics_batch(target_path_str: str) -> bool:
    """Batch processes lyrics fetching for a local directory using Rich Progress."""
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
