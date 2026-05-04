#!/usr/bin/env bash

set -e

DESKTOP_DIR="$HOME/.local/share/applications"

echo "=== .desktop Entry Creator ==="

# Ensure directory exists
mkdir -p "$DESKTOP_DIR"

# Prompt user
read -rp "App Name (what shows in rofi): " NAME
read -rp "Command to run (full path recommended): " EXEC
read -rp "Comment/Description: " COMMENT
read -rp "Icon (name or full path, leave blank for default): " ICON
read -rp "Run in terminal? (y/n): " TERMINAL
read -rp "Categories (e.g. Utility;Development;): " CATEGORIES

# Normalize terminal input
if [[ "$TERMINAL" =~ ^[Yy]$ ]]; then
  TERMINAL_VAL="true"
else
  TERMINAL_VAL="false"
fi

# Generate filename (safe)
FILENAME=$(echo "$NAME" | tr ' ' '_' | tr -cd '[:alnum:]_')
FILEPATH="$DESKTOP_DIR/$FILENAME.desktop"

# Create .desktop file
cat >"$FILEPATH" <<EOF
[Desktop Entry]
Name=$NAME
Exec=$EXEC
Comment=$COMMENT
Icon=${ICON:-utilities-terminal}
Terminal=$TERMINAL_VAL
Type=Application
Categories=${CATEGORIES:-Utility;}
EOF

# Make it executable (optional but nice)
chmod +x "$FILEPATH"

echo ""
echo "✅ Created: $FILEPATH"
echo "You can now launch it via rofi!"
