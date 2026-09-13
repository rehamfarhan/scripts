#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$SCRIPT_DIR/target/release/run"

if [[ ! -x "$BIN" ]]; then
    echo "Compiling game launcher release binary..."
    cargo build --release --manifest-path "$SCRIPT_DIR/Cargo.toml"
fi

exec "$BIN" "$@"
