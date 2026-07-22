"""
memphis.fit scraper (Playwright).

Memphis uses Cloudflare protection on its login API endpoint, blocking plain
HTTP clients. Playwright performs the browser login. After authentication,
GET /api/session/status returns JSON with a 'me' object containing
'uploaded' and 'downloaded' as raw bytes.

Session cookies are cached to .config/memphis_cookies.json.

Required env vars:
    MEMPHIS_USER
    MEMPHIS_PASS
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict

from playwright.async_api import async_playwright, BrowserContext, Page

from util import default_user_agent, load_file, write_file, MissingCredentialsError, ScrappingError

logger = logging.getLogger(__name__)

COOKIES_FILE = "memphis_cookies.json"
BASE_URL = "https://memphis.fit"
LOGIN_URL = f"{BASE_URL}/login"
SESSION_URL = f"{BASE_URL}/api/session/status"


async def _login(ctx: BrowserContext, page: Page) -> bool:
    user = os.getenv("MEMPHIS_USER")
    pwd = os.getenv("MEMPHIS_PASS")
    if not (user and pwd):
        raise MissingCredentialsError("Missing MEMPHIS_USER or MEMPHIS_PASS")

    logger.info("Memphis: logging in...")
    await page.goto(LOGIN_URL)
    await page.wait_for_load_state("domcontentloaded")

    # Memphis SPA login: inputs are identified by data attributes / id
    await page.wait_for_selector("#login-username, input[data-login-tab], #login-shell input", timeout=10000)
    await page.fill("#login-username", user)
    await page.fill("#login-password", pwd)

    async with page.expect_response(lambda r: "session" in r.url, timeout=20000):
        await page.click("#login-button, button[type='submit']")

    await asyncio.sleep(2)

    # Verify authenticated
    resp = await ctx.request.get(SESSION_URL)
    data = await resp.json()
    if not data.get("authenticated"):
        logger.error("Memphis: login failed")
        return False

    cookies = await ctx.cookies()
    write_file(COOKIES_FILE, json.dumps(cookies))
    logger.info("Memphis: login successful, cookies saved")
    return True


async def _fetch_stats(ctx: BrowserContext) -> Dict[str, Any]:
    resp = await ctx.request.get(SESSION_URL)
    if not resp.ok:
        raise ScrappingError(f"Memphis: /api/session/status returned HTTP {resp.status}")
    data = await resp.json()
    if not data.get("authenticated"):
        return None
    me = data.get("me", {})
    return {
        "raw_upload": float(me.get("uploaded_bytes", me.get("uploaded", 0))),
        "raw_download": float(me.get("downloaded_bytes", me.get("downloaded", 0))),
        "bonus": float(me.get("bonus_points", me.get("bonus", me.get("points", 0)))),
    }


async def get_stats(headless: bool = True) -> Dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(user_agent=default_user_agent)
        page = await ctx.new_page()
        try:
            try:
                cookies = load_file(COOKIES_FILE, is_json=True)
                await ctx.add_cookies(cookies)
            except FileNotFoundError:
                await _login(ctx, page)

            stats = await _fetch_stats(ctx)
            if stats is None:
                logger.info("Memphis: session expired, re-logging in...")
                await _login(ctx, page)
                stats = await _fetch_stats(ctx)
                if stats is None:
                    raise ScrappingError("Memphis: failed to authenticate")

            return stats

        except (MissingCredentialsError, ScrappingError):
            raise
        except Exception as e:
            raise ScrappingError(f"Memphis: unexpected error: {e}")
        finally:
            await browser.close()
