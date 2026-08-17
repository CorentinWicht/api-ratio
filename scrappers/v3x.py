"""
V3X.club scraper.

Uses the private JSON API at https://api.v3x.club.
Login via POST /auth/login (JSON body), then GET /auth/me for stats.
Session is maintained via cookies (httpx AsyncClient cookie jar).

Required env vars:
    V3X_USER   — username or email
    V3X_PASS   — password
"""

import logging
import os
from typing import Any, Dict

import httpx

from util import (
    default_user_agent,
    MissingCredentialsError,
    ScrappingError,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.v3x.club"
LOGIN_URL = f"{API_BASE}/auth/login"
ME_URL = f"{API_BASE}/auth/me"


async def get_stats(_: bool = False) -> Dict[str, Any]:
    username = os.getenv("V3X_USER")
    password = os.getenv("V3X_PASS")
    if not (username and password):
        raise MissingCredentialsError("Missing V3X_USER or V3X_PASS in .env")

    headers = {
        "User-Agent": default_user_agent,
        "Accept": "application/json",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Origin": "https://v3x.club",
        "Referer": "https://v3x.club/login",
    }

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        # Authenticate
        try:
            login_resp = await client.post(
                LOGIN_URL,
                json={"login": username, "password": password},
            )
        except httpx.HTTPError as e:
            raise ScrappingError(f"V3X: login request failed: {e}")

        if login_resp.status_code == 401:
            raise ScrappingError("V3X: login failed — invalid credentials.")
        if login_resp.status_code == 403:
            data = login_resp.json() if login_resp.text else {}
            code = data.get("error", "")
            if code == "email_not_verified":
                raise ScrappingError("V3X: login failed — email not verified.")
            raise ScrappingError(f"V3X: login forbidden ({code}).")
        if login_resp.status_code >= 400:
            raise ScrappingError(
                f"V3X: login returned HTTP {login_resp.status_code}: "
                f"{login_resp.text[:300]}"
            )

        logger.debug("V3X: login successful")

        # Fetch user profile
        try:
            me_resp = await client.get(ME_URL)
        except httpx.HTTPError as e:
            raise ScrappingError(f"V3X: /auth/me request failed: {e}")

        if me_resp.status_code == 401:
            raise ScrappingError("V3X: session expired immediately after login.")
        if me_resp.status_code >= 400:
            raise ScrappingError(
                f"V3X: /auth/me returned HTTP {me_resp.status_code}: "
                f"{me_resp.text[:300]}"
            )

        try:
            data = me_resp.json()
        except Exception as e:
            raise ScrappingError(f"V3X: failed to parse /auth/me JSON: {e}")

    raw_upload = float(data.get("uploaded", 0))
    raw_download = float(data.get("downloaded", 0))
    bonus = float(data.get("bonusPoints", 0))

    logger.debug(
        "V3X: upload=%s download=%s bonus=%s", raw_upload, raw_download, bonus
    )

    return {
        "raw_upload": raw_upload,
        "raw_download": raw_download,
        "bonus": bonus,
    }
