#!/usr/bin/env python3
import os
import sys
from pathlib import Path

script_dir = Path(__file__).resolve().parent
bin_path = script_dir / "target" / "release" / "run"

if bin_path.is_file() and os.access(bin_path, os.X_OK):
    os.execv(str(bin_path), [str(bin_path)] + sys.argv[1:])

sh_path = script_dir / "run.sh"
if sh_path.is_file() and os.access(sh_path, os.X_OK):
    os.execv(str(sh_path), [str(sh_path)] + sys.argv[1:])

print("Error: Compiled Rust binary 'target/release/run' not found. Run 'cargo build --release' first.", file=sys.stderr)
sys.exit(1)
