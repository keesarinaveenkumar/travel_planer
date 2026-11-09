"""Optional live "what travellers spend" results from Google (Programmable Search JSON API).

Set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX to enable. Without them the app simply offers a link that opens
the same search on google.com — nothing breaks.
"""
import os
from urllib.parse import urlparse

import requests

_cache = {}
CACHE_LIMIT = 200


def configured():
    return bool(os.getenv("GOOGLE_SEARCH_API_KEY") and os.getenv("GOOGLE_SEARCH_CX"))


def search_guides(place, n=4):
    """Up to n travel-blog results about the cost of visiting `place`. Returns [] on any problem."""
    if not configured():
        return []
    key = (place.lower(), n)
    if key in _cache:
        return _cache[key]
    try:
        r = requests.get("https://www.googleapis.com/customsearch/v1", timeout=10, params={
            "key": os.environ["GOOGLE_SEARCH_API_KEY"], "cx": os.environ["GOOGLE_SEARCH_CX"], "num": n, "gl": "in", "safe": "active",
            "q": f"{place} trip budget per person cost travel blog",
        })
        items = r.json().get("items", []) if r.ok else []
    except (requests.RequestException, ValueError):
        return []
    out = []
    for it in items[:n]:
        url = it.get("link", "")
        if urlparse(url).scheme not in ("http", "https"):
            continue
        out.append({"title": str(it.get("title", ""))[:140], "site": str(it.get("displayLink", ""))[:60],
                    "snippet": " ".join(str(it.get("snippet", "")).split())[:220], "url": url})
    if len(_cache) >= CACHE_LIMIT:
        _cache.pop(next(iter(_cache)))
    _cache[key] = out
    return out
