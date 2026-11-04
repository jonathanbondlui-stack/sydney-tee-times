#!/usr/bin/env python3
"""Builds site/tee-times.json from clubs' public guest timesheet pages.

Polite by design: checks robots.txt, identifies itself, max 1 request/second per
host, and skips any course marked enabled=false in data/courses.json.

Usage:
  python backend/build_feed.py                      # build the feed for the next 7 days
  python backend/build_feed.py --calendar page.html     # test the calendar parser on a saved page
  python backend/build_feed.py --timesheet page.html --course moore-park --date 2026-11-07
"""
import argparse, json, os, sys, time, datetime as dt
import urllib.request, urllib.robotparser, urllib.error
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from urllib.parse import urlencode, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = os.environ.get("TEE_UA") or "TeeSheetBot/0.1 (+mailto:YOUR_EMAIL_HERE)"
DAYS = int(os.environ.get("TEE_DAYS", "7"))
MIN_GAP = 1.0  # seconds between requests to the same host
WORKERS = 8  # clubs read at the same time
CAL_STEP = 6  # days shown on one MiClub calendar page
FAR_FEED = "tee-times-far.json"
FAR_DAYS = int(os.environ.get("TEE_FAR_DAYS", "28"))  # how far ahead the far feed goes
FAR_HOURS = float(os.environ.get("TEE_FAR_HOURS", "6"))  # how often to rebuild the far feed

_robots, _last = {}, {}

def load_robots(host):
    """Fetch robots.txt with our own identifying user agent. Returns (parser or None, reason, text)."""
    url = f"https://{host}/robots.txt"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode("utf-8", "replace")
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(text.splitlines())
        return rp, f"robots.txt read ({len(text)} bytes)", text
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            rp = urllib.robotparser.RobotFileParser()
            rp.parse([])
            return rp, f"no robots.txt (HTTP {e.code}), so nothing is disallowed", ""
        return None, f"robots.txt request returned HTTP {e.code}", ""
    except Exception as e:
        return None, f"could not read robots.txt ({type(e).__name__}: {e})", ""

def allowed(url):
    """Returns (ok, reason). When robots.txt can't be read we stay out, to be safe."""
    host = urlparse(url).netloc
    if host not in _robots:
        _robots[host] = load_robots(host)
    rp, reason, _ = _robots[host]
    if rp is None:
        return False, reason
    if rp.can_fetch(UA, url):
        return True, reason
    return False, "robots.txt disallows this path for our user agent"

def fetch(url):
    if "@" not in UA or "YOUR_EMAIL_HERE" in UA:
        raise PermissionError("TEE_UA has no contact email, so not fetching")
    ok, reason = allowed(url)
    if not ok:
        raise PermissionError(f"{reason}")
    host = urlparse(url).netloc
    wait = MIN_GAP - (time.time() - _last.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", "replace")
    finally:
        _last[host] = time.time()

import re

class CaptchaRequired(Exception):
    pass

def miclub_calendar_url(c, date):
    q = urlencode({"bookingResourceId": c["resource_id"], "selectedDate": date})
    return f"https://{c['host']}/guests/bookings/ViewPublicCalendar.msp?{q}"

def miclub_timesheet_url(c, date, fee_group_id):
    q = urlencode({"bookingResourceId": c["resource_id"], "selectedDate": date, "feeGroupId": fee_group_id})
    return f"https://{c['host']}/guests/bookings/ViewPublicTimesheet.msp?{q}"

_ROW = re.compile(r'<div class="row feeGroupRow[^"]*" data-feeid="(\d+)">(.*?)(?=<div class="row feeGroupRow|\Z)', re.S)
_CELL = re.compile(r'<div class="[^"]*\bcell\b[^"]*"[^>]*?redirectToTimesheet\(\'(\d+)\',\'([^\']+)\'\)[^>]*>(.*?)</div>', re.S)
def norm_date(s):
    """MiClub prints dates either as 2026-11-04 or 'Wed Nov 04 00:00:00 AEDT 2026'. Return ISO."""
    s = s.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    m = re.match(r"\w{3} (\w{3}) (\d{1,2}) [\d:]+ \w+ (\d{4})", s)
    if m:
        return dt.datetime.strptime(f"{m.group(2)} {m.group(1)} {m.group(3)}", "%d %b %Y").date().isoformat()
    raise ValueError(f"unrecognised MiClub date: {s!r}")

_PRICE = re.compile(r'<p class="price">\$([\d.,]+)</p>')

def parse_miclub_calendar(html):
    """Parse a MiClub public calendar page into fee groups.

    Returns [{"fee_group_id", "label", "holes", "prices": {"YYYY-MM-DD": price}}].
    Verified against Moore Park's page. Raises CaptchaRequired when the club has the
    public captcha switched on, because those pages can't be read without a human.
    """
    if re.search(r"publicCaptchaEnabled\s*=\s*true", html):
        raise CaptchaRequired("club has public captcha enabled")
    groups = []
    for fee_id, body in _ROW.findall(html):
        h3 = re.search(r"<h3>([^<]+)</h3>", body)
        label = h3.group(1).strip() if h3 else ""
        m = re.search(r"(\d+)\s*-?\s*holes?", label, re.I)
        prices = {}
        for _, day, inner in _CELL.findall(body):
            pm = _PRICE.search(inner)
            if pm:
                prices[norm_date(day)] = float(pm.group(1).replace(",", ""))
        groups.append({"fee_group_id": fee_id, "label": label,
                       "holes": int(m.group(1)) if m else None, "prices": prices})
    return groups

_TROW = re.compile(r'<div id="row-(\d+)" class="row row-time[^"]*"[^>]*>(.*?)(?=<div id="row-\d+" class="row row-time|<div id="no-rows"|\Z)', re.S)
_FEE = re.compile(r'<span class="price">\s*\$([\d.,]+)\s*</span>\s*([^<]*?)\s*</li>', re.S)
_FEE_POPOVER = re.compile(r'class="fee-applied[^>]*?data-content="([^"]*)"', re.S)
_POPOVER_LI = re.compile(r'<li>\s*([^<]*?)\s*\$([\d.,]+)\s*</li>', re.S)

def miclub_fees(body):
    """A row's fees. MiClub lists a few on the row, but tucks longer lists into a "Fees" popover."""
    found = [(p, l) for p, l in _FEE.findall(body)]
    if not found:
        pop = _FEE_POPOVER.search(body)
        if pop:
            found = [(p, l) for l, p in _POPOVER_LI.findall(unescape(pop.group(1)))]
    return [{"price": float(p.replace(",", "")), "label": unescape(l).strip()} for p, l in found]

_DISC = re.compile(r"\bdisc golf\b", re.I)
_LIMITED = {"Juniors": re.compile(r"\bjuniors?\b|\bjnr\b|\bunder\s*\d|\bu\d\d\b|\bchild|\bschool\b", re.I),
            "Seniors": re.compile(r"\bseniors?\b|\bpension", re.I),
            "Students": re.compile(r"\bstudents?\b", re.I),
            "Concession": re.compile(r"\bconcession", re.I)}

def limited_to(label):
    """Who a rate is limited to, by its name. Empty means anyone can book it."""
    return {who for who, pat in _LIMITED.items() if pat.search(label)}

def headline_fee(fees):
    """The price to show for a tee time, and who it is limited to when nobody else has a rate.

    MiClub lists rates in the club's own order, which sometimes starts with juniors or seniors.
    Returns (fee or None, "" or a label like "Juniors only").
    """
    if not fees:
        return None, ""
    golf = [f for f in fees if not _DISC.search(f["label"])]
    if not golf:
        return fees[0], "Disc golf only"
    for f in golf:
        if not limited_to(f["label"]):
            return f, ""
    who = set().union(*(limited_to(f["label"]) for f in golf))
    return golf[0], f"{who.pop()} only" if len(who) == 1 else "Concession only"

def parse_miclub_timesheet(html, course, date, group=None):
    """Parse a MiClub public timesheet page into tee times.

    Verified against Moore Park's 12-hole timesheet. Each row is one tee time with four
    slots; spots = slots marked available. Fully taken rows are left out.
    Returns [{course, date, time 'HH:MM', holes, price, spots, label, tee, min_players, fees}].
    """
    shown = re.search(r'<span class="fixtureDay">([^<]+)</span>', html)
    if shown:
        txt = shown.group(1).strip()
        try:
            page_date = dt.datetime.strptime(txt, "%d-%b-%Y").date().isoformat()
        except ValueError:
            page_date = norm_date(txt)
        if page_date != date:
            raise ValueError(f"page shows {page_date}, expected {date}")
    name = re.search(r'<h1 class="feeName">([^<]+)</h1>', html)
    hm = re.search(r"(\d+)\s*-?\s*holes?", name.group(1) if name else "", re.I)
    holes = int(hm.group(1)) if hm else (group or {}).get("holes")
    limits = {}
    lm = re.search(r"minimumBookingLimitJson\s*=\s*JSON\.parse\('([^']*)'\)", html)
    if lm:
        limits = json.loads(lm.group(1))
    rows = []
    for row_id, body in _TROW.findall(html):
        t = re.search(r"<h3>\s*([^<]+?)\s*</h3>", body)
        if not t:
            continue
        time24 = dt.datetime.strptime(t.group(1).strip(), "%I:%M %p").strftime("%H:%M")
        tee = re.search(r"<h4>\s*([^<]*?)\s*</h4>", body)
        fees = miclub_fees(body)
        spots = body.count("cell-available")
        if spots == 0:
            continue
        first, only = headline_fee(fees)
        first = first or {"price": None, "label": ""}
        rows.append({"course": course["id"], "date": date, "time": time24, "holes": holes,
                     "price": first["price"], "spots": spots, "label": first["label"], "only": only,
                     "group": (group or {}).get("label", ""),  # often the only place a group size or limit is named
                     "tee": tee.group(1) if tee else "", "min_players": int(limits.get(row_id, 1)),
                     "fees": fees})
    return rows

def collect_miclub(c, today, first=0, last=DAYS):
    """Collect tee times from first to last days ahead. A calendar page only shows about CAL_STEP days, so walk several."""
    rows, seen = [], set()
    start, end = (today + dt.timedelta(days=first)).isoformat(), (today + dt.timedelta(days=last)).isoformat()
    for ahead in range(first, last + 1, CAL_STEP):
        page = (today + dt.timedelta(days=ahead)).isoformat()
        for g in parse_miclub_calendar(fetch(miclub_calendar_url(c, page))):
            for d in g["prices"]:
                if not start <= d <= end or (g["fee_group_id"], d) in seen:
                    continue
                seen.add((g["fee_group_id"], d))
                url = miclub_timesheet_url(c, d, g["fee_group_id"])
                for r in parse_miclub_timesheet(fetch(url), c, d, g):
                    r.setdefault("url", url)
                    rows.append(r)
    return rows

def quick18_url(c, date):
    return f"https://{c['host']}/teetimes/searchmatrix?teedate={date.replace('-', '')}"

_Q_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
_Q_CELL = re.compile(r'<td class="matrixsched[^"]*">(.*?)</td>', re.S)

def parse_quick18(html, course, date):
    """Parse a Quick18 tee sheet page into tee times, with one row per public rate at each time.

    Verified against Lane Cove's pages. Member rates are left out, and concession rates are only
    listed in fees. Returns [] when the page has no tee sheet or shows a different date.
    """
    table = re.search(r'<table class="matrixTable".*?</table>', html, re.S)
    if not table:
        return []
    shown = re.search(r'class="matrixToday">.*?teedate=(\d{8})', html, re.S)
    if not shown:
        raise ValueError("Quick18 page doesn't show which date is selected")
    if shown.group(1) != date.replace("-", ""):
        return []
    rates = [r.strip() for r in re.findall(r'<th class="matrixHdrSched">(.*?)</th>', table.group(0), re.S)]
    rows = []
    for body in _Q_ROW.findall(table.group(0)[table.group(0).find("<tbody>"):]):
        t = re.search(r'class="mtrxTeeTimes">\s*(\d{1,2}:\d{2})\s*<div[^>]*>\s*(AM|PM)', body)
        players = re.search(r'class="matrixPlayers">(.*?)</td>', body, re.S)
        if not t or not players:
            continue
        time24 = dt.datetime.strptime(f"{t.group(1)} {t.group(2)}", "%I:%M %p").strftime("%H:%M")
        counts = [int(n) for n in re.findall(r"\d+", players.group(1))]
        fees = []
        for rate, cell in zip(rates, _Q_CELL.findall(body)):
            price = re.search(r'class="mtrxPrice">\$([\d.,]+)', cell)
            link = re.search(r'<a class="[^"]*teebutton[^"]*" href="([^"]+)"', cell)
            if price and link and not re.search(r"member", rate, re.I):
                fees.append({"price": float(price.group(1).replace(",", "")), "label": rate,
                             "url": f"https://{course['host']}{unescape(link.group(1))}"})
        for fee in fees:
            if re.search(r"concession", fee["label"], re.I):
                continue
            hm = re.search(r"(\d+)\s*-?\s*holes?", fee["label"], re.I)
            rows.append({"course": course["id"], "date": date, "time": time24, "holes": int(hm.group(1)) if hm else None,
                         "price": fee["price"], "spots": max(counts), "label": fee["label"], "tee": "",
                         "min_players": min(counts), "url": fee["url"],
                         "fees": [{"price": f["price"], "label": f["label"]} for f in fees]})
    return rows

def collect_quick18(c, today, first=0, last=DAYS):
    """Collect tee times from first to last days ahead. Each date is its own page."""
    rows = []
    for ahead in range(first, last + 1):
        d = (today + dt.timedelta(days=ahead)).isoformat()
        rows.extend(parse_quick18(fetch(quick18_url(c, d)), c, d))
    return rows

COLLECTORS = {"miclub": collect_miclub, "quick18": collect_quick18}

def build(courses, today, first, last):
    """Collect every live club for this date range. Returns (rows, failures, clubs tried)."""
    out, failures, tried = [], [], 0
    live = [c for c in courses if c.get("enabled") and c["platform"] in COLLECTORS]
    # Each worker handles one club, so a club still gets at most one request per MIN_GAP.
    assert len({c["host"] for c in live}) == len(live), "two courses share a host"
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        jobs = [(c, pool.submit(COLLECTORS[c["platform"]], c, today, first, last)) for c in live]
    for c, job in jobs:
        tried += 1
        try:
            out.extend(job.result())
        except CaptchaRequired as e:
            print(f"SKIP {c['id']}: {e}", file=sys.stderr); tried -= 1
        except Exception as e:
            failures.append(f"{c['id']}: {e}")
    for f in failures[:20]:
        print("FAIL", f, file=sys.stderr)
    return out, failures, tried

def write_feed(name, rows):
    path = os.path.join(ROOT, "site", name)
    feed = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "times": rows}
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(feed, fh)
    os.replace(tmp, path)

def far_due():
    """True when the far feed is missing or older than FAR_HOURS."""
    try:
        with open(os.path.join(ROOT, "site", FAR_FEED)) as fh:
            made = dt.datetime.fromisoformat(json.load(fh)["generated_at"])
    except (OSError, ValueError, KeyError):
        return True
    return (dt.datetime.now(dt.timezone.utc) - made).total_seconds() >= FAR_HOURS * 3600

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calendar", help="test the calendar parser on a saved page")
    ap.add_argument("--timesheet"); ap.add_argument("--course"); ap.add_argument("--date")
    ap.add_argument("--check-robots", metavar="HOST", help="show what a host's robots.txt says about us")
    a = ap.parse_args()
    if a.check_robots:
        rp, reason, text = load_robots(a.check_robots)
        print("User agent:", UA)
        print("Result:", reason)
        if text:
            print("--- robots.txt ---"); print("\n".join(text.splitlines()[:60])); print("--- end ---")
        if rp:
            for path in ("/guests/bookings/ViewPublicCalendar.msp?bookingResourceId=1&selectedDate=2026-11-03",
                         "/guests/bookings/ViewPublicTimesheet.msp?bookingResourceId=1&selectedDate=2026-11-03&feeGroupId=1"):
                print("allowed" if rp.can_fetch(UA, f"https://{a.check_robots}{path}") else "NOT allowed", path.split("?")[0])
        return
    courses = json.load(open(os.path.join(ROOT, "data", "courses.json")))
    by = {c["id"]: c for c in courses}

    if a.calendar:
        print(json.dumps(parse_miclub_calendar(open(a.calendar, encoding="utf-8").read()), indent=1)); return
    if a.timesheet:
        g = {"fee_group_id": "", "label": "", "holes": None, "prices": {}}
        print(json.dumps(parse_miclub_timesheet(open(a.timesheet, encoding="utf-8").read(), by[a.course], a.date, g), indent=1)); return

    today = dt.date.today()
    out, failures, tried = build(courses, today, 0, DAYS)
    if not out or len(failures) > tried * 0.5:
        print("Too little data or too many failures. Keeping the previous feed.", file=sys.stderr)
        sys.exit(1)
    write_feed("tee-times.json", out)
    print(f"Wrote {len(out)} tee times from {tried - len(failures)} clubs.")
    if far_due():
        out, failures, tried = build(courses, today, DAYS + 1, FAR_DAYS)
        if not out or len(failures) > tried * 0.5:
            print("Too little data or too many failures for later dates. Keeping the previous far feed.", file=sys.stderr)
            return
        write_feed(FAR_FEED, out)
        print(f"Wrote {len(out)} later tee times from {tried - len(failures)} clubs.")

if __name__ == "__main__":
    main()
