#!/usr/bin/env python3
"""money: a tiny git-like terminal app for tracking money.

Design goals:
- Simple single-file CLI
- Local persistence in a JSON file inside the current folder
- Git-ish workflow:
    money init
    money commit "source, add/spend, amount"
    money log
    money status
    money balance
    money delete <id>
    money undo
    money search <text>

Transaction format:
- source: where money came from or went to
- action: add or spend
- amount: positive number
- optional note: anything after the 3rd field, or via --note

Examples:
    money commit "salary, add, 5000"
    money commit "lunch, spend, 120"
    money commit "gift from uncle, add, 1000, eid"
    money commit --source salary --action add --amount 5000 --note monthly pay

This is intentionally lightweight. It does not try to do banking-grade accounting.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

APP_DIR_NAME = ".moneygit"
DATA_FILE_NAME = "ledger.json"
CONFIG_FILE_NAME = "config.json"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class AppError(Exception):
    pass


def now_str() -> str:
    return datetime.now().strftime(DATE_FORMAT)


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


class MoneyStore:
    def __init__(self, root: Path):
        self.root = root
        self.app_dir = root / APP_DIR_NAME
        self.data_file = self.app_dir / DATA_FILE_NAME
        self.config_file = self.app_dir / CONFIG_FILE_NAME

    def is_initialized(self) -> bool:
        return self.app_dir.exists() and self.data_file.exists()

    def init(self) -> None:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        if not self.data_file.exists():
            self._write_json(self.data_file, {"transactions": []})
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
        txs = []
        for item in raw.get("transactions", []):
            txs.append(Transaction(**item))
        return txs

    def save_transactions(self, txs: List[Transaction]) -> None:
        self._ensure_initialized()
        self._write_json(self.data_file, {"transactions": [asdict(t) for t in txs]})

    def add_transaction(self, tx: Transaction) -> None:
        txs = self.load_transactions()
        txs.append(tx)
        self.save_transactions(txs)

    def delete_transaction(self, tx_id: str) -> bool:
        txs = self.load_transactions()
        new_txs = [tx for tx in txs if tx.id != tx_id]
        if len(new_txs) == len(txs):
            return False
        self.save_transactions(new_txs)
        return True

    def pop_last_transaction(self) -> Optional[Transaction]:
        txs = self.load_transactions()
        if not txs:
            return None
        last = txs.pop()
        self.save_transactions(txs)
        return last

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
            f.write("\n")
        tmp.replace(path)


def parse_legacy_commit_text(text: str) -> Dict[str, str]:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 3:
        raise AppError(
            'Commit text must look like: "source, add/spend, amount[, note]"'
        )
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

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def line(sep: str = "-") -> str:
        return "+" + "+".join(sep * (w + 2) for w in widths) + "+"

    def row_line(values: List[str]) -> str:
        return "|" + "|".join(f" {str(v).ljust(w)} " for v, w in zip(values, widths)) + "|"

    print(line("-"))
    print(row_line(headers))
    print(line("="))
    for row in rows:
        print(row_line(row))
        print(line("-"))


def summarize(txs: List[Transaction]) -> Dict[str, float]:
    balance = 0.0
    income = 0.0
    expense = 0.0
    for tx in txs:
        balance += tx.signed_amount
        if tx.action == "add":
            income += tx.amount
        else:
            expense += tx.amount
    return {"balance": balance, "income": income, "expense": expense}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="money",
        description="Git-like money tracker.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize a new money repo in the current folder")

    commit = sub.add_parser("commit", help='Add a transaction, like git commit')
    commit.add_argument("text", nargs="?", help='"source, add/spend, amount[, note]"')
    commit.add_argument("--source", help="Transaction source/label")
    commit.add_argument("--action", help="add or spend")
    commit.add_argument("--amount", help="Positive amount")
    commit.add_argument("--note", default="", help="Optional note")

    sub.add_parser("log", help="Show all transactions")
    sub.add_parser("status", help="Show summary status")
    sub.add_parser("balance", help="Show current balance")

    delete = sub.add_parser("delete", help="Delete a transaction by ID")
    delete.add_argument("id", help="Transaction ID prefix or full ID")

    search = sub.add_parser("search", help="Search by source, note, or action")
    search.add_argument("query", help="Search text")

    sub.add_parser("undo", help="Remove the last transaction")

    config = sub.add_parser("config", help="Change settings")
    config.add_argument("--currency", help="Set currency label, e.g. BDT, USD")

    return parser


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

    raise AppError(
        'Provide either: money commit "source, add/spend, amount[, note]" or use flags.'
    )


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
    sign = "+" if action == "add" else "-"
    currency = store.load_config().get("currency", "BDT")
    print(
        f"Recorded {tx.id[:8]}: {source} {sign}{format_money(amount, currency)}"
    )
    return 0


def cmd_log(store: MoneyStore) -> int:
    txs = store.load_transactions()
    currency = store.load_config().get("currency", "BDT")
    print_tx_table(list(reversed(txs)), currency)
    return 0


def cmd_status(store: MoneyStore) -> int:
    txs = store.load_transactions()
    currency = store.load_config().get("currency", "BDT")
    summary = summarize(txs)
    print(f"Transactions: {len(txs)}")
    print(f"Income: {format_money(summary['income'], currency)}")
    print(f"Expense: {format_money(summary['expense'], currency)}")
    print(f"Balance: {format_money(summary['balance'], currency)}")
    return 0


def cmd_balance(store: MoneyStore) -> int:
    txs = store.load_transactions()
    currency = store.load_config().get("currency", "BDT")
    summary = summarize(txs)
    print(format_money(summary["balance"], currency))
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
    last = store.pop_last_transaction()
    if not last:
        raise AppError("Nothing to undo")
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
    print(json.dumps(store.load_config(), indent=2))
    return 0


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

    try:
        amount = parse_amount(amount_str)
    except AppError:
        raise AppError("Invalid quick amount format")

    rest = " ".join(argv[1:]).strip()
    if not rest:
        raise AppError("Provide a source or description")

    # Split note and source using '@'
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


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    # 🔥 Quick mode (no command, just + / -)
    quick = parse_quick_entry(argv)
    store = MoneyStore(Path.cwd())

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
            return cmd_log(store)
        if args.command == "status":
            return cmd_status(store)
        if args.command == "balance":
            return cmd_balance(store)
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


if __name__ == "__main__":
    raise SystemExit(main())
