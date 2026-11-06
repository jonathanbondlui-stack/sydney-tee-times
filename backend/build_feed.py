#!/usr/bin/env python3
"""Builds site/tee-times.json from clubs' public guest timesheet pages.

Polite by design: checks robots.txt, identifies itself, max 1 request/second per
host, and skips any course marked enabled=false in data/courses.json.

Usage:
  python backend/build_feed.py                      # build the feed for the next 7 days
  python backend/build_feed.py --calendar page.html     # test the calendar parser on a saved page
  python backend/build_feed.py --timesheet page.html --course moore-park --date 2026-11-07
"""
import argparse, json, os, sys, threading, time, datetime as dt
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
KEEP_HOURS = 12  # how long a club's last good times stand in when its refresh fails

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

def fetch(url, headers=None, data=None):
    if "@" not in UA or "YOUR_EMAIL_HERE" in UA:
        raise PermissionError("TEE_UA has no contact email, so not fetching")
    ok, reason = allowed(url)
    if not ok:
        raise PermissionError(f"{reason}")
    host = urlparse(url).netloc
    wait = MIN_GAP - (time.time() - _last.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, data=data, headers={**(headers or {}), "User-Agent": UA})
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
    # Some clubs (such as Tanilba Bay) leave every fee at $0 and charge at the counter, so $0 means "not shown".
    return [{"price": float(p.replace(",", "")) or None, "label": unescape(l).strip()} for p, l in found]

_DISC = re.compile(r"\bdisc golf\b", re.I)
_LIMITED = {"Juniors": re.compile(r"\bjuniors?\b|\bjnr\b|\bunder\s*\d|\bu\d\d\b|\bchild|\bschool\b", re.I),
            "Seniors": re.compile(r"\bseniors?\b|\bpension", re.I),
            "Students": re.compile(r"\bstudents?\b", re.I),
            "Concession": re.compile(r"\bconcession", re.I),
            "Members' guests": re.compile(r"\bmembers?'?s?\s+guests?\b", re.I),
            # rates for members of a partner club, such as "Wests Member 18 Holes" at Port Kembla or "DLC Member" at The Grange
            "Partner club members": re.compile(r"\b(?:wests|dlc|rsl|leagues)\s+members?\b", re.I)}

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

TEEITUP_API = "https://phx-api-be-east-1b.kenna.io"
_teeitup_lock = threading.Lock()  # every TeeItUp club shares one host, so they take turns

def sydney_time(utc):
    """Sydney local time for a UTC datetime. Daylight saving runs from the first Sunday of October to the first Sunday of April."""
    def change(month):  # both changes happen at 16:00 UTC on the Saturday before
        first = dt.date(utc.year, month, 1)
        sunday = first + dt.timedelta(days=(6 - first.weekday()) % 7)
        return dt.datetime(sunday.year, sunday.month, sunday.day, tzinfo=dt.timezone.utc) - dt.timedelta(hours=8)
    standard = change(4) <= utc < change(10)
    return (utc + dt.timedelta(hours=10 if standard else 11)).replace(tzinfo=None)

def parse_teeitup(text, course, date):
    """Parse a TeeItUp tee time response. Each rate at a time becomes one row, as with Quick18.

    TeeItUp prices are per player. A rate for a set group, such as "2 Player Promotion",
    is stored as the group's total, because that's how the site reads package rates.
    """
    alias = course["host"].split(".")[0]
    url = f"https://{course['host']}/?" + urlencode({"course": course["facility_id"], "date": date})
    rows = []
    for day in json.loads(text):
        for t in day.get("teetimes", []):
            when = sydney_time(dt.datetime.fromisoformat(t["teetime"].replace("Z", "+00:00")))
            if when.date().isoformat() != date or not t.get("maxPlayers"):
                continue
            fees = []
            for r in t.get("rates", []):
                each = r.get("greenFeeWalking", r.get("greenFeeCart"))
                promo = r.get("promotion") or {}  # a hot deal's real price; its listed fee is a made-up "was" price
                each = promo.get("greenFeeWalking", promo.get("greenFeeCart", each))
                if each is None or re.search(r"member", r["name"], re.I):
                    continue
                party = min(r.get("allowedPlayers") or [1])
                if party > t["maxPlayers"]:
                    continue
                label = r["name"] + (" with cart" if "greenFeeWalking" not in r else "")
                if party > 1 and not re.search(rf"{party}\s*players?", label, re.I):
                    label += f" ({party} players)"
                fees.append({"price": each / 100 * party, "label": label, "holes": r.get("holes")})
            rate_list = [{"price": f["price"], "label": f["label"]} for f in fees]
            for f in fees:
                rows.append({"course": course["id"], "date": date, "time": when.strftime("%H:%M"), "holes": f["holes"],
                             "price": f["price"], "spots": t["maxPlayers"], "label": f["label"], "only": "", "group": "",
                             "tee": "Back 9" if t.get("backNine") else "", "min_players": t.get("minPlayers", 1),
                             "url": url, "fees": rate_list})
    return rows

def collect_teeitup(c, today, first=0, last=DAYS):
    """Collect tee times from first to last days ahead. Each date is one request."""
    rows = []
    for ahead in range(first, last + 1):
        d = (today + dt.timedelta(days=ahead)).isoformat()
        q = urlencode({"date": d, "facilityIds": c["facility_id"]})
        with _teeitup_lock:
            text = fetch(f"{TEEITUP_API}/v2/tee-times?{q}", {"x-be-alias": c["host"].split(".")[0]})
        rows.extend(parse_teeitup(text, c, d))
    return rows

GOLFNOW_SEARCH = "https://www.golfnow.com.au/api/tee-times/tee-time-search-results"
_golfnow_lock = threading.Lock()  # every GolfNow club shares one host, so they take turns
_PLAYER_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4}

def golfnow_players(rule):
    """Group sizes a GolfNow player rule allows, such as OneTwo -> [1, 2] or TwoFour -> [2, 4]."""
    if rule == "Any":
        return [1, 2, 3, 4]
    sizes = [_PLAYER_WORDS[w] for w in re.findall(r"[A-Z][a-z]+", rule or "") if w in _PLAYER_WORDS]
    if not sizes:
        raise ValueError(f"unrecognised GolfNow player rule: {rule!r}")
    return sizes

def parse_golfnow(text, course, date):
    """Parse a GolfNow search response. Each rate at a time becomes one row.

    Prices are per player and leave out any booking fee. A rate for a set group is
    stored as the group's total, because that's how the site reads package rates.
    """
    results = json.loads(text).get("ttResults")
    if results is None:
        raise ValueError("GolfNow response has no results section")
    rows = []
    for t in results.get("teeTimes") or []:
        when = t["time"]["date"]  # already local time, despite the +00:00
        if when[:10] != date:
            continue
        for r in t.get("teeTimeRates") or []:
            name = r.get("rateName") or ""
            each = r["singlePlayerPrice"]["greensFees"]["value"]
            if not each or r.get("isHotDealHidden") or re.search(r"member", name, re.I):
                continue
            sizes = golfnow_players(r.get("playerRule") or t.get("playerRule"))
            party = min(sizes)
            label = name + (" with cart" if r.get("isCartIncluded") else "")
            if party > 1 and not re.search(rf"{party}\s*players?", label, re.I):
                label += f" ({party} players)"
            _, only = headline_fee([{"price": each, "label": label}])
            rows.append({"course": course["id"], "date": date, "time": when[11:16], "holes": r.get("holeCount"),
                         "price": each * party, "spots": max(sizes), "label": label, "only": only, "group": "", "tee": "",
                         "min_players": party, "url": "https://www.golfnow.com.au" + r["detailUrl"],
                         "fees": [{"price": each, "label": label}]})
    return rows

def collect_golfnow(c, today, first=0, last=DAYS):
    """Collect tee times from first to last days ahead. A search only returns one length of round, so each date takes two."""
    rows, seen = [], set()
    for ahead in range(first, last + 1):
        day = today + dt.timedelta(days=ahead)
        for holes in ("Eighteen", "Nine"):
            body = {"pageSize": 30, "teeTimeCount": 10, "pageNumber": 0, "date": day.strftime("%b %d %Y"), "sortBy": "Date",
                    "sortByRollup": "Date.MinDate", "sortDirection": 0, "priceMin": 0, "priceMax": 10000, "players": 0, "timePeriod": "Any",
                    "timeMin": 10, "timeMax": 42, "holes": holes, "facilityType": "GolfCourse", "radius": 100,
                    "facilityId": c["facility_id"], "facilityIds": [], "searchType": "Facility", "view": "Grouping", "rateType": "all"}
            with _golfnow_lock:
                text = fetch(GOLFNOW_SEARCH, {"Content-Type": "application/json", "Accept": "application/json"}, json.dumps(body).encode())
            for r in parse_golfnow(text, c, day.isoformat()):
                key = (r["date"], r["time"], r["holes"], r["price"], r["label"])
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
    return rows

COLLECTORS = {"miclub": collect_miclub, "quick18": collect_quick18, "teeitup": collect_teeitup, "golfnow": collect_golfnow}

def build(courses, today, first, last):
    """Collect every live club for this date range. Returns (rows, failures, clubs tried)."""
    out, failures, tried = [], [], 0
    live = [c for c in courses if c.get("enabled") and c["platform"] in COLLECTORS]
    # Each worker handles one club, so a club still gets at most one request per MIN_GAP.
    # GolfNow clubs do share a host, and take turns through _golfnow_lock instead.
    assert len({(c["host"], c.get("facility_id")) for c in live}) == len(live), "two courses share a host"
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        jobs = [(c, pool.submit(COLLECTORS[c["platform"]], c, today, first, last)) for c in live]
    for c, job in jobs:
        tried += 1
        try:
            out.extend(job.result())
        except CaptchaRequired as e:
            print(f"SKIP {c['id']}: {e}", file=sys.stderr); tried -= 1
        except Exception as e:
            failures.append((c["id"], e))
    for cid, e in failures[:20]:
        print(f"FAIL {cid}: {e}", file=sys.stderr)
    return out, failures, tried

def carry_over(name, rows, failed, now=None):
    """Add each failed club's times from the last published feed, so one bad refresh doesn't
    make it vanish. Only times not yet passed are kept, and only for KEEP_HOURS after they were
    last read. Returns {course id: when its times were read} for the clubs carried over."""
    now = now or dt.datetime.now().astimezone()
    try:
        with open(os.path.join(ROOT, "site", name)) as fh:
            prev = json.load(fh)
    except (OSError, ValueError):
        return {}
    today, clock = now.date().isoformat(), now.strftime("%H:%M")
    kept = {}
    for cid in failed:
        read_at = prev.get("kept", {}).get(cid, prev.get("generated_at"))
        try:
            if (now - dt.datetime.fromisoformat(read_at)).total_seconds() > KEEP_HOURS * 3600:
                continue
        except (TypeError, ValueError):
            continue
        old = [r for r in prev.get("times", []) if r.get("course") == cid
               and (r["date"] > today or (r["date"] == today and r["time"] >= clock))]
        if old:
            rows.extend(old)
            kept[cid] = read_at
            print(f"KEPT {len(old)} earlier times for {cid}, read {read_at}", file=sys.stderr)
    return kept

def write_feed(name, rows, kept=None):
    path = os.path.join(ROOT, "site", name)
    feed = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "times": rows}
    if kept:
        feed["kept"] = kept
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
    kept = carry_over("tee-times.json", out, [cid for cid, _ in failures])
    write_feed("tee-times.json", out, kept)
    print(f"Wrote {len(out)} tee times from {tried - len(failures)} clubs.")
    if far_due():
        out, failures, tried = build(courses, today, DAYS + 1, FAR_DAYS)
        if not out or len(failures) > tried * 0.5:
            print("Too little data or too many failures for later dates. Keeping the previous far feed.", file=sys.stderr)
            return
        kept = carry_over(FAR_FEED, out, [cid for cid, _ in failures])
        write_feed(FAR_FEED, out, kept)
        print(f"Wrote {len(out)} later tee times from {tried - len(failures)} clubs.")

if __name__ == "__main__":
    main()
