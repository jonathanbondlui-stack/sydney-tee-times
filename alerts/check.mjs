// Runs after each refresh is published (see .github/workflows/refresh.yml). For every saved search
// it reads the live times, finds the ones that are new since last time, and sends one ntfy message.
// Needs ALERTS_KEY, the password the alert service knows as CHECK_KEY.
import { REGIONS, SITE, unpackFeed, parseSearch, matches, describe, today, hourAt, addDays, dayName, line } from "./src/match.js";

const API = process.env.ALERTS_API || "https://tee-time-alerts.teetimefinder.workers.dev";
const KEY = (process.env.ALERTS_KEY || "").trim();
const QUIET = (process.env.QUIET || "22-6").split("-").map(Number); // no messages 10pm to 6am at the course; they wait until morning
const MAX_LINES = 8;
if (!KEY) { console.log("No ALERTS_KEY, so no alerts checked."); process.exit(0); }
const auth = { Authorization: `Bearer ${KEY}` };

const cache = {};
const get = n => cache[n] ??= fetch(SITE + n + "?t=" + Date.now(), { cache: "no-store" }).then(r => r.ok ? r.json() : null).catch(() => null);
async function timesFor(region, dates) {
  const far = dates.some(d => d > addDays(today(REGIONS[region].tz), 7));
  let times = [];
  for (const n of [`tee-times-${region}.json`, ...(far ? [`tee-times-far-${region}.json`] : [])]) {
    const j = await get(n);
    if (!j) return null; // a feed didn't load: try next time rather than alert on half the times
    times = times.concat(unpackFeed(j));
  }
  return times;
}
async function notify(w, title, lines) {
  const body = {
    topic: w.topic, title, message: lines.join("\n"), tags: ["golf"], click: SITE + "?" + w.q,
    actions: [{ action: "view", label: "See times", url: SITE + "?" + w.q, clear: true },
              { action: "http", label: "Stop this alert", url: `${w.base}/stop/${w.id}`, method: "POST", clear: true }],
  };
  const r = await fetch("https://ntfy.sh/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) console.log(`ntfy ${r.status} for ${w.id}: ${(await r.text()).slice(0, 200)}`);
  return r.ok;
}
const record = (w, body) => fetch(`${API}/seen/${w.id}`, { method: "POST", headers: { ...auth, "Content-Type": "application/json" }, body: JSON.stringify(body) });

const r = await fetch(`${API}/all`, { headers: auth });
if (!r.ok) { console.log(`Couldn't read saved searches (${r.status}).`); process.exit(0); }
const watches = await r.json(), courses = await get("courses.json"), results = {};
for (const w of watches) {
  try {
    const R = REGIONS[w.region], s = parseSearch(w.q), now = today(R.tz);
    if (!s || s.dates.every(d => d < now)) { results[w.id] = "ended"; continue; }
    const h = hourAt(R.tz);
    if (QUIET[0] !== QUIET[1] && (h >= QUIET[0] || h < QUIET[1])) { results[w.id] = "quiet"; continue; }
    const times = await timesFor(w.region, s.dates);
    if (!times || !courses) { results[w.id] = "no feed"; continue; }
    const found = matches(s, times, courses, w.region), seen = new Set(w.seen), fresh = found.filter(m => !seen.has(m.key));
    // Remember everything matching now plus what was seen before, so a time that drops out for one
    // refresh (a club's site having a bad moment) doesn't alert again when it comes back.
    const keep = [...new Set([...w.seen, ...found.map(m => m.key)])].filter(k => k.split("|")[1] >= now);
    if (!fresh.length) {
      if (keep.length !== w.seen.length) await record(w, { seen: keep });
      results[w.id] = "none"; continue;
    }
    const lines = fresh.slice(0, MAX_LINES).map(m => line(m, s.dates.length > 1));
    if (fresh.length > MAX_LINES) lines.push(`and ${fresh.length - MAX_LINES} more`);
    const title = `${fresh.length} new tee ${fresh.length == 1 ? "time" : "times"} for ${s.dates.map(dayName).join(", ")}`;
    if (await notify(w, title, lines)) {
      await record(w, { seen: keep, sent: (w.sent || 0) + 1, last: new Date().toISOString() });
      results[w.id] = `sent ${fresh.length}`;
    } else results[w.id] = "ntfy failed";
  } catch (e) { results[w.id] = "error " + e.message; }
}
console.log(`${watches.length} saved searches:`, JSON.stringify(results));
