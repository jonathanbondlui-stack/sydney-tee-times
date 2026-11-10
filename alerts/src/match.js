// Which tee times a saved search matches. This mirrors the filters in site/index.html, so an alert
// finds the same times the site would show for that search. Keep the two in step.

export const REGIONS = {
  nsw: { la: -33.87, lo: 151.21, tz: "Australia/Sydney" },
  vic: { la: -37.81, lo: 144.96, tz: "Australia/Melbourne" },
  qld: { la: -27.47, lo: 153.03, tz: "Australia/Brisbane" },
  wa: { la: -31.95, lo: 115.86, tz: "Australia/Perth" },
};

const HOLES = /(\d+)\s*-?\s*holes?/i, NO_FINISH = /will not finish/i, ROUND_MINS = 255, SHORT_HOLES = /\b(\d+)H\b/i;
export const mins = t => { const [a, b] = t.split(":"); return +a * 60 + +b; };
const rateName = x => (x.label || "") + " " + (x.group || "");
const holesOf = x => {
  const m = HOLES.exec((x.label || "").replace(NO_FINISH, ""));
  if (m) return +m[1];
  if (x.holes != null) return x.holes;
  const g = SHORT_HOLES.exec(x.group || "");
  return g ? +g[1] : null;
};
const partyOf = x => { const m = /(\d)\s*(?:players?|persons?)\b/i.exec(rateName(x)); return m && +m[1] > 1 ? +m[1] : 1; };
const fullRound = (x, latest, need) => {
  const all = need || Math.min(18, (x.c && x.c.holes) || 18), h = holesOf(x);
  return !NO_FINISH.test(rateName(x)) && x.m <= latest + ROUND_MINS * (1 - all / 18) &&
    (h == null ? ((x.c && x.c.holes) || 18) >= all : h >= all);
};
export const km = (a, b, c, d) => {
  const r = Math.PI / 180, x = (d - b) * r * Math.cos((a + c) / 2 * r), y = (c - a) * r;
  return Math.sqrt(x * x + y * y) * 6371;
};
// Sunset in minutes after midnight in the region's time zone (NOAA's approximation, as on the site).
export const sunset = (ds, lat, lon, tz) => {
  const d = new Date(ds + "T00:00:00Z"), g = 2 * Math.PI * ((d - Date.UTC(d.getUTCFullYear(), 0, 0)) / 864e5 - 1) / 365, r = Math.PI / 180, la = lat * r;
  const eq = 229.18 * (.000075 + .001868 * Math.cos(g) - .032077 * Math.sin(g) - .014615 * Math.cos(2 * g) - .040849 * Math.sin(2 * g));
  const dec = .006918 - .399912 * Math.cos(g) + .070257 * Math.sin(g) - .006758 * Math.cos(2 * g) + .000907 * Math.sin(2 * g) - .002697 * Math.cos(3 * g) + .00148 * Math.sin(3 * g);
  const ha = Math.acos(Math.cos(90.833 * r) / (Math.cos(la) * Math.cos(dec)) - Math.tan(la) * Math.tan(dec)) / r, utc = 720 - 4 * (lon - ha) - eq;
  return mins(new Date(d.getTime() + utc * 6e4).toLocaleTimeString("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }));
};
export const unpackFeed = j => j.v !== 2 ? (j.times || []) : j.times.map(r => {
  const x = { only: "", group: "", tee: "", min_players: 1, ...r, url: j.urls[r.u] };
  delete x.u; delete x.f; if (x.url == null) delete x.url; return x;
});

// A saved search is the site's share link query: d (dates), at (name|lat|lon), players, holes, from, to, dist, price.
export function parseSearch(q) {
  const p = new URLSearchParams(q), at = (p.get("at") || "").split("|");
  const s = {
    dates: (p.get("d") || "").split(",").filter(d => /^\d{4}-\d{2}-\d{2}$/.test(d)),
    place: at[0] || "", la: +at[1], lo: +at[2],
    players: +(p.get("players") || 4), holes: p.get("holes") || "18",
    from: +(p.get("from") || 5), to: +(p.get("to") || 19), dist: +(p.get("dist") || 20), price: +(p.get("price") || 200),
  };
  if (!s.dates.length || s.dates.length > 7 || !s.place || !isFinite(s.la) || !isFinite(s.lo)) return null;
  if (![1, 2, 3, 4].includes(s.players) || !["0", "9", "18"].includes(s.holes)) return null;
  return s;
}

// The times a search matches, one entry per course and start time (the cheapest matching rate).
// Rates for one group only ("Juniors only", "Seniors only") are left out, so they never set off an alert.
export function matches(s, times, courses, region) {
  const R = REGIONS[region] || REGIONS.nsw, by = {}, late = {}, best = new Map();
  courses.forEach(c => { if ((c.region || "nsw") === region) by[c.id] = c; });
  s.dates.forEach(d => { late[d] = sunset(d, R.la, R.lo, R.tz) - ROUND_MINS; });
  for (const t of times) {
    const c = by[t.course];
    if (!c || late[t.date] == null || t.only) continue;
    const x = { ...t, c, m: mins(t.time) }, party = partyOf(x), each = x.price == null ? null : x.price / party;
    const d = km(s.la, s.lo, c.lat, c.lon);
    const ok = (party === 1 ? x.spots >= s.players : party === s.players) && x.m >= s.from * 60 && x.m < s.to * 60 &&
      (s.price >= 200 || each == null || each <= s.price) && d <= s.dist &&
      (s.holes === "0" || (s.holes === "9" ? holesOf(x) && holesOf(x) < 18 : fullRound(x, late[x.date], 18)));
    if (!ok) continue;
    const key = `${t.course}|${t.date}|${t.time}`, prev = best.get(key);
    if (!prev || (each ?? 1e9) < (prev.each ?? 1e9)) best.set(key, { key, course: c.name, date: t.date, time: t.time, each, url: t.url, d });
  }
  return [...best.values()].sort((a, b) => a.date.localeCompare(b.date) || a.time.localeCompare(b.time) || a.d - b.d);
}

// Wording shared by the alert service (labels) and the check that sends messages.
export const SITE = "https://jonathanbondlui-stack.github.io/sydney-tee-times/";
export const today = tz => new Date().toLocaleDateString("en-CA", { timeZone: tz });
export const hourAt = tz => +new Date().toLocaleString("en-GB", { timeZone: tz, hour: "2-digit", hourCycle: "h23" });
export const addDays = (d, n) => { const x = new Date(d + "T12:00:00Z"); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
export const dayName = d => new Date(d + "T12:00:00Z").toLocaleDateString("en-AU", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
export const clock = t => { let [h, m] = t.split(":").map(Number); const ap = h < 12 ? "am" : "pm"; h = h % 12 || 12; return `${h}:${String(m).padStart(2, "0")}${ap}`; };
const hourLabel = h => clock(`${Math.floor(h)}:${h % 1 ? "30" : "00"}`);
export function describe(s) {
  const bits = [s.dates.map(dayName).join(", "), `${s.players} ${s.players == 1 ? "player" : "players"}`,
    s.holes === "18" ? "18 holes" : s.holes === "9" ? "under 18 holes" : "any length",
    `${hourLabel(s.from)}–${hourLabel(s.to)}`, `within ${s.dist >= 999 ? "any distance" : s.dist + " km"} of ${s.place}`];
  if (s.price < 200) bits.push(`up to $${s.price} each`);
  return bits.join(" · ");
}
export const line = (m, many) => `${m.course.replace(/ (Public )?Golf( Club| Course)?$/, "")} · ${many ? dayName(m.date).split(" ").slice(0, 2).join(" ").replace(",", "") + " " : ""}${clock(m.time)}${m.each != null ? " · $" + (Number.isInteger(m.each) ? m.each : m.each.toFixed(2)) + " each" : ""}`;
