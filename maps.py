"""Google Maps helpers (ported from src/lib/maps.server.ts): place photos and real hotels.

Calls the Google Places API (New) directly. Env: GOOGLE_MAPS_API_KEY.
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor

import requests

PLACES = "https://places.googleapis.com/v1"
_photo_cache = {}
_hotel_cache = {}
CACHE_LIMIT = 400


def _remember(cache, key, value):
    """Store in a cache that can never grow without bound."""
    if len(cache) >= CACHE_LIMIT:
        cache.pop(next(iter(cache)))
    cache[key] = value
    return value

PRICE_LABELS = {
    "PRICE_LEVEL_INEXPENSIVE": "Budget · ₹",
    "PRICE_LEVEL_MODERATE": "Mid-range · ₹₹",
    "PRICE_LEVEL_EXPENSIVE": "Upscale · ₹₹₹",
    "PRICE_LEVEL_VERY_EXPENSIVE": "Luxury · ₹₹₹₹",
}


class MapsError(Exception):
    pass


def _key():
    k = os.getenv("GOOGLE_MAPS_API_KEY")
    if not k:
        raise MapsError("Google Maps is not connected.")
    return k


def _headers(mask=None):
    h = {"X-Goog-Api-Key": _key(), "Content-Type": "application/json"}
    if mask:
        h["X-Goog-FieldMask"] = mask
    return h


def _check(r):
    if r.status_code == 403:
        raise MapsError("Google Maps request was denied. Check the Google Maps connection.")
    if not r.ok:
        raise MapsError(f"Google Maps request failed [{r.status_code}]")
    return r.json()


def _photo_uri(photo_name, width=1200):
    try:
        r = requests.get(f"{PLACES}/{photo_name}/media", params={"maxWidthPx": width, "skipHttpRedirect": "true"},
                         headers=_headers(), timeout=15)
        return r.json().get("photoUri") if r.ok else None
    except (requests.RequestException, ValueError):
        return None


def _search(query, mask, **extra):
    body = {"textQuery": query, "regionCode": "IN", **extra}
    try:
        r = requests.post(f"{PLACES}/places:searchText", headers=_headers(mask), json=body, timeout=15)
    except requests.RequestException:
        raise MapsError("Google Maps could not be reached.")
    return _check(r)


def find_photo(query):
    key = query.lower()
    if key in _photo_cache:
        return _photo_cache[key]
    j = _search(query, "places.photos", pageSize=1)
    places = j.get("places") or [{}]
    photos = places[0].get("photos") or []
    uri = _photo_uri(photos[0]["name"]) if photos else None
    return _remember(_photo_cache, key, uri)


def find_hotels(place):
    key = place.lower()
    if key in _hotel_cache:
        return _hotel_cache[key]
    mask = ("places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.priceLevel,"
            "places.priceRange,places.googleMapsUri,places.photos")
    j = _search(f"hotels in {place}, India", mask, includedType="lodging", pageSize=6)
    hotels = []
    for p in j.get("places", []):
        pr = p.get("priceRange") or {}
        start, end = pr.get("startPrice") or {}, pr.get("endPrice") or {}
        photos = p.get("photos") or []
        hotels.append({
            "name": (p.get("displayName") or {}).get("text", "Hotel"),
            "address": p.get("formattedAddress", ""),
            "rating": p.get("rating"),
            "reviews": p.get("userRatingCount", 0),
            "priceLevel": p.get("priceLevel"),
            "priceFrom": int(start["units"]) if start.get("units") else None,
            "priceTo": int(end["units"]) if end.get("units") else None,
            "currency": start.get("currencyCode"),
            "mapsUrl": p.get("googleMapsUri", ""),
            "photo": _photo_uri(photos[0]["name"], 600) if photos else None,
        })
    return _remember(_hotel_cache, key, hotels)


def wiki_photo(name):
    """Wikipedia fallback used when Google has no photo (same query as PlaceImage.tsx)."""
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php", timeout=10,
                         headers={"User-Agent": "narada-yatra/1.0"},
                         params={"action": "query", "generator": "search", "gsrsearch": f"{name} India", "gsrlimit": 3,
                                 "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 1200, "format": "json"})
        if not r.ok:
            return None
        pages = sorted(((r.json().get("query") or {}).get("pages") or {}).values(), key=lambda p: p.get("index", 0))
        return next((p["thumbnail"]["source"] for p in pages if p.get("thumbnail")), None)
    except (requests.RequestException, ValueError):
        return None


# ---------- several photos per place (gallery) ----------
_photos_cache = {}
_UA = {"User-Agent": "narada-yatra/1.0"}


def _photo_item(photo, width=1000):
    uri = _photo_uri(photo["name"], width)
    if not uri:
        return None
    author = (photo.get("authorAttributions") or [{}])[0].get("displayName")
    return {"url": uri, "credit": author or "Google Maps contributor", "source": "Google Maps"}


def find_photos(query, n=5):
    """Up to n photos of the best Google match for `query`, with author credit."""
    j = _search(query, "places.photos", pageSize=1)
    photos = ((j.get("places") or [{}])[0].get("photos") or [])[:n]
    if not photos:
        return []
    with ThreadPoolExecutor(max_workers=len(photos)) as ex:
        return [i for i in ex.map(_photo_item, photos) if i]


def wiki_photos(name, n=5):
    """Wikimedia Commons fallback: up to n freely licensed photos."""
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", timeout=10, headers=_UA, params={
            "action": "query", "generator": "search", "gsrsearch": f"{name} India", "gsrnamespace": 6,
            "gsrlimit": n * 3, "prop": "imageinfo", "iiprop": "url|mime|extmetadata", "iiurlwidth": 1000, "format": "json"})
        if not r.ok:
            return []
        pages = sorted(((r.json().get("query") or {}).get("pages") or {}).values(), key=lambda p: p.get("index", 0))
        out = []
        for p in pages:
            ii = (p.get("imageinfo") or [{}])[0]
            if ii.get("mime") not in ("image/jpeg", "image/png") or not ii.get("thumburl"):
                continue
            artist = re.sub(r"<[^>]+>", "", ((ii.get("extmetadata") or {}).get("Artist") or {}).get("value", "")).strip()
            out.append({"url": ii["thumburl"], "credit": artist[:60] or "Wikimedia Commons", "source": "Wikimedia Commons"})
            if len(out) >= n:
                break
        return out
    except (requests.RequestException, ValueError):
        return []


def photos_for(query, name, n=5):
    """Google photos first; top up from Wikimedia Commons when Google has fewer than 3."""
    key = (query.lower(), name.lower(), n)
    if key in _photos_cache:
        return _photos_cache[key]
    items = []
    try:
        items = find_photos(query, n)
    except MapsError:
        pass
    if len(items) < min(3, n):
        seen = {i["url"] for i in items}
        items += [i for i in wiki_photos(name, n) if i["url"] not in seen][: n - len(items)]
    return _remember(_photos_cache, key, items)


def cached_photos(query, name, n=5):
    """Photos already fetched for this place (by the galleries), or None — never makes a network call."""
    return _photos_cache.get((query.lower(), name.lower(), n))
