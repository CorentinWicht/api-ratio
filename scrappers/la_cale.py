import asyncio
import os
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any
from playwright.async_api import async_playwright, BrowserContext, Page
from dotenv import load_dotenv

from util import default_user_agent, load_file, write_file, MissingCredentialsError, ScrappingError

load_dotenv()
logger = logging.getLogger()

LOCKOUT_FILE = Path(".config/lacale_lockout")
LOCKOUT_DURATION = 3600  # 1 hour
COOKIES_FILE = "lacale_cookies.json"
LOGIN_PAGE_URL = "https://la-cale.space/login"
LOGIN_API_URL = "https://la-cale.space/api/internal/auth/login"
USER_STATS_URL = "https://la-cale.space/api/internal/me"

# La Cale's backend uses a `formLoadedAt` timestamp that the frontend embeds
# in the login POST body. If the time between page load and submit is too
# short (< ~15s), the server flags it as bot-like and rejects with 400 +
# challenge_required, escalating to ALTCHA. Real humans take 30-60 seconds
# to type credentials and click submit. We mimic that by waiting before the
# click. Total page-load-to-submit delay: ~35s (page goto + 2s + fill + 30s).
HUMAN_DELAY_SECONDS = 30

async def _get_lacale_cookies(ctx: BrowserContext, page: Page) -> bool:
    # Honor self-imposed lockout from previous failures.
    if LOCKOUT_FILE.exists():
        try:
            lockout_until = float(LOCKOUT_FILE.read_text().strip())
        except (ValueError, OSError):
            lockout_until = 0
        if time.time() < lockout_until:
            remaining = int(lockout_until - time.time())
            logger.warning(f"La Cale: in self-imposed lockout for {remaining}s more")
            return False

    email = os.getenv("LACALE_USER")
    password = os.getenv("LACALE_PASS")
    if not (email and password):
        raise MissingCredentialsError("Missing La Cale email or password")

    try:
        logger.info("La Cale: Attempting automated login...")
        await page.goto(LOGIN_PAGE_URL, wait_until="networkidle")
        await asyncio.sleep(2)
        await page.fill('input[type="email"], input[name="email"]', email)
        await page.fill('input[type="password"], input[name="password"]', password)

        logger.info(f"La Cale: Pausing {HUMAN_DELAY_SECONDS}s before submit (anti-bot timing)...")
        await asyncio.sleep(HUMAN_DELAY_SECONDS)
        await page.click('button[type="submit"]')
        await asyncio.sleep(4)

        response = await ctx.request.get(USER_STATS_URL)
        if response.ok:
            api_data = await response.json()
            if api_data.get("id"):
                cookies = await ctx.cookies()
                write_file(COOKIES_FILE, json.dumps(cookies))
                logger.info(f"La Cale: Login successful as {api_data.get('username')}, cookies saved.")
                # Clear any previous lockout on a successful login.
                LOCKOUT_FILE.unlink(missing_ok=True)
                return True
            logger.error(f"La Cale: /me returned no user: {api_data}")
        else:
            logger.error(f"La Cale: /me returned {response.status} after login")
    except Exception as e:
        logger.error(f"La Cale: Login failed: {e}")

    # Any path that gets here = login failed. Set lockout to avoid hammering.
    LOCKOUT_FILE.write_text(str(time.time() + LOCKOUT_DURATION))
    logger.warning(f"La Cale: login failed — locking out for {LOCKOUT_DURATION}s")
    return False

async def get_stats(headless: bool = True) -> Dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(user_agent=default_user_agent)
        page = await context.new_page()
        try:
            res: Dict[str, Any] = {"raw_upload": 0, "raw_download": 0}

            try:
                cookies = load_file(COOKIES_FILE, is_json=True)
            except FileNotFoundError:
                if not await _get_lacale_cookies(context, page):
                    raise ScrappingError("La Cale: Failed to authenticate")
                cookies = load_file(COOKIES_FILE, is_json=True)

            await context.add_cookies(cookies)
            response = await context.request.get(USER_STATS_URL)
            api_data = await response.json() if response.ok else {}

            if not api_data.get("id"):
                logger.warning("La Cale: Session expired or invalid, re-logging in...")
                if await _get_lacale_cookies(context, page):
                    cookies = load_file(COOKIES_FILE, is_json=True)
                    await context.add_cookies(cookies)
                    response = await context.request.get(USER_STATS_URL)
                    api_data = await response.json() if response.ok else {}
                else:
                    raise ScrappingError("La Cale: Failed to authenticate")

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
