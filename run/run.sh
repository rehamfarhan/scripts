#!/usr/bin/env bash
# Resolve this script's real path even when invoked through a symlink
# (the `run` command on PATH points here).
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
BIN="$SCRIPT_DIR/target/release/run"

if [[ ! -x "$BIN" ]]; then
    echo "Compiling game launcher release binary..."
    cargo build --release --manifest-path "$SCRIPT_DIR/Cargo.toml"
fi

exec "$BIN" "$@"
