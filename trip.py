"""Trip planner (ported from src/lib/trip.functions.ts)."""
from client import ask_json

SYSTEM = "You are an expert Indian travel planner. Only cover destinations inside India. Reply ONLY with valid JSON, no markdown."

PROMPT = '''Plan a {days}-day trip to "{place}", India. Interests: {interests}.
Order each day's stops by geographic proximity (nearest first, minimal back-tracking). For every stop give a realistic clock time (e.g. "09:00 AM"), how long to spend, distance in km from the previous stop (0 for the first) and travel mode/time.
Also give realistic per-person costs in Indian rupees (integers): entryFee (official Indian-citizen ticket price, 0 if free), transportCost (auto/cab/bus fare from previous stop, 0 for first), mealCost (typical meal/snack spend at or near this stop, 0 if none).
Return JSON with exactly these keys:
{{"place":string,"state":string,"overview":string (2-3 sentences),"bestSeason":string,"lat":number,"lng":number,
"days":[{{"day":number,"title":string,"stops":[{{"name":string,"time":string,"durationHrs":number,"distanceKm":number,"travel":string,"note":string,"entryFee":number,"transportCost":number,"mealCost":number}}]}}],
"foods":[6 famous local dishes: {{"name":string,"description":string,"where":string famous eatery/area}}],
"shopping":[4-5: {{"area":string,"buy":string,"tip":string}}],
"mustVisit":[top 6 sights],"tips":[4 short practical tips]}}'''

COSTS = ("entryFee", "transportCost", "mealCost")


MAX_DAYS, MAX_STOPS, MAX_ITEMS = 10, 12, 12            # keeps every page and PDF a sensible size
NAME_LEN, LINE_LEN, PARA_LEN = 120, 240, 700


def _money(v):
    try:
        return max(0, min(round(float(v)), 10_000_000))
    except (TypeError, ValueError, OverflowError):
        return 0


def _text(v, default="", limit=LINE_LEN):
    if isinstance(v, str):
        return v.strip()[:limit]
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)[:limit]
    return default


def _num(v, default=0):
    try:
        n = float(v)
        return int(n) if n == int(n) else round(n, 1)
    except (TypeError, ValueError, OverflowError):
        return default


def _dicts(v, limit=MAX_ITEMS):
    return [x for x in v if isinstance(x, dict)][:limit] if isinstance(v, list) else []


def _strs(v):
    if not isinstance(v, list):
        return []
    return [s for s in (_text(x) for x in v if isinstance(x, (str, int, float))) if s][:MAX_ITEMS]


def normalize_plan(raw, place):
    """Return a plan in a shape the pages and the PDF can always render, whatever `raw` contains.

    Used for the planner's answer and for a plan the browser posts back to be exported as a PDF.
    """
    raw = raw if isinstance(raw, dict) else {}
    plan = {
        "place": _text(raw.get("place"), limit=NAME_LEN) or place,
        "state": _text(raw.get("state"), limit=NAME_LEN) or "India",
        "overview": _text(raw.get("overview"), limit=PARA_LEN),
        "bestSeason": _text(raw.get("bestSeason")),
        "mustVisit": _strs(raw.get("mustVisit")),
        "tips": _strs(raw.get("tips")),
        "foods": [{"name": _text(f.get("name"), "Local dish", NAME_LEN), "description": _text(f.get("description"), limit=PARA_LEN),
                   "where": _text(f.get("where"))} for f in _dicts(raw.get("foods"))],
        "shopping": [{"area": _text(s.get("area"), "Local market", NAME_LEN), "buy": _text(s.get("buy")), "tip": _text(s.get("tip"), limit=PARA_LEN)}
                     for s in _dicts(raw.get("shopping"))],
        "days": [],
    }
    totals = {c: 0 for c in COSTS}
    for idx, d in enumerate(_dicts(raw.get("days"), MAX_DAYS), 1):
        day = {"day": int(_num(d.get("day"), idx)) or idx, "title": _text(d.get("title"), f"Day {idx}", NAME_LEN), "stops": []}
        for s in _dicts(d.get("stops"), MAX_STOPS):
            stop = {"name": _text(s.get("name"), "Stop", NAME_LEN), "time": _text(s.get("time"), limit=40), "durationHrs": _num(s.get("durationHrs")),
                    "distanceKm": _num(s.get("distanceKm")), "travel": _text(s.get("travel")), "note": _text(s.get("note"), limit=PARA_LEN)}
            for c in COSTS:
                stop[c] = _money(s.get(c))
                totals[c] += stop[c]
            day["stops"].append(stop)
        day["total"] = sum(s[c] for s in day["stops"] for c in COSTS)
        plan["days"].append(day)
    totals["total"] = sum(totals[c] for c in COSTS)
    plan["totals"] = totals
    return plan


def plan_trip(place: str, days: int, interests: str = "") -> dict:
    """Ask the planner for an itinerary and return it in a shape the pages can always render."""
    return normalize_plan(ask_json(SYSTEM, PROMPT.format(days=days, place=place, interests=interests or "general sightseeing")), place)
