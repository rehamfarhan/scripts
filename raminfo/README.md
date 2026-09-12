# 📊 raminfo

A simple, well-formatted script that displays detailed memory (RAM) and swap usage information on Linux systems.

## 🚀 Installation

```bash
# Make executable
chmod +x raminfo.sh

# Link to system path (using scrlink)
scrlink raminfo/raminfo.sh raminfo
```

## 📖 Usage

```bash
raminfo
```

## 📋 Output

The script displays:

### Overview
- Total RAM
- Used RAM (calculated)
- Available RAM
- Visual usage bar with percentage

### Breakdown
- Free memory
- Buffers
- Cached memory
- SReclaimable
- Slab
- Active / Inactive
- Mapped
- Shmem
- Mlocked
- Dirty

### Kernel
- Kernel Stack
- Page Tables

### Swap (if enabled)
- Total swap
- Used swap
- Free swap
- Visual usage bar

## ⚠️ Notes

- Works on Linux systems with `/proc/meminfo`
- No external dependencies required
- All values displayed in GB
