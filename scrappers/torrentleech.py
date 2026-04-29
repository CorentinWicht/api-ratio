"""
TorrentLeech.org scraper.

No public API, so we do a traditional form login (POST username/password)
and parse the top-bar stats from the homepage HTML.

Required env vars:
    TL_USER
    TL_PASS
"""

import logging
import os
from typing import Any, Dict

import httpx
from bs4 import BeautifulSoup

from util import (
    default_user_agent,
    parse_bytes,
    MissingCredentialsError,
    ScrappingError,
)

logger = logging.getLogger(__name__)

BASE = "https://www.torrentleech.org"
LOGIN_URL = f"{BASE}/user/account/login/"
HOME_URL = f"{BASE}/"


def _looks_like_login_page(html: str) -> bool:
    return 'name="login-form"' in html or '/user/account/login/' in html.lower()


def _extract_top_bar(html: str) -> Dict[str, Any]:
    """Pull upload, download and TL Points out of the top-bar HTML."""
    soup = BeautifulSoup(html, "html.parser")

    def _value_by_title(title: str) -> str:
        # The relevant <div> wraps an <i> icon and a <span class="link"> with the value.
        div = soup.find("div", attrs={"title": title})
        if not div:
            return ""
        span = div.find("span", class_="link")
        if span:
            return span.get_text(strip=True)
        # Fallback: take the div's own text minus the icon.
        return div.get_text(" ", strip=True)

    upload_str = _value_by_title("Uploaded (Seeding)")
    download_str = _value_by_title("Downloaded (Leeching)")

    tl_points_span = soup.find("span", class_="total-TL-points")
    tl_points = tl_points_span.get_text(strip=True) if tl_points_span else "0"

    if not upload_str or not download_str:
        raise ScrappingError(
            "TorrentLeech: could not find upload/download in the top bar — "
            "the page layout may have changed."
        )

    try:
        bonus = float(tl_points.replace(",", "."))
    except ValueError:
        bonus = 0.0

    return {
        "raw_upload": parse_bytes(upload_str),
        "raw_download": parse_bytes(download_str),
        "bonus": bonus,
    }


async def get_stats(_: bool = False) -> Dict[str, Any]:
    username = os.getenv("TL_USER")
    password = os.getenv("TL_PASS")
    if not (username and password):
        raise MissingCredentialsError(
            "Missing TL_USER or TL_PASS in .env"
        )

    headers = {
        "User-Agent": default_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        try:
            login_resp = await client.post(
                LOGIN_URL,
                data={"username": username, "password": password},
                headers={"Referer": f"{BASE}/user/account/login/"},
            )
        except httpx.HTTPError as e:
            raise ScrappingError(f"TorrentLeech: login request failed: {e}")

        # A successful login redirects to /, an invalid one re-renders the login form.
        if login_resp.status_code >= 400:
            raise ScrappingError(
                f"TorrentLeech: login returned HTTP {login_resp.status_code}"
            )
        if _looks_like_login_page(login_resp.text):
            raise ScrappingError(
                "TorrentLeech: login failed — check username/password "
                "(or the account may need a manual login first if 2FA / "
                "captcha was triggered)."
            )

        # If login redirected to a non-home page, fetch the home page explicitly
        # so we always parse the same place.
        if str(login_resp.url).rstrip("/") != BASE:
            try:
                home_resp = await client.get(HOME_URL)
            except httpx.HTTPError as e:
                raise ScrappingError(f"TorrentLeech: failed to load homepage: {e}")
            html = home_resp.text
        else:
            html = login_resp.text

    return _extract_top_bar(html)
