"""
digitalcore.club scraper.

POSTs credentials to /api/v1/auth/login which returns a JSON object with
'uploaded' and 'downloaded' as raw bytes and 'bonuspoang' as bonus points.
No session/token caching needed — the login call is cheap.

Required env vars:
    DIGITALCORE_USER
    DIGITALCORE_PASS
"""

import logging
import os
from typing import Any, Dict

import httpx

from util import default_user_agent, MissingCredentialsError, ScrappingError

logger = logging.getLogger(__name__)

LOGIN_URL = "https://digitalcore.club/api/v1/auth/login"


async def get_stats(_: bool = False) -> Dict[str, Any]:
    username = os.getenv("DIGITALCORE_USER")
    password = os.getenv("DIGITALCORE_PASS")
    if not (username and password):
        raise MissingCredentialsError("Missing DIGITALCORE_USER or DIGITALCORE_PASS")

    headers = {
        "User-Agent": default_user_agent,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            resp = await client.post(
                LOGIN_URL,
                json={"username": username, "password": password},
            )
    except httpx.HTTPError as e:
        raise ScrappingError(f"DigitalCore: request failed: {e}")

    if resp.status_code == 401:
        raise ScrappingError("DigitalCore: 401 Unauthorized — check username/password")
    if resp.status_code >= 400:
        raise ScrappingError(f"DigitalCore: HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except ValueError as e:
        raise ScrappingError(f"DigitalCore: response was not JSON: {e}")

    user = data.get("user", {})
    if not user:
        raise ScrappingError("DigitalCore: no 'user' object in login response")

    return {
        "raw_upload": float(user.get("uploaded", 0)),
        "raw_download": float(user.get("downloaded", 0)),
        "bonus": float(user.get("bonuspoang", 0)),
    }
