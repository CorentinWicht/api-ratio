import urllib.request
import urllib.error
import os
import json
import logging
from typing import Dict, Any

from util import default_user_agent, parse_bytes, MissingCredentialsError, ScrappingError

logger = logging.getLogger(__name__)

USER_STATS_URL = "https://tracker.teamflix.cc/api/user"


async def get_stats(_: bool) -> Dict[str, Any]:
    try:
        res: Dict[str, Any] = {"ratio": "N/A", "upload": "N/A", "download": "N/A"}
        token = os.getenv("TEAMFLIX_TOKEN")
        if not token:
            raise MissingCredentialsError("Missing TeamFlix api token (TEAMFLIX_TOKEN)")

        url = f"{USER_STATS_URL}?api_token={token}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": default_user_agent})
            with urllib.request.urlopen(req) as response:
                api_data = json.loads(response.read())
        except urllib.error.HTTPError as e:
            raise ScrappingError(f"Failed to get TeamFlix stats: HTTP {e.code}, Reason {e.reason}")
        except urllib.error.URLError as e:
            raise ScrappingError(e)

        up = parse_bytes(api_data.get("uploaded", "0"))
        dl = parse_bytes(api_data.get("downloaded", "0"))
        res["raw_upload"] = up
        res["raw_download"] = dl
        res["bonus"] = float(api_data.get("seedbonus", 0))
        return res
    except (MissingCredentialsError, ScrappingError):
        raise
    except Exception as e:
        raise ScrappingError(e)
