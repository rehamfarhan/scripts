#!/usr/bin/env python3
"""money: a tiny git-like terminal app for tracking money.

Goals:
- Keep input fast and natural.
- Store everything locally in a hidden folder.
- Treat each money event like a commit.
- Add a reservation layer for money that is "set aside".

Main ideas:
- Transactions change total balance.
- Reservations reduce available balance, but do not change total until settled.
- Settling a reservation creates a normal spend transaction.

Examples:
    money init
    money +500 Mom's vault
    money -90 Croissant Burger @lakeviewcafe
    money reserve 1200 RafiqulSir
    money settle RafiqulSir
    money log
    money reserves
    money status
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

APP_DIR_NAME = ".moneygit"
DATA_FILE_NAME = "ledger.json"
RESERVATION_FILE_NAME = "reservations.json"
CONFIG_FILE_NAME = "config.json"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class AppError(Exception):
    """Friendly exception for all user-facing errors."""


@dataclass
class Transaction:
    id: str
    timestamp: str
    source: str
    action: str  # add | spend
    amount: float
    note: str = ""

    @property
    def signed_amount(self) -> float:
        return self.amount if self.action == "add" else -self.amount


@dataclass
class Reservation:
    key: str      # normalized identifier used for matching
    label: str    # original display label
    amount: float
    created_at: str


class MoneyStore:
    """All file I/O lives here so the rest of the app stays simple."""

    def __init__(self, root: Path):
        self.root = root
        self.app_dir = root / APP_DIR_NAME
        self.data_file = self.app_dir / DATA_FILE_NAME
        self.reservation_file = self.app_dir / RESERVATION_FILE_NAME
        self.config_file = self.app_dir / CONFIG_FILE_NAME

    def is_initialized(self) -> bool:
        return self.app_dir.exists() and self.data_file.exists() and self.reservation_file.exists()

    def init(self) -> None:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        if not self.data_file.exists():
            self._write_json(self.data_file, {"transactions": []})
        if not self.reservation_file.exists():
            self._write_json(self.reservation_file, {"reservations": []})
        if not self.config_file.exists():
            self._write_json(self.config_file, {"currency": "BDT"})

    def load_config(self) -> Dict[str, Any]:
        if self.config_file.exists():
            return self._read_json(self.config_file)
        return {"currency": "BDT"}

    def set_currency(self, currency: str) -> None:
        self.init()
        cfg = self.load_config()
        cfg["currency"] = currency.strip().upper()
        self._write_json(self.config_file, cfg)

    def load_transactions(self) -> List[Transaction]:
        self._ensure_initialized()
        raw = self._read_json(self.data_file)
        return [Transaction(**item) for item in raw.get("transactions", [])]

    def save_transactions(self, txs: List[Transaction]) -> None:
        self._ensure_initialized()
        self._write_json(self.data_file, {"transactions": [asdict(t) for t in txs]})

    def add_transaction(self, tx: Transaction) -> None:
        txs = self.load_transactions()
        txs.append(tx)
        self.save_transactions(txs)

    def load_reservations(self) -> List[Reservation]:
        self._ensure_initialized()
        raw = self._read_json(self.reservation_file)
        return [Reservation(**item) for item in raw.get("reservations", [])]

    def save_reservations(self, reservations: List[Reservation]) -> None:
        self._ensure_initialized()
        self._write_json(self.reservation_file, {"reservations": [asdict(r) for r in reservations]})

    def add_reservation(self, label: str, amount: float) -> Reservation:
        reservations = self.load_reservations()
        key = normalize_identifier(label)
        if any(r.key == key for r in reservations):
            raise AppError(f"Active reservation already exists for: {label}")

        reservation = Reservation(
            key=key,
            label=label.strip(),
            amount=amount,
            created_at=now_str(),
        )
        reservations.append(reservation)
        self.save_reservations(reservations)
        return reservation

    def remove_reservation(self, identifier: str) -> Reservation:
        reservations = self.load_reservations()
        key = normalize_identifier(identifier)
        matches = [r for r in reservations if r.key == key]
        if not matches:
            raise AppError(f"No active reservation found for: {identifier}")

        reservation = matches[0]
        reservations = [r for r in reservations if r.key != key]
        self.save_reservations(reservations)
        return reservation

    def find_reservation(self, identifier: str) -> Optional[Reservation]:
        key = normalize_identifier(identifier)
        for reservation in self.load_reservations():
            if reservation.key == key:
                return reservation
        return None

    def _ensure_initialized(self) -> None:
        if not self.is_initialized():
            raise AppError("Repository not initialized. Run: money init")

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise AppError(f"Corrupted data file: {path}") from e

    @staticmethod
    def _write_json(path: Path, data: Dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("
")
        tmp.replace(path)


def now_str() -> str:
    return datetime.now().strftime(DATE_FORMAT)


def normalize_identifier(value: str) -> str:
    """Use a stable key for matching reservation IDs case-insensitively."""
    return value.strip().lower()


def parse_legacy_commit_text(text: str) -> Dict[str, str]:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 3:
        raise AppError('Commit text must look like: "source, add/spend, amount[, note]"')
    source = parts[0]
    action = parts[1].lower()
    amount = parts[2]
    note = ", ".join(parts[3:]).strip() if len(parts) > 3 else ""
    return {"source": source, "action": action, "amount": amount, "note": note}


def parse_amount(value: str) -> float:
    try:
        amount = float(value)
    except ValueError as e:
        raise AppError(f"Invalid amount: {value}") from e
    if amount <= 0:
        raise AppError("Amount must be greater than 0")
    return amount


def normalize_action(action: str) -> str:
    a = action.strip().lower()
    if a in {"add", "income", "in", "credit"}:
        return "add"
    if a in {"spend", "expense", "out", "debit"}:
        return "spend"
    raise AppError("Action must be add or spend")


def format_money(value: float, currency: str) -> str:
    rounded = round(value, 2)
    if float(int(rounded)) == rounded:
        return f"{currency} {int(rounded)}"
    return f"{currency} {rounded:.2f}"


def summarize(txs: List[Transaction]) -> Dict[str, float]:
    total = 0.0
    for tx in txs:
        total += tx.signed_amount
    return {"total": total}


def reservation_total(reservations: List[Reservation]) -> float:
    return sum(r.amount for r in reservations)


def print_table(headers: List[str], rows: List[List[str]]) -> None:
    """Print a simple pretty table with ASCII borders."""
    if not rows:
        widths = [len(h) for h in headers]
    else:
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))

    def line(sep: str) -> str:
        return "+" + "+".join(sep * (w + 2) for w in widths) + "+"

    def row_line(values: List[str]) -> str:
        return "|" + "|".join(f" {str(v).ljust(w)} " for v, w in zip(values, widths)) + "|"

    print(line("-"))
    print(row_line(headers))
    print(line("="))
    for row in rows:
        print(row_line(row))
        print(line("-"))


def print_tx_table(txs: List[Transaction], currency: str) -> None:
    if not txs:
        print("No transactions yet.")
        return

    headers = ["ID", "Date", "Action", "Source", "Amount", "Note"]
    rows = []
    for tx in txs:
        rows.append([
            tx.id[:8],
            tx.timestamp,
            tx.action,
            tx.source,
            format_money(tx.amount, currency),
            tx.note,
        ])
    print_table(headers, rows)


def print_reservation_table(reservations: List[Reservation], currency: str) -> None:
    if not reservations:
        print("No active reservations.")
        return

    headers = ["ID", "Created", "Amount"]
    rows = []
    for res in reservations:
        rows.append([
            res.label,
            res.created_at,
            format_money(res.amount, currency),
        ])
    print_table(headers, rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="money", description="Git-like money tracker.")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize a new money repo in the current folder")

    commit = sub.add_parser("commit", help='Add a transaction, like git commit')
    commit.add_argument("text", nargs="?", help='"source, add/spend, amount[, note]"')
    commit.add_argument("--source", help="Transaction source/label")
    commit.add_argument("--action", help="add or spend")
    commit.add_argument("--amount", help="Positive amount")
    commit.add_argument("--note", default="", help="Optional note")

    sub.add_parser("log", help="Show all transactions")
    sub.add_parser("status", help="Show a compact money summary")
    sub.add_parser("balance", help="Show current total balance")
    sub.add_parser("reserves", help="Show active reservations")

    reserve = sub.add_parser("reserve", help="Reserve money for a specific identifier")
    reserve.add_argument("amount", help="Amount to reserve")
    reserve.add_argument("identifier", help="Reservation identifier")

    settle = sub.add_parser("settle", help="Settle a reservation in full")
    settle.add_argument("identifier", help="Reservation identifier")

    delete = sub.add_parser("delete", help="Delete a transaction by ID")
    delete.add_argument("id", help="Transaction ID prefix or full ID")

    search = sub.add_parser("search", help="Search by source, note, or action")
    search.add_argument("query", help="Search text")

    sub.add_parser("undo", help="Remove the last transaction")

    config = sub.add_parser("config", help="Change settings")
    config.add_argument("--currency", help="Set currency label, e.g. BDT, USD")

    return parser


def parse_quick_entry(argv: List[str]) -> Optional[Dict[str, str]]:
    """Supports shorthand like:
    money +500 Salary
    money -90 Burger @place
    """
    if not argv:
        return None

    first = argv[0]
    if not (first.startswith("+") or first.startswith("-")):
        return None

    sign = first[0]
    amount_str = first[1:]
    amount = parse_amount(amount_str)

    rest = " ".join(argv[1:]).strip()
    if not rest:
        raise AppError("Provide a source or description")

    if "@" in rest:
        note_part, source_part = rest.split("@", 1)
        note = note_part.strip()
        source = source_part.strip()
    else:
        source = rest
        note = ""

    action = "add" if sign == "+" else "spend"
    return {
        "source": source,
        "action": action,
        "amount": str(amount),
        "note": note,
    }


def resolve_transaction_input(args: argparse.Namespace) -> Dict[str, str]:
    if args.source or args.action or args.amount:
        if not (args.source and args.action and args.amount):
            raise AppError("For flag mode, provide --source, --action, and --amount")
        return {
            "source": args.source.strip(),
            "action": args.action.strip(),
            "amount": args.amount.strip(),
            "note": args.note.strip(),
        }

    if args.text:
        return parse_legacy_commit_text(args.text)

    raise AppError('Provide either: money commit "source, add/spend, amount[, note]" or use flags.')


def show_status(store: MoneyStore) -> int:
    txs = store.load_transactions()
    reservations = store.load_reservations()
    currency = store.load_config().get("currency", "BDT")

    total = summarize(txs)["total"]
    reserved = reservation_total(reservations)
    available = total - reserved

    print(f"Total:     {format_money(total, currency)}")
    print(f"Reserved:  {format_money(reserved, currency)}")
    print(f"Available: {format_money(available, currency)}")

    if available < 0:
        print("⚠️ Available is below zero. That usually means the add entry is missing, or money is already spoken for.")
    return 0


def show_balance(store: MoneyStore) -> int:
    txs = store.load_transactions()
    currency = store.load_config().get("currency", "BDT")
    total = summarize(txs)["total"]
    print(format_money(total, currency))
    return 0


def cmd_init(store: MoneyStore) -> int:
    store.init()
    print(f"Initialized money repo in {store.app_dir}")
    return 0


def cmd_commit(store: MoneyStore, args: argparse.Namespace) -> int:
    store._ensure_initialized()
    data = resolve_transaction_input(args)
    source = data["source"].strip()
    action = normalize_action(data["action"])
    amount = parse_amount(data["amount"])
    note = data.get("note", "").strip()

    tx = Transaction(
        id=uuid4().hex,
        timestamp=now_str(),
        source=source,
        action=action,
        amount=amount,
        note=note,
    )
    store.add_transaction(tx)

    currency = store.load_config().get("currency", "BDT")
    sign = "+" if action == "add" else "-"
    print(f"Recorded {tx.id[:8]}: {source} {sign}{format_money(amount, currency)}")
    return 0


def cmd_reserve(store: MoneyStore, amount_text: str, identifier: str) -> int:
    store._ensure_initialized()
    amount = parse_amount(amount_text)
    label = identifier.strip()
    if not label:
        raise AppError("Reservation identifier cannot be empty")

    currency = store.load_config().get("currency", "BDT")
    tx_total = summarize(store.load_transactions())["total"]
    reserved_total = reservation_total(store.load_reservations())
    available_before = tx_total - reserved_total

    reservation = store.add_reservation(label, amount)
    available_after = available_before - amount

    print(f"Reserved {format_money(amount, currency)} for {reservation.label}")
    if available_after < 0:
        print("⚠️ This reservation pushes available money below zero. That is a real warning, not a typo.")
        print("   Usually this means you need to record the add first, or this money is already committed elsewhere.")
    return 0


def cmd_settle(store: MoneyStore, identifier: str) -> int:
    store._ensure_initialized()
    reservation = store.remove_reservation(identifier)

    # Settling turns the reserved money into a real spend transaction.
    tx = Transaction(
        id=uuid4().hex,
        timestamp=now_str(),
        source=reservation.label,
        action="spend",
        amount=reservation.amount,
        note="",
    )
    store.add_transaction(tx)

    currency = store.load_config().get("currency", "BDT")
    print(f"Settled {reservation.label}: {format_money(reservation.amount, currency)}")
    return 0


def cmd_reserves(store: MoneyStore) -> int:
    reservations = store.load_reservations()
    currency = store.load_config().get("currency", "BDT")
    print_reservation_table(reservations, currency)
    return 0


def cmd_delete(store: MoneyStore, tx_id: str) -> int:
    txs = store.load_transactions()
    matches = [tx for tx in txs if tx.id.startswith(tx_id)]
    if not matches:
        raise AppError(f"No transaction found with ID starting {tx_id}")
    if len(matches) > 1:
        raise AppError(f"More than one transaction matches {tx_id}. Use more characters.")
    if store.delete_transaction(matches[0].id):
        print(f"Deleted {matches[0].id[:8]}")
        return 0
    raise AppError("Delete failed")


def cmd_undo(store: MoneyStore) -> int:
    txs = store.load_transactions()
    if not txs:
        raise AppError("Nothing to undo")
    last = txs.pop()
    store.save_transactions(txs)
    print(f"Removed last transaction: {last.id[:8]} {last.source} {last.action} {last.amount}")
    return 0


def cmd_search(store: MoneyStore, query: str) -> int:
    txs = store.load_transactions()
    currency = store.load_config().get("currency", "BDT")
    q = query.lower().strip()
    matches = [
        tx for tx in txs
        if q in tx.source.lower() or q in tx.note.lower() or q in tx.action.lower() or q in tx.timestamp.lower()
    ]
    print_tx_table(list(reversed(matches)), currency)
    return 0


def cmd_config(store: MoneyStore, args: argparse.Namespace) -> int:
    store.init()
    if args.currency:
        store.set_currency(args.currency)
        print(f"Currency set to {args.currency.upper()}")
        return 0
    print(json.dumps(store.load_config(), indent=2, ensure_ascii=False))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    store = MoneyStore(Path.cwd())

    # Quick mode: the first token is +amount or -amount.
    try:
        quick = parse_quick_entry(argv)
    except AppError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if quick:
        try:
            store._ensure_initialized()
            tx = Transaction(
                id=uuid4().hex,
                timestamp=now_str(),
                source=quick["source"],
                action=quick["action"],
                amount=float(quick["amount"]),
                note=quick.get("note", ""),
            )
            store.add_transaction(tx)
            sign = "+" if tx.action == "add" else "-"
            currency = store.load_config().get("currency", "BDT")
            print(f"Recorded {tx.id[:8]}: {tx.source} {sign}{format_money(tx.amount, currency)}")
            return 0
        except AppError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2

    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "init":
            return cmd_init(store)
        if args.command == "commit":
            return cmd_commit(store, args)
        if args.command == "log":
            return show_log(store)
        if args.command == "status":
            return show_status(store)
        if args.command == "balance":
            return show_balance(store)
        if args.command == "reserves":
            return cmd_reserves(store)
        if args.command == "reserve":
            return cmd_reserve(store, args.amount, args.identifier)
        if args.command == "settle":
            return cmd_settle(store, args.identifier)
        if args.command == "delete":
            return cmd_delete(store, args.id)
        if args.command == "undo":
            return cmd_undo(store)
        if args.command == "search":
            return cmd_search(store, args.query)
        if args.command == "config":
            return cmd_config(store, args)

        raise AppError(f"Unknown command: {args.command}")

    except AppError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


def show_log(store: MoneyStore) -> int:
    txs = store.load_transactions()
    currency = store.load_config().get("currency", "BDT")
    print_tx_table(list(reversed(txs)), currency)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
