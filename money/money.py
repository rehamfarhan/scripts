#!/usr/bin/env python3
"""money - a tiny git-like terminal ledger, one folder per month.

Layout (default root ~/money, override with $MONEY_DIR):

    ~/money/
      config.json              currency
      recurring.json           monthly recurring reservations
      2026-09/ledger.jsonl     closed month (read-only) + closed.json (totals, checksum)
      2026-10/ledger.jsonl     the active month (the one folder without closed.json)

Each month is an append-only event log; balances and reservations are derived by
replaying it. `money archive` closes a finished month and opens the next one with the
carried-over balance, carried-over reservations and your recurring reservations.

Quick entry (quote anything the shell would eat, e.g. apostrophes):
    money init
    money +500 "Mom's vault"
    money -90 Croissant Burger @lakeviewcafe :food    # note, @source, :tags (or -t food)
    (@ _ - / . : work in sources and names; tags take @ _ - / . too; words may start with "-")
    money -90 cafe --date yesterday
    money reserve 1200 RafiqulSir :tutor
    money settle RafiqulSir [--amount 1150]            # becomes a real spend
    money release RafiqulSir                           # cancel, spend nothing
    money recur add 12000 Rent :housing                # re-reserved every new month
    money undo | money delete <id>
    money status | log | reserves | search | summary | export | months
    money archive                                      # once the month has ended

Money is stored as integer minor units (paisa/cents), never floats.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional
from uuid import uuid4

__version__ = "1.1.0"

ENV_DIR = "MONEY_DIR"
LEDGER_FILE = "ledger.jsonl"
CLOSED_FILE = "closed.json"
CONFIG_FILE = "config.json"
RECURRING_FILE = "recurring.json"
LOCK_FILE = ".lock"
SCHEMA_VERSION = 1
DEFAULT_CURRENCY = "BDT"

QUICK_RE = re.compile(r"^[+-]\d")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
AMOUNT_RE = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?$")


class AppError(Exception):
    """Friendly exception for every user-facing error."""


# --------------------------------------------------------------------------- #
# Time (everything goes through now() so tests can fake the clock)
# --------------------------------------------------------------------------- #

def now() -> datetime:
    return datetime.now().astimezone()


def now_ts() -> str:
    return now().isoformat(timespec="seconds")


def current_month() -> str:
    return now().strftime("%Y-%m")


def parse_month(text: str) -> str:
    text = text.strip()
    if not MONTH_RE.match(text):
        raise AppError(f"Invalid month: {text!r} (use YYYY-MM, e.g. 2026-10)")
    return text


def month_start(month: str) -> datetime:
    year, mon = map(int, month.split("-"))
    return datetime(year, mon, 1).astimezone()


def next_month(month: str) -> str:
    year, mon = map(int, month.split("-"))
    return f"{year + 1}-01" if mon == 12 else f"{year}-{mon + 1:02d}"


def months_between(first: str, last: str) -> list[str]:
    """Months strictly between two YYYY-MM strings."""
    out, m = [], next_month(first)
    while m < last:
        out.append(m)
        m = next_month(m)
    return out


def days_left(month: str) -> int:
    return (month_start(next_month(month)).date() - now().date()).days


def resolve_timestamp(text: Optional[str]) -> str:
    """None/today/yesterday/YYYY-MM-DD/'YYYY-MM-DD HH:MM' -> ISO timestamp (no future dates)."""
    current = now()
    if not text:
        return current.isoformat(timespec="seconds")
    raw = text.strip().lower()
    when = None
    if raw == "today":
        when = current
    elif raw == "yesterday":
        when = current - timedelta(days=1)
    else:
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M"):
            try:
                parsed = datetime.strptime(raw, fmt)
            except ValueError:
                continue
            when = (
                current.replace(year=parsed.year, month=parsed.month, day=parsed.day)
                if fmt == "%Y-%m-%d" else parsed.astimezone()
            )
            break
    if when is None:
        raise AppError(f"Invalid date: {text!r} (use YYYY-MM-DD, 'YYYY-MM-DD HH:MM', today or yesterday)")
    if when > current + timedelta(minutes=1):
        raise AppError("That date is in the future")
    return when.isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #

class Kind(str, Enum):
    OPEN = "open"        # opening balance of a month (carried over, not income)
    ADD = "add"
    SPEND = "spend"
    RESERVE = "reserve"
    RELEASE = "release"
    SETTLE = "settle"


MONEY_KINDS = {Kind.OPEN, Kind.ADD, Kind.SPEND, Kind.SETTLE}  # events that move the total
FLOW_KINDS = {Kind.ADD, Kind.SPEND, Kind.SETTLE}              # real income/expense
CLOSING_KINDS = {Kind.RELEASE, Kind.SETTLE}                   # events that close a reservation


def new_id() -> str:
    return uuid4().hex


def normalize_key(value: str) -> str:
    """Stable, case/whitespace-insensitive key for matching reservation names."""
    return " ".join(value.split()).casefold()


def normalize_tag(text: str) -> str:
    return re.sub(r"\s+", "-", text.strip().casefold())


def merge_tags(*groups: Iterable[str]) -> tuple[str, ...]:
    """Accepts ':a:b', 'a,b', 'a b' style input; returns unique normalized tags in order.
    ':' and ',' separate tags; every other character (including '#') is part of the tag."""
    out: list[str] = []
    for group in groups:
        for raw in group:
            for part in re.split(r"[,:]", raw):
                tag = normalize_tag(part)
                if tag and tag not in out:
                    out.append(tag)
    return tuple(out)


def extract_tags(words: list[str]) -> tuple[list[str], list[str]]:
    """Split ':tag' words from the rest. Returns (remaining words, raw tag words).
    A word of only colons/commas (':', '::') is plain text, not a tag."""
    rest, raw = [], []
    for w in words:
        (raw if w.startswith(":") and w.strip(":,") else rest).append(w)
    return rest, raw


@dataclass(frozen=True)
class Event:
    id: str
    ts: str                         # ISO 8601 with UTC offset
    kind: Kind
    amount: int = 0                 # minor units; >= 0 except OPEN (carried balance can be negative)
    source: str = ""                # who/where (or reservation label)
    note: str = ""
    key: str = ""                   # normalized reservation name
    ref: str = ""                   # id of the RESERVE this release/settle closes
    tags: tuple[str, ...] = ()
    since: str = ""                 # original creation time of a carried-over reservation
    sys: bool = False               # created by `archive`; protected from undo/delete

    @property
    def when(self) -> datetime:
        return datetime.fromisoformat(self.ts)

    @property
    def signed(self) -> int:
        if self.kind in (Kind.ADD, Kind.OPEN):
            return self.amount
        if self.kind in (Kind.SPEND, Kind.SETTLE):
            return -self.amount
        return 0

    def to_dict(self) -> dict:
        d: dict = {"v": SCHEMA_VERSION, "id": self.id, "ts": self.ts, "kind": self.kind.value}
        for name in ("amount", "source", "note", "key", "ref", "since"):
            value = getattr(self, name)
            if value:
                d[name] = value
        if self.tags:
            d["tags"] = list(self.tags)
        if self.sys:
            d["sys"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        if not isinstance(d, dict):
            raise ValueError("not a JSON object")
        if d.get("v") != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema version {d.get('v')!r}")
        kind = Kind(d["kind"])
        amount = d.get("amount", 0)
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise ValueError("bad amount")
        if amount < 0 and kind is not Kind.OPEN:
            raise ValueError("negative amount")
        text = {f: d.get(f, "") for f in ("id", "ts", "source", "note", "key", "ref", "since")}
        if not all(isinstance(v, str) for v in text.values()) or not text["id"]:
            raise ValueError("bad field type")
        tags = d.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ValueError("bad tags")
        event = cls(kind=kind, amount=amount, tags=tuple(tags), sys=bool(d.get("sys", False)), **text)
        datetime.fromisoformat(event.ts)  # validate
        if event.since:
            datetime.fromisoformat(event.since)
        return event


@dataclass(frozen=True)
class Reservation:
    id: str       # id of the RESERVE event
    key: str
    label: str
    amount: int
    created_at: str
    tags: tuple[str, ...]


class Ledger:
    """Read-only state derived by replaying one month's events in append order."""

    def __init__(self, events: Iterable[Event]):
        self.events = list(events)
        self.by_id = {e.id: e for e in self.events}
        self.reservations: dict[str, Reservation] = {}
        self.total = 0
        for e in self.events:
            self.total += e.signed
            if e.kind is Kind.RESERVE:
                self.reservations[e.id] = Reservation(e.id, e.key, e.source, e.amount, e.since or e.ts, e.tags)
            elif e.kind in CLOSING_KINDS:
                self.reservations.pop(e.ref, None)

    @property
    def reserved(self) -> int:
        return sum(r.amount for r in self.reservations.values())

    @property
    def available(self) -> int:
        return self.total - self.reserved

    @property
    def entry_count(self) -> int:
        return sum(1 for e in self.events if not e.sys)

    def find_reservation(self, name: str) -> Optional[Reservation]:
        key = normalize_key(name)
        return next((r for r in self.reservations.values() if r.key == key), None)

    def money_events(self) -> list[Event]:
        """Open/add/spend/settle events in chronological order (stable)."""
        return sorted((e for e in self.events if e.kind in MONEY_KINDS), key=lambda e: e.when)

    def resolve(self, prefix: str) -> Event:
        prefix = prefix.strip().lower()
        if not prefix:
            raise AppError("Provide an entry ID")
        matches = [e for e in self.events if e.id.startswith(prefix)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AppError(f"More than one entry matches {prefix}. Use more characters.")
        raise AppError(f"No entry found with ID starting {prefix} in the active month")


def check_deletable(ledger: Ledger, target: Event) -> Event:
    """Raise unless removing `target` leaves a consistent ledger."""
    if target.sys:
        hint = " To drop a reservation use: money release NAME" if target.kind is Kind.RESERVE else ""
        raise AppError(f"{target.id[:8]} was created by archive and can't be deleted.{hint}")
    if target.kind is Kind.RESERVE:
        closer = next((e for e in ledger.events if e.kind in CLOSING_KINDS and e.ref == target.id), None)
        if closer:
            raise AppError(
                f"Reservation '{target.source}' was closed by {closer.kind.value} "
                f"{closer.id[:8]}. Delete that first."
            )
    elif target.kind in CLOSING_KINDS:
        original = ledger.by_id.get(target.ref)
        if original and ledger.find_reservation(original.source):
            raise AppError(
                f"Can't restore '{original.source}': another active reservation with that "
                "name exists. Settle or release it first."
            )
    return target


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #

def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def serialize(events: Iterable[Event]) -> str:
    return "".join(json.dumps(e.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n" for e in events)


class Store:
    """All file I/O. Every read and read-modify-write happens under one root lock."""

    def __init__(self, root: Path):
        self.root = root
        self.config_path = root / CONFIG_FILE
        self.recurring_path = root / RECURRING_FILE
        self.lock_path = root / LOCK_FILE

    # -- locating ----------------------------------------------------------- #
    @staticmethod
    def default_root() -> Path:
        env = os.environ.get(ENV_DIR)
        return Path(env).expanduser() if env else Path.home() / "money"

    @classmethod
    def for_init(cls) -> "Store":
        return cls(cls.default_root())

    @classmethod
    def open(cls) -> "Store":
        store = cls(cls.default_root())
        if not store.config_path.exists():
            raise AppError(f"Not initialized ({store.root}). Run: money init")
        return store

    def ensure_initialized(self) -> bool:
        """Create root, config and the current month. Returns True if anything was created."""
        created = not self.config_path.exists()
        self.root.mkdir(parents=True, exist_ok=True)
        if created:
            atomic_write(self.config_path, json.dumps({"currency": DEFAULT_CURRENCY}, indent=2) + "\n")
        if not self.months():
            self._create_month(current_month(), [])
            created = True
        return created

    # -- months ------------------------------------------------------------- #
    def month_dir(self, month: str) -> Path:
        return self.root / month

    def ledger_path(self, month: str) -> Path:
        return self.month_dir(month) / LEDGER_FILE

    def closed_path(self, month: str) -> Path:
        return self.month_dir(month) / CLOSED_FILE

    def months(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_dir() and MONTH_RE.match(p.name) and (p / LEDGER_FILE).exists())

    def is_closed(self, month: str) -> bool:
        return self.closed_path(month).exists()

    def open_months(self) -> list[str]:
        return [m for m in self.months() if not self.is_closed(m)]

    def active_month(self) -> Optional[str]:
        opens = self.open_months()
        if len(opens) > 1:
            raise AppError(f"More than one open month ({', '.join(opens)}). Fix by hand: "
                           "an archived month needs a closed.json file.")
        return opens[0] if opens else None

    def _require_active(self) -> str:
        month = self.active_month()
        if not month:
            if not self.months():
                raise AppError("No months found. Run: money init")
            raise AppError("No active month. Run: money archive")
        return month

    def closed_ok(self, month: str) -> bool:
        try:
            info = json.loads(self.closed_path(month).read_text(encoding="utf-8"))
            digest = hashlib.sha256(self.ledger_path(month).read_bytes()).hexdigest()
            return info.get("sha256") == digest
        except (OSError, ValueError):
            return False

    def _write_closed(self, month: str, ledger: Ledger) -> None:
        path = self.ledger_path(month)
        info = {
            "month": month,
            "closed_at": now_ts(),
            "closing_total": ledger.total,
            "closing_reserved": ledger.reserved,
            "entries": ledger.entry_count,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        atomic_write(self.closed_path(month), json.dumps(info, indent=2) + "\n")
        os.chmod(path, 0o444)

    def _create_month(self, month: str, events: list[Event]) -> None:
        tmp = self.root / f".new-{month}"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir()
        self._write_events(tmp / LEDGER_FILE, events)
        os.rename(tmp, self.month_dir(month))

    # -- locking ------------------------------------------------------------ #
    @contextmanager
    def locked(self) -> Iterator[None]:
        with open(self.lock_path, "a+b") as fh:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(fh, fcntl.LOCK_UN)

    # -- ledger I/O (callers hold the lock) --------------------------------- #
    def _read(self, month: str) -> list[Event]:
        path = self.ledger_path(month)
        events: list[Event] = []
        try:
            with path.open("r", encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    if not line.strip():
                        continue
                    try:
                        events.append(Event.from_dict(json.loads(line)))
                    except (ValueError, KeyError, TypeError) as e:
                        raise AppError(f"{path}: line {n} is corrupt ({e})") from e
        except FileNotFoundError:
            raise AppError(f"No ledger for {month}. See: money months") from None
        return events

    @staticmethod
    def _write_events(path: Path, events: list[Event]) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(serialize(events))
            fh.flush()
            os.fsync(fh.fileno())

    def _append(self, month: str, events: list[Event]) -> None:
        with self.ledger_path(month).open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(serialize(events))
            fh.flush()
            os.fsync(fh.fileno())

    # -- public reads ------------------------------------------------------- #
    def load(self, month: str) -> Ledger:
        with self.locked():
            return Ledger(self._read(month))

    def snapshot(self, month: Optional[str] = None) -> tuple[str, Ledger]:
        """(month, ledger) for the given month, or the active one."""
        with self.locked():
            month = parse_month(month) if month else self._require_active()
            ledger = Ledger(self._read(month))
        self._warn_if_modified(month)
        return month, ledger

    def snapshots(self, month: Optional[str] = None, everything: bool = False) -> list[tuple[str, Ledger]]:
        if not everything:
            return [self.snapshot(month)]
        out = []
        for m in self.months():
            out.append((m, self.load(m)))
            self._warn_if_modified(m)
        return out

    def _warn_if_modified(self, month: str) -> None:
        if self.is_closed(month) and not self.closed_ok(month):
            warn(f"{month} was modified after it was closed (checksum mismatch).")

    # -- public writes (active month only) ---------------------------------- #
    def commit(self, build: Callable[[Ledger], Optional[Event]]) -> tuple[Optional[Event], Ledger]:
        """Atomically: read active ledger -> validate/build one event -> append it."""
        with self.locked():
            month = self._require_active()
            ledger = Ledger(self._read(month))
            event = build(ledger)
            if event is None:
                return None, ledger
            event_month = event.ts[:7]
            if event_month > month:
                raise AppError(f"{event_month} is a new month but {month} is still open. "
                               "Run: money archive")
            if event_month < month:
                raise AppError(f"{event_month} is closed. Entries can only go into {month}.")
            self._append(month, [event])
            return event, Ledger([*ledger.events, event])

    def delete_entry(self, pick: Callable[[Ledger], Event]) -> tuple[Event, Ledger]:
        """Permanently remove one entry from the active month (keeps ledger.jsonl.prev)."""
        with self.locked():
            month = self._require_active()
            ledger = Ledger(self._read(month))
            target = pick(ledger)
            remaining = [e for e in ledger.events if e.id != target.id]
            path = self.ledger_path(month)
            shutil.copy2(path, path.with_name(path.name + ".prev"))
            atomic_write(path, serialize(remaining))
            return target, Ledger(remaining)

    # -- recurring ---------------------------------------------------------- #
    def _read_recurring(self) -> list[dict]:
        try:
            data = json.loads(self.recurring_path.read_text(encoding="utf-8"))
            items = data["recurring"]
            for t in items:
                if (not isinstance(t["name"], str) or isinstance(t["amount"], bool)
                        or not isinstance(t["amount"], int) or t["amount"] <= 0
                        or not isinstance(t.get("tags", []), list)):
                    raise ValueError("bad entry")
            return [{"name": t["name"], "amount": t["amount"], "tags": list(t.get("tags", []))} for t in items]
        except FileNotFoundError:
            return []
        except (ValueError, KeyError, TypeError) as e:
            raise AppError(f"Corrupt recurring file: {self.recurring_path} ({e})") from e

    def load_recurring(self) -> list[dict]:
        with self.locked():
            return self._read_recurring()

    def update_recurring(self, mutate: Callable[[list[dict]], list[dict]]) -> list[dict]:
        with self.locked():
            items = mutate(self._read_recurring())
            atomic_write(self.recurring_path, json.dumps({"recurring": items}, indent=2, ensure_ascii=False) + "\n")
            return items

    # -- config ------------------------------------------------------------- #
    def load_config(self) -> dict:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except ValueError as e:
            raise AppError(f"Corrupt config file: {self.config_path}") from e
        if not isinstance(data, dict):
            raise AppError(f"Corrupt config file: {self.config_path}")
        return data

    @property
    def currency(self) -> str:
        return str(self.load_config().get("currency", DEFAULT_CURRENCY))

    def set_currency(self, currency: str) -> str:
        currency = currency.strip().upper()
        if not re.fullmatch(r"\S{1,8}", currency):
            raise AppError("Currency must be 1-8 characters with no spaces, e.g. BDT or USD")
        cfg = self.load_config()
        cfg["currency"] = currency
        atomic_write(self.config_path, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
        return currency


# --------------------------------------------------------------------------- #
# Parsing & formatting
# --------------------------------------------------------------------------- #

def parse_amount(text: str) -> int:
    """'1,200.50' -> 120050 minor units. Rejects nan/inf/zero/negatives/3+ decimals."""
    cleaned = text.strip()
    if not AMOUNT_RE.match(cleaned):
        raise AppError(f"Invalid amount: {text!r} (digits with up to 2 decimals, e.g. 1200 or 89.50)")
    whole, _, frac = cleaned.replace(",", "").partition(".")
    minor = int(whole) * 100 + int(frac.ljust(2, "0") or 0)
    if minor <= 0:
        raise AppError("Amount must be greater than 0")
    return minor


def format_money(minor: int, currency: str) -> str:
    sign = "-" if minor < 0 else ""
    whole, frac = divmod(abs(minor), 100)
    body = f"{whole:,}" + (f".{frac:02d}" if frac else "")
    return f"{currency} {sign}{body}"


def signed_money(minor: int, currency: str) -> str:
    if minor == 0:
        return format_money(0, currency)
    return ("+" if minor > 0 else "-") + format_money(abs(minor), currency)


def plain_money(minor: int) -> str:
    whole, frac = divmod(abs(minor), 100)
    return f"{'-' if minor < 0 else ''}{whole}.{frac:02d}"


def fmt_tags(tags: Iterable[str]) -> str:
    return " ".join(f":{t}" for t in tags)


def clean_text(text: str) -> str:
    """Collapse tabs/newlines/runs of spaces so stored text is always one tidy line."""
    return " ".join(text.split())


def split_description(words: list[str]) -> tuple[str, str]:
    """'Croissant Burger @lake cafe' -> (source='lake cafe', note='Croissant Burger').
    Without an '@', the whole text is the source."""
    text = clean_text(" ".join(words))
    m = re.search(r"(?:^|\s)@(.*)$", text)
    if m:
        source = m.group(1).strip()
        if not source:
            raise AppError("Nothing after '@'. Name the source, e.g. @lakeviewcafe")
        return source, text[: m.start()].strip()
    if not text:
        raise AppError("Provide a source or description")
    return text, ""


def fmt_ts(ts: str) -> str:
    return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M")


def display_width(s: str) -> int:
    width = 0
    for ch in s:
        if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def render_table(headers: list[str], rows: list[list[str]], aligns: str = "") -> str:
    aligns = aligns or "<" * len(headers)
    rows = [[re.sub(r"[\r\n\t]+", " ", str(c)) for c in r] for r in rows]
    widths = [max(display_width(c) for c in col) for col in zip(headers, *rows)]

    def line(cells: list[str]) -> str:
        out = []
        for cell, w, a in zip(cells, widths, aligns):
            pad = " " * (w - display_width(cell))
            out.append(pad + cell if a == ">" else cell + pad)
        return "  ".join(out).rstrip()

    return "\n".join([line(headers), "  ".join("-" * w for w in widths), *map(line, rows)])


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def month_note(store: Store, month: str) -> str:
    if store.is_closed(month):
        return "(closed)"
    if month < current_month():
        return "(ended - run: money archive)"
    return f"({plural(days_left(month), 'day')} left)"


def nudge(store: Store, month: str) -> None:
    if not store.is_closed(month) and month < current_month():
        warn(f"{month} has ended. Run: money archive")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #

def cmd_init(store: Store, args: argparse.Namespace) -> int:
    created = store.ensure_initialized()
    print(f"Initialized money in {store.root}" if created else f"Already initialized: {store.root}")
    return 0


def cmd_record(store: Store, args: argparse.Namespace) -> int:
    amount = parse_amount(args.amount)
    words, raw_tags = extract_tags(args.words)
    tags = merge_tags(raw_tags, args.tag or [])
    source, note = split_description(words)
    ts = resolve_timestamp(args.date)
    event, ledger = store.commit(
        lambda _l: Event(new_id(), ts, args.kind, amount, source, note, tags=tags))
    cur = store.currency
    print(f"Recorded {event.id[:8]}: {source} {signed_money(event.signed, cur)}"
          + (f"  {fmt_tags(tags)}" if tags else ""))
    if event.kind is Kind.SPEND:
        if ledger.total < 0:
            warn("Total balance is now negative. That's real debt (or a missing income entry).")
        elif ledger.available < 0:
            warn("You're now spending into money you've reserved. Available is below zero.")
    return 0


def cmd_reserve(store: Store, args: argparse.Namespace) -> int:
    amount = parse_amount(args.amount)
    words, raw_tags = extract_tags(args.name)
    tags = merge_tags(raw_tags, args.tag or [])
    label = clean_text(" ".join(words))
    if not label:
        raise AppError("Reservation name cannot be empty")

    def build(ledger: Ledger) -> Event:
        if ledger.find_reservation(label):
            raise AppError(f"Active reservation already exists for: {label}")
        return Event(new_id(), now_ts(), Kind.RESERVE, amount, source=label, key=normalize_key(label), tags=tags)

    _, ledger = store.commit(build)
    print(f"Reserved {format_money(amount, store.currency)} for {label}"
          + (f"  {fmt_tags(tags)}" if tags else ""))
    if ledger.available < 0:
        warn("This reservation pushes available money below zero. Record the income first, "
             "or this money is already committed elsewhere.")
    return 0


def _close_reservation(store: Store, name_words: list[str], kind: Kind,
                       amount_text: Optional[str] = None) -> tuple[Event, Ledger]:
    name = " ".join(name_words).strip()

    def build(ledger: Ledger) -> Event:
        res = ledger.find_reservation(name)
        if not res:
            active = ", ".join(r.label for r in ledger.reservations.values())
            hint = f" Active: {active}" if active else " There are no active reservations."
            raise AppError(f"No active reservation found for: {name}.{hint}")
        amount = parse_amount(amount_text) if amount_text else res.amount
        return Event(new_id(), now_ts(), kind, amount, source=res.label, key=res.key, ref=res.id, tags=res.tags)

    event, ledger = store.commit(build)
    assert event is not None
    return event, ledger


def cmd_settle(store: Store, args: argparse.Namespace) -> int:
    event, ledger = _close_reservation(store, args.name, Kind.SETTLE, args.amount)
    cur = store.currency
    reserved = ledger.by_id[event.ref].amount
    msg = f"Settled {event.source}: {format_money(event.amount, cur)}"
    if event.amount != reserved:
        msg += f" (reserved {format_money(reserved, cur)})"
    print(msg)
    if ledger.total < 0:
        warn("You settled more than you have. Total balance is now negative.")
    return 0


def cmd_release(store: Store, args: argparse.Namespace) -> int:
    event, _ = _close_reservation(store, args.name, Kind.RELEASE)
    print(f"Released {event.source}: {format_money(event.amount, store.currency)} is available again.")
    return 0


def _finish_delete(store: Store, target: Event) -> int:
    print(f"Deleted {target.id[:8]}: {target.kind.value} {target.source} "
          f"{format_money(target.amount, store.currency)}".rstrip())
    if target.kind in CLOSING_KINDS:
        print(f"   Reservation '{target.source}' is active again.")
    return 0


def cmd_delete(store: Store, args: argparse.Namespace) -> int:
    target, _ = store.delete_entry(lambda l: check_deletable(l, l.resolve(args.id)))
    return _finish_delete(store, target)


def cmd_undo(store: Store, args: argparse.Namespace) -> int:
    def pick(ledger: Ledger) -> Event:
        target = next((e for e in reversed(ledger.events) if not e.sys), None)
        if target is None:
            raise AppError("Nothing to undo")
        return check_deletable(ledger, target)

    target, _ = store.delete_entry(pick)
    return _finish_delete(store, target)


def tx_rows(ledger: Ledger) -> list[tuple[Event, int]]:
    running, rows = 0, []
    for e in ledger.money_events():
        running += e.signed
        rows.append((e, running))
    return rows


def print_tx_table(rows: list[tuple[Event, int]], cur: str) -> None:
    if not rows:
        print("No transactions found.")
        return
    body = [
        [e.id[:8], fmt_ts(e.ts), e.kind.value, e.source, signed_money(e.signed, cur),
         format_money(bal, cur), fmt_tags(e.tags), e.note]
        for e, bal in rows
    ]
    print(render_table(["ID", "Date", "Type", "Source", "Amount", "Balance", "Tags", "Note"], body, "<<<<>><<"))


def cmd_log(store: Store, args: argparse.Namespace) -> int:
    if args.limit is not None and args.limit <= 0:
        raise AppError("--limit must be a positive number")
    month, ledger = store.snapshot(args.month)
    nudge(store, month)
    cur = store.currency
    wanted = merge_tags([args.tag]) if args.tag else ()

    if args.all:
        events = [e for e in reversed(ledger.events) if all(t in e.tags for t in wanted)][: args.limit]
        if not events:
            print("No entries found.")
            return 0
        body = []
        for e in events:
            amount = signed_money(e.signed, cur) if e.kind in MONEY_KINDS else format_money(e.amount, cur)
            body.append([e.id[:8], fmt_ts(e.ts), e.kind.value, e.source, amount, fmt_tags(e.tags), e.note])
        print(render_table(["ID", "Date", "Event", "Detail", "Amount", "Tags", "Note"], body, "<<<<><<"))
        return 0

    rows = [(e, bal) for e, bal in tx_rows(ledger) if all(t in e.tags for t in wanted)]
    rows.reverse()  # newest first; running balances were computed chronologically
    print_tx_table(rows[: args.limit], cur)
    return 0


def cmd_search(store: Store, args: argparse.Namespace) -> int:
    query = " ".join(args.query).strip().casefold()

    def haystack(e: Event) -> str:
        return " ".join([e.source, e.note, e.kind.value, e.ts, plain_money(e.amount), fmt_tags(e.tags)]).casefold()

    rows: list[tuple[Event, int]] = []
    for _, ledger in store.snapshots(args.month, everything=args.month is None):
        rows += [(e, bal) for e, bal in tx_rows(ledger) if query in haystack(e)]
    rows.reverse()
    print_tx_table(rows, store.currency)
    return 0


def cmd_status(store: Store, args: argparse.Namespace) -> int:
    month, ledger = store.snapshot(args.month)
    cur = store.currency
    count = len(ledger.reservations)
    print(f"Month:     {month} {month_note(store, month)}")
    print(f"Total:     {format_money(ledger.total, cur)}")
    print(f"Reserved:  {format_money(ledger.reserved, cur)}" + (f"  ({count} active)" if count else ""))
    print(f"Available: {format_money(ledger.available, cur)}")
    if ledger.available < 0:
        warn("Available is below zero. Usually an income entry is missing, or money is already spoken for.")
    return 0


def cmd_balance(store: Store, args: argparse.Namespace) -> int:
    _, ledger = store.snapshot(args.month)
    print(format_money(ledger.total, store.currency))
    return 0


def cmd_reserves(store: Store, args: argparse.Namespace) -> int:
    _, ledger = store.snapshot(args.month)
    cur = store.currency
    if not ledger.reservations:
        print("No active reservations.")
        return 0
    body = [[r.label, fmt_ts(r.created_at), format_money(r.amount, cur), fmt_tags(r.tags)]
            for r in ledger.reservations.values()]
    print(render_table(["Name", "Created", "Amount", "Tags"], body, "<<><"))
    print(f"\nTotal reserved: {format_money(ledger.reserved, cur)}")
    return 0


def cmd_months(store: Store, args: argparse.Namespace) -> int:
    months = store.months()
    if not months:
        print("No months yet. Run: money init")
        return 0
    cur, today, body = store.currency, current_month(), []
    for m in months:
        ledger = store.load(m)
        if store.is_closed(m):
            status = "closed" if store.closed_ok(m) else "closed - MODIFIED after close!"
        elif m < today:
            status = "open - ended, run: money archive"
        else:
            status = "open"
        body.append([m, str(ledger.entry_count), format_money(ledger.total, cur),
                     format_money(ledger.reserved, cur), status])
    print(render_table(["Month", "Entries", "Balance", "Reserved", "Status"], body, "<>>><"))
    return 0


def cmd_summary(store: Store, args: argparse.Namespace) -> int:
    cur = store.currency
    events = [e for _, ledger in store.snapshots(args.month, everything=args.month is None)
              for e in ledger.events if e.kind in FLOW_KINDS]
    groups: dict[str, list[int]] = {}
    labels: dict[str, str] = {}
    for e in events:
        if args.by == "month":
            pairs = [(e.ts[:7], e.ts[:7])]
        elif args.by == "source":
            pairs = [(e.source.casefold(), e.source)]
        else:
            pairs = [(t, f":{t}") for t in e.tags] or [("", "(untagged)")]
        for key, label in pairs:
            labels.setdefault(key, label)
            groups.setdefault(key, [0, 0])[0 if e.signed > 0 else 1] += e.amount
    if not groups:
        print("No transactions yet.")
        return 0
    keys = sorted(groups) if args.by == "month" else sorted(groups, key=lambda k: -sum(groups[k]))
    tin = sum(e.amount for e in events if e.signed > 0)
    tout = sum(e.amount for e in events if e.signed < 0)
    body = [[labels[k], format_money(groups[k][0], cur), format_money(groups[k][1], cur),
             format_money(groups[k][0] - groups[k][1], cur)] for k in keys]
    body.append(["TOTAL", format_money(tin, cur), format_money(tout, cur), format_money(tin - tout, cur)])
    print(render_table([args.by.capitalize(), "In", "Out", "Net"], body, "<>>>"))
    if args.by == "tag":
        print("\n(an entry with several tags counts under each; TOTAL counts it once)")
    return 0


def cmd_export(store: Store, args: argparse.Namespace) -> int:
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["id", "date", "type", "source", "amount", "tags", "note"])
    for _, ledger in store.snapshots(args.month, everything=args.all):
        for e in ledger.money_events():
            writer.writerow([e.id, e.ts, e.kind.value, e.source, plain_money(e.signed),
                             " ".join(e.tags), e.note])
    return 0


def cmd_config(store: Store, args: argparse.Namespace) -> int:
    if args.currency:
        print(f"Currency set to {store.set_currency(args.currency)}")
    else:
        print(json.dumps(store.load_config(), indent=2, ensure_ascii=False))
    return 0


# -- recurring reservations -------------------------------------------------- #

def cmd_recur_add(store: Store, args: argparse.Namespace) -> int:
    amount = parse_amount(args.amount)
    words, raw_tags = extract_tags(args.name)
    tags = merge_tags(raw_tags, args.tag or [])
    name = clean_text(" ".join(words))
    if not name:
        raise AppError("Recurring name cannot be empty")
    key = normalize_key(name)
    if any(normalize_key(t["name"]) == key for t in store.load_recurring()):
        raise AppError(f"Recurring '{name}' already exists. Remove it first: money recur remove {name}")

    def build(ledger: Ledger) -> Optional[Event]:  # also reserve it for the current month
        if ledger.find_reservation(name):
            return None
        return Event(new_id(), now_ts(), Kind.RESERVE, amount, source=name, key=key, tags=tags)

    event, _ = store.commit(build)
    store.update_recurring(lambda items: [*items, {"name": name, "amount": amount, "tags": list(tags)}])
    cur = store.currency
    print(f"Recurring: {name} {format_money(amount, cur)}/month" + (f"  {fmt_tags(tags)}" if tags else ""))
    print("   Reserved for this month too." if event else "   Already reserved this month; starts fresh next month.")
    return 0


def cmd_recur_list(store: Store, args: argparse.Namespace) -> int:
    items = store.load_recurring()
    if not items:
        print("No recurring reservations.")
        return 0
    cur = store.currency
    body = [[t["name"], format_money(t["amount"], cur), fmt_tags(t["tags"])] for t in items]
    print(render_table(["Name", "Amount/month", "Tags"], body, "<>>"))
    return 0


def cmd_recur_remove(store: Store, args: argparse.Namespace) -> int:
    name = " ".join(args.name).strip()
    key = normalize_key(name)
    removed: list[dict] = []

    def mutate(items: list[dict]) -> list[dict]:
        removed.extend(t for t in items if normalize_key(t["name"]) == key)
        return [t for t in items if normalize_key(t["name"]) != key]

    store.update_recurring(mutate)
    if not removed:
        raise AppError(f"No recurring reservation named: {name}")
    print(f"Removed recurring {removed[0]['name']}. Existing reservations are untouched.")
    return 0


# -- archive ------------------------------------------------------------------ #

def cmd_archive(store: Store, args: argparse.Namespace) -> int:
    if args.undo:
        return _archive_undo(store)
    cur, today = store.currency, current_month()
    with store.locked():
        months = store.months()
        opens = [m for m in months if not store.is_closed(m)]
        if len(opens) > 1:
            raise AppError(f"More than one open month ({', '.join(opens)}). Fix by hand.")
        if opens:
            src, needs_close = opens[0], True
            if src >= today:
                raise AppError(f"{src} hasn't ended yet ({plural(days_left(src), 'day')} left). "
                               "Archive after it ends.")
        elif months:  # recovery: a month was closed but its successor was never created
            src, needs_close = months[-1], False
            if src >= today:
                raise AppError(f"Nothing to archive: {src} is already closed and still current.")
        else:
            raise AppError("Nothing to archive. Run: money init")
        if store.month_dir(today).exists():
            raise AppError(f"{today} already exists. Fix by hand.")

        ledger = Ledger(store._read(src))
        start = month_start(today).isoformat(timespec="seconds")
        note = f"carried from {src}"
        events = [Event(new_id(), start, Kind.OPEN, ledger.total, "Opening balance", note, sys=True)]
        taken = set()
        for r in ledger.reservations.values():
            taken.add(r.key)
            events.append(Event(new_id(), start, Kind.RESERVE, r.amount, r.label, note, r.key,
                                tags=r.tags, since=r.created_at, sys=True))
        recurring = store._read_recurring()
        renamed: list[tuple[str, str]] = []
        for t in recurring:
            label = t["name"]
            if normalize_key(label) in taken:  # last month's one is still unsettled
                base, n = f"{label} {today}", 1
                label = base
                while normalize_key(label) in taken:
                    n += 1
                    label = f"{base}-{n}"
                renamed.append((t["name"], label))
            taken.add(normalize_key(label))
            events.append(Event(new_id(), start, Kind.RESERVE, t["amount"], label, "recurring",
                                normalize_key(label), tags=merge_tags(t["tags"]), sys=True))

        if needs_close:
            store._write_closed(src, ledger)
        store._create_month(today, events)

    if needs_close:
        n = ledger.entry_count
        print(f"Closed {src}: {format_money(ledger.total, cur)} ({n} entr{'y' if n == 1 else 'ies'}).")
    print(f"Opened {today} with {format_money(ledger.total, cur)}; "
          f"{plural(len(ledger.reservations), 'reservation')} carried over, {len(recurring)} recurring added.")
    for original, label in renamed:
        print(f"   '{original}' is still unsettled from {src}, so this month's is named '{label}'.")
    gap = months_between(src, today)
    if gap:
        print(f"   No ledger exists for: {', '.join(gap)}")
    return 0


def _archive_undo(store: Store) -> int:
    with store.locked():
        months = store.months()
        opens = [m for m in months if not store.is_closed(m)]
        if len(opens) > 1:
            raise AppError(f"More than one open month ({', '.join(opens)}). Fix by hand.")
        if opens:
            cur_month = opens[0]
            earlier = [m for m in months if m < cur_month and store.is_closed(m)]
            if not earlier:
                raise AppError("There's no earlier month to reopen.")
            if any(not e.sys for e in store._read(cur_month)):
                raise AppError(f"{cur_month} already has entries, so the archive can't be undone. "
                               "Undo or delete them first.")
            shutil.rmtree(store.month_dir(cur_month))
            prev = earlier[-1]
        else:
            closed = [m for m in months if store.is_closed(m)]
            if not closed:
                raise AppError("Nothing to undo.")
            cur_month, prev = None, closed[-1]
        store.closed_path(prev).unlink()
        os.chmod(store.ledger_path(prev), 0o644)
    print((f"Removed {cur_month} and reopened {prev}." if cur_month else f"Reopened {prev}."))
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

EPILOG = """\
quick entry:
  money +500 "Mom's vault"                          income (quote apostrophes!)
  money -90 Croissant Burger @lakeviewcafe :food    spend: note, @source, :tags
  money -90 cafe :food :treat  (or :food:treat)     several tags
  money -90 cafe -t food -t treat                   tags via flag, same thing
  money -90 cafe --date yesterday                   backdate (within the active month)

options go after the description. Bare `money` shows status. Data lives in ~/money
(or $MONEY_DIR): one folder per month; `money archive` closes a finished month.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="money", description="Git-like money tracker, one folder per month.", epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"money {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    def command(name: str, help: str, func, aliases: tuple = (), **defaults) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help, description=help, aliases=list(aliases))
        sp.set_defaults(func=func, **defaults)
        return sp

    def tag_flag(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("-t", "--tag", action="append", help="add a tag (repeatable; same as :tag)")

    def month_flag(sp: argparse.ArgumentParser, help: str = "month to read, e.g. 2026-09 (default: active)") -> None:
        sp.add_argument("-m", "--month", help=help)

    command("init", "Create ~/money and the current month", cmd_init, store_mode="init")

    sp = command("archive", "Close the finished month and open the current one", cmd_archive)
    sp.add_argument("--undo", action="store_true", help="reopen the previous month (only if the new one is untouched)")
    command("months", "List all months", cmd_months)

    for name, kind, desc in (("add", Kind.ADD, "Record income (same as: money +AMOUNT ...)"),
                             ("spend", Kind.SPEND, "Record an expense (same as: money -AMOUNT ...)")):
        sp = command(name, desc, cmd_record, kind=kind)
        sp.add_argument("amount", help="e.g. 500, 89.50, 1,200")
        sp.add_argument("words", nargs="*", metavar="description", help="source, or: note @source :tags")
        sp.add_argument("-d", "--date", help="YYYY-MM-DD, 'YYYY-MM-DD HH:MM', today, yesterday")
        tag_flag(sp)

    sp = command("reserve", "Set money aside for a named purpose", cmd_reserve)
    sp.add_argument("amount")
    sp.add_argument("name", nargs="+")
    tag_flag(sp)

    sp = command("settle", "Turn a reservation into a real spend", cmd_settle)
    sp.add_argument("name", nargs="+")
    sp.add_argument("--amount", help="actual amount paid, if different from the reserved amount")

    sp = command("release", "Cancel a reservation without spending", cmd_release)
    sp.add_argument("name", nargs="+")

    sp = command("delete", "Permanently delete an entry by ID (previous file kept as .prev)", cmd_delete)
    sp.add_argument("id", help="entry ID or unique prefix")
    command("undo", "Delete the most recent entry", cmd_undo)

    sp = command("log", "Show transactions with a running balance", cmd_log)
    sp.add_argument("-n", "--limit", type=int, help="show only the newest N rows")
    sp.add_argument("-t", "--tag", help="only entries with this tag (e.g. food or :food)")
    sp.add_argument("-a", "--all", action="store_true", help="show every event, including reserves and releases")
    month_flag(sp)

    sp = command("search", "Search source, note, tags, type, date or amount (all months)", cmd_search)
    sp.add_argument("query", nargs="+")
    month_flag(sp, "limit to one month, e.g. 2026-09")

    sp = command("status", "Month, total, reserved and available", cmd_status)
    month_flag(sp)
    sp = command("balance", "Show total balance", cmd_balance)
    month_flag(sp)
    sp = command("reserves", "Show active reservations", cmd_reserves)
    month_flag(sp)

    sp = command("summary", "Totals grouped by month, source or tag (all months)", cmd_summary)
    sp.add_argument("--by", choices=("month", "source", "tag"), default="month")
    month_flag(sp, "limit to one month, e.g. 2026-09")

    sp = command("export", "Print transactions as CSV", cmd_export)
    sp.add_argument("--all", action="store_true", help="include every month")
    month_flag(sp)

    sp = command("config", "Show or change settings", cmd_config)
    sp.add_argument("--currency", help="currency label, e.g. BDT, USD")

    recur = sub.add_parser("recur", help="Manage recurring monthly reservations",
                           description="Recurring reservations are re-created at the start of every month.")
    rsub = recur.add_subparsers(dest="recur_action", metavar="<action>", required=True)
    sp = rsub.add_parser("add", help="Add a recurring reservation (also reserves it this month)")
    sp.set_defaults(func=cmd_recur_add)
    sp.add_argument("amount")
    sp.add_argument("name", nargs="+", help="name, plus optional :tags")
    tag_flag(sp)
    rsub.add_parser("list", help="List recurring reservations").set_defaults(func=cmd_recur_list)
    sp = rsub.add_parser("remove", help="Stop a recurring reservation")
    sp.set_defaults(func=cmd_recur_remove)
    sp.add_argument("name", nargs="+")

    return parser


_HELP = {"-h", "--help"}
_DATE_TAG = {"-d", "--date", "-t", "--tag"}
# command -> (flags that take a value, flags that don't, accepts free-text words)
_FLAGS: dict[str, tuple[set, set, bool]] = {
    "add": (_DATE_TAG, _HELP, True),
    "spend": (_DATE_TAG, _HELP, True),
    "reserve": ({"-t", "--tag"}, _HELP, True),
    "settle": ({"--amount"}, _HELP, True),
    "release": (set(), _HELP, True),
    "search": ({"-m", "--month"}, _HELP, True),
    "recur add": ({"-t", "--tag"}, _HELP, True),
    "recur remove": (set(), _HELP, True),
    "log": ({"-n", "--limit", "-t", "--tag", "-m", "--month"}, _HELP | {"-a", "--all"}, False),
}


def protect_dashes(argv: list[str]) -> list[str]:
    """Let free text and tag values start with '-' ('-cafe', '->', '-5% off', '-t -lead').

    argparse reads any '-word' as an option. A leading space makes it a plain word
    instead; clean_text()/normalize_tag() strip that space again later.
    """
    if not argv:
        return argv
    head = 2 if argv[0] == "recur" and len(argv) > 1 else 1
    spec = _FLAGS.get(" ".join(argv[:head]))
    if spec is None:
        return argv
    valued, plain, words_ok = spec

    def shield(tok: str) -> str:
        return " " + tok if len(tok) > 1 and tok.startswith("-") else tok

    out, i = list(argv[:head]), head
    while i < len(argv):
        tok = argv[i]
        name, eq, _ = tok.partition("=")
        if name in valued:
            out.append(tok)
            if not eq and i + 1 < len(argv):   # its value may start with '-' too
                i += 1
                out.append(shield(argv[i]))
        elif tok in plain or not words_ok:
            out.append(tok)
        else:
            out.append(shield(tok))
        i += 1
    return out


def _prepare_streams() -> None:
    """Never crash on unencodable characters (e.g. legacy Windows consoles)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _prepare_streams()

    if not argv:  # bare `money` -> status
        argv = ["status"]
    # Quick mode: "+500 ..." / "-90 ..." becomes "add 500 ..." / "spend 90 ...".
    elif QUICK_RE.match(argv[0]):
        argv = ["add" if argv[0][0] == "+" else "spend", argv[0][1:], *argv[1:]]
    argv = protect_dashes(argv)

    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1

    try:
        store = Store.for_init() if getattr(args, "store_mode", "open") == "init" else Store.open()
        return func(store, args)
    except AppError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except BrokenPipeError:  # e.g. `money log | head`
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (OSError, ValueError, AttributeError):
            pass
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
