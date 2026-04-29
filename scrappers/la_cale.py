import asyncio
import os
import json
import logging
from typing import Dict, Any
from playwright.async_api import async_playwright, BrowserContext, Page
from dotenv import load_dotenv

from util import default_user_agent, load_file, write_file, MissingCredentialsError, ScrappingError

load_dotenv()
logger = logging.getLogger()

COOKIES_FILE = "lacale_cookies.json"
LOGIN_PAGE_URL = "https://la-cale.space/login"
USER_STATS_URL = "https://la-cale.space/api/internal/me"


async def _get_lacale_cookies(ctx: BrowserContext, page: Page) -> bool:
    """Automated login to get fresh La Cale cookies if missing or expired."""
    email = os.getenv("LACALE_USER")
    password = os.getenv("LACALE_PASS")
    if not (email and password):
        raise MissingCredentialsError("Missing La Cale email or password")

    try:
        logger.info("La Cale: Attempting automated login...")
        # Don't use wait_until="networkidle" — la-cale.space has background
        # network activity (likely Cloudflare's bot-detection JS or telemetry)
        # that prevents the page from ever reaching idle. Use the default
        # "load" event, same as c411.
        await page.goto(LOGIN_PAGE_URL)
        await asyncio.sleep(2)

        await page.fill('input[type="email"], input[name="email"], input[placeholder*="mail"]', email)
        await page.fill('input[type="password"], input[name="password"], input[placeholder*="assword"]', password)
        await asyncio.sleep(1)

        btn = await page.query_selector(
            'button[type="submit"], button:has-text("Connexion"), button:has-text("Se connecter")'
        )
        if btn:
            await btn.click()
        else:
            await page.keyboard.press("Enter")

        await asyncio.sleep(5)

        # Validate session by navigating to /me through the browser (not ctx.request),
        # so Cloudflare sees a real browser and lets the API call through.
        await page.goto(USER_STATS_URL)
        content = await page.inner_text("body")
        api_data = json.loads(content)

        if api_data.get("id"):
            cookies = await ctx.cookies()
            write_file(COOKIES_FILE, json.dumps(cookies))
            logger.info(f"La Cale: Login successful as {api_data.get('username')}, cookies saved.")
            return True
        logger.error(f"La Cale: Login response unexpected: {api_data}")
    except Exception as e:
        logger.error(f"La Cale: Login failed: {e}")

    return False


async def get_stats(headless: bool = True) -> Dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(user_agent=default_user_agent)
        page = await context.new_page()
        try:
            res: Dict[str, Any] = {"raw_upload": 0, "raw_download": 0}

            # Try cached cookies first; if the file doesn't exist OR the login
            # flow fails to produce one, surface a clean error instead of
            # falling into the misleading FileNotFoundError downstream.
            cookies = None
            try:
                cookies = load_file(COOKIES_FILE, is_json=True)
            except FileNotFoundError:
                logger.info("La Cale: No cached cookies, attempting login...")
                if not await _get_lacale_cookies(context, page):
                    raise ScrappingError("La Cale: Failed to authenticate (initial login)")
                cookies = load_file(COOKIES_FILE, is_json=True)

            await context.add_cookies(cookies)

            # Use browser navigation rather than ctx.request — same reason as in
            # _get_lacale_cookies above (Cloudflare blocks non-browser API calls).
            await page.goto(USER_STATS_URL)
            content = await page.inner_text("body")
            try:
                api_data = json.loads(content)
            except json.JSONDecodeError:
                api_data = {}

            if not api_data.get("id"):
                logger.warning("La Cale: Session expired or invalid, re-logging in...")
                if not await _get_lacale_cookies(context, page):
                    raise ScrappingError("La Cale: Failed to authenticate (after session expiry)")
                cookies = load_file(COOKIES_FILE, is_json=True)
                await context.add_cookies(cookies)
                await page.goto(USER_STATS_URL)
                content = await page.inner_text("body")
                try:
                    api_data = json.loads(content)
                except json.JSONDecodeError:
                    api_data = {}

            res["raw_upload"] = float(api_data.get("uploaded", 0))
            res["raw_download"] = float(api_data.get("downloaded", 0))
            res["bonus"] = float(api_data.get("bonusPoints", 0))
            return res

        except (MissingCredentialsError, ScrappingError) as e:
            raise e
        except Exception as e:
            raise ScrappingError(e)
        finally:
            await browser.close()
