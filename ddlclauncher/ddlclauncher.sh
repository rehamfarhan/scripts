#!/usr/bin/env bash
set -euo pipefail

# ========= CONFIG =========
MODS_ROOT="$HOME/DDLC Mods"
LAUNCHER_DIR="$MODS_ROOT/.launchers"
DB_FILE="$LAUNCHER_DIR/mod_database.txt"

# ========= DEP CHECK =========
command -v fzf >/dev/null 2>&1 || {
  echo "fzf required"
  exit 1
}

# ========= SETUP =========
mkdir -p "$MODS_ROOT"
mkdir -p "$LAUNCHER_DIR"
touch "$DB_FILE"

cd "$MODS_ROOT" || {
  echo "DDLC Mods folder not found: $MODS_ROOT"
  exit 1
}

# ========= EMOJI POOL =========
EMOJIS=(💔 🩸 🧠 🌸 🎭 😢 😈 🖤 💌 🕊️ 🧩 🌀 👁️ 🔮 🫥 🫠 🧬 🎮 🕹️ 🚪 📖 🎧 🍪 🎀 📚 📝)

get_random_emoji() {
  printf "%s\n" "${EMOJIS[RANDOM % ${#EMOJIS[@]}]}"
}

# ========= DETACH RUN =========
run_detached() {
  setsid "$@" >/dev/null 2>&1 &
  disown || true
}

# ========= LOAD DATABASE =========
mapfile -t KNOWN_MODS <"$DB_FILE"

is_known_mod() {
  local mod="$1"
  for m in "${KNOWN_MODS[@]}"; do
    [[ "$m" == "$mod" ]] && return 0
  done
  return 1
}

# ========= FIND EXECUTABLES =========
find_executables() {
  find "$1" -maxdepth 1 -type f \( -name "*.sh" -o -name "*.py" -o -name "*.exe" \) -printf "%f\n"
}

# ========= CREATE LAUNCHER =========
create_launcher() {
  local mod_dir="$1"
  local mod_name
  mod_name="$(basename "$mod_dir")"

  echo "New Mod Folder Detected: $mod_name"

  mapfile -t EXES < <(find_executables "$mod_dir")

  if [ ${#EXES[@]} -eq 0 ]; then
    echo "No executables found in $mod_name, skipping..."
    return
  fi

  exe=$(printf "%s\n" "${EXES[@]}" | fzf --prompt="Select executable for $mod_name: " --height=20 --border)
  [ -z "$exe" ] && return

  read -rp "Enter launcher name: " lname
  [ -z "$lname" ] && return

  safe_name="$(echo "$lname" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')"
  launcher_path="$LAUNCHER_DIR/$safe_name"

  emoji="$(get_random_emoji)"

  # PRECOMPUTE EXTENSION
  ext="${exe##*.}"

  cat >"$launcher_path" <<EOF
#!/usr/bin/env bash
# NAME: $lname
# EMOJI: $emoji
# TARGET: $exe
# MODDIR: $mod_dir

cd "$mod_dir" || exit 1

if [ ! -f "$exe" ]; then
  echo "Executable not found: $exe"
  exit 1
fi

echo "Opening $lname @ $exe"

ext="$ext"

case "\$ext" in
  sh)
    cmd=( "./$exe" )
    ;;
  py)
    cmd=( python "./$exe" )
    ;;
  exe)
    cmd=( wine "./$exe" )
    ;;
  *)
    echo "Unsupported file type: $exe"
    exit 1
    ;;
esac

setsid "\${cmd[@]}" >/dev/null 2>&1 &
disown || true
EOF

  chmod +x "$launcher_path"

  echo "$mod_dir" >>"$DB_FILE"

  echo "Launcher created: $lname ($emoji)"
}

# ========= SCAN FOR NEW MODS =========
for dir in */; do
  dir="${dir%/}"

  [ "$dir" = ".launchers" ] && continue

  [ -d "$dir" ] || continue

  full_path="$MODS_ROOT/$dir"

  if ! is_known_mod "$full_path"; then
    create_launcher "$full_path"
  fi
done

# ========= BUILD MENU =========
build_menu() {
  for l in "$LAUNCHER_DIR"/*; do
    [ -f "$l" ] || continue

    name=$(grep '^# NAME:' "$l" | cut -d':' -f2- | xargs)
    emoji=$(grep '^# EMOJI:' "$l" | cut -d':' -f2- | xargs)

    printf "%s\t%s\t%s\n" "$emoji" "$name" "$l"
  done
}

menu=$(build_menu)

[ -z "$menu" ] && {
  echo "No launchers available."
  exit 1
}

IFS=$'\n' read -r -d '' -a out < <(
  printf '%s\n' "$menu" |
    fzf --prompt="Select DDLC Mod: " \
      --expect=tab,enter \
      --delimiter=$'\t' \
      --with-nth=1,2 \
      --height=20 --border &&
    printf '\0'
)

[ ${#out[@]} -eq 0 ] && exit 0

key="${out[0]}"
sel_line="${out[1]:-}"
[ -z "$sel_line" ] && exit 0

launcher="${sel_line##*$'\t'}"

# ========= DELETE MODE =========
if [ "$key" = "tab" ]; then
  mod_dir=$(grep '^# MODDIR:' "$launcher" | cut -d':' -f2- | xargs)

  rm -f "$launcher"

  grep -Fxv "$mod_dir" "$DB_FILE" >"$DB_FILE.tmp" && mv "$DB_FILE.tmp" "$DB_FILE"

  echo "Launcher removed."
  exit 0
fi

# ========= RUN =========
run_detached "$launcher"
