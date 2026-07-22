"""
immortalseed.me scraper.

Logs in via POST to takelogin.php and parses the upload/download/bonus
stats from the top bar of the homepage.

Required env vars:
    IMMORTALSEED_USER
    IMMORTALSEED_PASS
"""

import logging
import os
import re
from typing import Any, Dict

import httpx

from util import default_user_agent, parse_bytes, MissingCredentialsError, ScrappingError

logger = logging.getLogger(__name__)

BASE = "https://immortalseed.me"
LOGIN_URL = f"{BASE}/takelogin.php"
HOME_URL = f"{BASE}/"


def _extract_stats(html: str) -> Dict[str, Any]:
    m = re.search(r'Up:\s*<font[^>]*>(.*?)</font>\s*Down:\s*<font[^>]*>(.*?)</font>', html)
    if not m:
        raise ScrappingError("ImmortalSeed: could not find Up/Down stats in page HTML")

    bonus_m = re.search(r'Bonus:.*?<a[^>]*>([\d,]+\.[\d]+)</a>', html)
    bonus = float(bonus_m.group(1).replace(",", "")) if bonus_m else 0.0

    return {
        "raw_upload": parse_bytes(m.group(1)),
        "raw_download": parse_bytes(m.group(2)),
        "bonus": bonus,
    }


async def get_stats(_: bool = False) -> Dict[str, Any]:
    username = os.getenv("IMMORTALSEED_USER")
    password = os.getenv("IMMORTALSEED_PASS")
    if not (username and password):
        raise MissingCredentialsError("Missing IMMORTALSEED_USER or IMMORTALSEED_PASS")

    headers = {
        "User-Agent": default_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": f"{BASE}/",
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30.0) as client:
        # Fetch homepage first to get any required tokens
        try:
            login_resp = await client.post(
                LOGIN_URL,
                data={"username": username, "password": password},
            )
        except httpx.HTTPError as e:
            raise ScrappingError(f"ImmortalSeed: login request failed: {e}")

        if login_resp.status_code >= 400:
            raise ScrappingError(f"ImmortalSeed: login returned HTTP {login_resp.status_code}")

        # Check we're actually logged in
        if "takelogin.php" in str(login_resp.url) or "login" in str(login_resp.url).lower():
            raise ScrappingError("ImmortalSeed: login failed — check username/password")

        html = login_resp.text

        # If we didn't land on the homepage, fetch it explicitly
        if "Up:" not in html:
            try:
                home_resp = await client.get(HOME_URL)
                html = home_resp.text
            except httpx.HTTPError as e:
                raise ScrappingError(f"ImmortalSeed: failed to load homepage: {e}")

    return _extract_stats(html)
