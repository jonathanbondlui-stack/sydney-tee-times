// Tee time alerts: holds saved searches, checks the site's feeds every 15 minutes, and sends one
// ntfy message per search when new matching times appear. A search ends by itself after its last
// date, and every message has a "Stop this alert" button.
import { REGIONS, unpackFeed, parseSearch, matches } from "./match.js";

const SITE = "https://jonathanbondlui-stack.github.io/sydney-tee-times/";
const NTFY = "https://ntfy.sh/";
const MAX_PER_TOPIC = 5, MAX_TOTAL = 200, MAX_LINES = 8;
const CORS = {
  "Access-Control-Allow-Origin": "https://jonathanbondlui-stack.github.io",
  "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...CORS } });
const page = (title, text) => new Response(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title>
<body style="font:16px/1.5 system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 16px;color:#16291D;background:#EEF3E8">
<h1 style="font-size:22px">${title}</h1><p>${text}</p><p><a href="${SITE}" style="color:#1F6B3A">Back to tee times</a></p></body>`,
  { headers: { "Content-Type": "text/html; charset=utf-8" } });

const newId = () => [...crypto.getRandomValues(new Uint8Array(12))].map(b => b.toString(16).padStart(2, "0")).join("");
const today = tz => new Date().toLocaleDateString("en-CA", { timeZone: tz });
const hourAt = tz => +new Date().toLocaleString("en-GB", { timeZone: tz, hour: "2-digit", hourCycle: "h23" });
const dayName = d => new Date(d + "T12:00:00Z").toLocaleDateString("en-AU", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
const clock = t => { let [h, m] = t.split(":").map(Number); const ap = h < 12 ? "am" : "pm"; h = h % 12 || 12; return `${h}:${String(m).padStart(2, "0")}${ap}`; };
const hourLabel = h => clock(`${Math.floor(h)}:${h % 1 ? "30" : "00"}`);

export function describe(s) {
  const bits = [s.dates.map(dayName).join(", "), `${s.players} ${s.players == 1 ? "player" : "players"}`,
    s.holes === "18" ? "18 holes" : s.holes === "9" ? "under 18 holes" : "any length",
    `${hourLabel(s.from)}–${hourLabel(s.to)}`, `within ${s.dist >= 999 ? "any distance" : s.dist + " km"} of ${s.place}`];
  if (s.price < 200) bits.push(`up to $${s.price} each`);
  return bits.join(" · ");
}

async function feeds(region, dates, cache) {
  const far = dates.some(d => d > addDays(today(REGIONS[region].tz), 7));
  const names = [`tee-times-${region}.json`, ...(far ? [`tee-times-far-${region}.json`] : [])];
  let times = [];
  for (const n of names) {
    if (!cache[n]) cache[n] = fetch(SITE + n, { cf: { cacheTtl: 60 } }).then(r => r.ok ? r.json() : null).catch(() => null);
    const j = await cache[n];
    if (!j) return null; // a feed we need didn't load: try again next time rather than alert on half the times
    times = times.concat(unpackFeed(j));
  }
  return times;
}
const addDays = (d, n) => { const x = new Date(d + "T12:00:00Z"); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
async function courses(cache) {
  if (!cache.courses) cache.courses = fetch(SITE + "courses.json", { cf: { cacheTtl: 300 } }).then(r => r.ok ? r.json() : null).catch(() => null);
  return cache.courses;
}

async function notify(w, title, lines, extra = {}) {
  const stop = `${w.base}/stop/${w.id}`;
  const body = {
    topic: w.topic, title, message: lines.join("\n"), tags: ["golf"], click: SITE + "?" + w.q,
    actions: [{ action: "view", label: "See times", url: SITE + "?" + w.q, clear: true },
              { action: "http", label: "Stop this alert", url: stop, method: "POST", clear: true }],
    ...extra,
  };
  const r = await fetch(NTFY, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.ok;
}
const line = (m, many) => `${m.course.replace(/ (Public )?Golf( Club| Course)?$/, "")} · ${many ? dayName(m.date).split(" ").slice(0, 2).join(" ").replace(",", "") + " " : ""}${clock(m.time)}${m.each != null ? " · $" + (Number.isInteger(m.each) ? m.each : m.each.toFixed(2)) + " each" : ""}`;

async function check(env, w, cache) {
  const R = REGIONS[w.region], s = parseSearch(w.q), now = today(R.tz);
  if (!s || s.dates.every(d => d < now)) { await env.WATCHES.delete("w:" + w.id); return "ended"; }
  // No messages from 10pm to 6am at the course; they wait until morning. QUIET="0-0" turns this off for testing.
  const [qs, qe] = (env.QUIET || "22-6").split("-").map(Number), h = hourAt(R.tz);
  if (qs !== qe && (h >= qs || h < qe)) return "quiet";
  const [times, cs] = [await feeds(w.region, s.dates, cache), await courses(cache)];
  if (!times || !cs) return "no feed";
  const found = matches(s, times, cs, w.region), seen = new Set(w.seen), fresh = found.filter(m => !seen.has(m.key));
  // Remember everything matching now, plus what was seen before, so a time that drops out for one
  // refresh (a club's site having a bad moment) doesn't alert again when it comes back.
  const keep = new Set([...w.seen, ...found.map(m => m.key)].filter(k => k.split("|")[1] >= now));
  if (!fresh.length) {
    if (keep.size !== w.seen.length) await save(env, { ...w, seen: [...keep] }, s);
    return "none";
  }
  const lines = fresh.slice(0, MAX_LINES).map(m => line(m, s.dates.length > 1));
  if (fresh.length > MAX_LINES) lines.push(`and ${fresh.length - MAX_LINES} more`);
  const ok = await notify(w, `${fresh.length} new tee ${fresh.length == 1 ? "time" : "times"} for ${s.dates.map(dayName).join(", ")}`, lines);
  if (ok) await save(env, { ...w, seen: [...keep], sent: (w.sent || 0) + 1, last: new Date().toISOString() }, s);
  return ok ? `sent ${fresh.length}` : "ntfy failed";
}
async function save(env, w, s) {
  const end = new Date(s.dates.reduce((a, b) => a > b ? a : b) + "T23:59:00+08:00").getTime() / 1000 + 86400;
  await env.WATCHES.put("w:" + w.id, JSON.stringify(w), { expiration: Math.max(Math.floor(end), Math.floor(Date.now() / 1000) + 120) });
}
async function all(env) {
  const out = [];
  let cursor;
  do {
    const page = await env.WATCHES.list({ prefix: "w:", cursor });
    for (const k of page.keys) { const w = await env.WATCHES.get(k.name, "json"); if (w) out.push(w); }
    cursor = page.list_complete ? null : page.cursor;
  } while (cursor);
  return out;
}

async function create(req, env) {
  let b;
  try { b = await req.json(); } catch { return json({ error: "Bad request" }, 400); }
  const s = parseSearch(b.q || ""), region = b.region, topic = b.topic || "";
  if (!s || !REGIONS[region]) return json({ error: "That search can't be saved." }, 400);
  if (!/^tee-[a-z0-9]{16,40}$/.test(topic)) return json({ error: "Bad alert channel." }, 400);
  const now = today(REGIONS[region].tz);
  s.dates = s.dates.filter(d => d >= now && d <= addDays(now, 30));
  if (!s.dates.length) return json({ error: "Pick a date from today to 30 days ahead." }, 400);
  const p = new URLSearchParams(b.q); p.set("d", s.dates.join(","));
  const existing = await all(env);
  if (existing.length >= MAX_TOTAL) return json({ error: "Alerts are full right now." }, 503);
  if (existing.filter(w => w.topic === topic).length >= MAX_PER_TOPIC) return json({ error: `You can have ${MAX_PER_TOPIC} alerts at once. Stop one first.` }, 409);
  const cache = {}, times = await feeds(region, s.dates, cache), cs = await courses(cache);
  if (!times || !cs) return json({ error: "Couldn't read tee times right now. Try again soon." }, 503);
  const found = matches(s, times, cs, region);
  const w = { id: newId(), topic, region, q: p.toString(), base: new URL(req.url).origin, seen: found.map(m => m.key), created: new Date().toISOString(), sent: 0 };
  await save(env, w, s);
  const label = describe(s);
  await notify(w, "Tee time alert is on", [label, found.length ? `${found.length} times match now. You'll hear about new ones.` : "Nothing matches yet. You'll hear when times appear."], { priority: 2 });
  return json({ id: w.id, label, now: found.length });
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url), [, a, id] = url.pathname.split("/");
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (a === "watch" && !id && req.method === "POST") return create(req, env);
    if (a === "watch" && id && req.method === "GET") {
      const w = await env.WATCHES.get("w:" + id, "json");
      return w ? json({ active: true, label: describe(parseSearch(w.q)), sent: w.sent || 0 }) : json({ active: false });
    }
    if ((a === "watch" && id && req.method === "DELETE") || (a === "stop" && id && req.method === "POST")) {
      await env.WATCHES.delete("w:" + id);
      return a === "stop" ? page("Alert stopped", "You won't get any more messages for that search.") : json({ stopped: true });
    }
    if (a === "stop" && id) { // a link opened in a browser asks first, so a link preview can't stop it by accident
      const w = await env.WATCHES.get("w:" + id, "json");
      if (!w) return page("Alert already off", "That alert has ended or was stopped.");
      return new Response(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stop alert</title>
<body style="font:16px/1.5 system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 16px;color:#16291D;background:#EEF3E8">
<h1 style="font-size:22px">Stop this alert?</h1><p>${describe(parseSearch(w.q))}</p>
<form method="post"><button style="font:600 16px system-ui;padding:10px 18px;border-radius:999px;border:0;background:#1F6B3A;color:#fff">Stop alert</button></form></body>`,
        { headers: { "Content-Type": "text/html; charset=utf-8" } });
    }
    return json({ error: "Not found" }, 404);
  },
  async scheduled(event, env, ctx) {
    const cache = {}, results = {};
    for (const w of await all(env)) {
      try { results[w.id] = await check(env, w, cache); } catch (e) { results[w.id] = "error " + e.message; }
    }
    console.log(JSON.stringify(results));
  },
};
