#!/usr/bin/env bash
set -euo pipefail

declare -A mem

while IFS=: read -r key value; do
  key=$(echo "$key" | xargs)
  value=$(echo "$value" | sed 's/ kB//' | xargs)
  mem[$key]=$value
done </proc/meminfo

to_gb() { awk "BEGIN {printf \"%.2f\", $1/1048576}"; }
to_pct() { awk "BEGIN {printf \"%.1f\", ($1/$2)*100}"; }

total=${mem[MemTotal]}
free=${mem[MemFree]}
available=${mem[MemAvailable]}
buffers=${mem[Buffers]}
cached=${mem[Cached]}
sreclaimable=${mem[SReclaimable]}
swap_total=${mem[SwapTotal]}
swap_free=${mem[SwapFree]}
swap_used=$((swap_total - swap_free))

used=$((total - free - buffers - cached - sreclaimable))
if ((used < 0)); then used=0; fi

swap_used=$((swap_total - swap_free))

bar() {
  local pct=$1 width=30
  local filled=$(awk "BEGIN {printf \"%d\", $pct * $width / 100}")
  local empty=$((width - filled))
  printf "["
  for ((i = 0; i < filled; i++)); do printf "█"; done
  for ((i = 0; i < empty; i++)); do printf "░"; done
  printf "]"
}

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                      MEMORY OVERVIEW                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Total:       $(to_gb $total) GB"
echo "  Used:        $(to_gb $used) GB  ($(to_pct $used $total)%)"
echo "  Available:   $(to_gb $available) GB  ($(to_pct $available $total)%)"
echo ""
echo "  $(bar $(to_pct $used $total))  $(to_pct $used $total)%"
echo ""
