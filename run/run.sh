#!/usr/bin/env bash
set -euo pipefail

GAMES_ROOT="${1:-$HOME/Games}"
IGNORE_FILE="$GAMES_ROOT/.runignore"

# Check for fzf dependency
command -v fzf >/dev/null 2>&1 || {
  echo "fzf required"
  exit 1
}
cd "$GAMES_ROOT" || {
  echo "games root not found: $GAMES_ROOT"
  exit 1
}

mkdir -p "$(dirname -- "$IGNORE_FILE")"
touch "$IGNORE_FILE"

# Background vs Foreground logic
run_detached() {
  setsid "$@" >/dev/null 2>&1 &
  disown || true
  exit 0
}

generate_list() {
  # Find native executables, ignoring common library/data directories and git
  find . -maxdepth 3 \
    -not \( -path '*/lib/*' -o -path '*/lib64/*' -o -path '*/share/*' -o -path '*/.git/*' \) \
    -type f -executable -not -name "*.exe" -printf '%P\n' 2>/dev/null || true
}

build_menu() {
  # Load ignored files into an associative array for O(1) lookups
  declare -A ignores
  if [ -f "$IGNORE_FILE" ]; then
    while IFS= read -r line; do
      [ -n "$line" ] && ignores["$line"]=1
    done < "$IGNORE_FILE"
  fi

  generate_list | sort -u | while IFS= read -r rel; do
    [ -z "$rel" ] || [ "$rel" = "." ] && continue
    [[ -v ignores["$rel"] ]] && continue

    local filename="${rel##*/}"
    local icon="🐧"

    # Peek at first 2 bytes to check if it's a script before reading lines
    if [ -f "$rel" ] && [ -r "$rel" ]; then
      local magic
      read -r -N 2 magic < "$rel" 2>/dev/null || true
      if [ "${magic:-}" = "#!" ]; then
        local line line_count=0
        while IFS= read -r line && [ $line_count -lt 5 ]; do
          if [[ "$line" == *"# ICON: 💻"* ]]; then
            icon="💻"
            break
          elif [[ "$line" == *"# ICON: 🐧"* ]]; then
            icon="🐧"
            break
          fi
          ((line_count++))
        done < "$rel" 2>/dev/null
      fi
    fi

    printf '%s\t%s\t%s\n' "$icon" "$filename" "$rel"
  done
}

# Build the menu once and cache it in memory
menu=$(build_menu)

while true; do
  [ -z "$menu" ] && {
    echo "No games found."
    exit 1
  }

  # UI with fzf
  IFS=$'\n' read -r -d '' -a out < <(printf '%s\n' "$menu" |
    fzf --prompt="Select game: " \
      --expect=tab,enter \
      --delimiter=$'\t' \
      --with-nth=1,2 \
      --height=20 --border --ansi && printf '\0')

  [ ${#out[@]} -eq 0 ] && exit 1

  key="${out[0]}"
  sel_line="${out[1]:-}"
  [ -z "$sel_line" ] && exit 0

  relpath="${sel_line##*$'\t'}"
  sel_icon="${sel_line%%$'\t'*}"

  # Tab to ignore functionality
  if [ "$key" = "tab" ]; then
    if ! grep -Fxq -- "$relpath" "$IGNORE_FILE"; then
      printf '%s\n' "$relpath" >>"$IGNORE_FILE"
    fi
    # Remove the selected item from the menu variable dynamically
    menu="$(printf '%s\n' "$menu" | grep -v -F "$sel_line" || true)"
    continue
  fi

  SEL_PATH="$(realpath -- "$relpath")"
  cd "$(dirname -- "$SEL_PATH")" || exit 1

  # Wayland/Potato fixes for native games
  if [ "$sel_icon" = "💻" ]; then
    cmd=("./${relpath##*/}")
  else
    cmd=(env SDL_VIDEODRIVER=x11 "./${relpath##*/}")
  fi

  run_detached "${cmd[@]}"
  break
done
