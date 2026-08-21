#!/usr/bin/env python3
"""
embed_lyrics.py - Lyrics Fetcher & Metadata Embedder for mediafetch (mf)

Fetches synchronized and unsynchronized lyrics from LRCLIB and embeds them
into audio metadata (ID3v2 USLT / SYLT) while creating matching .lrc sidecar
files for terminal music players like kew.
"""

import sys
import os
import re
import json
import urllib.request
import urllib.parse
from pathlib import Path

try:
    from mutagen.id3 import ID3, USLT, TIT2, TPE1, TALB, Encoding, ID3NoHeaderError
    from mutagen.mp3 import MP3
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False


def clean_title(title: str) -> str:
    """Removes noise and clutter common in YouTube video titles."""
    # Strip YouTube ID at end of title if present: e.g., "Song [dQw4w9WgXcQ]"
    title = re.sub(r'\s*\[[a-zA-Z0-9_-]{11}\]$', '', title)
    
    # Strip common suffixes/brackets
    patterns = [
        r'\s*[\(\[](official\s*(music\s*)?(video|audio|visualizer|lyric\s*video|hd|4k|4k\s*remaster)?|lyrics?|audio|remastered|remaster\s*\d*|video)[\)\]]',
        r'\s*[\(\[]ft\.?|\s*feat\.?.*[\)\]]',
        r'\s*[\(\[]HD[\)\]]',
        r'\s*[\(\[]HQ[\)\]]',
        r'\s*[\(\[]4K[\)\]]',
    ]
    cleaned = title
    for p in patterns:
        cleaned = re.sub(p, '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def parse_filename_metadata(filepath: Path):
    """Extracts fallback artist and title from filename."""
    stem = filepath.stem
    # Remove youtube ID at end
    stem = re.sub(r'\s*\[[a-zA-Z0-9_-]{11}\]$', '', stem)
    
    if " - " in stem:
        parts = stem.split(" - ", 1)
        artist = clean_title(parts[0])
        title = clean_title(parts[1])
        return artist, title
    
    return "", clean_title(stem)


def get_audio_metadata(filepath: Path):
    """Retrieves artist, title, and album from ID3 tags or filename."""
    artist, title, album = "", "", ""
    
    if MUTAGEN_AVAILABLE and filepath.suffix.lower() == ".mp3":
        try:
            tags = ID3(filepath)
            if "TIT2" in tags:
                title = str(tags["TIT2"])
            if "TPE1" in tags:
                artist = str(tags["TPE1"])
            if "TALB" in tags:
                album = str(tags["TALB"])
        except (ID3NoHeaderError, Exception):
            pass

    # Fallback to filename parsing if tags are missing or generic
    if not title or not artist:
        fn_artist, fn_title = parse_filename_metadata(filepath)
        if not title:
            title = fn_title
        if not artist:
            artist = fn_artist

    return clean_title(artist), clean_title(title), clean_title(album)


def query_lrclib(title: str, artist: str = "", album: str = "", duration: float = 0.0):
    """Queries the LRCLIB API for lyrics."""
    headers = {"User-Agent": "mediafetch/1.0 (https://github.com/rehamfarhan/scripts)"}
    
    # 1. Try exact get if artist and title are available
    if title and artist:
        params = {"track_name": title, "artist_name": artist}
        if album:
            params["album_name"] = album
        if duration > 0:
            params["duration"] = int(duration)
            
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

    # 2. Fallback to full-text search
    query_str = f"{artist} {title}".strip()
    if not query_str:
        return None

    search_url = f"https://lrclib.net/api/search?{urllib.parse.urlencode({'q': query_str})}"
    req = urllib.request.Request(search_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                results = json.loads(resp.read().decode("utf-8"))
                if results and isinstance(results, list) and len(results) > 0:
                    # Prefer first result with lyrics
                    for item in results:
                        if item.get("syncedLyrics") or item.get("plainLyrics"):
                            return item
    except Exception:
        pass

    return None


def embed_lyrics_in_file(filepath: Path, plain_lyrics: str, synced_lyrics: str):
    """Embeds USLT frame into MP3 file and writes .lrc companion file."""
    # 1. Write .lrc sidecar file (for kew and players supporting .lrc)
    lyrics_content = synced_lyrics if synced_lyrics else plain_lyrics
    if lyrics_content:
        lrc_path = filepath.with_suffix(".lrc")
        try:
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.write(lyrics_content.strip() + "\n")
        except Exception as e:
            print(f"  [lyrics] Warning: Could not write .lrc file: {e}", file=sys.stderr)

    # 2. Embed into ID3 metadata (USLT frame for MP3)
    if MUTAGEN_AVAILABLE and filepath.suffix.lower() == ".mp3":
        try:
            try:
                audio = ID3(filepath)
            except ID3NoHeaderError:
                audio = ID3()

            # Embed plain lyrics in USLT frame (standard for ID3v2)
            lyrics_text = plain_lyrics if plain_lyrics else synced_lyrics
            if lyrics_text:
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
            print(f"  [lyrics] Warning: Could not embed ID3 USLT tag: {e}", file=sys.stderr)
            return False

    return True


def process_audio_file(file_str: str):
    """Main processor for a single audio file."""
    filepath = Path(file_str).resolve()
    if not filepath.exists() or not filepath.is_file():
        print(f"[lyrics] Error: File not found: {file_str}", file=sys.stderr)
        return False

    artist, title, album = get_audio_metadata(filepath)
    if not title:
        print(f"[lyrics] Could not determine title for {filepath.name}", file=sys.stderr)
        return False

    display_name = f"{artist} - {title}" if artist else title
    print(f"\n[lyrics] Fetching lyrics for: {display_name} ...")

    # Get duration if mutagen is available
    duration = 0.0
    if MUTAGEN_AVAILABLE and filepath.suffix.lower() == ".mp3":
        try:
            mp3_info = MP3(filepath)
            duration = mp3_info.info.length
        except Exception:
            pass

    data = query_lrclib(title, artist, album, duration)
    if not data:
        print(f"[lyrics] No lyrics found on LRCLIB for: {display_name}")
        return False

    synced = data.get("syncedLyrics") or ""
    plain = data.get("plainLyrics") or ""

    embed_lyrics_in_file(filepath, plain, synced)

    lyric_type = "synchronized (.lrc + ID3)" if synced else "plain text (ID3)"
    print(f"[lyrics] ✓ Successfully embedded {lyric_type} for: {display_name}")
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: embed_lyrics.py <audio_file> [audio_file2 ...]")
        sys.exit(1)

    for target in sys.argv[1:]:
        process_audio_file(target)


if __name__ == "__main__":
    main()
