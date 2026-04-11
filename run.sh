#!/usr/bin/env bash
set -euo pipefail

GAMES_ROOT="${1:-$HOME/Games}"
IGNORE_FILE="$GAMES_ROOT/.runignore"

# Check for fzf dependency
command -v fzf >/dev/null 2>&1 || { echo "fzf required"; exit 1; }
cd "$GAMES_ROOT" || { echo "games root not found: $GAMES_ROOT"; exit 1; }

mkdir -p "$(dirname -- "$IGNORE_FILE")"
touch "$IGNORE_FILE"

# Background vs Foreground logic
run_foreground() { exec "$@"; }
run_detached() { setsid "$@" >/dev/null 2>&1 & disown || true; exit 0; }

generate_list() {
    # Find native executables while ignoring raw .exe files 
    find . -maxdepth 3 -type f -executable -not -name "*.exe" -printf '%P\n' 2>/dev/null || true
}

build_menu() {
    mapfile -t _ign < "$IGNORE_FILE"
    generate_list | sort -u | while IFS= read -r rel; do
        [ -z "$rel" ] || [ "$rel" = "." ] && continue
        
        # Respect .runignore
        skip=false
        for ig in "${_ign[@]}"; do
            [ "$ig" = "$rel" ] && { skip=true; break; }
        done
        $skip && continue

        local filename="${rel##*/}"
        
        # Peek at header for metadata icons 
        local icon="🐧"
        if head -n 5 "$rel" 2>/dev/null | grep -q "# ICON: 💻"; then
            icon="💻"
        elif head -n 5 "$rel" 2>/dev/null | grep -q "# ICON: 🐧"; then
            icon="🐧"
        fi

        printf '%s\t%s\t%s\n' "$icon" "$filename" "$rel"
    done
}

while true; do
    menu=$(build_menu)
    [ -z "$menu" ] && { echo "No games found."; exit 1; }

    # UI with fzf
    IFS=$'\n' read -r -d '' -a out < <(printf '%s\n' "$menu" | \
        fzf --prompt="Select game: " \
            --expect=tab,enter \
            --delimiter=$'\t' \
            --with-nth=1,2 \
            --height=20 --border --ansi && printf '\0')
    
    [ ${#out[@]} -eq 0 ] && exit 1

    key="${out[0]}"
    sel_line="${out[1]:-}"
    [ -z "$sel_line" ] && continue

    relpath="${sel_line##*$'\t'}"
    sel_icon="${sel_line%%$'\t'*}"

    # Tab to ignore functionality 
    if [ "$key" = "tab" ]; then
        if ! grep -Fxq -- "$relpath" "$IGNORE_FILE"; then
            printf '%s\n' "$relpath" >> "$IGNORE_FILE"
        fi
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

    [ -t 1 ] && run_foreground "${cmd[@]}" || run_detached "${cmd[@]}"
    break
done
