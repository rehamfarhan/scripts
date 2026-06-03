#!/usr/bin/env bash

# Exit immediately if any command fails or a pipeline breaks
set -eo pipefail

# Check for required system dependencies before running
for cmd in yt-dlp aria2c ffmpeg; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: Required dependency '$cmd' is not installed." >&2
    exit 1
  fi
done

# Default video resolution configurations
format="bv*[height=1080]+ba/best[height<=1080]"
output="%(title)s.%(ext)s"

# Base configuration flags (Thumbnails, Subs, Fast Downloader + H.265 Recode)
extra_flags=(
  --embed-thumbnail
  --convert-thumbnails png
  --write-subs
  --write-auto-subs
  --sub-langs "en.*"
  --embed-subs
  --recode-video mkv
  --postprocessor-args "ffmpeg:-c:v libx265 -vtag hvc1 -c:a copy"
  --downloader aria2c
  --downloader-args "aria2c:-x 16 -s 16"
)

# Parse configuration modifiers
while [[ "$1" == --* ]]; do
  case "$1" in
  --mp3)
    # 1. Extracts high-quality audio track and discards subtitles.
    # 2. Crops sidebars from 16:9 thumbnails to form a native square album cover.
    # 3. Bypasses the H.265 video recode processing array.
    extra_flags=(
      --embed-thumbnail
      --convert-thumbnails png
      --downloader aria2c
      --downloader-args "aria2c:-x 16 -s 16"
      --extract-audio
      --audio-format mp3
      --audio-quality 0
      --embed-metadata
      --ppa "ThumbnailsConvertor:-vf crop=ih:ih"
    )
    ;;
  --best)
    format="bestvideo+bestaudio/best"
    ;;
  --720)
    format="bv*[height=720]+ba/best[height<=720]"
    ;;
  --1080)
    format="bv*[height=1080]+ba/best[height<=1080]"
    ;;
  *)
    echo "Unknown flag: $1" >&2
    exit 1
    ;;
  esac
  shift
done

# URL verification check (Ensures at least one target is provided)
if [[ $# -eq 0 ]]; then
  echo "Usage: $(basename "$0") [--mp3] [--720|--1080|--best] <url1> [url2 ...]" >&2
  exit 1
fi

# Fire the downloader for all provided URLs
yt-dlp -f "$format" -o "$output" "${extra_flags[@]}" "$@"
