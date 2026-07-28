#!/usr/bin/env bash
set -euo pipefail

# Script Linker (scrlink)
# Symlinks repository scripts to /usr/local/bin for system-wide execution.

SCRIPTS_DIR="/home/directpass/scripts"
BIN_DIR="/usr/local/bin"

# Help message
show_help() {
  cat <<EOF
Usage: scrlink [<source_script_or_folder>] [<target_name>]

Examples:
  scrlink money.py money
  scrlink money/money.py
  scrlink money
  scrlink                (Launches fzf interactive menu)
EOF
}

# Check for help flags
if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  show_help
  exit 0
fi

# 1. Interactive fzf mode if no args provided
if [ $# -eq 0 ]; then
  if ! command -v fzf >/dev/null 2>&1; then
    echo "Error: fzf is required for interactive mode."
    show_help
    exit 1
  fi

  cd "$SCRIPTS_DIR"
  # Find all standalone script files (.sh, .py)
  SELECTED=$(find . -maxdepth 2 -type f \( -name "*.sh" -o -name "*.py" \) -not -path '*/.*' | sed 's|^\./||' | fzf --prompt="Select script to link: " --height=20 --border)

  if [ -z "$SELECTED" ]; then
    echo "No script selected."
    exit 0
  fi

  read -rp "Enter target command name (leave blank for default): " TARGET_INPUT
  SOURCE="$SELECTED"
  TARGET="$TARGET_INPUT"
else
  SOURCE="$1"
  TARGET="${2:-}"
fi

# 2. Resolve source script path
SCRIPT_PATH=""

if [[ "$SOURCE" = /* ]]; then
  # Absolute path passed
  SCRIPT_PATH="$SOURCE"
elif [ -f "$SCRIPTS_DIR/$SOURCE" ]; then
  # Script directly in root scripts directory
  SCRIPT_FILE="$SCRIPTS_DIR/$SOURCE"
  BASENAME="$(basename "$SOURCE")"
  DIRNAME="${BASENAME%.*}"
  NEW_DIR="$SCRIPTS_DIR/$DIRNAME"

  echo "📦 Migration detected: Attempting to move '$BASENAME' into standalone directory '$DIRNAME/'..."
  
  MOVED=0
  if mkdir -p "$NEW_DIR" 2>/dev/null; then
    TARGET_FILE="$NEW_DIR/$BASENAME"
    if command -v git >/dev/null 2>&1 && git ls-files --error-unmatch "$SCRIPT_FILE" >/dev/null 2>&1; then
      if git mv "$SCRIPT_FILE" "$TARGET_FILE" 2>/dev/null; then
        MOVED=1
      fi
    fi

    if [ $MOVED -eq 0 ]; then
      if mv "$SCRIPT_FILE" "$TARGET_FILE" 2>/dev/null; then
        MOVED=1
      fi
    fi

    if [ $MOVED -eq 1 ]; then
      # Create starter README.md if missing
      README_FILE="$NEW_DIR/README.md"
      if [ ! -f "$README_FILE" ]; then
        cat >"$README_FILE" <<EOF
# 🛠️ $DIRNAME

Standalone utility script \`$BASENAME\`.

## 📖 Usage
\`\`\`bash
./$BASENAME
\`\`\`
EOF
        echo "📝 Created starter README.md in '$DIRNAME/README.md'."
      fi
      SCRIPT_PATH="$TARGET_FILE"
    else
      echo "⚠️  Warning: Failed to move '$BASENAME' to '$DIRNAME/'. Proceeding with original script location."
      SCRIPT_PATH="$SCRIPT_FILE"
    fi
  else
    echo "⚠️  Warning: Failed to create directory '$NEW_DIR/'. Proceeding with original script location."
    SCRIPT_PATH="$SCRIPT_FILE"
  fi
elif [ -f "$SCRIPTS_DIR/$SOURCE/$SOURCE.sh" ]; then
  SCRIPT_PATH="$SCRIPTS_DIR/$SOURCE/$SOURCE.sh"
elif [ -f "$SCRIPTS_DIR/$SOURCE/$SOURCE.py" ]; then
  SCRIPT_PATH="$SCRIPTS_DIR/$SOURCE/$SOURCE.py"
elif [ -d "$SCRIPTS_DIR/$SOURCE" ]; then
  # Passed a directory name, look for contained executable script matching name
  FOUND_PATH=$(find "$SCRIPTS_DIR/$SOURCE" -maxdepth 1 -type f \( -name "*.sh" -o -name "*.py" \) | head -n 1)
  if [ -n "$FOUND_PATH" ]; then
    SCRIPT_PATH="$FOUND_PATH"
  fi
elif [ -f "$SCRIPTS_DIR/$SOURCE" ]; then
  SCRIPT_PATH="$SCRIPTS_DIR/$SOURCE"
else
  # Subfolder relative path search
  FOUND_PATH=$(find "$SCRIPTS_DIR" -mindepth 2 -maxdepth 2 -type f -name "$(basename "$SOURCE")" | head -n 1)
  if [ -n "$FOUND_PATH" ]; then
    SCRIPT_PATH="$FOUND_PATH"
  fi
fi

if [ -z "$SCRIPT_PATH" ] || [ ! -f "$SCRIPT_PATH" ]; then
  echo "Error: Could not locate script '$SOURCE' in $SCRIPTS_DIR"
  exit 1
fi

# 3. Derive target command name if not specified
if [ -z "$TARGET" ]; then
  BASE_FILE="$(basename "$SCRIPT_PATH")"
  TARGET="${BASE_FILE%.*}"
fi

# 4. Make executable & create symlink
chmod +x "$SCRIPT_PATH"

echo "🔗 Symlinking $SCRIPT_PATH -> $BIN_DIR/$TARGET"
if [ "$EUID" -ne 0 ]; then
  sudo ln -sf "$SCRIPT_PATH" "$BIN_DIR/$TARGET"
else
  ln -sf "$SCRIPT_PATH" "$BIN_DIR/$TARGET"
fi

echo "✅ Linked successfully: $TARGET -> $SCRIPT_PATH"
