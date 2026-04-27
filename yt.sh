yt() {
  # Default values
  format="bv*[height=1080]+ba/best[height<=1080]"
  output="%(title)s.%(ext)s"
  extra_flags+=(--downloader aria2c --downloader-args "aria2c:-x 16 -s 16")

  # Parse flags
  while [[ "$1" == --* ]]; do
    case "$1" in
    --mp3)
      extra_flags+=(--extract-audio --audio-format mp3)
      ;;
    --subs)
      extra_flags+=(--write-subs --sub-langs "en.*" --embed-subs)
      ;;
    --playlist)
      extra_flags+=(--yes-playlist)
      ;;
    --no-playlist)
      extra_flags+=(--no-playlist)
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
      echo "Unknown flag: $1"
      return 1
      ;;
    esac
    shift
  done

  # URL check
  if [[ -z "$1" ]]; then
    echo "Usage: yt [--mp3] [--subs] [--playlist] [--720|--1080|--best] <url>"
    return 1
  fi

  # Run command
  yt-dlp -f "$format" -o "$output" "${extra_flags[@]}" "$1"
}
