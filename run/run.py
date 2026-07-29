#!/usr/bin/env python3
"""
🎮 Game Launcher (run.py)

Interactive fzf game launcher featuring automatic game folder discovery,
executable & Wine prefix configuration wizard, standalone runner script generator,
optional .desktop menu entry creator, and instant quick-launch mode (`run <name>`).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

DEFAULT_GAMES_DIR = Path.home() / "Games"
REGISTRY_FILENAME = ".run_registry.json"
IGNORE_DIRS = {"lib", "lib64", "share", ".git", ".wine", "node_modules"}
DESKTOP_DIR = Path.home() / ".local" / "share" / "applications"


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
) -> Tuple[Optional[str], str, Optional[str]]:
    """
    Run fzf with given items and return (selected_line, key_pressed, full_raw_selection).
    """
    cmd = [
        "fzf",
        f"--prompt={prompt}",
        "--height=~14",
        "--margin=1,8%",
        "--border=rounded",
        "--ansi",
    ]
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

    input_bytes = "\n".join(items).encode("utf-8")
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out_bytes, _ = proc.communicate(input=input_bytes)

    if proc.returncode not in (0, 130):
        # 130 is user ESC / Ctrl+C in fzf
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
        # User pressed enter on default or esc
        if lines[0] in expect_keys:
            key = lines[0]
            selected = ""
        else:
            selected = lines[0]
    else:
        selected = lines[0]

    return selected if selected else None, key, selected


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


def scan_executables(game_dir: Path, max_depth: int = 3) -> List[Path]:
    """Scan game_dir up to max_depth for executable files or .exe files."""
    binaries: List[Path] = []
    base_depth = len(game_dir.parts)

    for root, dirs, files in os.walk(game_dir):
        current_path = Path(root)
        depth = len(current_path.parts) - base_depth
        if depth >= max_depth:
            dirs.clear()
            continue

        # Filter out ignored directories in-place
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

        for f in files:
            file_path = current_path / f
            lname = f.lower()
            if lname.endswith((".exe", ".bat", ".msi")):
                binaries.append(file_path)
            elif os.access(file_path, os.X_OK) and not file_path.is_dir():
                binaries.append(file_path)

    # Sort relative paths
    return sorted(binaries, key=lambda p: str(p.relative_to(game_dir)))


def create_launcher_script(
    game_dir: Path,
    rel_binary: Path,
    display_name: str,
    is_windows: bool,
    wine_prefix: Optional[Path],
) -> Path:
    """Generate executable start_game.sh wrapper inside game_dir."""
    script_path = game_dir / "start_game.sh"
    icon = "💻" if is_windows else "🐧"

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

        icon = "applications-games"
        content = f"""[Desktop Entry]
Type=Application
Name={display_name}
Exec={launcher_script.resolve()}
Icon={icon}
Terminal=false
Categories=Game;
Comment=Launched via Python Game Launcher
"""
        desktop_path.write_text(content, encoding="utf-8")
        return desktop_path
    except Exception as e:
        print(f"Warning: Failed to create .desktop entry: {e}", file=sys.stderr)
        return None


def run_detached(script_path: Path) -> None:
    """Launch script in background detached session and exit terminal."""
    subprocess.Popen(
        [str(script_path.resolve())],
        cwd=script_path.parent,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    sys.exit(0)


def configure_new_folders(games_root: Path, registry: Dict[str, Any]) -> bool:
    """Scan games_root for unregistered folders and run configuration wizard."""
    registered_dirs = set(registry.get("games", {}).keys())
    changed = False

    # Find unregistered top-level folders
    unregistered: List[Path] = []
    for item in sorted(games_root.iterdir()):
        if item.is_dir() and not item.name.startswith(".") and item.name not in IGNORE_DIRS:
            if item.name not in registered_dirs:
                unregistered.append(item)

    if not unregistered:
        return False

    print(f"\n🎮 Found {len(unregistered)} new game folder(s) to configure!\n")

    for folder in unregistered:
        print(f"--------------------------------------------------")
        print(f"📁 Configuring Folder: {folder.name}")

        binaries = scan_executables(folder)
        if not binaries:
            print(f"⚠️  No executables found in {folder.name}.")
            ans, _, _ = run_fzf(
                ["1) Skip this folder for now", "2) Mark as ignored directory"],
                prompt=f"Action for {folder.name}: ",
            )
            if ans and "Mark as ignored" in ans:
                registry["games"][folder.name] = {
                    "dir": folder.name,
                    "display_name": folder.name,
                    "ignored": True,
                }
                changed = True
            continue

        # Let user pick binary via fzf
        rel_bin_strings = [str(b.relative_to(folder)) for b in binaries]
        selected_bin_str, _, _ = run_fzf(
            rel_bin_strings,
            prompt=f"Select executable for {folder.name}: ",
            header="Use arrow keys and press ENTER to select the main binary",
        )

        if not selected_bin_str:
            print(f"Skipped {folder.name}.")
            continue

        rel_binary = Path(selected_bin_str)
        is_windows = rel_binary.suffix.lower() in (".exe", ".bat", ".msi")

        # Prompt for Display Name
        clean_name = folder.name.replace("_", " ").replace("-", " ").title()
        print(f"\nSuggested Game Name: {clean_name}")
        user_name = input(f"Enter Game Display Name [default: {clean_name}]: ").strip()
        display_name = user_name if user_name else clean_name

        wine_prefix: Optional[Path] = None
        if is_windows:
            shared_prefix = games_root / ".wine"
            isolated_prefix = folder / ".wine"
            ans, _, _ = run_fzf(
                [
                    f"1) Shared Wine Prefix ({shared_prefix}) [Default]",
                    f"2) Isolated Per-Game Wine Prefix ({isolated_prefix})",
                ],
                prompt="Select Wine Prefix Configuration: ",
            )
            if ans and "Isolated" in ans:
                wine_prefix = isolated_prefix
            else:
                wine_prefix = shared_prefix
                shared_prefix.mkdir(parents=True, exist_ok=True)

        # Ask for .desktop entry
        ans_dt, _, _ = run_fzf(
            ["1) Yes (Create system menu shortcut)", "2) No (Keep fzf only)"],
            prompt="Create .desktop Application Entry? ",
        )
        create_dt = bool(ans_dt and "Yes" in ans_dt)

        # Generate launcher script
        launcher_script = create_launcher_script(
            folder, rel_binary, display_name, is_windows, wine_prefix
        )

        desktop_path_str = None
        if create_dt:
            dt_path = create_desktop_entry(display_name, launcher_script, is_windows)
            if dt_path:
                desktop_path_str = str(dt_path)

        # Update registry
        registry["games"][folder.name] = {
            "dir": folder.name,
            "display_name": display_name,
            "binary": str(rel_binary),
            "is_windows": is_windows,
            "wine_prefix": str(wine_prefix) if wine_prefix else None,
            "icon": "💻" if is_windows else "🐧",
            "launcher_script": str(launcher_script.relative_to(folder)),
            "desktop_entry": desktop_path_str,
            "ignored": False,
        }
        changed = True
        print(f"✅ Configured '{display_name}' successfully!\n")

    if changed:
        save_registry(games_root, registry)
    return changed


def quick_launch(games_root: Path, query: str, registry: Dict[str, Any]) -> None:
    """Fuzzy match query against configured games and launch immediately."""
    games = registry.get("games", {})
    active_games = [g for g in games.values() if not g.get("ignored")]

    if not active_games:
        print("No configured games found in registry.", file=sys.stderr)
        sys.exit(1)

    query_lower = query.lower().strip()

    # Exact or substring matches
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
        # Fallback to recreate launcher if missing
        script_path = create_launcher_script(
            folder_path,
            Path(target["binary"]),
            target["display_name"],
            target["is_windows"],
            Path(target["wine_prefix"]) if target.get("wine_prefix") else None,
        )

    print(f"🚀 Quick-launching: {target['display_name']}...")
    run_detached(script_path)


def main_launcher_menu(games_root: Path, registry: Dict[str, Any]) -> None:
    """Render main fzf launcher menu for selecting & launching games."""
    check_fzf()

    while True:
        games = registry.get("games", {})
        active_games = [g for g in games.values() if not g.get("ignored")]

        if not active_games:
            print("No games available. Run setup or check your Games folder.", file=sys.stderr)
            sys.exit(1)

        menu_items = []
        for g in active_games:
            icon = g.get("icon", "🐧")
            name = g.get("display_name", g.get("dir"))
            folder = g.get("dir")
            menu_items.append(f"{icon}  {name}\t{folder}")

        selected_line, key, _ = run_fzf(
            menu_items,
            prompt="Select Game: ",
            header="ENTER: Launch Game | TAB: Ignore/Hide Game | ESC: Exit",
            expect_keys=["tab", "enter"],
            delimiter="\t",
            with_nth="1",
            border_label="🎮 Game Launcher",
        )

        if not selected_line:
            sys.exit(0)

        # Parse selected line
        parts = selected_line.split("\t")
        if len(parts) < 2:
            sys.exit(0)

        folder_key = parts[1]
        game_info = games.get(folder_key)
        if not game_info:
            continue

        if key == "tab":
            # Toggle ignore state
            game_info["ignored"] = True
            save_registry(games_root, registry)
            print(f"Ignored '{game_info.get('display_name')}'.")
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
            )

        run_detached(script_path)
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
    args = parser.parse_args()

    games_root = args.games_dir.expanduser().resolve()
    games_root.mkdir(parents=True, exist_ok=True)

    registry = load_registry(games_root)

    # Check for quick-launch argument
    if args.query:
        quick_launch(games_root, args.query, registry)
        return

    # Standard interactive flow: check for new un-registered folders
    configure_new_folders(games_root, registry)

    # Open main launcher menu
    main_launcher_menu(games_root, registry)


if __name__ == "__main__":
    main()
