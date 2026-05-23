#!/usr/bin/env bash

# b64decode.sh
# Minimal Base64 decoder with automatic clipboard copy

decoded="$(printf '%s' "$1" | base64 -d 2>/dev/null)"

if [ $? -ne 0 ]; then
    echo "Invalid Base64 input"
    exit 1
fi

printf '%s' "$decoded"

# Clipboard support (Wayland/X11/macOS fallback)
if command -v wl-copy >/dev/null 2>&1; then
    printf '%s' "$decoded" | wl-copy
elif command -v xclip >/dev/null 2>&1; then
    printf '%s' "$decoded" | xclip -selection clipboard
elif command -v pbcopy >/dev/null 2>&1; then
    printf '%s' "$decoded" | pbcopy
fi
