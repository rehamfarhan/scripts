#!/usr/bin/env python3
"""money: git-like CLI for tracking money with reservations.

Refactor notes:
- Fixed missing delete_transaction method
- Reduced repeated file loads where easy
- Improved warning consistency
- Minor cleanup for readability
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
    pass


@dataclass
class Transaction:
    id: str
    timestamp: str
    source: str
    action: str
    amount: float
    note: str = ""

    @property
    def signed_amount(self) -> float:
        return self.amount if self.action == "add" else -self.amount


@dataclass
class Reservation:
    key: str
    label: str
    amount: float
    created_at: str


class MoneyStore:
    def __init__(self, root: Path):
        self.root = root
        self.app_dir = root / APP_DIR_NAME
        self.data_file = self.app_dir / DATA_FILE_NAME
        self.reservation_file = self.app_dir / RESERVATION_FILE_NAME
        self.config_file = self.app_dir / CONFIG_FILE_NAME

    def init(self) -> None:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        if not self.data_file.exists():
            self._write_json(self.data_file, {"transactions": []})
        if not self.reservation_file.exists():
            self._write_json(self.reservation_file, {"reservations": []})
        if not self.config_file.exists():
            self._write_json(self.config_file, {"currency": "BDT"})

    def _ensure_initialized(self) -> None:
        if not self.data_file.exists() or not self.reservation_file.exists():
            raise AppError("Run 'money init' first.")

    def load_transactions(self) -> List[Transaction]:
        self._ensure_initialized()
        raw = self._read_json(self.data_file)
        return [Transaction(**t) for t in raw.get("transactions", [])]

    def save_transactions(self, txs: List[Transaction]) -> None:
        self._write_json(self.data_file, {"transactions": [asdict(t) for t in txs]})

    def add_transaction(self, tx: Transaction) -> None:
        txs = self.load_transactions()
        txs.append(tx)
        self.save_transactions(txs)

    def delete_transaction(self, tx_id: str) -> bool:
        txs = self.load_transactions()
        new = [t for t in txs if not t.id.startswith(tx_id)]
        if len(new) == len(txs):
            return False
        self.save_transactions(new)
        return True

    def load_reservations(self) -> List[Reservation]:
        raw = self._read_json(self.reservation_file)
        return [Reservation(**r) for r in raw.get("reservations", [])]

    def save_reservations(self, rs: List[Reservation]) -> None:
        self._write_json(self.reservation_file, {"reservations": [asdict(r) for r in rs]})

    def add_reservation(self, label: str, amount: float) -> Reservation:
        rs = self.load_reservations()
        key = label.lower().strip()
        if any(r.key == key for r in rs):
            raise AppError("Reservation already exists.")
        r = Reservation(key, label.strip(), amount, now())
        rs.append(r)
        self.save_reservations(rs)
        return r

    def remove_reservation(self, label: str) -> Reservation:
        rs = self.load_reservations()
        key = label.lower().strip()
        match = next((r for r in rs if r.key == key), None)
        if not match:
            raise AppError("Reservation not found.")
        rs = [r for r in rs if r.key != key]
        self.save_reservations(rs)
        return match

    def _read_json(self, path: Path) -> Dict[str, Any]:
        try:
            with path.open() as f:
                return json.load(f)
        except Exception:
            raise AppError("Data file corrupted.")

    def _write_json(self, path: Path, data: Dict[str, Any]) -> None:
        with path.open("w") as f:
            json.dump(data, f, indent=2)


# helpers

def now() -> str:
    return datetime.now().strftime(DATE_FORMAT)


def parse_amount(x: str) -> float:
    v = float(x)
    if v <= 0:
        raise AppError("Amount must be > 0")
    return v


def summarize(txs: List[Transaction]) -> float:
    return sum(t.signed_amount for t in txs)


def reservation_total(rs: List[Reservation]) -> float:
    return sum(r.amount for r in rs)


# commands

def status(store: MoneyStore):
    txs = store.load_transactions()
    rs = store.load_reservations()
    total = summarize(txs)
    reserved = reservation_total(rs)
    available = total - reserved

    print(f"Total:     {total}")
    print(f"Reserved:  {reserved}")
    print(f"Available: {available}")

    if available < 0:
        print("⚠️ Available below zero.")
    if total < 0:
        print("⚠️ Total below zero (real debt).")


def main():
    store = MoneyStore(Path.cwd())
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init")

    r = sub.add_parser("reserve")
    r.add_argument("amount")
    r.add_argument("id")

    s = sub.add_parser("settle")
    s.add_argument("id")

    sub.add_parser("status")

    args = parser.parse_args()

    if args.cmd == "init":
        store.init()
        print("Initialized.")

    elif args.cmd == "reserve":
        amt = parse_amount(args.amount)
        store.add_reservation(args.id, amt)
        print("Reserved.")

    elif args.cmd == "settle":
        r = store.remove_reservation(args.id)
        store.add_transaction(Transaction(uuid4().hex, now(), r.label, "spend", r.amount))
        print("Settled.")

    elif args.cmd == "status":
        status(store)


if __name__ == "__main__":
    main()
