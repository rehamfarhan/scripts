# raminfo

Prints memory usage.

`free -h` gives the headline numbers but not the breakdown, and it doesn't show how much of the total is actually in use at a glance. `raminfo` reads `/proc/meminfo`, calculates used memory the same way `free` does, and prints it with bars and the individual fields.

## Output

Overview: total, used and available, plus a bar with the used percentage.

Breakdown: free, buffers, cached, SReclaimable, slab, active/inactive, mapped, shared memory, mlocked, dirty.

Kernel: kernel stack and page tables.

Swap: total, used and free, with a bar. Skipped if there's no swap.

All values are in GB, rounded to two decimals.

## Install

```bash
chmod +x raminfo.sh
scrlink raminfo/raminfo.sh raminfo
```

## Usage

```bash
raminfo
```

## Notes

- Linux only; it reads `/proc/meminfo`.
- No external dependencies.
- The "used" figure is `MemTotal - MemFree - Buffers - Cached - SReclaimable`, not `MemTotal - MemAvailable`, so it can differ from some other tools. `Available` is printed separately if that's what you want.
