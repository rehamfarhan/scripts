#!/bin/bash

# Usage: linkscript <source_script> <target_name>

SCRIPTS_DIR="$HOME/scripts"
BIN_DIR="/usr/local/bin"

# Check args
if [ $# -ne 2 ]; then
  echo "Usage: linkscript <source_script> <target_name>"
  exit 1
fi

SOURCE="$1"
TARGET="$2"

# Resolve source path
if [[ "$SOURCE" = /* ]]; then
  SCRIPT_PATH="$SOURCE"
else
  SCRIPT_PATH="$SCRIPTS_DIR/$SOURCE"
fi

# Check if script exists
if [ ! -f "$SCRIPT_PATH" ]; then
  echo "Error: Script not found at $SCRIPT_PATH"
  exit 1
fi

# Make executable
chmod +x "$SCRIPT_PATH"

# Create symlink with custom name
sudo ln -sf "$SCRIPT_PATH" "$BIN_DIR/$TARGET"

echo "Linked $SCRIPT_PATH -> $BIN_DIR/$TARGET"
