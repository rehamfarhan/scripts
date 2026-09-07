#!/usr/bin/env python3
"""
mediafetch (mf) - High-Performance Profile-Based Media Downloader & Tagging Pipeline

Modular architecture:
  - utils: Config, paths, sanitization, .mfignore, cleanup
  - lyrics: LRCLIB API, ID3/FLAC embedding, non-interactive tagging
  - downloader: Multi-threaded engine, instant startup, cancellation
  - tui: Alternate-buffer full-screen dashboard with cut-in borders
"""

import sys
import os
import re
import signal
import shutil
import argparse
import subprocess
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Lightweight top-level imports (<0.01s)
try:
    from .utils import (
        load_config,
        find_cookie_file,
        safe_print,
        get_clipboard_url,
        check_dependencies,
        cleanup_directory,
        PROFILES,
        PROFILE_ALIASES,
        resolve_profile_name,
        DEFAULT_MUSIC_DIR,
        DEFAULT_VIDEO_DIR,
        CACHE_DIR,
        CYAN,
        GREEN,
        YELLOW,
        RED,
        BOLD,
        RESET,
    )
except ImportError:
    from utils import (
        load_config,
        find_cookie_file,
        safe_print,
        get_clipboard_url,
        check_dependencies,
        cleanup_directory,
        PROFILES,
        PROFILE_ALIASES,
        resolve_profile_name,
        DEFAULT_MUSIC_DIR,
        DEFAULT_VIDEO_DIR,
        CACHE_DIR,
        CYAN,
        GREEN,
        YELLOW,
        RED,
        BOLD,
        RESET,
    )


def run_pipeline(
    profile_name: str,
    urls: list[str],
    target_dir: Path,
    config: dict,
    cookie_file: Path = None,
    nolyrics: bool = False
) -> int:
    """Orchestrates the full-screen alternate-buffer download & tagging pipeline."""
    # Lazily import heavy rendering & downloader engines
    try:
        from .utils import get_console
        from .lyrics import process_lyrics_for_file
        from .downloader import (
            prepare_track_items,
            build_ydl_options,
            download_track_worker,
            cleanup_partial_downloads,
            DashboardState,
        )
        from .tui import (
            render_dashboard,
            render_final_summary_panel,
            KeyboardListener,
        )
    except ImportError:
        from utils import get_console
        from lyrics import process_lyrics_for_file
        from downloader import (
            prepare_track_items,
            build_ydl_options,
            download_track_worker,
            cleanup_partial_downloads,
            DashboardState,
        )
        from tui import (
            render_dashboard,
            render_final_summary_panel,
            KeyboardListener,
        )

    from rich.live import Live
    console = get_console()

    shutdown_event = threading.Event()

    def sig_handler(signum, frame):
        shutdown_event.set()

    # Hook OS interrupt signals
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    # Fast track preparation (<0.01s for single URLs)
    track_items, playlist_title = prepare_track_items(urls, shutdown_event, cookie_file=cookie_file)
    if not track_items or shutdown_event.is_set():
        if shutdown_event.is_set():
            safe_print(f"\n{YELLOW}Cancelled.{RESET}\n")
            return 130
        safe_print(f"{RED}Error: No media tracks found to download.{RESET}\n")
        return 1

    # Route into album subfolder if enabled and multi-track playlist detected
    if playlist_title and config.get("album_subfolders", True) and len(track_items) > 1:
        safe_album = re.sub(r'[\/\\:*?"<>|]', '', playlist_title).strip()
        if safe_album:
            target_dir = target_dir / safe_album
            target_dir.mkdir(parents=True, exist_ok=True)

    cookies_mode = config.get("cookies_mode", "auto")
    initial_cookie = cookie_file if cookies_mode == "always" else None

    state = DashboardState(profile_name, target_dir, track_items, nolyrics=nolyrics)
    base_opts = build_ydl_options(profile_name, target_dir, config, cookie_file=initial_cookie)
    max_workers = min(len(track_items), int(config.get("parallel_downloads", 3)))

    # Start non-blocking keyboard listener ('q' to abort, 'c' to clear completed)
    keyboard = KeyboardListener(shutdown_event, state)
    keyboard.start()

    stop_ui_thread = threading.Event()

    def ui_refresh_loop(live):
        while not stop_ui_thread.is_set():
            try:
                curr_w, curr_h = console.size
                live.update(render_dashboard(state, curr_w, curr_h))
            except Exception:
                pass
            time.sleep(0.10)

    try:
        # Enter Alternate Screen Buffer (screen=True)
        init_w, init_h = console.size
        with Live(
            render_dashboard(state, init_w, init_h),
            console=console,
            refresh_per_second=10,
            screen=True
        ) as live:
            ui_thread = threading.Thread(target=ui_refresh_loop, args=(live,), daemon=True)
            ui_thread.start()

            try:
                # Phase 1: Parallel Downloads
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [
                        executor.submit(
                            download_track_worker,
                            item,
                            base_opts,
                            state,
                            shutdown_event,
                            cookie_file=cookie_file,
                            cookies_mode=cookies_mode
                        )
                        for item in track_items
                    ]
                    for f in as_completed(futures):
                        if shutdown_event.is_set():
                            break
                        try:
                            f.result()
                        except Exception:
                            pass

                # Phase 2: Lyrics Tagging (100% Non-Interactive)
                profile_type = PROFILES.get(profile_name, {}).get("type", "video")
                if profile_type == "music" and not nolyrics and not shutdown_event.is_set():
                    with state.lock:
                        state.phase = "Lyrics Tagging"

                    for item in track_items:
                        if shutdown_event.is_set():
                            break
                        if item.status == "done" and item.file_path:
                            with state.lock:
                                state.active_idx = item.idx
                                item.stage_text = "Fetching Lyrics"

                            # Query and embed
                            res = process_lyrics_for_file(item.file_path)
                            with state.lock:
                                item.lyrics_status = res
                                if "Synced" in res or "Exists" in res or "Tagged" in res:
                                    state.synced_lyrics_count += 1
                                elif "Skipped" in res:
                                    state.skipped_lyrics_count += 1

                with state.lock:
                    state.end_time = time.time()
                    if shutdown_event.is_set():
                        state.phase = "Aborted"
                    else:
                        state.phase = "Complete"

            finally:
                stop_ui_thread.set()
                ui_thread.join(timeout=0.5)
                try:
                    curr_w, curr_h = console.size; live.update(render_dashboard(state, curr_w, curr_h))
                except Exception:
                    pass

    finally:
        keyboard.stop()

    # Clean up and print post-screen summaries
    if shutdown_event.is_set():
        cleanup_partial_downloads(target_dir)
        console.print()
        console.print("[bold yellow]⚡ Download aborted by user. Cleaned up partial files.[/]")
        console.print()
        return 130

    # Automatically strip YouTube IDs and clutter from filenames post-session
    if config.get("auto_cleanup", True) and not shutdown_event.is_set():
        cleanup_directory(str(target_dir), quiet=True)

    # Print final pristine summary card into normal terminal scrollback
    render_final_summary_panel(state, console)
    return 0


def interactive_menu(config: dict, clipboard_url: str = None) -> tuple[str, list[str], str | None]:
    """Interactive CLI menu when run without arguments."""
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
        description="Media Fetcher (mf) - Full-screen alternate-buffer modular media downloader & tagger",
        add_help=False
    )

    parser.add_argument("profile_or_url", nargs="?", help="Profile name (video, music, flac, etc.) or URL")
    parser.add_argument("urls", nargs="*", help="Additional URLs")
    parser.add_argument("--list", action="store_true", help="Inspect available video/audio streams (-F)")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive menu")
    parser.add_argument("-o", "--output-dir", help="Override output directory")
    parser.add_argument("-c", "--cookies", help="Path to Netscape-format cookies.txt file")
    parser.add_argument("-f", "--force", action="store_true", help="Force re-fetching lyrics even if already present")
    parser.add_argument("--nolyrics", action="store_true", help="Skip fetching and embedding lyrics for audio tracks")
    parser.add_argument("--no-album-dir", action="store_true", help="Do not create a subfolder for albums or playlists")
    parser.add_argument("--update", action="store_true", help="Update yt-dlp executable")
    parser.add_argument("-h", "--help", action="store_true", help="Show help menu")

    args, unknown = parser.parse_known_args()
    if args.no_album_dir:
        config["album_subfolders"] = False
    cookie_file = find_cookie_file(args.cookies, config)

    # Subcommand: attach
    if args.profile_or_url == "attach":
        try:
            from .lyrics import attach_lyrics_interactive
        except ImportError:
            from lyrics import attach_lyrics_interactive
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
        try:
            from .lyrics import process_local_lyrics_batch
        except ImportError:
            from lyrics import process_local_lyrics_batch

        force = getattr(args, "force", False) or any(arg in ("--force", "-f") for arg in sys.argv[1:])
        targets = [t for t in args.urls if t not in ("--force", "-f")]

        if not targets:
            music_dir = Path(config.get("music_dir", DEFAULT_MUSIC_DIR)).expanduser()
            if music_dir.exists() and any(music_dir.iterdir()):
                targets = [str(music_dir)]
            elif (Path.home() / "Music").exists():
                targets = [str(Path.home() / "Music")]
            else:
                safe_print(f"{RED}Usage: mf lyrics <file1.mp3> [dir_or_file2 ...] [-f/--force]{RESET}")
                sys.exit(1)

        for t in targets:
            process_local_lyrics_batch(t, force=force)
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
        safe_print("  -c, --cookies <PATH>    Path to cookies.txt (for age-restricted content)")
        safe_print("  -f, --force             Force re-fetching lyrics even if already present")
        safe_print("  --nolyrics              Skip fetching and embedding lyrics for audio tracks")
        safe_print("  --no-album-dir          Do not create subfolders for albums or playlists")
        safe_print("  attach [DIR]            Interactive fzf picker to attach lyrics to untagged audio")
        safe_print("  cleanup [DIR]           Remove YouTube IDs & clutter from filenames (Defaults to ~/Music)")
        safe_print("  lyrics [FILE/DIR...]    Fetch & embed lyrics into local audio (skips existing, -f to force)")
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
        list_cmd = ["yt-dlp"]
        if cookie_file and Path(cookie_file).exists():
            list_cmd.extend(["--cookies", str(cookie_file)])
        list_cmd.extend(["-F", target_url])
        subprocess.run(list_cmd)
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

    # Target directory routing (Defaults: ~/Music/Downloads for music, ~/Videos/Downloads for video)
    profile = PROFILES[profile_name]
    if custom_out_dir:
        target_dir = Path(custom_out_dir).expanduser().resolve()
    else:
        if profile["type"] == "music":
            target_dir = Path(config.get("music_dir", DEFAULT_MUSIC_DIR)).expanduser().resolve()
        else:
            target_dir = Path(config.get("video_dir", DEFAULT_VIDEO_DIR)).expanduser().resolve()

    target_dir.mkdir(parents=True, exist_ok=True)

    # Execute modular pipeline
    nolyrics = args.nolyrics or not config.get("embed_lyrics", True)
    ret = run_pipeline(profile_name, urls, target_dir, config, cookie_file=cookie_file, nolyrics=nolyrics)
    sys.exit(ret)


if __name__ == "__main__":
    main()
