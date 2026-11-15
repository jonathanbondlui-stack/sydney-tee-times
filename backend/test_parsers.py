"""Run: python backend/test_parsers.py   (checks both MiClub parsers against saved pages)"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from build_feed import headline_fee, limited_to, parse_miclub_calendar, parse_miclub_timesheet, parse_quick18

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

named = parse_miclub_timesheet(rd("moore-park-timesheet.html"), course, "2026-11-03", {"label": "4 Players + 2 Carts", "holes": None})
assert named and all(r["group"] == "4 Players + 2 Carts" for r in named)
assert all(r["group"] == "" for r in rows)

popover = '''<div id="row-1" class="row row-time"><h3>12:41 pm </h3><h4>1st Tee Social Play</h4>
<a tabindex="0" class="fee-applied popover-right" role="button" title="Fees" data-html="true" data-content="<ul><li>Adult $44.50</li><li>Pensioner (Mid-week) $30.20</li></ul>" data-placement="right"><span>Fees</span></a>
<div class="cell cell-taken"></div><div class="cell cell-available"></div></div>'''
tucked = parse_miclub_timesheet(popover, course, "2026-11-05")
assert [(r["price"], r["label"], r["spots"]) for r in tucked] == [(44.5, "Adult", 1)], tucked
assert tucked[0]["fees"] == [{"price": 44.5, "label": "Adult"}, {"price": 30.2, "label": "Pensioner (Mid-week)"}], tucked
escaped = popover.replace("<ul>", "&lt;ul&gt;").replace("<li>", "&lt;li&gt;").replace("</li>", "&lt;/li&gt;").replace("</ul>", "&lt;/ul&gt;")
assert parse_miclub_timesheet(escaped, course, "2026-11-05")[0]["price"] == 44.5

fee = lambda *names: [{"price": 10.0 + i, "label": n} for i, n in enumerate(names)]
pick = lambda *names: (lambda f, only: (f["label"], only))(*headline_fee(fee(*names)))
assert pick("Adult", "Junior") == ("Adult", "")
assert pick("Juniors Midweek (under 18)", "Twilight Midweek") == ("Twilight Midweek", "")
assert pick("Concession & Juniors (Weekend)", "Twilight", "Disc Golf") == ("Twilight", "")
assert pick("Midweek Under 18") == ("Midweek Under 18", "Juniors only")
assert pick("Green Fee Jnr M-F") == ("Green Fee Jnr M-F", "Juniors only")
assert pick("Senior 9 hole") == ("Senior 9 hole", "Seniors only")
assert pick("Pensioner", "Senior") == ("Pensioner", "Seniors only")
assert pick("Student (Mon-Fri)", "Disc Golf") == ("Student (Mon-Fri)", "Students only")
assert pick("Junior 18 Holes", "Pensioner") == ("Junior 18 Holes", "Concession only")
assert pick("18 Holes Student & Pensioner (Mon - Fri)") == ("18 Holes Student & Pensioner (Mon - Fri)", "Concession only")
assert pick("Disc Golf") == ("Disc Golf", "Disc golf only")
assert pick("Wests Member 18 Holes", "Public Social Weekday 18 Holes") == ("Public Social Weekday 18 Holes", "")
assert pick("18 Hole Monday Special DLC Member") == ("18 Hole Monday Special DLC Member", "Partner club members only")
assert not limited_to("Non Member 18 Holes") and not limited_to("Non-Member Weekend")
assert headline_fee([]) == (None, "")
for name in ("Adult Visitor Midweek", "18 Holes International Green Fee", "Social Weekday - Online", "Gangurru 18 holes", "Twilight $15",
             "1 Player  (Twilight)", "Foreplay Friday", "Afternoon Special Mon-Fri", "12 HOLES OFF PEAK", "Green Fee M-F", "9 Holes Adult"):
    assert not limited_to(name), name

import datetime as dt, json
from build_feed import parse_teeitup, sydney_time
utc = lambda *a: dt.datetime(*a, tzinfo=dt.timezone.utc)
assert sydney_time(utc(2026, 11, 5, 20, 0)) == dt.datetime(2026, 11, 6, 7, 0)  # summer, +11
assert sydney_time(utc(2026, 7, 1, 0, 0)) == dt.datetime(2026, 7, 1, 10, 0)    # winter, +10
assert sydney_time(utc(2026, 4, 4, 15, 59)) == dt.datetime(2026, 4, 5, 2, 59)  # just before clocks go back
assert sydney_time(utc(2026, 4, 4, 16, 0)) == dt.datetime(2026, 4, 5, 2, 0)
assert sydney_time(utc(2026, 10, 3, 15, 59)) == dt.datetime(2026, 10, 4, 1, 59)  # just before clocks go forward
assert sydney_time(utc(2026, 10, 3, 16, 0)) == dt.datetime(2026, 10, 4, 3, 0)

gr = {"id": "georges-river", "host": "georges-river-golf-course.book.teeitup.com", "facility_id": 16001}
sat = parse_teeitup(rd("georges-river-teeitup.json"), gr, "2026-11-07")
assert len(sat) == 35 and sat[0]["time"] == "10:21" and sat[-1]["time"] == "15:56", (len(sat), sat[0]["time"], sat[-1]["time"])
assert {(r["holes"], r["price"]) for r in sat} == {(18, 45.0), (9, 32.0)}
assert sat[0]["url"] == "https://georges-river-golf-course.book.teeitup.com/?course=16001&date=2026-11-07", sat[0]["url"]
assert parse_teeitup(rd("georges-river-teeitup.json"), gr, "2026-11-08") == []  # response is for another date
one = {"teetime": "2026-11-05T20:00:00.000Z", "maxPlayers": 2, "minPlayers": 1, "backNine": False, "rates": [
    {"name": "2 Player Promotion", "allowedPlayers": [2, 4], "holes": 18, "greenFeeCart": 5200},
    {"name": "18 Holes", "allowedPlayers": [1, 2], "holes": 18, "greenFeeWalking": 3200},
    {"name": "Member Rate", "allowedPlayers": [1], "holes": 18, "greenFeeWalking": 1000}]}
got = parse_teeitup(json.dumps([{"teetimes": [one]}]), gr, "2026-11-06")
assert [(r["time"], r["label"], r["price"], r["spots"]) for r in got] == [
    ("07:00", "2 Player Promotion with cart", 104.0, 2), ("07:00", "18 Holes", 32.0, 2)], got
one["maxPlayers"] = 1  # a two-player rate can't fit in one remaining spot
assert [r["label"] for r in parse_teeitup(json.dumps([{"teetimes": [one]}]), gr, "2026-11-06")] == ["18 Holes"]

from build_feed import golfnow_players, parse_golfnow
assert golfnow_players("Any") == [1, 2, 3, 4] and golfnow_players("OneTwo") == [1, 2] and golfnow_players("TwoFour") == [2, 4]
try:
    golfnow_players("Sometimes")
    raise SystemExit("unknown player rule should have raised")
except ValueError:
    pass
gn = {"id": "lakeside-camden", "host": "www.golfnow.com.au", "facility_id": 15858}
def gn_rate(name, holes, price, rule="Any", cart=False, hidden=False, url="/tee-times/facility/15858/tee-time/1"):
    return {"rateName": name, "holeCount": holes, "playerRule": rule, "isCartIncluded": cart, "isHotDealHidden": hidden, "detailUrl": url,
            "singlePlayerPrice": {"greensFees": {"value": price}, "transactionFeesTotal": {"value": 1.0}}}
gn_time = lambda when, *rates: {"time": {"date": when}, "teeTimeRates": list(rates)}
gn_day = parse_golfnow(json.dumps({"ttResults": {"teeTimes": [
    gn_time("2026-11-06T13:28:00+00:00", gn_rate("9 Holes", 9, 35.0, "OneTwoThree")),
    gn_time("2026-11-06T13:36:00+00:00", gn_rate("18 Holes", 18, 95.0, "TwoFour", cart=True)),
    gn_time("2026-11-06T13:44:00+00:00", gn_rate("Hot Deal", 18, 49.0, hidden=True)),
    gn_time("2026-11-06T13:52:00+00:00", gn_rate("Senior", 18, 30.0)),
    gn_time("2026-11-06T14:00:00+00:00", gn_rate("Member", 18, 10.0)),
    gn_time("2026-11-07T07:00:00+00:00", gn_rate("18 Holes", 18, 60.0))]}}), gn, "2026-11-06")
assert [(r["time"], r["holes"], r["price"], r["spots"], r["min_players"], r["label"], r["only"]) for r in gn_day] == [
    ("13:28", 9, 35.0, 3, 1, "9 Holes", ""),
    ("13:36", 18, 190.0, 4, 2, "18 Holes with cart (2 players)", ""),
    ("13:52", 18, 30.0, 4, 1, "Senior", "Seniors only")], gn_day
assert gn_day[0]["url"] == "https://www.golfnow.com.au/tee-times/facility/15858/tee-time/1"
assert parse_golfnow(json.dumps({"ttResults": {"teeTimes": []}}), gn, "2026-11-06") == []
try:
    parse_golfnow("{}", gn, "2026-11-06")
    raise SystemExit("a response with no results should have raised")
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

# Victorian rate names
assert limited_to("Mid Week - 13 - 17 Year Old 18 Holes") == {"Juniors"}
assert limited_to("Midweek - 13-17 Year Old 9 Holes") == {"Juniors"}
assert limited_to("Midweek Over 60's") == {"Seniors"}
assert limited_to("RACV Member Required to Show Member Card") == {"Partner club members"}
assert not limited_to("Non RACV Member (Off Peak)") and not limited_to("Non-Wests Member")
torquay = [{"price": 80.0, "label": "RACV Member Required to Show Member Card (Off Peak)"},
           {"price": 100.0, "label": "Non RACV Member (Off Peak)"}, {"price": 35.0, "label": "Junior (Under 18)"}]
assert headline_fee(torquay) == (torquay[1], ""), headline_fee(torquay)
assert not limited_to("Adult Midweek 18H") and not limited_to("2026 Green Fee - 9 Holes") and not limited_to("Adult Midweek 13 Holes")
print("victorian rate tests passed")

# Clubs that book several courses on one site
from build_feed import apply_splits, with_parts
club = [{"id": "moonah-links", "split": [{"match": r"^Trackman", "to": None}, {"match": r"^Legends", "to": "moonah-legends"}]},
        {"id": "moonah-legends", "part_of": "moonah-links"}, {"id": "other"}]
got = apply_splits([{"course": "moonah-links", "group": "Open Course - 18 Holes", "tee": "1st Tee"},
                    {"course": "moonah-links", "group": "Legends Course - 18 Holes", "tee": "1st Tee"},
                    {"course": "moonah-links", "group": "Trackman", "tee": "Trackman"},
                    {"course": "other", "group": "Legends", "tee": ""}], club)
assert [r["course"] for r in got] == ["moonah-links", "moonah-legends", "other"], got
assert with_parts(["moonah-links", "other"], club) == ["moonah-links", "moonah-legends", "other"]
print("split tests passed")

from build_feed import _PASS
assert _PASS.search("Annual Pass Booking") and _PASS.search("Pass Holders") and not _PASS.search("Twilight Passport")
print("pass rate tests passed")

from build_feed import local_time
assert local_time(utc(2026, 11, 5, 20, 0), "qld") == dt.datetime(2026, 11, 6, 6, 0)  # Brisbane has no daylight saving
assert local_time(utc(2026, 11, 5, 20, 0), "vic") == dt.datetime(2026, 11, 6, 7, 0)
assert local_time(utc(2026, 11, 5, 22, 0), "wa") == dt.datetime(2026, 11, 6, 6, 0)  # Perth is UTC+8 all year
assert local_time(utc(2026, 11, 5, 20, 0), "sa") == dt.datetime(2026, 11, 6, 6, 30)  # Adelaide in summer is UTC+10:30
assert local_time(utc(2026, 6, 5, 20, 0), "sa") == dt.datetime(2026, 6, 6, 5, 30)  # and UTC+9:30 in winter
assert local_time(utc(2026, 11, 5, 20, 0), "tas") == dt.datetime(2026, 11, 6, 7, 0)
assert local_time(utc(2026, 11, 5, 20, 0), "act") == dt.datetime(2026, 11, 6, 7, 0)
assert local_time(utc(2026, 11, 5, 20, 0), "nt") == dt.datetime(2026, 11, 6, 5, 30)  # Darwin has no daylight saving  # Hobart keeps Sydney's time
print("local time tests passed")

# Chronogolf: one answer per party size; full, restricted and frozen times are left out, and the
# reader works out each time's open spots from which party sizes can still book it.
import json, build_feed as bf
def cg(tm, full=False, restr=(), frozen=False, fee=43.0, date="2026-11-14"):
    t = {"start_time": tm, "date": date, "out_of_capacity": full, "restrictions": list(restr), "frozen": frozen}
    if fee is not None: t["green_fees"] = [{"green_fee": fee}]
    return t
one = [cg("05:30"), cg("05:37"), cg("05:45"), cg("06:00", full=True), cg("06:07", restr=["no adults"]), cg("06:15", frozen=True), cg("06:22", fee=None), cg("06:30", date="2026-11-15")]
assert bf.parse_chronogolf(json.dumps(one), "2026-11-14") == {"05:30": 43.0, "05:37": 43.0, "05:45": 43.0}
answers = {1: one, 4: [cg("05:30"), cg("05:37", full=True), cg("05:45", full=True)],
           2: [cg("05:30"), cg("05:37"), cg("05:45", full=True)], 3: [cg("05:30"), cg("05:37", full=True)]}
real_fetch = bf.fetch
bf.fetch = lambda url: json.dumps(answers[url.count("affiliation_type_ids")])
try:
    import datetime
    c = {"id": "albert-park", "facility_id": 15748, "resource_id": 18100, "rate_id": 64772, "book_url": "https://example/#?date={date}"}
    rows = bf.collect_chronogolf(c, datetime.date(2026, 11, 14), 0, 0)
finally:
    bf.fetch = real_fetch
assert [(r["time"], r["spots"], r["price"], r["holes"]) for r in rows] == [("05:30", 4, 43.0, 18), ("05:37", 2, 43.0, 18), ("05:45", 1, 43.0, 18)], rows
assert rows[0]["url"].endswith("#?course_id=18100&nb_holes=18&date=2026-11-14"), rows[0]["url"]
print("chronogolf tests passed")

# Release log: a batch of new times on a date an earlier read covered is a release, timed between
# that read and now; a few new times (cancellations) or a date that's only just in view are not.
U = datetime.timezone.utc
now = datetime.datetime(2026, 11, 15, 9, 0, tzinfo=U)
cs = [{"id": "wakehurst"}, {"id": "cammeray"}, {"id": "rosebud-north", "part_of": "rosebud"}, {"id": "rosebud"}]
row = lambda c, d, t: {"course": c, "date": d, "time": t}
prev = {("wakehurst", "2026-11-20"): {("07:00", "", "")}, ("cammeray", "2026-11-20"): {("07:00", "", "")}}
near_read = {"wakehurst": "2026-11-15T08:30:00+00:00", "cammeray": "2026-11-15T08:30:00+00:00", "rosebud": "2026-11-15T08:30:00+00:00"}
far_read = {"wakehurst": "2026-11-15T03:00:00+00:00"}
rows = [row("wakehurst", "2026-11-20", t) for t in ("07:00", "07:08", "07:16", "07:24", "07:32")]       # 4 new: a release
rows += [row("cammeray", "2026-11-20", t) for t in ("07:00", "07:08", "07:16")]                          # 2 new: cancellations
rows += [row("wakehurst", "2026-12-01", t) for t in ("06:00", "06:08", "06:16", "06:24")]                # a new later date
rows += [row("wakehurst", "2026-12-14", t) for t in ("06:00", "06:08", "06:16", "06:24")]                # only just in view
rows += [row("rosebud-north", "2026-11-18", t) for t in ("06:00", "06:08", "06:16", "06:24")]            # a split-off course
got = bf.find_releases(rows, {"wakehurst", "cammeray", "rosebud"}, prev, near_read, far_read, cs, now=now)
assert [(e["c"], e["d"], e["n"], e["new"], e["since"][11:16]) for e in got] == [
    ("rosebud-north", "2026-11-18", 4, True, "08:30"), ("wakehurst", "2026-11-20", 4, False, "08:30"),
    ("wakehurst", "2026-12-01", 4, True, "03:00")], got
assert bf.find_releases(rows, {"cammeray"}, prev, near_read, far_read, cs, now=now) == []  # only clubs read this run
print("release log tests passed")
# Times that come back within a day of being seen (the sheet hid them for a while) aren't a release.
peak = {"wakehurst": {"2026-11-20": [5, "2026-11-15T02:00+00:00"]}}
got = bf.find_releases(rows, {"wakehurst"}, prev, near_read, far_read, cs, peak, now=now)
assert [(e["c"], e["d"]) for e in got] == [("wakehurst", "2026-12-01")], got
assert peak["wakehurst"]["2026-11-20"] == [5, "2026-11-15T09:00+00:00"] and peak["wakehurst"]["2026-12-01"][0] == 4, peak
print("release peak tests passed")
# Peeking past the 4 weeks: only clubs whose times reach the edge, starting the day after their furthest date.
today = datetime.date(2026, 11, 15)
pcs = [{"id": "wakehurst", "platform": "miclub", "enabled": True, "host": "w"}, {"id": "cammeray", "platform": "miclub", "enabled": True, "host": "c"},
       {"id": "leura", "platform": "teeitup", "enabled": True, "host": "l"}, {"id": "rosebud", "platform": "miclub", "enabled": True, "host": "r"},
       {"id": "rosebud-north", "platform": "miclub", "enabled": True, "host": "r", "part_of": "rosebud"},
       {"id": "far-out", "platform": "golfnow", "enabled": True, "host": "g"}]
seen = {("wakehurst", "2026-12-13"): set(), ("cammeray", "2026-12-01"): set(), ("leura", "2026-12-13"): set(),
        ("rosebud-north", "2026-12-14"): set(), ("far-out", "2027-01-14"): set()}
beyond = {"read": {"rosebud": ["2026-11-15T08:00+00:00", "x", "y"]}, "times": {}}
plan, order = bf.peek_plan(pcs, today, seen, beyond)
assert plan == {"wakehurst": (29, 31), "rosebud": (30, 32)} and order == ["wakehurst", "rosebud"], (plan, order)
# A peek that finds a new date is kept; the next run sees more on it and logs that as a release.
bf.keep_peeks(beyond, [row("wakehurst", "2026-12-14", "06:00")], ["wakehurst"], plan, pcs, today, now=now)
assert beyond["times"] == {"wakehurst": {"2026-12-14": [["06:00", "", ""]]}} and beyond["read"]["wakehurst"] == ["2026-11-15T09:00+00:00", "2026-12-14", "2026-12-16"], beyond
later = now + datetime.timedelta(minutes=15)
prevb = bf.beyond_slots(beyond)
rows = [row("wakehurst", "2026-12-14", t) for t in ("06:00", "06:08", "06:16", "06:24", "06:32")] + [row("wakehurst", "2026-12-17", t) for t in ("06:00", "06:08", "06:16", "06:24")]
got = bf.find_releases(rows, {"wakehurst"}, prevb, {}, {}, pcs, now=later, peek_read=beyond["read"])
assert [(e["d"], e["n"], e["since"][11:16]) for e in got] == [("2026-12-14", 4, "09:00")], got  # 12-17 wasn't peeked before
print("peek tests passed")
