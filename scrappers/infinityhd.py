"""
infinityhd.net scraper.

Uses the /api/user?api_token=<token> endpoint.

Required env var:
    INFINITYHD_TOKEN
"""

import urllib.request
import urllib.error
import os
import json
import logging
from typing import Dict, Any

from util import default_user_agent, parse_bytes, MissingCredentialsError, ScrappingError

logger = logging.getLogger(__name__)

USER_STATS_URL = "https://infinityhd.net/api/user"


async def get_stats(_: bool = False) -> Dict[str, Any]:
    try:
        token = os.getenv("INFINITYHD_TOKEN")
        if not token:
            raise MissingCredentialsError("Missing INFINITYHD_TOKEN")

        url = f"{USER_STATS_URL}?api_token={token}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": default_user_agent})
            with urllib.request.urlopen(req) as response:
                api_data = json.loads(response.read())
        except urllib.error.HTTPError as e:
            raise ScrappingError(f"Failed to get InfinityHD stats: HTTP {e.code}, Reason {e.reason}")
        except urllib.error.URLError as e:
            raise ScrappingError(e)

        return {
            "raw_upload": parse_bytes(api_data.get("uploaded", "0")),
            "raw_download": parse_bytes(api_data.get("downloaded", "0")),
            "bonus": float(api_data.get("seedbonus", 0)),
        }
    except (MissingCredentialsError, ScrappingError):
        raise
    except Exception as e:
        raise ScrappingError(e)
