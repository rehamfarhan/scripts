#!/usr/bin/env python3
"""
rngname.py - Rename picture files with random strings.

Default directory: ~/Pictures/wallpapers
Allows specifying a target folder as an argument.
"""

import argparse
import os
import random
import string
import sys
from pathlib import Path

# Common image extensions
IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".tiff",
    ".tif",
    ".avif",
    ".svg",
    ".heic",
    ".heif",
    ".jxl",
}

DEFAULT_DIR = Path.home() / "Pictures" / "wallpapers"


def generate_random_string(length: int = 12) -> str:
    """Generate a random alphanumeric string."""
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choices(alphabet, k=length))


def get_unique_random_name(directory: Path, ext: str, length: int = 12, reserved_names: set = None) -> Path:
    """Generate a unique random destination file path that doesn't collide with existing or planned names."""
    if reserved_names is None:
        reserved_names = set()

    while True:
        rand_stem = generate_random_string(length)
        new_path = directory / f"{rand_stem}{ext}"
        if not new_path.exists() and new_path not in reserved_names:
            reserved_names.add(new_path)
            return new_path


def rename_pictures_in_dir(target_dir: Path, length: int = 12, dry_run: bool = False, recursive: bool = False) -> None:
    if not target_dir.exists():
        print(f"Error: Target directory does not exist: {target_dir}", file=sys.stderr)
        sys.exit(1)

    if not target_dir.is_dir():
        print(f"Error: Target path is not a directory: {target_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning directory: {target_dir}")
    if dry_run:
        print("[DRY RUN MODE] No files will actually be renamed.\n")

    files_to_rename = []
    iterator = target_dir.rglob("*") if recursive else target_dir.iterdir()

    for item in iterator:
        if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS:
            files_to_rename.append(item)

    if not files_to_rename:
        print("No matching image files found.")
        return

    print(f"Found {len(files_to_rename)} image(s).\n")

    renamed_count = 0
    reserved_names = set()

    # Plan renames first
    planned_renames = []
    for file_path in files_to_rename:
        ext = file_path.suffix.lower()
        new_path = get_unique_random_name(file_path.parent, ext, length=length, reserved_names=reserved_names)
        planned_renames.append((file_path, new_path))

    for old_path, new_path in planned_renames:
        action = "[DRY-RUN] Would rename" if dry_run else "Renamed"
        print(f"{action}: {old_path.name} -> {new_path.name}")
        if not dry_run:
            try:
                old_path.rename(new_path)
                renamed_count += 1
            except OSError as e:
                print(f"Error renaming {old_path.name}: {e}", file=sys.stderr)

    if not dry_run:
        print(f"\nSuccessfully renamed {renamed_count}/{len(files_to_rename)} files.")
    else:
        print(f"\nDry run finished. {len(files_to_rename)} files would be renamed.")


def main():
    parser = argparse.ArgumentParser(
        description="Rename picture files to random alphanumeric strings."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=str(DEFAULT_DIR),
        help=f"Target directory to rename pictures in (default: {DEFAULT_DIR})",
    )
    parser.add_argument(
        "-l",
        "--length",
        type=int,
        default=12,
        help="Length of the random string (default: 12)",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Simulate the renaming process without modifying any files",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively rename pictures in subdirectories",
    )

    args = parser.parse_args()
    target_path = Path(os.path.expanduser(args.folder)).resolve()

    rename_pictures_in_dir(
        target_dir=target_path,
        length=args.length,
        dry_run=args.dry_run,
        recursive=args.recursive,
    )


if __name__ == "__main__":
    main()
