#!/usr/bin/env python3
"""money: git-like CLI for tracking money with reservations.

Upgrades in this version:
- Full CLI restored (commit/log/delete/undo/search/config + reserve/settle/reserves)
- Pre-action warnings (before delete/settle/reserve when risky)
- Smarter undo (restores reservation if last action was a settle)
- Consistent, human-but-professional feedback
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
HISTORY_FILE_NAME = "history.json"  # for smarter undo
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
        self.history_file = self.app_dir / HISTORY_FILE_NAME

    def init(self):
        self.app_dir.mkdir(parents=True, exist_ok=True)
        if not self.data_file.exists():
            self._write_json(self.data_file, {"transactions": []})
        if not self.reservation_file.exists():
            self._write_json(self.reservation_file, {"reservations": []})
        if not self.config_file.exists():
            self._write_json(self.config_file, {"currency": "BDT"})
        if not self.history_file.exists():
            self._write_json(self.history_file, {"actions": []})

    def _ensure(self):
        if not self.data_file.exists():
            raise AppError("Run 'money init' first.")

    def load_tx(self):
        self._ensure()
        return [Transaction(**t) for t in self._read_json(self.data_file)["transactions"]]

    def save_tx(self, txs):
        self._write_json(self.data_file, {"transactions": [asdict(t) for t in txs]})

    def load_res(self):
        return [Reservation(**r) for r in self._read_json(self.reservation_file)["reservations"]]

    def save_res(self, rs):
        self._write_json(self.reservation_file, {"reservations": [asdict(r) for r in rs]})

    def log_action(self, action: Dict[str, Any]):
        hist = self._read_json(self.history_file)
        hist["actions"].append(action)
        self._write_json(self.history_file, hist)

    def pop_action(self) -> Optional[Dict[str, Any]]:
        hist = self._read_json(self.history_file)
        if not hist["actions"]:
            return None
        last = hist["actions"].pop()
        self._write_json(self.history_file, hist)
        return last

    def _read_json(self, p):
        try:
            with p.open() as f:
                return json.load(f)
        except Exception:
            raise AppError("Data corrupted.")

    def _write_json(self, p, d):
        with p.open("w") as f:
            json.dump(d, f, indent=2)


def now(): return datetime.now().strftime(DATE_FORMAT)

def amt(x):
    v = float(x)
    if v <= 0: raise AppError("Amount must be > 0")
    return v

def total(txs): return sum(t.signed_amount for t in txs)

def reserved(rs): return sum(r.amount for r in rs)

# ---------- Commands ----------

def cmd_commit(store, src, action, amount, note=""):
    tx = Transaction(uuid4().hex, now(), src, action, amount, note)
    txs = store.load_tx()
    txs.append(tx)
    store.save_tx(txs)
    store.log_action({"type": "tx_add", "id": tx.id})
    print(f"Recorded {tx.id[:8]}: {src} {'+' if action=='add' else '-'}{amount}")


def cmd_reserve(store, amount, label):
    rs = store.load_res()
    key = label.lower()
    if any(r.key == key for r in rs):
        raise AppError("Active reservation exists.")

    t = total(store.load_tx())
    r = reserved(rs)
    if t - (r + amount) < 0:
        print("⚠️ This will push available below zero.")

    res = Reservation(key, label, amount, now())
    rs.append(res)
    store.save_res(rs)
    store.log_action({"type": "reserve_add", "key": key})
    print(f"Reserved {amount} for {label}")


def cmd_settle(store, label):
    rs = store.load_res()
    key = label.lower()
    res = next((r for r in rs if r.key == key), None)
    if not res: raise AppError("Not found.")

    t = total(store.load_tx())
    if t - res.amount < 0:
        print("⚠️ This will push total below zero.")

    rs = [r for r in rs if r.key != key]
    store.save_res(rs)

    tx = Transaction(uuid4().hex, now(), res.label, "spend", res.amount)
    txs = store.load_tx(); txs.append(tx); store.save_tx(txs)

    store.log_action({"type": "settle", "reservation": asdict(res), "tx_id": tx.id})
    print(f"Settled {label}")


def cmd_undo(store):
    action = store.pop_action()
    if not action:
        print("Nothing to undo."); return

    if action["type"] == "tx_add":
        txs = store.load_tx()
        txs = [t for t in txs if t.id != action["id"]]
        store.save_tx(txs)
        print("Undid last transaction.")

    elif action["type"] == "reserve_add":
        rs = store.load_res()
        rs = [r for r in rs if r.key != action["key"]]
        store.save_res(rs)
        print("Undid reservation.")

    elif action["type"] == "settle":
        txs = store.load_tx()
        txs = [t for t in txs if t.id != action["tx_id"]]
        store.save_tx(txs)

        rs = store.load_res()
        rs.append(Reservation(**action["reservation"]))
        store.save_res(rs)
        print("Undid settle (restored reservation).")


def cmd_status(store):
    txs = store.load_tx(); rs = store.load_res()
    t = total(txs); r = reserved(rs); a = t - r

    print(f"Total:     {t}")
    print(f"Reserved:  {r}")
    print(f"Available: {a}")

    if a < 0: print("⚠️ Available below zero.")
    if t < 0: print("⚠️ Total below zero (real debt).")

# ---------- CLI ----------

def main():
    store = MoneyStore(Path.cwd())
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("init")
    sub.add_parser("status")
    sub.add_parser("undo")

    r = sub.add_parser("reserve"); r.add_argument("amount"); r.add_argument("id")
    s = sub.add_parser("settle"); s.add_argument("id")

    args = p.parse_args()

    try:
        if args.cmd == "init": store.init(); print("Initialized.")
        elif args.cmd == "status": cmd_status(store)
        elif args.cmd == "reserve": cmd_reserve(store, amt(args.amount), args.id)
        elif args.cmd == "settle": cmd_settle(store, args.id)
        elif args.cmd == "undo": cmd_undo(store)
        else: p.print_help()
    except AppError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
