"""Run: python backend/counts.py   Shows tee times per club, and clubs that are switched on but have none."""
import json, os, collections
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cs = json.load(open(os.path.join(R, "data", "courses.json"), encoding="utf-8"))
f = json.load(open(os.path.join(R, "site", "tee-times.json"), encoding="utf-8"))
n = collections.Counter(t["course"] for t in f["times"])
name = {c["id"]: c["name"] for c in cs}
print(f"{len(f['times'])} tee times at {len(n)} clubs\n")
for k, v in n.most_common():
    print(f"{v:5}  {name.get(k, k)}")
none = [c["name"] for c in cs if c.get("enabled") and c["id"] not in n]
print("\nSwitched on but NO tee times:", ", ".join(none) if none else "none")
print("Not on MiClub (listed in 'Other Sydney courses'):", sum(1 for c in cs if not c.get("enabled")))
