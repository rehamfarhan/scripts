#!/usr/bin/env python3
"""
🎮 Game Launcher (run.py)

Interactive fzf game launcher featuring automatic game folder discovery,
executable & Wine prefix configuration wizard, real-time binary inspector preview,
star rating system, playtime tracking & background session monitoring,
TAB utility menu, toast notifications, optional .desktop menu entry creator,
and instant quick-launch mode (`run <name>`).
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

DEFAULT_GAMES_DIR = Path.home() / "Games"
REGISTRY_FILENAME = ".run_registry.json"
STATS_FILENAME = ".run_stats.json"
IGNORE_DIRS = {"lib", "lib64", "share", ".git", ".wine", "node_modules"}
DESKTOP_DIR = Path.home() / ".local" / "share" / "applications"

USER_NAME = os.environ.get("USER", "DirectPass").strip().title()
MAIN_BORDER_TITLE = f"🏰 {USER_NAME}'s Game Dungeon 🎮"

# ANSI Color Codes
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_YELLOW = "\033[33m"
COLOR_CYAN = "\033[36m"
COLOR_GREY = "\033[90m"
COLOR_GREEN = "\033[32m"
COLOR_RED = "\033[31m"


def clear_screen() -> None:
    """Clear terminal screen and position cursor at top-left."""
    sys.stdout.write("\033[H\033[2J")
    sys.stdout.flush()


def check_fzf() -> None:
    """Ensure fzf is installed and available in PATH."""
    if not shutil.which("fzf"):
        print("Error: 'fzf' is required but not installed or not in PATH.", file=sys.stderr)
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
    footer: str = "",
    margin: str = "12%,12%",
) -> Tuple[Optional[str], str, Optional[str]]:
    """
    Run fzf with given items and return (selected_line, key_pressed, full_raw_selection).
    """
    cmd = [
        "fzf",
        f"--prompt={prompt}",
        "--height=40",
        f"--margin={margin}",
        "--border=rounded",
        "--pointer=▶ ",
        "--ansi",
    ]
    if border_label:
        cmd.append(f"--border-label= {border_label} ")
    if header:
        cmd.append(f"--header={header}")
    if footer:
        cmd.append(f"--footer={footer}")
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

    if proc.returncode not in (0, 130):
        return None, "", None

    lines = out_bytes.decode("utf-8", errors="replace").splitlines()
    if not lines:
        return None, "", None

    key = ""
    selected = ""
    if expect_keys and len(lines) >= 2:
        key = lines[0].strip()
        selected = lines[1]
    elif expect_keys and len(lines) == 1:
        if lines[0] in expect_keys:
            key = lines[0]
            selected = ""
        else:
            selected = lines[0]
    else:
        selected = lines[0]

    return selected if selected else None, key, selected


# --- Registry & Stats Management ---

def load_registry(games_root: Path) -> Dict[str, Any]:
    """Load registry file from $GAMES_ROOT/.run_registry.json."""
    reg_path = games_root / REGISTRY_FILENAME
    if reg_path.is_file():
        try:
            with open(reg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "games" in data:
                    return data
        except Exception as e:
            print(f"Warning: Could not read {reg_path}: {e}", file=sys.stderr)
    return {"version": 1, "games": {}}


def save_registry(games_root: Path, registry: Dict[str, Any]) -> None:
    """Save registry file to $GAMES_ROOT/.run_registry.json."""
    reg_path = games_root / REGISTRY_FILENAME
    try:
        with open(reg_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving registry to {reg_path}: {e}", file=sys.stderr)


def load_stats(games_root: Path) -> Dict[str, Any]:
    """Load stats file from $GAMES_ROOT/.run_stats.json."""
    stats_path = games_root / STATS_FILENAME
    if stats_path.is_file():
        try:
            with open(stats_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "stats" in data:
                    return data
        except Exception:
            pass
    return {"version": 1, "stats": {}}


def save_stats(games_root: Path, stats: Dict[str, Any]) -> None:
    """Save stats file to $GAMES_ROOT/.run_stats.json."""
    stats_path = games_root / STATS_FILENAME
    try:
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving stats to {stats_path}: {e}", file=sys.stderr)


# --- Formatting Helpers ---

def format_playtime(seconds: int) -> str:
    """Format seconds into readable playtime (e.g. 14.5h or 45m)."""
    if seconds <= 0:
        return ""
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins}m"
    hours = seconds / 3600.0
    return f"{hours:.1f}h"


def format_relative_time(iso_str: Optional[str]) -> str:
    """Format ISO timestamp into relative time string (e.g. 2h ago, yesterday)."""
    if not iso_str:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_str)
        now = datetime.datetime.now(datetime.timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        diff = (now - dt).total_seconds()

        if diff < 60:
            return "just now"
        if diff < 3600:
            return f"{int(diff // 60)}m ago"
        if diff < 86400:
            return f"{int(diff // 3600)}h ago"
        days = int(diff // 86400)
        if days == 1:
            return "yesterday"
        if days < 30:
            return f"{days}d ago"
        return dt.strftime("%b %d")
    except Exception:
        return ""


def get_star_string(rating: int) -> str:
    """Return star rating string."""
    if rating <= 0:
        return ""
    rating = min(rating, 5)
    return f"{COLOR_YELLOW}{'★' * rating}{COLOR_RESET}"


# --- Binary Inspection & Heuristics ---

def get_file_size_str(size_bytes: int) -> str:
    """Format file size into human-readable MB / KB string."""
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024*1024*1024):.2f} GB"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024*1024):.2f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def evaluate_binary_score(game_dir: Path, bin_path: Path) -> Tuple[int, str]:
    """
    Score candidate binary (higher = more likely main executable).
    Returns (score, tag_name).
    """
    name_lower = bin_path.name.lower()
    score = 100

    if any(k in name_lower for k in ("unins", "uninstall", "crash", "bugreport", "dxsetup", "vcredist", "redist", "setup", "update")):
        score -= 200
        return score, "⚠️ Utility / Uninstaller"

    folder_name_clean = game_dir.name.lower().replace("_", "").replace("-", "")
    bin_clean = bin_path.stem.lower().replace("_", "").replace("-", "")
    if bin_clean in folder_name_clean or folder_name_clean in bin_clean:
        score += 150

    try:
        size = bin_path.stat().st_size
        if size > 10 * 1024 * 1024:  # > 10 MB
            score += 80
        elif size > 2 * 1024 * 1024:  # > 2 MB
            score += 40
    except Exception:
        pass

    tag = "⭐ Recommended Main Binary" if score >= 100 else " Executable"
    return score, tag


def scan_executables(game_dir: Path, max_depth: int = 2) -> List[Path]:
    """Scan game_dir up to max_depth and return executables sorted by heuristic score."""
    binaries: List[Path] = []
    base_depth = len(game_dir.parts)

    for root, dirs, files in os.walk(game_dir):
        current_path = Path(root)
        depth = len(current_path.parts) - base_depth
        if depth >= max_depth:
            dirs.clear()
            continue

        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

        for f in files:
            file_path = current_path / f
            lname = f.lower()
            if lname.endswith((".exe", ".bat", ".msi")):
                binaries.append(file_path)
            elif os.access(file_path, os.X_OK) and not file_path.is_dir():
                binaries.append(file_path)

    def sort_key(p: Path) -> Tuple[int, int]:
        score, _ = evaluate_binary_score(game_dir, p)
        size = p.stat().st_size if p.is_file() else 0
        return (-score, -size)

    return sorted(binaries, key=sort_key)


def render_binary_preview(binary_path: Path) -> None:
    """CLI handler for rendering rich binary information in fzf preview window."""
    if not binary_path.is_file():
        print(f"File not found: {binary_path}")
        return

    try:
        stat = binary_path.stat()
        size_str = get_file_size_str(stat.st_size)
        mtime_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        size_str = "Unknown"
        mtime_str = "Unknown"

    file_type = "Executable"
    if shutil.which("file"):
        try:
            res = subprocess.run(["file", "-b", str(binary_path)], capture_output=True, text=True)
            if res.returncode == 0:
                file_type = res.stdout.strip()
        except Exception:
            pass

    score, tag = evaluate_binary_score(binary_path.parent, binary_path)

    print(f"{COLOR_BOLD}──────────────────────────────────────────{COLOR_RESET}")
    print(f"{COLOR_BOLD}📄 File:{COLOR_RESET} {binary_path.name}")
    print(f"{COLOR_BOLD}📂 Rel Path:{COLOR_RESET} {binary_path}")
    print(f"{COLOR_BOLD}📏 File Size:{COLOR_RESET} {COLOR_CYAN}{size_str}{COLOR_RESET}")
    print(f"{COLOR_BOLD}📅 Modified:{COLOR_RESET} {mtime_str}")
    print(f"{COLOR_BOLD}🏷️ Type:{COLOR_RESET} {file_type}")
    print(f"{COLOR_BOLD}💡 Status:{COLOR_RESET} {tag}")
    print(f"{COLOR_BOLD}──────────────────────────────────────────{COLOR_RESET}\n")

    if binary_path.suffix.lower() in (".sh", ".bat") or file_type.startswith("text"):
        print(f"{COLOR_BOLD}📜 Script Preview (First 15 Lines):{COLOR_RESET}")
        try:
            with open(binary_path, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f):
                    if i >= 15:
                        break
                    print(f"  {line.rstrip()}")
        except Exception:
            pass


# --- Launcher & Desktop Generators ---

def create_launcher_script(
    game_dir: Path,
    rel_binary: Path,
    display_name: str,
    is_windows: bool,
    wine_prefix: Optional[Path],
    wine_opts: Optional[Dict[str, Any]] = None,
) -> Path:
    """Generate executable start_game.sh wrapper inside game_dir."""
    script_path = game_dir / "start_game.sh"
    icon = "💻" if is_windows else "🐧"
    wine_opts = wine_opts or {}

    lines = [
        "#!/usr/bin/env bash",
        f"# GAME_NAME: {display_name}",
        f"# ICON: {icon}",
        "# GENERATED BY RUN.PY - DO NOT EDIT HEADER",
        "set -e",
        'cd "$(dirname "$0")"',
    ]

    if is_windows:
        if wine_prefix:
            lines.append(f'export WINEPREFIX="{wine_prefix.resolve()}"')
        
        hud = wine_opts.get("dxvk_hud")
        if hud:
            lines.append(f'export DXVK_HUD="{hud}"')

        res = wine_opts.get("resolution")
        safe_title = re.sub(r'[^a-zA-Z0-9]', '_', display_name)
        if res:
            lines.append(f'wine explorer /desktop={safe_title},{res} "{rel_binary}" "$@"')
        else:
            lines.append(f'wine "{rel_binary}" "$@"')
    else:
        lines.append('export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-x11}"')
        lines.append(f'exec "./{rel_binary}" "$@"')

    script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


def create_desktop_entry(display_name: str, launcher_script: Path, is_windows: bool) -> Optional[Path]:
    """Create a .desktop application menu entry in ~/.local/share/applications/."""
    try:
        DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", display_name.lower()).strip("_")
        desktop_path = DESKTOP_DIR / f"game_{safe_id}.desktop"

        content = f"""[Desktop Entry]
Type=Application
Name={display_name}
Exec={launcher_script.resolve()}
Icon=applications-games
Terminal=false
Categories=Game;
Comment=Launched via Python Game Launcher
"""
        desktop_path.write_text(content, encoding="utf-8")
        return desktop_path
    except Exception as e:
        print(f"Warning: Failed to create .desktop entry: {e}", file=sys.stderr)
        return None


# --- Process Detachment & Background Playtime Monitoring ---

def launch_game_and_monitor(games_root: Path, folder_key: str, script_path: Path) -> None:
    """Launch game in background detached session and launch background playtime monitor."""
    game_proc = subprocess.Popen(
        [str(script_path.resolve())],
        cwd=script_path.parent,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    self_py = sys.executable
    script_py = str(Path(__file__).resolve())
    subprocess.Popen(
        [self_py, script_py, "--monitor", str(games_root.resolve()), folder_key, str(game_proc.pid)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    clear_screen()
    sys.exit(0)


def monitor_background_session(games_root: Path, folder_key: str, pid: int) -> None:
    """Background monitor process: polls PID, tracks elapsed time, logs to .run_stats.json."""
    start_time = time.time()
    iso_now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    while True:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(3)

    elapsed_seconds = int(time.time() - start_time)

    stats_data = load_stats(games_root)
    game_stats = stats_data["stats"].setdefault(folder_key, {
        "rating": 0,
        "playtime_seconds": 0,
        "play_count": 0,
        "last_played": None,
    })

    game_stats["playtime_seconds"] = game_stats.get("playtime_seconds", 0) + elapsed_seconds
    game_stats["play_count"] = game_stats.get("play_count", 0) + 1
    game_stats["last_played"] = iso_now

    save_stats(games_root, stats_data)
    sys.exit(0)


# --- Wine & Execution Settings Wizard ---

def configure_wine_settings(
    games_root: Path,
    folder: Path,
    is_windows: bool,
    current_name: str = "",
) -> Tuple[Optional[Path], Dict[str, Any]]:
    """Prompt interactively for Wine prefix, virtual desktop resolution, DXVK HUD, and Windows version."""
    if not is_windows:
        return None, {}

    shared_prefix = games_root / ".wine"
    isolated_prefix = folder / ".wine"

    clear_screen()
    ans_p, _, _ = run_fzf(
        [
            f"1) Shared Wine Prefix ({shared_prefix}) [Default]",
            f"2) Isolated Per-Game Wine Prefix ({isolated_prefix})",
        ],
        prompt="Select Wine Prefix: ",
        border_label=f"🍷 Wine Prefix ({current_name})",
    )
    wine_prefix = isolated_prefix if (ans_p and "Isolated" in ans_p) else shared_prefix
    wine_prefix.mkdir(parents=True, exist_ok=True)

    res_options = [
        "1) Disabled (Native Fullscreen) [Default]",
        "2) 1920x1080 (Full HD)",
        "3) 2560x1440 (2K QHD)",
        "4) 3840x2160 (4K UHD)",
        "5) 1280x720 (HD)",
    ]
    clear_screen()
    ans_res, _, _ = run_fzf(
        res_options,
        prompt="Virtual Desktop Resolution: ",
        border_label="🖥️ Wine Virtual Desktop",
    )
    resolution = None
    if ans_res:
        if "1920x1080" in ans_res: resolution = "1920x1080"
        elif "2560x1440" in ans_res: resolution = "2560x1440"
        elif "3840x2160" in ans_res: resolution = "3840x2160"
        elif "1280x720" in ans_res: resolution = "1280x720"

    hud_options = [
        "1) Off (Default)",
        "2) Basic (FPS Counter)",
        "3) Full (FPS, GPU, VRAM, Temp)",
    ]
    clear_screen()
    ans_hud, _, _ = run_fzf(
        hud_options,
        prompt="DXVK Vulkan Performance HUD: ",
        border_label="📊 DXVK Performance HUD",
    )
    dxvk_hud = None
    if ans_hud:
        if "Basic" in ans_hud: dxvk_hud = "fps"
        elif "Full" in ans_hud: dxvk_hud = "full"

    win_options = [
        "1) Windows 10 (win10) [Default]",
        "2) Windows 7 (win7)",
        "3) Windows 11 (win11)",
    ]
    clear_screen()
    ans_win, _, _ = run_fzf(
        win_options,
        prompt="Windows OS Version: ",
        border_label="🪟 Windows Version",
    )
    win_ver = "win10"
    if ans_win:
        if "win7" in ans_win: win_ver = "win7"
        elif "win11" in ans_win: win_ver = "win11"

    opts = {
        "resolution": resolution,
        "dxvk_hud": dxvk_hud,
        "win_ver": win_ver,
    }
    return wine_prefix, opts


# --- Rating & Setup Wizard ---

def prompt_star_rating(game_name: str) -> int:
    """Prompt user to choose a star rating 0 to 5."""
    rating_options = [
        "⭐⭐⭐⭐⭐  5/5 (Masterpiece)",
        "⭐⭐⭐⭐  4/5 (Great)",
        "⭐⭐⭐  3/5 (Good)",
        "⭐⭐  2/5 (Mediocre)",
        "⭐  1/5 (Bad)",
        "Unrated (0/5)",
    ]
    clear_screen()
    ans, _, _ = run_fzf(
        rating_options,
        prompt=f"Rate '{game_name}': ",
        border_label="⭐ Star Rating Picker",
    )
    if ans:
        if "5/5" in ans: return 5
        if "4/5" in ans: return 4
        if "3/5" in ans: return 3
        if "2/5" in ans: return 2
        if "1/5" in ans: return 1
    return 0


def configure_new_folders(games_root: Path, registry: Dict[str, Any], stats_data: Dict[str, Any]) -> bool:
    """Scan games_root for unregistered folders and run configuration wizard in locked fzf frames."""
    registered_dirs = set(registry.get("games", {}).keys())
    changed = False

    unregistered: List[Path] = []
    for item in sorted(games_root.iterdir()):
        if item.is_dir() and not item.name.startswith(".") and item.name not in IGNORE_DIRS:
            if item.name not in registered_dirs:
                unregistered.append(item)

    if not unregistered:
        return False

    total = len(unregistered)
    for idx, folder in enumerate(unregistered, start=1):
        clear_screen()
        binaries = scan_executables(folder)
        if not binaries:
            ans, _, _ = run_fzf(
                ["1) Skip this folder for now", "2) Mark as ignored directory"],
                prompt=f"Action for {folder.name}: ",
                border_label=f"⚠️ No Binary ({idx}/{total}): {folder.name}",
            )
            if ans and "Mark as ignored" in ans:
                registry["games"][folder.name] = {
                    "dir": folder.name,
                    "display_name": folder.name,
                    "ignored": True,
                }
                changed = True
            continue

        # Clean binary menu items: size and path only (no cluttering tags in column 1)
        menu_items = []
        for b in binaries:
            rel = b.relative_to(folder)
            size_str = get_file_size_str(b.stat().st_size if b.is_file() else 0)
            menu_items.append(f"{size_str:>10}\t{b.resolve()}\t{rel}")

        py_exec = sys.executable
        script_path = str(Path(__file__).resolve())
        preview_cmd = f"'{py_exec}' '{script_path}' --preview-binary {{2}}"

        clear_screen()
        selected_line, _, _ = run_fzf(
            menu_items,
            prompt="Select Binary: ",
            header=f"Folder {idx}/{total}: {folder.name}\nUse ARROWS to preview binary metadata on right.",
            delimiter="\t",
            with_nth="1,3",
            border_label=f"📁 Select Executable ({idx}/{total})",
            preview_cmd=preview_cmd,
            preview_window="right:55%:wrap",
        )

        if not selected_line:
            continue

        parts = selected_line.split("\t")
        rel_binary = Path(parts[2])
        is_windows = rel_binary.suffix.lower() in (".exe", ".bat", ".msi")

        clean_name = folder.name.replace("_", " ").replace("-", " ").title()

        # Display Name Prompt & Directory Renaming on Disk
        clear_screen()
        print(f"{COLOR_BOLD}──────────────────────────────────────────────────{COLOR_RESET}")
        print(f"🧙 {COLOR_BOLD}Setup ({idx}/{total}):{COLOR_RESET} {folder.name}")
        print(f"💡 {COLOR_BOLD}Suggested Game Name:{COLOR_RESET} {COLOR_CYAN}{clean_name}{COLOR_RESET}")
        print(f"{COLOR_BOLD}──────────────────────────────────────────────────{COLOR_RESET}\n")
        user_name = input("Enter Game Display Name [Press ENTER for default]: ").strip()
        display_name = user_name if user_name else clean_name

        # Disk directory renaming
        target_dir_name = re.sub(r'[/\\?%*:|"<>]', '', display_name).strip()
        if target_dir_name and target_dir_name != folder.name:
            target_folder = games_root / target_dir_name
            if not target_folder.exists():
                try:
                    folder.rename(target_folder)
                    folder = target_folder
                except Exception as e:
                    print(f"Warning: Could not rename folder to '{target_dir_name}': {e}", file=sys.stderr)

        wine_prefix: Optional[Path] = None
        wine_opts: Dict[str, Any] = {}
        if is_windows:
            wine_prefix, wine_opts = configure_wine_settings(games_root, folder, is_windows, current_name=display_name)

        clear_screen()
        ans_dt, _, _ = run_fzf(
            ["1) Yes (Create system menu shortcut)", "2) No (Keep fzf only)"],
            prompt="Create .desktop Application Entry? ",
            border_label=f"🖥️ Desktop Entry ({display_name})",
        )
        create_dt = bool(ans_dt and "Yes" in ans_dt)

        launcher_script = create_launcher_script(
            folder, rel_binary, display_name, is_windows, wine_prefix, wine_opts
        )

        desktop_path_str = None
        if create_dt:
            dt_path = create_desktop_entry(display_name, launcher_script, is_windows)
            if dt_path:
                desktop_path_str = str(dt_path)

        registry["games"][folder.name] = {
            "dir": folder.name,
            "display_name": display_name,
            "binary": str(rel_binary),
            "is_windows": is_windows,
            "wine_prefix": str(wine_prefix) if wine_prefix else None,
            "wine_opts": wine_opts,
            "icon": "💻" if is_windows else "🐧",
            "launcher_script": str(launcher_script.relative_to(folder)),
            "desktop_entry": desktop_path_str,
            "ignored": False,
        }

        changed = True

    if changed:
        save_registry(games_root, registry)
    return changed


# --- TAB Utilities Sub-Menu ---

def show_utilities_menu(
    games_root: Path,
    folder_key: str,
    game_info: Dict[str, Any],
    registry: Dict[str, Any],
    stats_data: Dict[str, Any],
) -> Optional[str]:
    """Display interactive utility sub-menu for selected game."""
    g_name = game_info.get("display_name", folder_key)
    options = [
        "⭐ Rate Game (0 - 5 Stars)",
        "🍷 Configure Wine / Execution Settings",
        "🖥️ Create / Recreate Desktop Shortcut",
        "📁 Open Game Folder",
        "🙈 Hide / Ignore Game",
        "🗑️ Delete Launcher Entry",
    ]
    clear_screen()
    ans, _, _ = run_fzf(
        options,
        prompt="Select Utility: ",
        header=f"Managing: {g_name}",
        border_label=f"⚙️ Utilities ({g_name})",
    )
    if not ans:
        return None

    if "Rate Game" in ans:
        new_rating = prompt_star_rating(g_name)
        stats_data["stats"].setdefault(folder_key, {})["rating"] = new_rating
        save_stats(games_root, stats_data)
        stars_preview = "⭐" * new_rating if new_rating > 0 else "Unrated"
        return f"{COLOR_GREEN}✓ Rated '{g_name}' {stars_preview}{COLOR_RESET}"

    elif "Configure Wine" in ans:
        folder_path = games_root / folder_key
        is_win = game_info.get("is_windows", False)
        prefix, wine_opts = configure_wine_settings(games_root, folder_path, is_win, current_name=g_name)
        game_info["wine_prefix"] = str(prefix) if prefix else None
        game_info["wine_opts"] = wine_opts
        
        create_launcher_script(
            folder_path,
            Path(game_info["binary"]),
            g_name,
            is_win,
            prefix,
            wine_opts,
        )
        save_registry(games_root, registry)
        return f"{COLOR_GREEN}✓ Updated Wine settings for '{g_name}'{COLOR_RESET}"

    elif "Desktop Shortcut" in ans:
        folder_path = games_root / folder_key
        launcher_rel = game_info.get("launcher_script", "start_game.sh")
        script_path = folder_path / launcher_rel
        dt_path = create_desktop_entry(g_name, script_path, game_info.get("is_windows", False))
        if dt_path:
            game_info["desktop_entry"] = str(dt_path)
            save_registry(games_root, registry)
            return f"{COLOR_GREEN}✓ Created desktop entry for '{g_name}'{COLOR_RESET}"
        return f"{COLOR_RED}✗ Failed to create desktop entry{COLOR_RESET}"

    elif "Open Game Folder" in ans:
        folder_path = games_root / folder_key
        fm = shutil.which("xdg-open")
        if fm:
            subprocess.Popen([fm, str(folder_path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"{COLOR_CYAN}📁 Opened folder '{folder_key}'{COLOR_RESET}"

    elif "Hide / Ignore" in ans:
        game_info["ignored"] = True
        save_registry(games_root, registry)
        return f"{COLOR_YELLOW}🙈 Ignored '{g_name}' (Hidden from menu){COLOR_RESET}"

    elif "Delete Launcher Entry" in ans:
        registry.get("games", {}).pop(folder_key, None)
        stats_data.get("stats", {}).pop(folder_key, None)
        save_registry(games_root, registry)
        save_stats(games_root, stats_data)
        return f"{COLOR_RED}🗑️ Removed '{g_name}' launcher entry{COLOR_RESET}"

    return None


# --- Quick Launch & Main Launcher Menu ---

def quick_launch(games_root: Path, query: str, registry: Dict[str, Any]) -> None:
    """Fuzzy match query against configured games and launch immediately."""
    games = registry.get("games", {})
    active_games = [g for g in games.values() if not g.get("ignored")]

    if not active_games:
        print("No configured games found in registry.", file=sys.stderr)
        sys.exit(1)

    query_lower = query.lower().strip()

    matches = []
    for g in active_games:
        name = g.get("display_name", "").lower()
        folder = g.get("dir", "").lower()
        if query_lower == name or query_lower == folder:
            matches = [g]
            break
        if query_lower in name or query_lower in folder:
            matches.append(g)

    if not matches:
        print(f"No game matching '{query}' found.", file=sys.stderr)
        sys.exit(1)

    target = matches[0]
    folder_path = games_root / target["dir"]
    launcher_rel = target.get("launcher_script", "start_game.sh")
    script_path = folder_path / launcher_rel

    if not script_path.is_file():
        script_path = create_launcher_script(
            folder_path,
            Path(target["binary"]),
            target["display_name"],
            target["is_windows"],
            Path(target["wine_prefix"]) if target.get("wine_prefix") else None,
            target.get("wine_opts"),
        )

    print(f"🚀 Quick-launching: {target['display_name']}...")
    launch_game_and_monitor(games_root, target["dir"], script_path)


def main_launcher_menu(games_root: Path, registry: Dict[str, Any], stats_data: Dict[str, Any]) -> None:
    """Render main fzf launcher menu featuring aligned columns, ratings, playtime & TAB utilities."""
    check_fzf()
    toast_message: Optional[str] = None

    while True:
        clear_screen()
        games = registry.get("games", {})
        stats = stats_data.get("stats", {})
        active_games = [g for g in games.values() if not g.get("ignored")]

        if not active_games:
            print("No games available. Run setup or check your Games folder.", file=sys.stderr)
            sys.exit(1)

        menu_items = []
        for g in active_games:
            folder_key = g.get("dir")
            icon = g.get("icon", "🐧")
            name = g.get("display_name", folder_key)

            g_stats = stats.get(folder_key, {})
            rating = g_stats.get("rating", 0)
            playtime_sec = g_stats.get("playtime_seconds", 0)
            last_played_iso = g_stats.get("last_played")

            stars_str = get_star_string(rating)
            time_str = format_playtime(playtime_sec)
            rel_played = format_relative_time(last_played_iso)

            # Fixed-width column formatting
            name_padded = f"{name[:22]:<22}"
            stars_padded = f"{stars_str:<10}" if stars_str else f"{'':<10}"
            time_padded = f"{COLOR_CYAN}{time_str:<6}{COLOR_RESET}" if time_str else f"{'':<6}"
            rel_padded = f"{COLOR_GREY}(played {rel_played}){COLOR_RESET}" if rel_played else ""

            row_str = f"{icon}  {name_padded}   {stars_padded}   {time_padded}   {rel_padded}"
            menu_items.append(f"{row_str}\t{folder_key}")

        current_toast = toast_message if toast_message else ""
        selected_line, key, _ = run_fzf(
            menu_items,
            prompt="🔍 Select Game: ",
            header="ENTER: Launch Game | TAB: Utilities | ESC: Exit",
            expect_keys=["tab", "enter"],
            delimiter="\t",
            with_nth="1",
            border_label=MAIN_BORDER_TITLE,
            footer=f" {current_toast} " if current_toast else "",
        )

        toast_message = None  # Reset toast

        if not selected_line:
            clear_screen()
            sys.exit(0)

        parts = selected_line.split("\t")
        if len(parts) < 2:
            clear_screen()
            sys.exit(0)

        folder_key = parts[1]
        game_info = games.get(folder_key)
        if not game_info:
            continue

        if key == "tab":
            toast_message = show_utilities_menu(games_root, folder_key, game_info, registry, stats_data)
            continue

        # Launch game
        folder_path = games_root / folder_key
        launcher_rel = game_info.get("launcher_script", "start_game.sh")
        script_path = folder_path / launcher_rel

        if not script_path.is_file():
            script_path = create_launcher_script(
                folder_path,
                Path(game_info["binary"]),
                game_info["display_name"],
                game_info["is_windows"],
                Path(game_info["wine_prefix"]) if game_info.get("wine_prefix") else None,
                game_info.get("wine_opts"),
            )

        launch_game_and_monitor(games_root, folder_key, script_path)
        break


def main() -> None:
    parser = argparse.ArgumentParser(
        description="🎮 Interactive fzf Game Launcher & Manager",
        epilog="Usage: run [quick_search_name]",
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Optional game name to quick-launch directly without menu",
    )
    parser.add_argument(
        "--games-dir",
        type=Path,
        default=DEFAULT_GAMES_DIR,
        help="Path to games directory (default: ~/Games)",
    )
    parser.add_argument(
        "--preview-binary",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--monitor",
        nargs=3,
        metavar=("GAMES_ROOT", "FOLDER_KEY", "PID"),
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args.preview_binary:
        render_binary_preview(args.preview_binary)
        return

    if args.monitor:
        g_root = Path(args.monitor[0])
        f_key = args.monitor[1]
        pid_val = int(args.monitor[2])
        monitor_background_session(g_root, f_key, pid_val)
        return

    games_root = args.games_dir.expanduser().resolve()
    games_root.mkdir(parents=True, exist_ok=True)

    registry = load_registry(games_root)
    stats_data = load_stats(games_root)

    if args.query:
        quick_launch(games_root, args.query, registry)
        return

    configure_new_folders(games_root, registry, stats_data)
    main_launcher_menu(games_root, registry, stats_data)


if __name__ == "__main__":
    main()
