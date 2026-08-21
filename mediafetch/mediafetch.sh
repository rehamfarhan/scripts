#!/usr/bin/env bash

set -euo pipefail

################################################################################
# mediafetch (mf)
#
# Profiles:
#   video   - 1080p H.265 MKV with subtitles
#   music   - High quality MP3 with album art
#   podcast - Audio-focused Opus download
#   archive - Maximum preservation quality
#
# Usage:
#   mf URL
#   mf video URL
#   mf music URL
#   mf podcast URL
#   mf archive URL
#   mf --list URL
################################################################################

DEPENDENCIES=(
  yt-dlp
  aria2c
  ffmpeg
  python3
)

for cmd in "${DEPENDENCIES[@]}"; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo
    echo "Error: Missing dependency: $cmd"
    echo

    case "$cmd" in
    ffmpeg)
      echo "Arch:          sudo pacman -S ffmpeg"
      echo "Debian/Ubuntu: sudo apt install ffmpeg"
      ;;
    yt-dlp)
      echo "Arch:          sudo pacman -S yt-dlp"
      echo "Debian/Ubuntu: sudo apt install yt-dlp"
      ;;
    aria2c)
      echo "Arch:          sudo pacman -S aria2"
      echo "Debian/Ubuntu: sudo apt install aria2"
      ;;
    python3)
      echo "Arch:          sudo pacman -S python python-mutagen"
      echo "Debian/Ubuntu: sudo apt install python3 python3-mutagen"
      ;;
    esac

    exit 1
  fi
done

################################################################################
# Configuration
################################################################################

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/mediafetch"
ARCHIVE_FILE="$CACHE_DIR/archive.txt"

mkdir -p "$CACHE_DIR"

OUTPUT="%(title)s [%(id)s].%(ext)s"

COMMON_FLAGS=(
  --newline
  --download-archive "$ARCHIVE_FILE"

  --downloader aria2c
  --downloader-args "aria2c:-x 8 -s 8"
)

################################################################################
# Parse arguments
################################################################################

PROFILE="video"

case "${1:-}" in
video | music | podcast | archive)
  PROFILE="$1"
  shift
  ;;
--list)
  shift

  if [[ $# -eq 0 ]]; then
    echo "Usage: $(basename "$0") --list <url>"
    exit 1
  fi

  yt-dlp -F "$1"
  exit 0
  ;;
esac

if [[ $# -eq 0 ]]; then
  cat <<EOF
Usage:
  $(basename "$0") URL
  $(basename "$0") video URL
  $(basename "$0") music URL
  $(basename "$0") podcast URL
  $(basename "$0") archive URL
  $(basename "$0") --list URL

Profiles:

  video    1080p H.265 MKV with subtitles
  music    High quality MP3 with album artwork & lyrics (kew compatible)
  podcast  Audio-only Opus
  archive  Maximum quality preservation

EOF
  exit 1
fi

################################################################################
# Profile Definitions
################################################################################

case "$PROFILE" in

video)

  FORMAT="bv*[height=1080]+ba/best[height<=1080]"

  PROFILE_FLAGS=(
    --embed-thumbnail
    --convert-thumbnails png

    --write-subs
    --write-auto-subs
    --sub-langs "en.*"
    --embed-subs

    --recode-video mkv
  )

  ;;

music)

  FORMAT="bestaudio"

  PROFILE_FLAGS=(
    --extract-audio
    --audio-format mp3
    --audio-quality 0

    --embed-thumbnail
    --convert-thumbnails png
    --embed-metadata

    --ppa "ThumbnailsConvertor:-vf crop=ih:ih"

    --exec "post_process:python3 \"$SCRIPT_DIR/embed_lyrics.py\" {}"
  )

  ;;

podcast)

  FORMAT="bestaudio"

  PROFILE_FLAGS=(
    --extract-audio
    --audio-format opus

    --embed-thumbnail
    --embed-metadata
  )

  ;;

archive)

  FORMAT="bv*+ba/b"

  PROFILE_FLAGS=(
    --embed-thumbnail

    --write-subs
    --write-auto-subs
    --sub-langs all
    --embed-subs
  )

  ;;

*)

  echo "Unknown profile: $PROFILE"
  exit 1

  ;;

esac

################################################################################
# Download
################################################################################

echo
echo "Profile : $PROFILE"
echo "Targets : $#"
echo

yt-dlp \
  -f "$FORMAT" \
  -o "$OUTPUT" \
  "${COMMON_FLAGS[@]}" \
  "${PROFILE_FLAGS[@]}" \
  "$@"
