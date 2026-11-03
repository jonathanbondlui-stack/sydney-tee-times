"""Run from the project folder:  python backend/probe.py
Looks for more Sydney clubs that use MiClub public booking, adds every candidate course to
data/courses.json (and site/courses.json), and switches on the ones that work.
Safe to re-run. Makes a backup first. Polite: identifies itself, obeys robots.txt, 1 request/sec/host."""
import os, sys, json, shutil, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_feed as b

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)
courses = json.load(open(P("data", "courses.json"), encoding="utf-8"))
cands = json.load(open(P("data", "candidates.json"), encoding="utf-8"))
shutil.copy(P("data", "courses.json"), P("data", "courses.backup.json"))
have = {c["id"]: c for c in courses}
today = dt.date.today().isoformat()
print("User agent:", b.UA, "\n")
found = 0
for cand in cands:
    hosts = cand.pop("probe_hosts", [])
    existing = have.get(cand["id"])
    if existing and existing.get("enabled"):
        continue
    hit = None
    for h in hosts:
        trial = dict(cand, host=h, resource_id=3000000)
        try:
            html = b.fetch(b.miclub_calendar_url(trial, today))
            if b.re.search(r"publicCaptchaEnabled\s*=\s*true", html):
                hit = (h, "captcha"); break
            groups = b.parse_miclub_calendar(html)
            if sum(len(g["prices"]) for g in groups) > 0:
                hit = (h, "ok"); break
        except Exception:
            continue
    c = existing or cand
    if hit and hit[1] == "ok":
        c.update(status="online", platform="miclub", host=hit[0], resource_id=3000000, enabled=True)
        c.pop("note", None)
        found += 1
        print(f"FOUND  {cand['name']}  ->  {hit[0]}")
    elif hit:
        c["note"] = "Uses MiClub but requires a captcha, so times can't be shown. Book on the club's website."
        print(f"CAPTCHA {cand['name']}  ->  {hit[0]}")
    else:
        print(f"none   {cand['name']}")
    if not existing:
        courses.append(c); have[c["id"]] = c
json.dump(courses, open(P("data", "courses.json"), "w", encoding="utf-8"), indent=1)
shutil.copy(P("data", "courses.json"), P("site", "courses.json"))
print(f"\nDone. {found} new MiClub clubs switched on. {len(courses)} courses in the directory.")
print("Next: run  python backend/build_feed.py  to pull their tee times.")
