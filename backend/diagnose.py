"""Run from the project folder:  python backend/diagnose.py
Checks each MiClub club that returned no tee times and reports why, without writing anything."""
import os, sys, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_feed as b

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
courses = json.load(open(os.path.join(ROOT, "data", "courses.json"), encoding="utf-8"))
feed = json.load(open(os.path.join(ROOT, "site", "tee-times.json"), encoding="utf-8"))
have = {t["course"] for t in feed["times"]}
today = b.dt.date.today()
print("User agent:", b.UA)
print("Clubs with no tee times:\n")
for c in courses:
    if c.get("platform") != "miclub" or not c.get("enabled") or c["id"] in have:
        continue
    url = b.miclub_calendar_url(c, today.isoformat())
    print(f"== {c['id']}  ({c['host']}, bookingResourceId={c['resource_id']})")
    try:
        html = b.fetch(url)
    except Exception as e:
        print(f"   could not fetch: {type(e).__name__}: {e}\n")
        continue
    title = re.search(r"<title>([^<]*)</title>", html)
    print("   page title:", (title.group(1).strip() if title else "none"), "| bytes:", len(html))
    print("   captcha on:", bool(re.search(r"publicCaptchaEnabled\s*=\s*true", html)))
    try:
        groups = b.parse_miclub_calendar(html)
        print("   fee groups found:", len(groups), "| days with prices:", sum(len(g["prices"]) for g in groups))
        for g in groups[:4]:
            print("     -", g["label"], g["fee_group_id"], len(g["prices"]), "days")
    except Exception as e:
        print("   calendar parse:", type(e).__name__, e)
    os.makedirs(os.path.join(ROOT, "fixtures"), exist_ok=True)
    with open(os.path.join(ROOT, "fixtures", f"debug-{c['id']}.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    i = html.find("items-wrapper")
    if i >= 0:
        print("   first cells:", re.sub(r"\s+", " ", html[i:i + 4000])[:900])
    ids = sorted(set(re.findall(r"bookingResourceId=(\d+)", html)))
    if ids:
        print("   booking IDs mentioned on page:", ", ".join(ids[:8]))
    print()
