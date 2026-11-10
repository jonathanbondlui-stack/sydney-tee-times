// Tee time alerts: holds saved searches. The site saves and stops them here; the site's refresh
// (alerts/check.mjs, run by GitHub Actions after each publish) reads them with the CHECK_KEY
// password, sends the ntfy messages, and writes back which times it has already told you about.
// Sending happens there because ntfy.sh doesn't accept connections from Cloudflare.
// A search ends by itself after its last date.
import { REGIONS, SITE, unpackFeed, parseSearch, matches, describe, today, addDays } from "./match.js";

const MAX_PER_TOPIC = 5, MAX_TOTAL = 200;
const CORS = {
  "Access-Control-Allow-Origin": "https://jonathanbondlui-stack.github.io",
  "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...CORS } });
const html = (title, body) => new Response(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title>
<body style="font:16px/1.5 system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 16px;color:#16291D;background:#EEF3E8">
<h1 style="font-size:22px">${title}</h1>${body}<p><a href="${SITE}" style="color:#1F6B3A">Back to tee times</a></p></body>`,
  { headers: { "Content-Type": "text/html; charset=utf-8" } });
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const newId = () => [...crypto.getRandomValues(new Uint8Array(12))].map(b => b.toString(16).padStart(2, "0")).join("");

async function feeds(region, dates) {
  const far = dates.some(d => d > addDays(today(REGIONS[region].tz), 7));
  let times = [];
  for (const n of [`tee-times-${region}.json`, ...(far ? [`tee-times-far-${region}.json`] : [])]) {
    const r = await fetch(SITE + n, { cf: { cacheTtl: 60 } }).catch(() => null);
    if (!r || !r.ok) return null;
    times = times.concat(unpackFeed(await r.json()));
  }
  return times;
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
const authorised = (req, env) => !!env.CHECK_KEY && env.CHECK_KEY.trim().length >= 32 && req.headers.get("Authorization") === `Bearer ${env.CHECK_KEY.trim()}`;

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
  const times = await feeds(region, s.dates);
  const cs = await fetch(SITE + "courses.json", { cf: { cacheTtl: 300 } }).then(r => r.ok ? r.json() : null).catch(() => null);
  if (!times || !cs) return json({ error: "Couldn't read tee times right now. Try again soon." }, 503);
  // What matches now is what you can already see, so only times after this count as new.
  const found = matches(s, times, cs, region), base = new URL(req.url).origin;
  const w = { id: newId(), topic, region, q: p.toString(), base, seen: found.map(m => m.key), created: new Date().toISOString(), sent: 0 };
  await save(env, w, s);
  return json({ id: w.id, label: describe(s), now: found.length, q: w.q, stop: `${base}/stop/${w.id}` });
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
      return a === "stop" ? html("Alert stopped", "<p>You won't get any more messages for that search.</p>") : json({ stopped: true });
    }
    if (a === "stop" && id) { // a link opened in a browser asks first, so a link preview can't stop it by accident
      const w = await env.WATCHES.get("w:" + id, "json");
      if (!w) return html("Alert already off", "<p>That alert has ended or was stopped.</p>");
      return html("Stop this alert?", `<p>${esc(describe(parseSearch(w.q)))}</p><form method="post"><button style="font:600 16px system-ui;padding:10px 18px;border-radius:999px;border:0;background:#1F6B3A;color:#fff">Stop alert</button></form>`);
    }
    // For the refresh only: every saved search, and recording what each has been told about.
    if (a === "all" && req.method === "GET") {
      if (!authorised(req, env)) return json({ error: "Not allowed" }, 403);
      return json(await all(env));
    }
    if (a === "seen" && id && req.method === "POST") {
      if (!authorised(req, env)) return json({ error: "Not allowed" }, 403);
      const w = await env.WATCHES.get("w:" + id, "json");
      if (!w) return json({ gone: true });
      const b = await req.json(), s = parseSearch(w.q);
      await save(env, { ...w, seen: Array.isArray(b.seen) ? b.seen.slice(0, 20000) : w.seen, sent: +b.sent || w.sent || 0, last: b.last || w.last }, s);
      return json({ saved: true });
    }
    return json({ error: "Not found" }, 404);
  },
};
