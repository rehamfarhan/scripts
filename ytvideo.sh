#!/usr/bin/env bash

# Exit immediately if any command fails or a pipeline breaks
set -eo pipefail

# Check for required system dependencies
for cmd in yt-dlp aria2c ffmpeg; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: Required dependency '$cmd' is not installed." >&2
    exit 1
  fi
done

# Default values
format="bv*[height=1080]+ba/best[height<=1080]"
output="%(title)s.%(ext)s"

# Base configuration flags (Thumbnails, English Subtitles, and Fast Downloader)
extra_flags=(
  --embed-thumbnail
  --convert-thumbnails png
  --write-subs
  --sub-langs "en.*"
  --embed-subs
  --downloader aria2c
  --downloader-args "aria2c:-x 16 -s 16"
)

# Parse configuration flags
while [[ "$1" == --* ]]; do
  case "$1" in
  --mp3)
    # --extract-audio will discard the subtitle track automatically for audio files
    # Mutates thumbnail embedding slightly to comply with audio metadata containers
    extra_flags+=(--extract-audio --audio-format mp3 --audio-quality 0 --embed-metadata)
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

# URL verification check
if [[ $# -eq 0 ]]; then
  echo "Usage: $(basename "$0") [--mp3] [--720|--1080|--best] <url1> [url2 ...]" >&2
  exit 1
fi

# Run the download for all provided URLs
yt-dlp -f "$format" -o "$output" "${extra_flags[@]}" "$@"
