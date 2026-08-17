# AGENTS.md

## What this repo is

Python FastAPI app that scrapes upload/download/ratio stats from private BitTorrent trackers and exposes them as a REST API (`/ratios`) and Prometheus metrics (`/metrics`). Runs on port **8679**.

## Running locally

```bash
pip install -r requirements.txt
playwright install chromium --with-deps
cp .env.example .env  # fill in credentials
python api.py
# or: uvicorn api:app --host 0.0.0.0 --port 8679
```

One-shot CLI scrape (for debugging a single tracker):
```bash
python scrap_ratio.py --site <tracker_name>
python scrap_ratio.py --site all
python scrap_ratio.py --site torr9 --no-headless  # opens visible browser
```

## Docker (production method)

```bash
docker compose up -d
```

`docker-compose.yml` uses the pre-built image `sabuontop/api-ratio:test` (not `:latest` as README says — trust the compose file). To build locally, uncomment `build: .` in `docker-compose.yml`.

The volume maps `./config` (host, no dot) → `/app/.config` (container). Locally the config dir is `.config` (with dot) relative to project root.

## No tests, no linter, no CI

There are no test suite, no linter, no formatter, no type checker, and no CI pipelines. Nothing to run before committing.

## Adding a new tracker scraper

Drop a `.py` file in `scrappers/`. It is auto-discovered via `glob("scrappers/*.py")`. The filename becomes the tracker ID everywhere (cache key, CLI arg, Prometheus label).

Every scraper **must** export:
```python
async def get_stats(headless: bool = True) -> dict:
    # must return at minimum: raw_upload (float, bytes), raw_download (float, bytes), bonus (float)
```

Ratio is computed centrally in `api.py`, not in scrapers.

## Scraper types

- **Browser-based (Playwright):** `c411`, `torr9`, `la_cale`, `nostradamus`
- **httpx async:** `nexum`, `tr4ker`, `torrentleech`, `crazyspirits`
- **urllib (sync wrapped in async):** `gemini`, `gf_free`, `teamflix`, `theoldschool`

## Anti-bot quirks

- **la_cale:** Waits 30 s before submit (`HUMAN_DELAY_SECONDS = 30`) to defeat a server-side `formLoadedAt` check. Self-imposes a 1-hour lockout (`lacale_lockout` file in `.config/`) after a failed login to prevent bans.
- **nostradamus:** Polls up to 24× with 2.5 s delays waiting for an anti-bot challenge to clear. Uses `fr-FR` locale and a specific Linux Chrome UA.
- **crazyspirits:** Automated login is blocked by anti-bot. User must manually copy `uid` and `pass` cookies from browser DevTools and set `.env` as `CRAZYSPIRITS_COOKIE='uid=xxx; pass=xxx'`.

## Env var aliases (backwards compat)

- `TORR9_USER` or `TOR9_USER` (typo variant both accepted)
- `TORR9_PASSWORD`, `TORR9_PASS`, or `TOR9_PASS`
- `NOSTRADAMUS_PRIVATE_KEY`, `NOSTRADAMUS_API_KEY`, or `NOSTRADAMUS_PRIVATE_TICKET`

## Stateful `.config/` directory

Browser scrapers persist session cookies/tokens to `.config/` (e.g., `c411_cookies.json`, `torr9_token.txt`). On session expiry they re-authenticate automatically. Dir permissions: `0700`; file permissions: `0600`. Gitignored.

## Ratio edge cases (api.py)

- download == 0 and upload > 0 → ratio = `999`
- both == 0 → ratio = `0`

This logic is duplicated in `scrap_ratio.py` (not DRY).

## Unused dependencies

`playwright-stealth`, `aiohttp`, and `requests` are in `requirements.txt` but not used in current code.
