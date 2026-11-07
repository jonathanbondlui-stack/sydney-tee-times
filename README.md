# Tee Time Finder

```
data/courses.json        the course directory (status, platform, location). Edit this to add courses.
site/                    the website: static files, host anywhere (Cloudflare Pages, Netlify, GitHub Pages)
backend/build_feed.py    builds site/tee-times.json from clubs' public booking pages
```

## How it fits together
The site loads `courses.json` and `tee-times.json`. If the times file is missing it shows clearly labelled demo data.
The builder runs about every 20 minutes and rewrites `tee-times.json`, which covers the next 7 days. Every 6 hours it also rewrites `tee-times-far.json`, which covers up to 28 days ahead and which the site only loads when someone picks a later date. Visitors always book on the club's own page.

## To go live
1. **Set your contact email** in `TEE_UA` so clubs can reach you. The builder won't fetch anything without it. Keep it out of the code, because the repo is public:
   locally run `setx TEE_UA "TeeSheetBot/0.1 (+mailto:you@example.com)"` once and open a new terminal, and on GitHub add it as the repository secret `TEE_UA`.
2. **Check the MiClub parsers on a second club.** Both MiClub parsers (calendar and timesheet) are written and pass `python backend/test_parsers.py`,
   but they were built against Moore Park's pages only. Clubs can customise their pages, so save a second club's calendar and timesheet
   pages into `fixtures/` and run `--calendar` and `--timesheet` on them before trusting the feed. Clubs that switch on the public captcha
   can't be read automatically; the builder skips them. Never run it without your contact email set (step 1).
3. **Run the builder locally if you want to test:** `python backend/build_feed.py`.
4. **Hosting and schedule.** `.github/workflows/refresh.yml` runs the builder and publishes `site/` to GitHub Pages. The feed isn't stored in git:
   each run starts from the live feed, so a failed run leaves the last good one online and shows as a failed run on GitHub. The repo must stay public for free Actions minutes at this schedule.
   Regular refreshes come from a cron-job.org job, because GitHub's own schedule runs late and skips runs, so it's only a backup every 3 hours. The job sends a `POST` to
   `https://api.github.com/repos/jonathanbondlui-stack/sydney-tee-times/actions/workflows/refresh.yml/dispatches` with the body `{"ref":"main"}` and the headers `Authorization: Bearer <token>`,
   `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28` and `Content-Type: application/json`. The token is a fine-grained GitHub token for this repo only, with Actions set to read and write.
   If the times go stale, check that the token hasn't expired and that cron-job.org hasn't switched the job off. That API version stops working on 10 March 2028.
5. **Before you launch publicly:** read each platform's terms and contact MiClub. Keep the link-out model, honour any club's request to be removed,
   and add a privacy policy if you collect emails. Then remove the `noindex` tag from `site/index.html` so search engines can list the site.

## Rules built into the builder
- Checks robots.txt on every host and skips anything disallowed. Quick18's robots.txt blocks AI crawlers by name but allows this builder, so a person saves its pages for testing rather than an AI assistant fetching them.
- Maximum one request per second per host, with an honest user agent. Up to 8 clubs are read at the same time, one worker per club.
- Courses with `"enabled": false` are never fetched.
- If most fetches fail or nothing is parsed, it keeps the last good feed.

## Making money (once the data works)
Booking commission is out: TeeNet and teeFinder both take none. The realistic paths are tee time alerts as a paid feature,
featured listings for clubs, and partnerships with clubs or MiClub.
