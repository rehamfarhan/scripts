# 💰 Money Git CLI (`money.py`)

A **Git-inspired terminal ledger** to track your finances with speed, clarity, and discipline. It stores data locally in a hidden `.moneygit/` folder within your current project or workspace.

---

## 📋 Technical Overview

- **Language**: Python 3
- **Dependencies**: Python standard library (`argparse`, `json`, `pathlib`, `datetime`, `re`)
- **System Location**: `money/money.py`
- **Target Command**: `money`

---

## ✨ Features

- **Shorthand Quick Entry**: Record transactions instantly with syntax like `money +500 Salary` or `money -90 Burger @cafe` (use `@` to separate optional notes from the source).
- **Reservation System**: Mentally lock/reserve funds (e.g., for rent, bills) to see your actual available balance.
- **Detailed Log**: View complete transaction history in a cleanly formatted ASCII table.
- **Search & Filter**: Search transactions by source, action, timestamp, or notes.
- **Undo & Delete**: Quickly remove the last transaction using `undo` or delete specific transactions via ID prefixes.
- **Configurable Currency**: Set and display custom currencies (e.g., USD, BDT, EUR).

---

## 🚀 Setup & Installation

Link the script to `/usr/local/bin` using `scrlink`:

```bash
sudo ../scrlink/scrlink.sh money/money.py money
# or using scrlink helper:
sudo scrlink money
```

Initialize a ledger in any working directory:

```bash
money init
```

---

## 📖 Command Reference

```bash
money init                                     # Initialize a new ledger in the current directory
money status                                   # View total, reserved, and available balance
money balance                                  # Print current total balance value only
money log                                      # Display history of all transactions
money commit --source <src> --action <act> ... # Record transaction with specific flags
money commit "<source>, <action>, <amount>"    # Record transaction with legacy comma-separated text
money reserve <amount> <identifier>            # Lock funds under a specific label
money reserves                                 # List all active reservations
money settle <identifier>                      # Settle a reservation (converts to spend transaction)
money delete <id_prefix>                       # Delete transaction matching ID prefix
money undo                                     # Remove the last recorded transaction
money search <query>                           # Search ledger history
money config --currency <USD/BDT/etc>          # Configure display currency
```

---

## 💡 Usage Examples

```bash
# Quick income entry
money +1500 Freelance Pay

# Quick expense entry with custom note
money -25 Coffee @coffeebar

# Reserve funds for bills
money reserve 1200 Rent

# View current balance and available funds
money status

# Settle reservation once paid
money settle Rent
```
