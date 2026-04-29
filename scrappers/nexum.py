"""
Nexum-Core scraper.

Uses the official API endpoint /api/v1/me with an API key sent as the
X-API-Key header. Generate the key from Paramètres → Clé API on the site
(this is different from your tracker passkey).
"""

import logging
import os
from typing import Any, Dict

import httpx

from util import default_user_agent, MissingCredentialsError, ScrappingError

logger = logging.getLogger(__name__)

API_URL = "https://nexum-core.com/api/v1/me"


async def get_stats(_: bool = False) -> Dict[str, Any]:
    api_key = os.getenv("NEXUM_TOKEN")
    if not api_key:
        raise MissingCredentialsError(
            "Missing NEXUM_TOKEN — generate one at "
            "nexum-core.com → Paramètres → Clé API and set it in .env."
        )

    headers = {
        "X-API-Key": api_key,
        "Accept": "application/json",
        "User-Agent": default_user_agent,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            resp = await client.get(API_URL)
    except httpx.HTTPError as e:
        raise ScrappingError(f"Failed to reach nexum-core API: {e}")

    if resp.status_code == 401:
        raise ScrappingError("nexum-core: 401 Unauthorized — API key invalid or expired.")
    if resp.status_code >= 400:
        raise ScrappingError(
            f"nexum-core: HTTP {resp.status_code} from {API_URL}: {resp.text[:300]}"
        )

    try:
        data = resp.json()
    except ValueError as e:
        raise ScrappingError(f"nexum-core: response was not JSON: {e}")

    return {
        "raw_upload": float(data.get("uploaded", 0)),
        "raw_download": float(data.get("downloaded", 0)),
        "bonus": float(data.get("bonus_points", 0)),
        } 
