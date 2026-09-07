#!/usr/bin/env python3
"""
mediafetch.downloader - Parallel Download Manager with Instant Startup & Graceful Cancellation
"""

import sys
import os
import time
import shutil
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from .utils import clean_title, format_bytes, PROFILES, PROFILE_ALIASES, resolve_profile_name
    from .lyrics import get_audio_metadata
except ImportError:
    from utils import clean_title, format_bytes, PROFILES, PROFILE_ALIASES, resolve_profile_name
    from lyrics import get_audio_metadata


def is_playlist_url(url: str) -> bool:
    """Checks whether a URL points to a playlist or album."""
    u = url.lower()
    return "list=" in u or "/playlist" in u or "/sets/" in u or "/album/" in u


class TrackItem:
    """Represents a single track or video in the pipeline."""
    def __init__(self, idx: int, url: str, title: str, item_id: str = "", artist: str = "", album: str = ""):
        self.idx = idx
        self.url = url
        self.title = title
        self.item_id = item_id
        self.artist = artist
        self.album = album

        # Fallback parse "Artist - Title" if present
        if not self.artist and " - " in self.title:
            parts = self.title.split(" - ", 1)
            self.artist = parts[0].strip()
            self.title = parts[1].strip()

        self.status = "queued"  # "queued", "downloading", "processing", "done", "error"
        self.stage_text = "Queued"
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.speed = 0.0
        self.eta = 0
        self.percent = 0.0
        self.final_size_str = ""
        self.file_path = None
        self.lyrics_status = ""  # "✓ Synced", "✓ Plain", "✗ Skipped"
        self.error_msg = ""


class DashboardState:
    """Thread-safe coordinator for the live full-screen dashboard."""
    def __init__(self, profile_name: str, target_dir: Path, items: list[TrackItem], nolyrics: bool = False):
        self.lock = threading.Lock()
        self.profile_name = profile_name
        self.target_dir = target_dir
        self.items = items
        self.nolyrics = nolyrics
        self.active_idx = 0
        self.total_speed = 0.0
        self.completed_count = 0
        self.synced_lyrics_count = 0
        self.skipped_lyrics_count = 0
        self.start_time = time.time()
        self.phase = "Downloading"  # "Downloading", "Lyrics Tagging", "Complete", "Aborted"
        self.aborted = False

    def get_progress_info(self) -> tuple[float, str, str]:
        """Calculates current overall progress percentage and descriptive strings."""
        with self.lock:
            total_items = len(self.items)
            completed = self.completed_count
            active = self.items[self.active_idx] if (0 <= self.active_idx < total_items) else None
            is_music = PROFILES.get(self.profile_name, {}).get("type") == "music"

            if total_items == 1 and active:
                pct = active.percent
                size_str = f" ({format_bytes(active.downloaded_bytes)} / {format_bytes(active.total_bytes) or '?'})" if active.total_bytes > 0 else ""
                label = "Track" if is_music else "Download"
                title = f"⚡ {label} Progress: {pct:.0f}%{size_str}"
                sub = f"{format_bytes(active.downloaded_bytes)} of {format_bytes(active.total_bytes) or '?'}"
                return pct, title, sub
            else:
                pct = (completed / total_items * 100) if total_items > 0 else 0.0
                unit = "Tracks" if is_music else "Videos"
                phase_label = "Batch Progress" if self.phase != "Lyrics Tagging" else "Lyrics Tagging Progress"
                title = f"⚡ {phase_label}: {pct:.0f}% ({completed}/{total_items} {unit})"
                sub = f"{completed} of {total_items} Completed"
                return pct, title, sub


class QuietLogger:
    """Silences noisy yt-dlp console prints to protect the TUI alternate screen."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def prepare_track_items(
    urls: list[str],
    shutdown_event: threading.Event = None,
    cookie_file: Path = None
) -> list[TrackItem]:
    """Expands playlist URLs if needed, or immediately returns direct TrackItems (<0.01s)."""
    has_playlist = any(is_playlist_url(u) for u in urls)
    if not has_playlist:
        items = []
        for idx, u in enumerate(urls):
            fallback_title = "Resolving Stream..." if len(urls) == 1 else f"Media Item {idx+1}"
            items.append(TrackItem(idx, u, fallback_title))
        return items

    import yt_dlp
    expanded = []
    seen_ids = set()
    flat_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "logger": QuietLogger(),
    }
    if cookie_file and Path(cookie_file).exists():
        flat_opts["cookiefile"] = str(cookie_file)
    with yt_dlp.YoutubeDL(flat_opts) as ydl:
        for u in urls:
            if shutdown_event and shutdown_event.is_set():
                break
            if not is_playlist_url(u):
                expanded.append({"url": u, "title": "Media Item"})
                continue
            try:
                info = ydl.extract_info(u, download=False)
                playlist_title = clean_title(info.get("title") or "") if info else ""
                playlist_uploader = clean_title(info.get("uploader") or info.get("channel") or "") if info else ""

                if info and "entries" in info:
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
                        e_artist = clean_title(entry.get("artist") or entry.get("uploader") or playlist_uploader)
                        e_album = clean_title(entry.get("album") or playlist_title)

                        if e_url:
                            expanded.append({
                                "url": e_url,
                                "id": eid or "",
                                "title": e_title,
                                "artist": e_artist,
                                "album": e_album
                            })
                else:
                    eid = info.get("id") if info else None
                    if eid and eid in seen_ids:
                        continue
                    if eid:
                        seen_ids.add(eid)
                    expanded.append({
                        "url": u,
                        "id": eid or "",
                        "title": clean_title(info.get("title") or "Media Item") if info else "Media Item",
                        "artist": clean_title(info.get("artist") or info.get("uploader") or ""),
                        "album": clean_title(info.get("album") or "")
                    })
            except Exception:
                expanded.append({"url": u, "title": "Media Item"})

    if not expanded:
        for idx, u in enumerate(urls):
            expanded.append({"url": u, "title": "Media Item"})

    return [
        TrackItem(
            i,
            it["url"],
            it.get("title", "Media Item"),
            it.get("id", ""),
            it.get("artist", ""),
            it.get("album", "")
        )
        for i, it in enumerate(expanded)
    ]


def build_ydl_options(
    profile_name: str,
    target_dir: Path,
    config: dict,
    cookie_file: Path = None
) -> dict:
    """Builds native yt_dlp options dictionary corresponding to profile."""
    out_template = str(target_dir / "%(title)s [%(id)s].%(ext)s")

    opts = {
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": QuietLogger(),
    }

    if cookie_file and Path(cookie_file).exists():
        opts["cookiefile"] = str(cookie_file)

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
                {"key": "FFmpegThumbnailsConvertor", "format": "png", "when": "before_dl"},
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ],
            "postprocessor_args": {
                "thumbnailsconvertor": ["-vf", "crop=min(iw\\,ih):min(iw\\,ih)"],
                "ThumbnailsConvertor": ["-vf", "crop=min(iw\\,ih):min(iw\\,ih)"],
            }
        })
    elif profile_name == "flac":
        opts.update({
            "format": "bestaudio/best",
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegThumbnailsConvertor", "format": "png", "when": "before_dl"},
                {"key": "FFmpegExtractAudio", "preferredcodec": "flac"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ],
            "postprocessor_args": {
                "thumbnailsconvertor": ["-vf", "crop=min(iw\\,ih):min(iw\\,ih)"],
                "ThumbnailsConvertor": ["-vf", "crop=min(iw\\,ih):min(iw\\,ih)"],
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
            "subtitleslangs": ["en", "en-US", "en-GB"],
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mkv"},
                {"key": "FFmpegEmbedSubtitle"},
                {"key": "EmbedThumbnail"},
                {"key": "FFmpegMetadata"},
            ]
        })

    return opts


def is_age_restricted_error(err_str: str) -> bool:
    """Checks if an error string indicates YouTube age-restriction / sign-in requirement."""
    lower = err_str.lower()
    return any(p in lower for p in [
        "confirm your age",
        "age-restricted",
        "sign in to confirm",
        "login required",
        "use --cookies"
    ])


def is_cookie_invalid_error(err_str: str) -> bool:
    """Checks if an error string indicates expired or invalid cookies."""
    lower = err_str.lower()
    return any(p in lower for p in [
        "cookies are no longer valid",
        "cookies are expired",
        "could not decrypt"
    ])


def download_track_worker(
    item: TrackItem,
    base_opts: dict,
    state: DashboardState,
    shutdown_event: threading.Event,
    cookie_file: Path = None,
    cookies_mode: str = "auto"
):
    """Executes download of a single track with real-time cancellation check and cookie fallback."""
    if shutdown_event.is_set():
        item.status = "error"
        item.stage_text = "Aborted"
        return

    import yt_dlp
    ydl_opts = dict(base_opts)

    # If user configured 'always' mode and cookie_file exists, use cookies immediately
    if cookies_mode == "always" and cookie_file and Path(cookie_file).exists():
        ydl_opts["cookiefile"] = str(cookie_file)

    def progress_hook(d):
        if shutdown_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Download aborted by user")

        status = d.get("status")
        if status == "downloading":
            item.status = "downloading"
            item.downloaded_bytes = d.get("downloaded_bytes") or 0
            item.total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            item.speed = float(d.get("speed") or 0)
            if item.total_bytes > 0:
                item.percent = min(100.0, (item.downloaded_bytes / item.total_bytes) * 100)
            item.stage_text = "Downloading"

            info_dict = d.get("info_dict")
            if info_dict:
                if "title" in info_dict and info_dict["title"]:
                    clean_t = clean_title(info_dict["title"])
                    if clean_t and clean_t != "Resolving Stream...":
                        item.title = clean_t
                if not item.artist:
                    item.artist = clean_title(info_dict.get("artist") or info_dict.get("creator") or info_dict.get("uploader") or "")
                if not item.album and "album" in info_dict:
                    item.album = clean_title(info_dict.get("album") or "")

            with state.lock:
                state.active_idx = item.idx

        elif status == "finished":
            item.status = "processing"
            item.stage_text = "Processing..."

    def postprocessor_hook(d):
        if shutdown_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Download aborted by user")

        item.status = "processing"
        pp = d.get("postprocessor", "")
        if pp == "ExtractAudio":
            item.stage_text = "Extracting Audio"
        elif pp == "FFmpegThumbnailsConvertor":
            item.stage_text = "Cropping Cover Art"
        elif pp == "EmbedThumbnail":
            item.stage_text = "Embedding Thumbnail"
        elif pp == "FFmpegMetadata":
            item.stage_text = "Embedding Metadata"
        elif pp == "FFmpegVideoConvertor":
            item.stage_text = "Converting Video"
        elif pp == "FFmpegEmbedSubtitle":
            item.stage_text = "Embedding Subtitles"

    ydl_opts["progress_hooks"] = [progress_hook]
    ydl_opts["postprocessor_hooks"] = [postprocessor_hook]

    def execute_dl(opts_dict):
        with yt_dlp.YoutubeDL(opts_dict) as ydl_inst:
            if shutdown_event.is_set():
                raise yt_dlp.utils.DownloadCancelled("Download aborted by user")
            info_res = ydl_inst.extract_info(item.url, download=True)
            return info_res, ydl_inst

    try:
        info, ydl = execute_dl(ydl_opts)
    except yt_dlp.utils.DownloadCancelled:
        item.status = "error"
        item.stage_text = "Aborted"
        return
    except Exception as e:
        if shutdown_event.is_set():
            item.status = "error"
            item.stage_text = "Aborted"
            return

        err_str = str(e)
        age_restricted = is_age_restricted_error(err_str)

        # Automatic retry with cookies if available and not yet attempted
        if age_restricted and cookie_file and Path(cookie_file).exists() and "cookiefile" not in ydl_opts and not shutdown_event.is_set():
            item.stage_text = "Retrying (Cookies)"
            retry_opts = dict(ydl_opts)
            retry_opts["cookiefile"] = str(cookie_file)
            try:
                info, ydl = execute_dl(retry_opts)
            except yt_dlp.utils.DownloadCancelled:
                item.status = "error"
                item.stage_text = "Aborted"
                return
            except Exception as retry_err:
                retry_str = str(retry_err)
                item.status = "error"
                if is_cookie_invalid_error(retry_str) or is_age_restricted_error(retry_str):
                    item.stage_text = "Expired Cookies" if is_cookie_invalid_error(retry_str) else "Age Restricted"
                    item.error_msg = "Age-restricted video: YouTube cookies expired or invalid"
                else:
                    item.stage_text = "Error"
                    item.error_msg = retry_str
                return
        else:
            item.status = "error"
            if age_restricted:
                item.stage_text = "Age Restricted"
                item.error_msg = "Age-restricted video: requires YouTube cookies"
            elif is_cookie_invalid_error(err_str):
                item.stage_text = "Expired Cookies"
                item.error_msg = "YouTube cookies in cookies.txt are no longer valid"
            else:
                item.stage_text = "Error"
                item.error_msg = err_str
            return

    if not info:
        item.status = "error"
        item.stage_text = "Failed"
        return

    if "title" in info and info["title"]:
        item.title = clean_title(info["title"])
    if "artist" in info and info["artist"]:
        item.artist = clean_title(info["artist"])
    if "album" in info and info["album"]:
        item.album = clean_title(info["album"])

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
        is_music = PROFILES.get(state.profile_name, {}).get("type") == "music"
        if is_music:
            artist, title, album = get_audio_metadata(file_found)
            if artist:
                item.artist = artist
            if album:
                item.album = album

    item.status = "done"
    item.stage_text = "Done"
    with state.lock:
        state.completed_count += 1


def cleanup_partial_downloads(target_dir: Path):
    """Deletes incomplete .part or .ytdl files left behind on abort."""
    try:
        for p in target_dir.glob("*.part*"):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        for p in target_dir.glob("*.ytdl*"):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        pass
