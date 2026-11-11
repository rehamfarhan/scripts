# money

A tiny terminal money tracker. One command, plain-text files, one folder per month.

```
$ money -90 Croissant Burger @lakeviewcafe :food
Recorded 43e15982: lakeviewcafe -BDT 90  :food
```

- **Fast entry:** `money +500 ...` for income, `money -90 ...` for spending.
- **Reservations:** set money aside for a purpose, then settle it into a real spend when you pay.
- **Months:** `money archive` closes a finished month, carries the balance forward and starts a fresh ledger.
- **Plain files:** append-only JSON lines you can `grep`, diff and back up with git.

Python 3.9+, standard library only. Developed and tested on Python 3.12.

---

## Contents

1. [Install](#install)
2. [The idea in 60 seconds](#the-idea-in-60-seconds)
3. [First-time walkthrough](#first-time-walkthrough)
4. [Entry syntax](#entry-syntax)
5. [Command reference](#command-reference)
6. [Month-end and archives](#month-end-and-archives)
7. [Undo, delete and recovery](#undo-delete-and-recovery)
8. [Where your data lives](#where-your-data-lives)
9. [Troubleshooting](#troubleshooting)
10. [Design notes and limits](#design-notes-and-limits)
11. [Development](#development)

---

## Install

```bash
chmod +x money.py
ln -s "$PWD/money.py" /usr/local/bin/money    # may need sudo
money init
```

`money init` creates `~/money/` and the current month's ledger. To keep your data somewhere else, set `MONEY_DIR`:

```bash
export MONEY_DIR=~/Documents/finances
```

Change the currency label (default `BDT`) any time:

```bash
money config --currency USD
```

---

## The idea in 60 seconds

Every month has three numbers:

| Number | Meaning |
|---|---|
| **Total** | Everything you actually have: income minus spending. |
| **Reserved** | Money you've earmarked for something, like rent or a tutor, but haven't paid yet. |
| **Available** | `Total - Reserved`. This is what you can spend freely. |

A **reservation** moves money from Available to Reserved without spending it. When you pay, you **settle** it: it becomes a real spend and Total drops. If plans change, **release** it and the money is Available again.

Each calendar month has its own folder and its own ledger. When a month ends, `money archive` locks it, then opens the new month with your carried-over balance, your unsettled reservations, and your recurring ones.

---

## First-time walkthrough

Everything below is real output from the script. Your IDs, dates and paths will differ.

### 1. Create your ledger (once)

```
$ money init
Initialized money in /home/you/money
```

### 2. Record money coming in

```
$ money +25000 "Mom's vault"
Recorded 29c1c0ce: Mom's vault +BDT 25,000
```

Quote the description if it contains an apostrophe, or your shell will wait for a closing quote.

### 3. Set up bills that repeat every month

```
$ money recur add 12000 Rent :housing
Recurring: Rent BDT 12,000/month  :housing
   Reserved for this month too.

$ money recur add 500 Internet :bills
Recurring: Internet BDT 500/month  :bills
   Reserved for this month too.
```

Each one is reserved now and re-reserved automatically at the start of every new month.

### 4. Log everyday spending

The format is `-AMOUNT note @source :tags`:

```
$ money -90 Croissant Burger @lakeviewcafe :food
Recorded 43e15982: lakeviewcafe -BDT 90  :food

$ money -250 Rickshaw fares :transport
Recorded 4c212d4b: Rickshaw fares -BDT 250  :transport
```

With an `@`, the text after it is the **source** and the text before it is the **note**. Without an `@`, the whole text is the source.

### 5. Reserve money for something coming up

```
$ money reserve 1500 RafiqulSir :tutor
Reserved BDT 1,500 for RafiqulSir  :tutor

$ money status
Month:     2026-10 (26 days left)
Total:     BDT 24,660
Reserved:  BDT 14,000  (3 active)
Available: BDT 10,660
```

You have BDT 24,660, but BDT 14,000 is spoken for (rent, internet, tutor). Only BDT 10,660 is free to spend. Bare `money` with no arguments also shows this.

### 6. Pay a reservation (settle)

```
$ money settle RafiqulSir --amount 1400
Settled RafiqulSir: BDT 1,400 (reserved BDT 1,500)

$ money settle Internet
Settled Internet: BDT 500
```

`--amount` records what you actually paid when it differs from what you reserved. Without it, the full reserved amount is used. If you decide not to pay at all, `money release RafiqulSir` cancels the reservation and spends nothing.

### 7. Fix mistakes

Typo'd a spend? `undo` deletes the most recent entry:

```
$ money -900 groceri @shwapno :food
Recorded 9ca7676f: shwapno -BDT 900  :food

$ money undo
Deleted 9ca7676f: spend shwapno BDT 900

$ money -90 Rice and dal @shwapno -d yesterday
Recorded 0e8edf6d: shwapno -BDT 90
```

`-d yesterday` (or `--date 2026-10-03`) backdates an entry within the current month.

### 8. Look at where the money went

```
$ money log
ID        Date              Type    Source               Amount     Balance  Tags        Note
--------  ----------------  ------  --------------  -----------  ----------  ----------  ----------------
0e8edf6d  2026-10-07 20:02  spend   shwapno             -BDT 90  BDT 22,670              Rice and dal
1c015b8b  2026-10-07 11:05  settle  Internet           -BDT 500  BDT 22,760  :bills
6db6d390  2026-10-07 11:00  settle  RafiqulSir       -BDT 1,400  BDT 23,260  :tutor
4c212d4b  2026-10-05 18:40  spend   Rickshaw fares     -BDT 250  BDT 24,660  :transport
43e15982  2026-10-05 13:10  spend   lakeviewcafe        -BDT 90  BDT 24,910  :food       Croissant Burger
29c1c0ce  2026-10-05 09:30  add     Mom's vault     +BDT 25,000  BDT 25,000

$ money summary --by tag
Tag                 In        Out         Net
----------  ----------  ---------  ----------
(untagged)  BDT 25,000     BDT 90  BDT 24,910
#tutor           BDT 0  BDT 1,400  BDT -1,400
#bills           BDT 0    BDT 500    BDT -500
#transport       BDT 0    BDT 250    BDT -250
#food            BDT 0     BDT 90     BDT -90
TOTAL       BDT 25,000  BDT 2,330  BDT 22,670

(an entry with several tags counts under each; TOTAL counts it once)
```

Newest entries come first, and the **Balance** column is the running total after each one. The 8-character ID in the first column is what you pass to `money delete`. You can also group `summary` by `month` or `source`.

### 9. The month ends

Once the calendar rolls over, `status` tells you:

```
$ money status
Month:     2026-10 (ended - run: money archive)
Total:     BDT 22,670
Reserved:  BDT 12,000  (1 active)
Available: BDT 10,670
```

Rent is still unpaid. Archive the month:

```
$ money archive
Closed 2026-10: BDT 22,670 (9 entries).
Opened 2026-11 with BDT 22,670; 1 reservation carried over, 2 recurring added.
   'Rent' is still unsettled from 2026-10, so this month's is named 'Rent 2026-11'.
```

What happened:

- October is now closed and read-only, with a checksum recorded.
- November starts with an **opening balance** of BDT 22,670. It is carried over, not counted as income.
- Last month's unpaid Rent was carried over, keeping its original creation date.
- Your recurring reservations were added. Rent would have clashed with the carried one, so it got the month in its name.

```
$ money status
Month:     2026-11 (30 days left)
Total:     BDT 22,670
Reserved:  BDT 24,500  (3 active)
Available: BDT -1,830
warning: Available is below zero. Usually an income entry is missing, or money is already spoken for.

$ money reserves
Name          Created               Amount  Tags
------------  ----------------  ----------  --------
Rent          2026-10-05 09:30  BDT 12,000  :housing
Rent 2026-11  2026-11-01 00:00  BDT 12,000  :housing
Internet      2026-11-01 00:00     BDT 500  :bills

Total reserved: BDT 24,500
```

Available is negative because you've reserved two months of rent and haven't recorded this month's income yet. Record it and pay the old rent:

```
$ money +20000 Salary
Recorded 9c5aa751: Salary +BDT 20,000

$ money settle Rent
Settled Rent: BDT 12,000
```

`settle Rent` always clears the **oldest** reservation with that name. To pay the other one, type its full name: `money settle Rent 2026-11` (no quotes needed).

### 10. Look back at old months

```
$ money months
Month    Entries     Balance    Reserved  Status
-------  -------  ----------  ----------  ------
2026-10        9  BDT 22,670  BDT 12,000  closed
2026-11        2  BDT 30,670  BDT 12,500  open

$ money log -m 2026-10 -n 3
ID        Date              Type    Source          Amount     Balance  Tags    Note
--------  ----------------  ------  ----------  ----------  ----------  ------  ------------
13103a42  2026-10-07 20:02  spend   shwapno        -BDT 90  BDT 22,670          Rice and dal
b0f9fadf  2026-10-07 11:05  settle  Internet      -BDT 500  BDT 22,760  :bills
27f823aa  2026-10-07 11:00  settle  RafiqulSir  -BDT 1,400  BDT 23,260  :tutor
```

`-m YYYY-MM` works on `log`, `status`, `balance`, `reserves`, `summary`, `search` and `export`.

You're set. The daily loop is `money -N what @where :tag`, `money status` when you wonder what's free, and `money archive` once a month.

---

## Entry syntax

```
money +AMOUNT  description      income
money -AMOUNT  description      spending
```

`add` and `spend` are the same thing spelled out: `money spend 90 cafe`.

**Amounts:** `500`, `89.50`, `1,200`, `1,200.50`. Up to 2 decimals. Zero, negatives, `nan`, `1e5` and 3+ decimals are rejected.

**Description:** `note @source :tags`

| You type | Source | Note | Tags |
|---|---|---|---|
| `cafe` | cafe | | |
| `Croissant Burger @lakeviewcafe` | lakeviewcafe | Croissant Burger | |
| `Burger @cafe :food :treat` | cafe | Burger | food, treat |
| `Burger @cafe -t food -t treat` | cafe | Burger | food, treat |

- **Tags:** start a word with `:`, like `:food`. Unlike `#` (a comment in many shells) and `!` (history expansion), `:` works unquoted in bash and zsh. Stack them as `:food :treat`, `:food:treat` or `:food,treat`, or use `-t food` (repeatable; `-t food,treat` also works). Tags are case-insensitive. Settling a reservation passes its tags on to the spend.
- A word made only of colons (`:`, `::`) is plain text, and colons inside a word (`10:30`, `shop:main`) are fine.
- **Dates:** `--date yesterday`, `--date 2026-10-03`, `--date "2026-10-03 14:30"`. Short form `-d`. Dates must be inside the active month and not in the future.
- **Options go after the description.**
- **Whitespace** (tabs, newlines, repeated spaces) is collapsed to single spaces.

### Special characters in sources, tags and names

These work **unquoted, anywhere** in sources, notes and reservation names: `@` `_` `-` `/` `.` `:` `+` `%` `=`. Tags take the same set, except `:` and `,`, which separate tags.

```
money -250 cashout @bkash/personal :fees/mobile-banking
money -90 lunch @me@bank.com :v2.1_beta
money -40 -discount applied @shop.v2:main      # a word may even start with "-"
money reserve 5000 Dr.Rafiq/tutor_1 :edu/private
```

Details:

- **Leading dashes:** after the amount, anything that isn't `-d/--date`, `-t/--tag` (or `-h`) is plain text, so `-cafe`, `-5% off` and `-weird` are fine. Tag values too: `-t -lead`.
- **`:` and `,` separate tags**, so they can't appear inside one: `:a:b` and `:a,b` are each two tags.
- **`#` means nothing to money.** `item #3` stays plain text. (A word *starting* with an unquoted `#` is eaten by shells that treat it as a comment, which is why tags use `:`. Quote it if you need it: `'#3'`.)
- **Tags** are lower-cased and spaces become `-` (`-t "eating out"` is `eating-out`). Sources keep the case you typed but are grouped case-insensitively in summaries.
- **Needs quotes (your shell, not money):** `! $ & ; | < > ( ) [ ] { } * ? \ ' "`, a leading `#`, and a leading `~`. In particular, an unquoted `>` or `<` is a shell redirect: write `money -20 bus "->" home`, not `money -20 bus -> home`.

---

## Command reference

| Command | What it does |
|---|---|
| `money` | Same as `money status`. |
| `money init` | Create `~/money` and the current month. |
| `money +N ...` / `money -N ...` | Record income / spending. |
| `money reserve N NAME [:tags]` | Set money aside. Names are case-insensitive and can be several words. |
| `money settle NAME [--amount N]` | Turn a reservation into a real spend. |
| `money release NAME` | Cancel a reservation without spending. |
| `money recur add N NAME [:tags]` | Reserve this every month. Also reserves it now. |
| `money recur list` / `remove NAME` | Show or stop recurring reservations. Existing reservations are untouched. |
| `money undo` | Delete the most recent entry. |
| `money delete ID` | Delete any entry by ID or unique ID prefix. |
| `money status` | Month, Total, Reserved, Available. |
| `money balance` | Just the total. |
| `money reserves` | Active reservations. |
| `money log` | Transactions with a running balance. Options: `-n 10`, `-t tag`, `-a` (all events), `-m 2026-09`. |
| `money search WORDS` | Searches source, note, tags, type, date and amount across **all** months. |
| `money summary` | In / Out / Net by `--by month` (default), `source` or `tag`, across all months. |
| `money export` | CSV to stdout. `--all` for every month, `-m` for one. |
| `money months` | Every month with entries, balance and status. |
| `money archive` | Close the finished month, open the current one. `--undo` reverses it (see below). |
| `money config [--currency XYZ]` | Show or change settings. |

Exit codes: `0` success, `2` an error (message on stderr). Warnings go to stderr and don't change the exit code.

---

## Month-end and archives

`money archive`:

1. Refuses to run until the month has actually ended.
2. Writes `closed.json` (closing total, reserved total, entry count, a SHA-256 checksum) and makes the ledger read-only.
3. Creates the folder for the **current** calendar month. If you skipped a month or more, it tells you which ones have no ledger.
4. Seeds it with, in order:
   - an **opening balance** (can be negative, never counted as income),
   - every still-active reservation, with its original creation date,
   - your recurring reservations.

**If you forget to archive:** once a month has ended and isn't archived, `status` and `log` remind you, and new entries are refused with "Run: money archive". You can still backdate entries *into* the ended month until you archive it. After archiving, the old month is closed and entries dated there are rejected.

**Archived entries (opening balance, carried and recurring reservations) are protected.** `undo` and `delete` won't touch them. To drop a carried or recurring reservation, `release` it.

**Undoing an archive:** `money archive --undo` deletes the new month and reopens the old one, but only if the new month still contains nothing except the archive's own entries. Once you've recorded anything, undo or delete those entries first.

**Tamper check:** if a closed month's file changes after closing, `money months` shows `closed - MODIFIED after close!` and reading that month warns you.

---

## Undo, delete and recovery

- `money undo` deletes the last entry you made. Undoing a settle or release brings the reservation back.
- `money delete ID` deletes a specific entry. Two safety checks apply:
  - you can't delete a reservation that was already settled or released (delete the settle/release first),
  - you can't delete a settle/release if another active reservation now has the same name.
- Deletes are **permanent**, but the previous version of the file is kept as `ledger.jsonl.prev` before every delete. To recover the last delete:

```bash
cd ~/money/2026-11
cp ledger.jsonl.prev ledger.jsonl
```

`.prev` only holds one step back. For real history, keep `~/money` in a private git repo (see below).

---

## Where your data lives

```
~/money/
  config.json              currency
  recurring.json           recurring reservations
  2026-10/
    ledger.jsonl           closed month (read-only)
    closed.json            closing totals + checksum
  2026-11/
    ledger.jsonl           the active month (the folder without closed.json)
```

Each line of a ledger is one event:

```json
{"v":1,"id":"91c0fb25084745648b6de3ae4057deee","ts":"2026-10-05T05:30:13+00:00","kind":"add","amount":100000,"source":"Mom"}
```

`amount` is in minor units (100000 = 1,000.00). Balances and reservations are never stored. They're recomputed by replaying the month's events every time, so there's no way for a total to drift out of sync with its entries.

**Backup and sync:** it's all text, so this works well:

```bash
cd ~/money && git init && git add -A && git commit -m "money"
```

Only use one machine at a time per ledger, since two machines appending to the same file will conflict. Every command takes a file lock, so several terminals on the **same** machine are safe.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Shell shows `dquote>` or waits for more input | An unmatched apostrophe or quote. Quote the whole text: `money +500 "Mom's vault"`. |
| My note lost a `#...` word | Your shell treats an unquoted word starting with `#` as a comment (zsh with `interactive_comments`). Quote it: `'#3'`. money itself keeps `#` as plain text. |
| A word turned into a tag by accident (e.g. `:)`) | Any word starting with `:` is a tag. Rephrase it. A lone `:` or `::`, and colons inside words (`10:30`, `shop:main`), are fine. |
| `zsh: no matches found: ...` | The text contains `[ ] * ?`. Quote it. Auto-generated names like `Rent 2026-11` are chosen to avoid this. |
| A stray file appeared (e.g. `home`) and the note is cut short | An unquoted `>` or `<` is a shell redirect. Quote it: `"->"`. |
| `bash: !...: event not found` | `!` triggers history expansion. Quote it with single quotes. |
| `Error: 2026-11 is a new month but 2026-10 is still open` | Run `money archive`. |
| `Error: 2026-10 hasn't ended yet` | By design. Archive only works after the month is over. |
| `Error: 2026-09 is closed` | You can't add entries to an archived month. Record it in the current month, with a note. |
| `warning: Available is below zero` | Reservations plus spending exceed your total. Usually income isn't recorded yet. |
| `Error: Not initialized` | Run `money init`. If you use `MONEY_DIR`, check it's set in this shell. |
| `?` where a character should be | Your terminal can't show it. The data is intact. Fix the terminal's encoding (UTF-8). |
| `line N is corrupt` | A ledger line was hand-edited badly. Fix or delete that line, or restore `ledger.jsonl.prev`. |

---

## Design notes and limits

**Why it works the way it does**

- **Integer money.** Amounts are stored in paisa/cents, never floats, so sums never drift.
- **Append-only log + derived state.** Every action, including settle, is a single atomic write, so there's no window where money exists in two places or neither.
- **Writes are locked and fsynced.** Concurrent commands can't lose each other's entries.
- **JSONL, not SQLite.** A month's file is a few hundred lines at most, which is greppable, diffable and fixable in a text editor. If you ever want year-wide queries, build a read-only index from the monthly files.

**Current limits**

- One currency per ledger.
- Recurring reservations are monthly only.
- Entries can't be edited in place. `delete` and re-enter (`undo` is the fast path for the latest one).
- Timestamps use your machine's local time zone, and the month boundary is local midnight.
- Not tested on Windows or on Python versions other than 3.12.

---

## Development

```bash
python -m unittest test_money -v     # 48 tests; or: pytest
```

The tests fake the clock (`money.now`), so month-end behaviour, gap months and crash recovery are all covered without waiting for real months to pass. The suite also launches 30 simultaneous writers to check that no entries are lost.

`money.py` is a single file. The layers, top to bottom: time helpers, the event model and `Ledger` (pure replay logic), `Store` (all file I/O and locking), parsing and formatting, commands, then the CLI.
