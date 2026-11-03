"""Run: python backend/patch_courses.py   Adds booking details found for a few more courses. Safe to re-run."""
import json, os, shutil
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(R, *a)
shutil.copy(P("data", "courses.json"), P("data", "courses.before-patch.json"))
d = json.load(open(P("data", "courses.json"), encoding="utf-8"))
patch = {
 "marrickville": dict(phone="(02) 9558 6862", cta="Book online (TeeItUp)", book_url="https://marrickville-golf-club.book.teeitup.com/",
     note="Books through TeeItUp and GolfNow. Times aren't shown here yet."),
 "botany": dict(phone="(02) 9316 4930", note="Pay and play. No bookings: turn up in opening hours, first come first served. Run by Bayside Council."),
 "hurstville": dict(cta="Visit Hurstville Golf", book_url="https://hurstvillegolf.com.au/", note="Council-run. See the course website to book."),
 "canterbury": dict(phone="(02) 9707 9000", note="Nine-hole council course (Canterbury Bankstown). The number is the council's main line; booking method not confirmed."),
 "woodville": dict(cta="Cumberland Council golf page", book_url="https://cumberland.nsw.gov.au/golf", note="Council-run. Booking method not confirmed."),
 "auburn": dict(cta="Cumberland Council golf page", book_url="https://cumberland.nsw.gov.au/golf", note="Council-run. Booking method not confirmed."),
}
n = 0
for c in d:
    if c["id"] in patch and not c.get("enabled"):
        c.update(patch[c["id"]]); n += 1
json.dump(d, open(P("data", "courses.json"), "w", encoding="utf-8"), indent=1)
shutil.copy(P("data", "courses.json"), P("site", "courses.json"))
print(f"Updated {n} courses.")
