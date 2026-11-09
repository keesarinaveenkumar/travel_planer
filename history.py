"""Search / saved-trip history (ported from src/lib/history.ts).

The original kept this in the browser's localStorage; here it lives in Flask's signed
session cookie, so it is per-browser just like before.
"""
import time

from flask import session

KEY = "narada-history-v1"
MAX_ENTRIES = 30


MAX_PLACE, MAX_STATE = 80, 60


def _place(v):
    return v.strip()[:MAX_PLACE] if isinstance(v, str) else ""


def _state(v):
    if not isinstance(v, str):
        return None
    return v.strip()[:MAX_STATE] or None


def get_history():
    """Entries from the cookie, cleaned — a damaged or hand-edited cookie can never break a page."""
    raw = session.get(KEY, [])
    out = []
    for e in raw if isinstance(raw, list) else []:
        if not isinstance(e, dict):
            continue
        place = _place(e.get("place"))
        if len(place) < 2:
            continue
        ts = e.get("ts")
        out.append({"place": place, "state": _state(e.get("state")), "kind": "trip" if e.get("kind") == "trip" else "search",
                    "ts": int(ts) if isinstance(ts, (int, float)) and not isinstance(ts, bool) else 0})
    return out[:MAX_ENTRIES]


def _save(entries):
    session[KEY] = entries[:MAX_ENTRIES]
    session.permanent = True


def add_history(place, state=None):
    place = _place(place)
    if len(place) < 2:
        return
    h = get_history()
    existing = next((e for e in h if e["place"].lower() == place.lower()), None)
    rest = [e for e in h if e is not existing]
    _save([{
        "place": place,
        "state": _state(state) or (existing or {}).get("state"),
        "kind": "trip" if existing and existing.get("kind") == "trip" else "search",
        "ts": int(time.time() * 1000),
    }] + rest)


def mark_trip(place, state=None):
    place = _place(place)
    if len(place) < 2:
        return
    rest = [e for e in get_history() if e["place"].lower() != place.lower()]
    _save([{"place": place, "state": _state(state), "kind": "trip", "ts": int(time.time() * 1000)}] + rest)


def is_trip(place):
    place = _place(place)
    return any(e["place"].lower() == place.lower() and e["kind"] == "trip" for e in get_history())


def clear_history():
    session.pop(KEY, None)
