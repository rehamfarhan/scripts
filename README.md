# 💰 Money Git CLI

A **Git-inspired terminal app** to track your money with speed, clarity, and discipline.

Instead of complex apps, this tool keeps things simple:

* Every transaction = a commit
* Your balance = your repo state
* Reservations = money you’ve already mentally spent

---

# 🚀 Features

## ⚡ 1. Lightning-Fast Transactions

Log money naturally using shorthand:

```bash
money +500 Mom's vault
money -90 Croissant Burger @lakeviewcafe
```

### Rules:

* `+` → money added
* `-` → money spent
* `@source` → where it was spent
* everything else → note

---

## 📜 2. Transaction History (Log)

```bash
money log
```

Shows a clean table:

```
+----------+---------------------+--------+----------------+---------+--------------------------+
| ID       | Date                | Action | Source         | Amount  | Note                     |
+----------+---------------------+--------+----------------+---------+--------------------------+
```

* Unique IDs for each transaction
* Fully readable history
* Acts like `git log`

---

## 📊 3. Status Overview

```bash
money status
```

Outputs:

```
Total:     BDT 1100
Reserved:  BDT 1200
Available: BDT -100
```

### Definitions:

* **Total** → all money you physically have
* **Reserved** → money already committed
* **Available** → what you can safely spend

---

## 🔒 4. Reservation System (Core Feature)

Reserve money you *shouldn’t touch*:

```bash
money reserve 1200 RafiqulSir
```

### What this does:

* Locks the amount mentally
* Does NOT reduce total balance
* Reduces available balance

---

## ✅ 5. Settle Reservations

```bash
money settle RafiqulSir
```

### What happens:

* Reservation is removed
* A **spend transaction is created automatically**

Example:

```
-1200 RafiqulSir
```

---

## 📋 6. View Active Reservations

```bash
money reserves
```

Shows:

```
+--------------+---------------------+---------+
| ID           | Created             | Amount  |
+--------------+---------------------+---------+
| RafiqulSir   | 2026-04-11 12:00:00 | BDT 1200|
```

---

## 🧹 7. Undo & Delete

### Undo last transaction:

```bash
money undo
```

### Delete specific transaction:

```bash
money delete <id>
```

---

## 🔍 8. Search

```bash
money search coffee
```

Searches:

* source
* note
* action
* timestamp

---

## ⚙️ 9. Configuration

Set currency:

```bash
money config --currency BDT
```

---

# ⚠️ Intelligent Warnings

The app doesn’t just track — it **guides you**.

### Examples:

#### Overspending reserved money:

```
⚠️ Available is below zero.
   That usually means money is already committed.
```

#### Going into real debt:

```
⚠️ Your total balance is now negative.
   This is real debt.
```

#### Risky settlement:

```
⚠️ You are about to go into negative balance.
```

#### Over-reserving:

```
⚠️ This reservation pushes available below zero.
```

---

# 🧠 Philosophy

This tool is built on 3 core ideas:

### 1. Truth over comfort

It will not hide bad decisions — it shows them clearly.

---

### 2. Speed over friction

If logging is slow, you won’t use it.
That’s why shorthand exists.

---

### 3. Awareness over automation

You stay in control.
The tool simply reflects your behavior.

---

# 🧩 Data Structure

All data is stored locally:

```
.moneygit/
├── ledger.json        # transactions
├── reservations.json  # active reservations
├── history.json       # action history (for universal undo)
└── config.json        # settings
```

---

# 🔥 Example Workflow

```bash
money init

money +1200 Mom
money reserve 1200 RafiqulSir

money -100 snacks

money status
# Available will go negative → warning

money settle RafiqulSir

money status
# Now total reflects reality
```

---

---

# 🔄 Universal Undo System (history.json)

The app uses a **history-based undo system** instead of only removing the last transaction.

### 📁 history.json

Stores every action performed:

- transaction commits
- reservations
- settlements
- deletions

---

## 🔁 How Undo Works

money undo

Reverses the **last action**, not just the last transaction.

### Examples:

#### Undo a transaction:
+500 Mom → undo → removed

#### Undo a reservation:
reserve 1200 RafiqulSir → undo → reservation removed

#### Undo a settle:
settle RafiqulSir → undo →
- removes spend transaction
- restores reservation

---

## 🧠 Why This Matters

This makes undo:

- consistent  
- predictable  
- safe  

You no longer lose reservations accidentally.

---

# ⚠️ Known Limitations

* no partial settle (by design)
* deleting transactions can affect balance logic

---

# 🛠️ Future Ideas

* Category/tag system
* Monthly reports
* Export to CSV
* Risk detection before actions

---

# 💡 Final Note

This isn’t just a money tracker.

It’s a **behavior mirror**.

If something looks wrong — it probably is.

---

# 📦 Installation

Clone your repo:

```bash
git clone https://github.com/rehamfarhan/scripts.git
cd scripts
```

Run:

```bash
python3 money.py
```

(Optional alias)

```bash
alias m="python3 money.py"
```

---

# 🧠 Author

Built by Reham Farhan
Refined with obsessive attention to clarity, speed, and real-life usability.

---
