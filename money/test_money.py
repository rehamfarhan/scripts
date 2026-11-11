"""Run with: python -m unittest test_money -v   (or: pytest)"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import money

HERE = Path(__file__).parent


def run(*argv):
    """Run money.main in-process. Returns (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = money.main(list(argv))
        except SystemExit as e:  # argparse
            code = e.code
    return code, out.getvalue(), err.getvalue()


def at(text):
    """Fake the clock: with at('2026-09-10 10:00'): ..."""
    fixed = datetime.strptime(text, "%Y-%m-%d %H:%M").astimezone()
    return mock.patch("money.now", lambda: fixed)


class ParsingTests(unittest.TestCase):
    def test_parse_amount_ok(self):
        self.assertEqual(money.parse_amount("500"), 50000)
        self.assertEqual(money.parse_amount("89.5"), 8950)
        self.assertEqual(money.parse_amount("1,200.50"), 120050)
        self.assertEqual(money.parse_amount("0.01"), 1)

    def test_parse_amount_rejects(self):
        for bad in ["nan", "inf", "-5", "0", "0.00", "1.234", "1,2,3", "", "abc", "1e5", "+5"]:
            with self.assertRaises(money.AppError, msg=bad):
                money.parse_amount(bad)

    def test_no_float_drift(self):
        self.assertEqual(sum(money.parse_amount("0.10") for _ in range(10)), money.parse_amount("1"))

    def test_format_money(self):
        self.assertEqual(money.format_money(120000, "BDT"), "BDT 1,200")
        self.assertEqual(money.format_money(8950, "BDT"), "BDT 89.50")
        self.assertEqual(money.format_money(-5000, "BDT"), "BDT -50")
        self.assertEqual(money.signed_money(0, "BDT"), "BDT 0")

    def test_split_description(self):
        self.assertEqual(money.split_description(["Mom's", "vault"]), ("Mom's vault", ""))
        sd = money.split_description
        self.assertEqual(sd(["Burger", "@lake", "cafe"]), ("lake cafe", "Burger"))      # source = rest of the text
        self.assertEqual(sd(["Chicken", "Fry", "@Sadar", "Hospital"]), ("Sadar Hospital", "Chicken Fry"))
        self.assertEqual(sd(["Chicken Fry @Sadar Hospital"]), ("Sadar Hospital", "Chicken Fry"))   # one quoted argument
        self.assertEqual(sd(["@Sadar", "Hospital"]), ("Sadar Hospital", ""))
        self.assertEqual(sd(["x", "@a", "@b"]), ("a @b", "x"))                         # later '@' stays in the source
        self.assertEqual(sd(["@me@bank.com"]), ("me@bank.com", ""))
        self.assertEqual(sd(["coffee", "@", "cafe"]), ("cafe", "coffee"))               # space after '@' is fine
        self.assertEqual(sd(["Tutor", "Fees"]), ("Tutor Fees", ""))                     # no @ -> whole text
        for bad in ([], ["Burger", "@"]):
            with self.assertRaises(money.AppError):
                money.split_description(bad)

    def test_whitespace_is_collapsed(self):
        self.assertEqual(money.split_description(["tabs\tand\n", "newlines", "@my\n cafe"]),
                         ("my cafe", "tabs and newlines"))

    def test_protect_dashes(self):
        p = money.protect_dashes
        self.assertEqual(p(["spend", "1", "bus", "->", "home"]), ["spend", "1", "bus", " ->", "home"])
        self.assertEqual(p(["spend", "1", "x", "-t", "-a", "--date=yesterday", "-d", "x"]),
                         ["spend", "1", "x", "-t", " -a", "--date=yesterday", "-d", "x"])
        self.assertEqual(p(["spend", "1", "x", "-h"]), ["spend", "1", "x", "-h"])
        self.assertEqual(p(["recur", "add", "5", "-x"]), ["recur", "add", "5", " -x"])
        self.assertEqual(p(["log", "-a", "-t", "-lead"]), ["log", "-a", "-t", " -lead"])
        self.assertEqual(p(["log", "--bogus"]), ["log", "--bogus"])   # log has no free text
        self.assertEqual(p(["status", "-m", "2026-10"]), ["status", "-m", "2026-10"])

    def test_tags(self):
        rest, raw = money.extract_tags(["Burger", ":Food", "@cafe", ":treat,fun", ":", "::", "#3", "a:b"])
        self.assertEqual(rest, ["Burger", "@cafe", ":", "::", "#3", "a:b"])   # '#' and mid-word ':' are plain text
        self.assertEqual(money.merge_tags(raw, ["Food", "eating out"]), ("food", "treat", "fun", "eating-out"))
        self.assertEqual(money.merge_tags([":a:b", "c#d", ":-x"]), ("a", "b", "c#d", "-x"))

    def test_months(self):
        self.assertEqual(money.next_month("2026-12"), "2027-01")
        self.assertEqual(money.months_between("2026-08", "2026-11"), ["2026-09", "2026-10"])
        with self.assertRaises(money.AppError):
            money.parse_month("2026-13")

    def test_timestamps(self):
        self.assertIn("T", money.resolve_timestamp("yesterday"))
        for bad in ("2999-01-01", "not a date"):
            with self.assertRaises(money.AppError):
                money.resolve_timestamp(bad)

    def test_table_handles_wide_chars(self):
        lines = money.render_table(["A", "B"], [["日本", "x"], ["ab", "y"]]).splitlines()
        self.assertEqual(money.display_width(lines[2].split("  ")[0]), 4)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "money"
        self.old_env = os.environ.get(money.ENV_DIR)
        os.environ[money.ENV_DIR] = str(self.root)

    def tearDown(self):
        if self.old_env is None:
            os.environ.pop(money.ENV_DIR, None)
        else:
            os.environ[money.ENV_DIR] = self.old_env
        self.tmp.cleanup()

    def total(self, *extra):
        return run("balance", *extra)[1].strip()


class BasicTests(Base):
    def setUp(self):
        super().setUp()
        self.assertEqual(run("init")[0], 0)

    def test_init_layout_and_idempotent(self):
        month = money.current_month()
        self.assertTrue((self.root / month / "ledger.jsonl").exists())
        self.assertTrue((self.root / "config.json").exists())
        self.assertIn("Already", run("init")[1])

    def test_not_initialized(self):
        os.environ[money.ENV_DIR] = str(Path(self.tmp.name) / "nowhere")
        self.assertEqual(run("balance")[0], 2)

    def test_bare_money_shows_status(self):
        code, out, _ = run()
        self.assertEqual(code, 0)
        self.assertIn("Month:", out)
        self.assertIn("days left", out.replace("day left", "days left"))

    def test_help_flags_are_not_quick_entries(self):
        self.assertEqual(run("-h")[0], 0)
        self.assertEqual(run("--version")[0], 0)

    def test_quick_entry_and_balance(self):
        self.assertEqual(run("+1000", "Salary")[0], 0)
        code, out, _ = run("-90", "Croissant", "Burger", "@lakeviewcafe")
        self.assertEqual(code, 0)
        self.assertIn("lakeviewcafe", out)
        self.assertEqual(self.total(), "BDT 910")
        log = run("log")[1]
        self.assertIn("lakeviewcafe", log)
        self.assertIn("Croissant Burger", log)

    def test_bad_amounts_never_reach_ledger(self):
        for bad in ("+nan", "+inf", "-0", "+1.234"):
            self.assertEqual(run(bad, "x")[0], 2, bad)
        self.assertEqual(self.total(), "BDT 0")

    def test_missing_description_errors(self):
        self.assertEqual(run("-90")[0], 2)
        self.assertEqual(run("-90", "burger", "@")[0], 2)

    def test_reserve_settle(self):
        run("+2000", "Mom")
        run("reserve", "1200", "RafiqulSir")
        self.assertIn("Available: BDT 800", run("status")[1])
        self.assertEqual(run("reserve", "5", "rafiqulsir")[0], 2)  # duplicate, case-insensitive
        code, out, _ = run("settle", "RAFIQULSIR", "--amount", "1150")
        self.assertEqual(code, 0)
        self.assertIn("reserved BDT 1,200", out)
        self.assertEqual(self.total(), "BDT 850")
        self.assertIn("No active reservations", run("reserves")[1])
        code, _, err = run("settle", "RafiqulSir")
        self.assertEqual(code, 2)
        self.assertIn("no active reservations", err.lower())

    def test_release_spends_nothing(self):
        run("+500", "Mom")
        run("reserve", "300", "Rent")
        self.assertEqual(run("release", "rent")[0], 0)
        self.assertEqual(self.total(), "BDT 500")
        self.assertIn("Available: BDT 500", run("status")[1])

    def test_undo_deletes_last_entry_for_real(self):
        run("+500", "Mom")
        run("-50", "tea")
        code, out, _ = run("undo")
        self.assertEqual(code, 0)
        self.assertIn("Deleted", out)
        self.assertEqual(self.total(), "BDT 500")
        path = self.root / money.current_month() / "ledger.jsonl"
        self.assertEqual(len(path.read_text().splitlines()), 1)
        self.assertTrue(path.with_name("ledger.jsonl.prev").exists())

    def test_undo_settle_restores_reservation(self):
        run("+500", "Mom")
        run("reserve", "300", "Rent")
        run("settle", "Rent")
        self.assertEqual(self.total(), "BDT 200")
        code, out, _ = run("undo")
        self.assertEqual(code, 0)
        self.assertIn("active again", out)
        self.assertEqual(self.total(), "BDT 500")
        self.assertIn("Rent", run("reserves")[1])

    def test_undo_nothing(self):
        self.assertEqual(run("undo")[0], 2)

    def test_delete_rules(self):
        run("+500", "Mom")
        run("reserve", "300", "Rent")
        reserve_id = next(l.split()[0] for l in run("log", "--all")[1].splitlines() if " reserve " in l)
        run("settle", "Rent")
        self.assertEqual(run("delete", reserve_id)[0], 2)   # closed -> delete the settle first
        run("reserve", "10", "Rent")                        # a new active "Rent"
        settle_id = next(l.split()[0] for l in run("log", "--all")[1].splitlines() if " settle " in l)
        self.assertEqual(run("delete", settle_id)[0], 2)    # would collide with the new "Rent"
        self.assertEqual(run("delete", "zzzz")[0], 2)

    def test_delete_by_prefix(self):
        run("+500", "Mom")
        run("-50", "tea")
        tx_id = run("log")[1].splitlines()[2].split()[0]
        self.assertEqual(run("delete", tx_id[:4])[0], 0)
        self.assertEqual(self.total(), "BDT 500")
        self.assertEqual(run("delete", tx_id)[0], 2)         # already gone

    def test_negative_warnings(self):
        run("+100", "Mom")
        code, _, err = run("-500", "oops")
        self.assertEqual(code, 0)
        self.assertIn("negative", err)
        self.assertIn("below zero", run("reserve", "50", "X")[2])

    def test_backdate_orders_log_and_balance(self):
        first_day = money.current_month() + "-01"
        run("+1000", "Salary", "--date", first_day)
        run("-100", "later")
        rows = run("log")[1].splitlines()[2:]
        self.assertIn("later", rows[0])                      # newest first
        self.assertIn("BDT 900", rows[0])
        self.assertIn("BDT 1,000", rows[1])
        self.assertEqual(run("-5", "old", "--date", "2020-01-01")[0], 2)  # closed/other month

    def test_corrupt_ledger_reports_line(self):
        run("+5", "x")
        with (self.root / money.current_month() / "ledger.jsonl").open("a") as fh:
            fh.write("{not json}\n")
        code, _, err = run("balance")
        self.assertEqual(code, 2)
        self.assertIn("line 2", err)

    def test_config_currency(self):
        self.assertEqual(run("config", "--currency", "usd")[0], 0)
        run("+5", "x")
        self.assertEqual(self.total(), "USD 5")
        self.assertEqual(run("config", "--currency", "bad cur")[0], 2)

    def test_concurrent_writers_lose_nothing(self):
        procs = [
            subprocess.Popen([sys.executable, str(HERE / "money.py"), "+1", f"w{i}-{j}"],
                             env=dict(os.environ), stdout=subprocess.DEVNULL)
            for i in range(6) for j in range(5)
        ]
        for p in procs:
            self.assertEqual(p.wait(), 0)
        self.assertEqual(self.total(), "BDT 30")


class TagTests(Base):
    def setUp(self):
        super().setUp()
        run("init")

    def test_tags_hash_flag_and_filters(self):
        run("+1000", "Salary", ":income")
        run("-90", "Burger", "@Cafe", ":food", ":treat")
        run("-10", "tea", "@cafe", "-t", "food")
        run("-20", "bus", "-t", "transport,commute")
        run("-5", "misc")
        log_food = run("log", "-t", "food")[1]
        self.assertIn("tea", log_food)
        self.assertIn("Burger", log_food)
        self.assertNotIn("bus", log_food)
        self.assertIn(":transport :commute", run("log")[1])
        self.assertIn("transport", run("search", "commute")[1])

    def test_summary_by_tag_counts_each_once_in_total(self):
        run("+1000", "Salary")
        run("-90", "Burger", ":food", ":treat")
        run("-10", "misc")
        out = run("summary", "--by", "tag")[1]
        self.assertIn(":food", out)
        self.assertIn(":treat", out)
        self.assertIn("(untagged)", out)
        total_line = next(l for l in out.splitlines() if l.startswith("TOTAL"))
        self.assertIn("BDT 100", total_line)                 # 90 + 10, burger counted once

    def test_summary_by_source_and_month_and_export(self):
        run("+1000", "Salary")
        run("-90", "Burger", "@Cafe", ":food")
        run("-10", "tea", "@cafe")
        summary = run("summary", "--by", "source")[1]
        self.assertEqual(summary.count("Cafe"), 1)           # grouped case-insensitively
        self.assertIn("TOTAL", run("summary")[1])
        csv_out = run("export")[1].splitlines()
        self.assertEqual(csv_out[0], "id,date,type,source,amount,tags,note")
        self.assertEqual(len(csv_out), 4)
        self.assertTrue(any(",-90.00,food," in l for l in csv_out))

    def test_reserve_tags_flow_to_settle(self):
        run("+500", "Mom")
        run("reserve", "200", "Tutor", ":education")
        self.assertIn(":education", run("reserves")[1])
        run("settle", "Tutor")
        self.assertIn(":education", run("log")[1])


class SourceTests(Base):
    def setUp(self):
        super().setUp()
        run("init")
        run("+1000", "seed")

    def last_row(self):
        return run("log")[1].splitlines()[2]

    def test_multiword_source_with_tags_before_or_after(self):
        for args in (["Chicken", "Fry", "@Sadar", "Hospital", ":food"],
                     ["Chicken", "Fry", ":food", "@Sadar", "Hospital"],
                     [":food", "Chicken", "Fry", "@Sadar", "Hospital"]):
            self.assertEqual(run("-40", *args)[0], 0)
            row = self.last_row()
            self.assertIn(" Sadar Hospital ", row)
            self.assertIn("Chicken Fry", row)
            self.assertEqual(row.count(":food"), 1)

    def test_options_after_a_multiword_source(self):
        self.assertEqual(run("-5", "tea", "@Sadar", "Hospital", "Canteen", "-t", "drink", "-d", "yesterday")[0], 0)
        row = next(l for l in run("log")[1].splitlines() if "Canteen" in l)   # backdated, so not the newest row
        self.assertIn("Sadar Hospital Canteen", row)
        self.assertIn(":drink", row)

    def test_case_preserved_but_grouped_case_insensitively(self):
        run("-10", "a", "@Sadar Hospital")
        run("-20", "b", "@sadar hospital")
        run("-30", "c", "@SADAR HOSPITAL")
        rows = run("log")[1]
        for spelling in ("Sadar Hospital", "sadar hospital", "SADAR HOSPITAL"):
            self.assertIn(spelling, rows)                 # stored exactly as typed
        summary = run("summary", "--by", "source")[1]
        line = next(l for l in summary.splitlines() if "adar" in l.lower())
        self.assertIn("Sadar Hospital", line)             # first spelling labels the group
        self.assertIn("BDT 60", line)                     # all three counted together
        self.assertEqual(sum("adar" in l.lower() for l in summary.splitlines()), 1)
        self.assertIn("b", run("search", "SADAR hospital")[1])   # search ignores case

    def test_no_at_means_whole_text_is_source(self):
        run("+3000", "Tutor Fees")
        self.assertIn("Tutor Fees", self.last_row())

    def test_empty_source_after_at_is_an_error(self):
        code, _, err = run("-5", "coffee", "@")
        self.assertEqual(code, 2)
        self.assertIn("Nothing after '@'", err)


class SpecialCharTests(Base):
    """@ _ - / . : (and a leading '-') must work in sources, tags and names."""

    def setUp(self):
        super().setUp()
        run("init")
        run("+1000", "seed")

    def last_row(self):
        return run("log")[1].splitlines()[2]

    def test_sources_with_special_characters(self):
        for src in ("bkash/personal", "user_name.v2", "me@bank.com", "a-b-c", "-cafe", "shop:main", "50%-off"):
            code, _, err = run("-1", "note", f"@{src}")
            self.assertEqual(code, 0, f"{src}: {err}")
            self.assertIn(f" {src} ", self.last_row())
        self.assertEqual(run("summary", "--by", "source")[1].count("me@bank.com"), 1)

    def test_tags_with_special_characters(self):
        run("-1", "x", ":food/lunch", ":a_b", ":c-d", ":e.f", ":g@h", ":50%")
        row = self.last_row()
        for tag in (":food/lunch", ":a_b", ":c-d", ":e.f", ":g@h", ":50%"):
            self.assertIn(tag, row)
        self.assertIn("x", run("log", "-t", "food/lunch")[1])
        self.assertIn("x", run("log", "-t", ":e.f")[1])
        self.assertIn(":g@h", run("search", ":g@h")[1])
        self.assertIn(":food/lunch", run("summary", "--by", "tag")[1])

    def test_colon_is_the_tag_marker_and_separator(self):
        run("-1", "a", ":x:y", ":z,w")
        self.assertIn(":x :y :z :w", self.last_row())
        run("-1", "b", "-t", "p:q,r")
        self.assertIn(":p :q :r", self.last_row())
        self.assertIn("b", run("log", "-t", "p")[1])
        self.assertIn("b", run("log", "-t", ":q")[1])
        both = run("log", "-t", "x:y")[1]            # several tags = entries having all of them
        self.assertIn("a", both)
        self.assertNotIn("  b  ", both)

    def test_hash_and_midword_colons_are_plain_text(self):
        run("-1", "item", "#3", "ratio", "1:2", "@shop:main")
        row = self.last_row()
        self.assertIn(" shop:main ", row)
        self.assertIn("item #3 ratio 1:2", row)       # note keeps '#3' and '1:2'
        self.assertNotIn(" :", row)                   # no tags were created
        run("-1", "lonely", ":", "::")
        self.assertIn("lonely : ::", self.last_row())   # source, no tags created

    def test_words_and_values_may_start_with_dash(self):
        self.assertEqual(run("-1", "bus", "->", "home")[0], 0)
        self.assertIn("bus -> home", self.last_row())
        self.assertEqual(run("-1", "-5%", "off", "@shop", "-d", "yesterday")[0], 0)
        self.assertIn("-5% off", run("log")[1])
        self.assertEqual(run("-1", "x", "-t", "-lead", "-t", "@work")[0], 0)
        self.assertIn(":-lead :@work", self.last_row())
        self.assertEqual(run("-1", "y", "--tag=-eq")[0], 0)
        self.assertIn(":-eq", self.last_row())
        self.assertIn("y", run("log", "-t", "-eq")[1])
        self.assertIn("bus -> home", run("search", "->")[1])

    def test_flags_and_help_still_work(self):
        self.assertEqual(run("spend", "1", "x", "-h")[0], 0)
        self.assertEqual(run("log", "-a", "-n", "1")[0], 0)
        self.assertEqual(run("-1", "x", "--date", "yesterday")[0], 0)
        self.assertEqual(run("log", "--bogus")[0], 2)
        self.assertEqual(run("-1", "x", "--nope")[0], 0)   # unknown "options" are just words

    def test_names_roundtrip(self):
        run("reserve", "5", "Dr.Rafiq/tutor_1", ":edu/private")
        run("reserve", "6", "-weird")
        self.assertIn("-weird", run("reserves")[1])
        self.assertEqual(run("settle", "-weird")[0], 0)
        self.assertEqual(run("release", "Dr.Rafiq/tutor_1")[0], 0)
        self.assertIn("No active reservations", run("reserves")[1])
        self.assertEqual(run("recur", "add", "7", "-isp", ":net/home")[0], 0)
        self.assertIn("-isp", run("recur", "list")[1])
        self.assertEqual(run("recur", "remove", "-isp")[0], 0)


class RecurringTests(Base):
    def setUp(self):
        super().setUp()
        run("init")
        run("+5000", "Mom")

    def test_recur_add_list_remove(self):
        code, out, _ = run("recur", "add", "1,200", "Rent", ":housing")
        self.assertEqual(code, 0)
        self.assertIn("Reserved for this month", out)
        self.assertIn("Rent", run("reserves")[1])
        self.assertIn("BDT 1,200", run("recur", "list")[1])
        self.assertEqual(run("recur", "add", "5", "rent")[0], 2)      # duplicate template
        self.assertEqual(run("recur", "remove", "RENT")[0], 0)
        self.assertIn("No recurring", run("recur", "list")[1])
        self.assertEqual(run("recur", "remove", "rent")[0], 2)
        self.assertIn("Rent", run("reserves")[1])                      # existing reservation untouched

    def test_recur_add_skips_reserve_if_already_active(self):
        run("reserve", "100", "Rent")
        out = run("recur", "add", "1200", "Rent")[1]
        self.assertIn("Already reserved", out)
        self.assertIn("BDT 100", run("reserves")[1])


class ArchiveTests(Base):
    def test_full_month_cycle(self):
        with at("2026-09-10 10:00"):
            run("init")
            run("+1000", "Salary")
            run("-100", "lunch", ":food")
            run("reserve", "300", "Rent", ":housing")
            run("recur", "add", "200", "Netflix", ":fun")
            run("recur", "add", "300", "Rent", ":housing")
            run("settle", "Netflix")
            code, _, err = run("archive")                                # too early
            self.assertEqual(code, 2)
            self.assertIn("hasn't ended", err)
            self.assertIn("(21 days left)", run("status")[1])

        with at("2026-10-02 09:00"):
            code, out, err = run("-5", "late")                           # stale month refuses new entries
            self.assertEqual(code, 2)
            self.assertIn("archive", err)
            self.assertIn("ended - run: money archive", run("status")[1])
            self.assertIn("ended", run("months")[1])

            code, out, _ = run("archive")
            self.assertEqual(code, 0)
            self.assertIn("Closed 2026-09: BDT 700", out)
            self.assertIn("1 reservation carried over, 2 recurring added", out)
            self.assertIn("'Rent' is still unsettled from 2026-09", out)

            # layout & read-only close
            self.assertTrue((self.root / "2026-09" / "closed.json").exists())
            info = json.loads((self.root / "2026-09" / "closed.json").read_text())
            self.assertEqual((info["closing_total"], info["closing_reserved"]), (70000, 30000))
            self.assertTrue((self.root / "2026-10" / "ledger.jsonl").exists())

            # new month state
            status = run("status")[1]
            self.assertIn("Month:     2026-10", status)
            self.assertIn("Total:     BDT 700", status)
            self.assertIn("Reserved:  BDT 800", status)
            reserves = run("reserves")[1]
            self.assertIn("Rent 2026-10", reserves)                    # collides with carried Rent
            self.assertIn("Netflix", reserves)
            self.assertIn("2026-09-10", reserves)                        # carried reservation keeps its age
            self.assertIn("open", run("log")[1])
            self.assertIn("Opening balance", run("log")[1])

            # opening entries are protected
            self.assertEqual(run("undo")[0], 2)
            opening_id = run("log", "-a")[1].splitlines()[-1].split()[0]
            self.assertEqual(run("delete", opening_id)[0], 2)

            # closed month: readable via -m, not writable
            self.assertIn("lunch", run("log", "-m", "2026-09")[1])
            self.assertIn("(closed)", run("status", "-m", "2026-09")[1])
            self.assertEqual(run("-5", "x", "--date", "2026-09-30")[0], 2)
            self.assertIn("closed", run("-5", "x", "--date", "2026-09-30")[2])
            self.assertEqual(run("log", "-m", "2019-01")[0], 2)

            # settle clears the oldest 'Rent' first; the other keeps its bracketed name
            run("settle", "Rent")
            reserves = run("reserves")[1]
            self.assertIn("Rent 2026-10", reserves)
            self.assertEqual(self.total(), "BDT 400")

            # summary spans months and excludes the opening balance
            out = run("summary")[1]
            self.assertIn("2026-09", out)
            self.assertIn("2026-10", out)
            self.assertIn("TOTAL", out)
            self.assertIn("fun", run("summary", "--by", "tag")[1])
            self.assertIn("lunch", run("search", "lunch")[1])            # search spans all months

            months = run("months")[1]
            self.assertIn("closed", months)
            self.assertIn("open", months)

            # the renamed one needs no shell quoting
            self.assertEqual(run("settle", "Rent", "2026-10")[0], 0)
            self.assertEqual(self.total(), "BDT 100")

            # can't undo the archive once the new month has entries
            self.assertEqual(run("archive", "--undo")[0], 2)

    def test_archive_undo_roundtrip(self):
        with at("2026-09-10 10:00"):
            run("init")
            run("+100", "x")
        with at("2026-10-02 09:00"):
            self.assertEqual(run("archive")[0], 0)
            code, out, _ = run("archive", "--undo")
            self.assertEqual(code, 0)
            self.assertIn("reopened 2026-09", out)
            self.assertFalse((self.root / "2026-10").exists())
            self.assertFalse((self.root / "2026-09" / "closed.json").exists())
            self.assertEqual(self.total(), "BDT 100")
            self.assertEqual(run("archive")[0], 0)                       # and again, cleanly
            self.assertEqual(self.total(), "BDT 100")

    def test_gap_months_are_skipped(self):
        with at("2026-08-10 10:00"):
            run("init")
            run("+100", "x")
        with at("2026-11-02 09:00"):
            code, out, _ = run("archive")
            self.assertEqual(code, 0)
            self.assertIn("No ledger exists for: 2026-09, 2026-10", out)
            self.assertTrue((self.root / "2026-11").exists())
            self.assertEqual(self.total(), "BDT 100")

    def test_archive_recovers_if_new_month_was_never_created(self):
        with at("2026-09-10 10:00"):
            run("init")
            run("+100", "x")
        with at("2026-10-02 09:00"):
            store = money.Store(self.root)
            store._write_closed("2026-09", store.load("2026-09"))        # simulate a crash mid-archive
            self.assertEqual(run("balance")[0], 2)                        # no active month
            self.assertEqual(run("archive")[0], 0)
            self.assertEqual(self.total(), "BDT 100")

    def test_tampering_with_closed_month_is_detected(self):
        with at("2026-09-10 10:00"):
            run("init")
            run("+100", "x")
        with at("2026-10-02 09:00"):
            run("archive")
            path = self.root / "2026-09" / "ledger.jsonl"
            path.chmod(0o644)
            path.write_text(path.read_text() + "\n")
            self.assertIn("MODIFIED", run("months")[1])
            self.assertIn("modified after it was closed", run("log", "-m", "2026-09")[2])


if __name__ == "__main__":
    unittest.main()
