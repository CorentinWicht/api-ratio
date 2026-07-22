"""
filelist.io scraper.

Logs in via POST to takelogin.php (requires fetching the validator token first)
and parses upload/download stats from the homepage top bar.

Required env vars:
    FILELIST_USER
    FILELIST_PASS
"""

import logging
import os
import re
from typing import Any, Dict

import httpx

from util import default_user_agent, parse_bytes, MissingCredentialsError, ScrappingError

logger = logging.getLogger(__name__)

BASE = "https://filelist.io"
LOGIN_PAGE_URL = f"{BASE}/login.php"
TAKE_LOGIN_URL = f"{BASE}/takelogin.php"
HOME_URL = f"{BASE}/index.php"


def _extract_stats(html: str) -> Dict[str, Any]:
    up_m = re.search(r'Uploaded</font>:&nbsp;([\d.]+ \w+)', html)
    dl_m = re.search(r'Downloaded</font>:&nbsp;([\d.]+ \w+)', html)
    if not up_m or not dl_m:
        raise ScrappingError(
            "FileList: could not find Uploaded/Downloaded stats in page HTML — "
            "login may have failed or page layout changed."
        )

    bonus_m = re.search(r'Tokens</font>&nbsp;([\d,]+)', html)
    bonus = float(bonus_m.group(1).replace(",", "")) if bonus_m else 0.0

    return {
        "raw_upload": parse_bytes(up_m.group(1)),
        "raw_download": parse_bytes(dl_m.group(1)),
        "bonus": bonus,
    }


async def get_stats(_: bool = False) -> Dict[str, Any]:
    username = os.getenv("FILELIST_USER")
    password = os.getenv("FILELIST_PASS")
    if not (username and password):
        raise MissingCredentialsError("Missing FILELIST_USER or FILELIST_PASS")

    headers = {
        "User-Agent": default_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30.0) as client:
        # Fetch login page to get the validator token
        try:
            login_page = await client.get(LOGIN_PAGE_URL)
        except httpx.HTTPError as e:
            raise ScrappingError(f"FileList: failed to load login page: {e}")

        validator_m = re.search(r"name='validator'\s+value='([a-f0-9]+)'", login_page.text)
        if not validator_m:
            raise ScrappingError("FileList: could not find validator token on login page")
        validator = validator_m.group(1)

        # Submit login
        try:
            login_resp = await client.post(
                TAKE_LOGIN_URL,
                data={"username": username, "password": password, "validator": validator},
                headers={"Referer": LOGIN_PAGE_URL},
            )
        except httpx.HTTPError as e:
            raise ScrappingError(f"FileList: login request failed: {e}")

        if login_resp.status_code >= 400:
            raise ScrappingError(f"FileList: login returned HTTP {login_resp.status_code}")

        html = login_resp.text

        if "Uploaded" not in html:
            try:
                home_resp = await client.get(HOME_URL)
                html = home_resp.text
            except httpx.HTTPError as e:
                raise ScrappingError(f"FileList: failed to load homepage: {e}")

        if "Uploaded" not in html:
            raise ScrappingError("FileList: login failed — check username/password")

    return _extract_stats(html)
