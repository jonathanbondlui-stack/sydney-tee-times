"""Run: python backend/test_parsers.py   (checks both MiClub parsers against saved pages)"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from build_feed import parse_miclub_calendar, parse_miclub_timesheet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rd = lambda n: open(os.path.join(ROOT, "fixtures", n), encoding="utf-8").read()
course = {"id": "moore-park"}

cal = parse_miclub_calendar(rd("moore-park-calendar.html"))
assert cal[0]["holes"] == 12 and cal[0]["prices"]["2026-11-07"] == 50.0

rows = parse_miclub_timesheet(rd("moore-park-timesheet.html"), course, "2026-11-03")
got = [(r["time"], r["spots"], r["price"], r["label"]) for r in rows]
assert got == [("10:34", 1, 42.0, "12 HOLES OFF PEAK"), ("10:42", 3, 42.0, "12 HOLES OFF PEAK"),
               ("12:02", 4, 42.0, "12 HOLES OFF PEAK"), ("17:06", 2, 27.0, "TWILIGHT OFF PEAK")], got
assert all(r["holes"] == 12 for r in rows)
try:
    parse_miclub_timesheet(rd("moore-park-timesheet.html"), course, "2026-11-04")
    raise SystemExit("date mismatch should have raised")
except ValueError:
    pass
print("all parser tests passed")
