"""Run: python backend/test_parsers.py   (checks both MiClub parsers against saved pages)"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from build_feed import parse_miclub_calendar, parse_miclub_timesheet, parse_quick18

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

lane = {"id": "lane-cove", "host": "lanecove.quick18.com"}
day = parse_quick18(rd("lane-cove-weekday.html"), lane, "2026-11-05")
assert len(day) == 54, len(day)  # 5 of the 59 times only have a member rate
r = day[0]
assert (r["time"], r["holes"], r["price"], r["spots"], r["min_players"], r["label"]) == ("07:00", 9, 28.5, 4, 1, "9 Holes"), r
assert r["url"] == "https://lanecove.quick18.com/teetimes/course/877/teetime/202611050700?psid=4454&p=0", r["url"]
assert [f["label"] for f in r["fees"]] == ["9 Holes", "9 Holes Concession"], r["fees"]
assert all(x["label"] == "9 Holes" and "psid=4454" in x["url"] and "20261105" in x["url"] for x in day)

end = parse_quick18(rd("lane-cove-weekend.html"), lane, "2026-11-07")
assert len(end) == 44 and {x["price"] for x in end} == {32.0}, len(end)
assert (end[0]["time"], end[-1]["time"]) == ("06:00", "18:10"), (end[0]["time"], end[-1]["time"])
assert sorted({x["spots"] for x in end}) == [2, 4]
assert parse_quick18(rd("lane-cove-weekend.html"), lane, "2026-11-08") == []  # page shows another date
assert parse_quick18("<html>no tee sheet</html>", lane, "2026-11-07") == []
print("all parser tests passed")
