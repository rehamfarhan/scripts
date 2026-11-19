# rngname

Renames image files to random strings.

Wallpaper and screenshot folders tend to fill up with names that collide when you copy from different sources: `image (1).jpg`, `wallpaper.jpg`, the same filename from three different packs. `rngname` gives every file a random name and checks for collisions before touching anything.

## What it does

- Scans a folder for image files (`.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, `.bmp`, `.avif`, `.svg`, `.heic`, `.jxl`, among others).
- Generates a random name for each file, checking against both existing filenames and the names already planned in this run.
- Keeps the original extension.
- Can recurse into subfolders.
- `--dry-run` prints the plan without renaming.
- Name length is configurable.

Default folder is `~/Pictures/wallpapers`.

## Install

```bash
sudo ../scrlink/scrlink.sh rngname/rngname.py rngname
# or
sudo scrlink rngname
```

## Usage

```bash
rngname                                  # default folder
rngname ~/Pictures/Screenshots           # another folder
rngname ~/Pictures/wallpapers --dry-run  # show what would happen
rngname ~/Pictures/wallpapers -r         # include subfolders
rngname ~/Pictures/wallpapers -l 16      # 16-character names
```

Run a dry run first if the folder has files you care about; renames aren't reversible except by undoing them by hand.

## Requirements

Python 3. No external packages.
