"""Trip budget per person, calibrated from published traveller budgets (Google results & travel blogs).

All money is Indian rupees (₹), 2026 price levels. The model is deliberately simple and transparent:

    stay   = rooms × room price per night × nights ÷ travellers   (rooms shared by 2; a solo traveller pays a whole room)
    food   = daily food cost per person × days
    local  = stop-to-stop transport from the itinerary + daily rides (cabs/autos are split by up to 4 travellers)
    entry  = ticket prices from the itinerary (Indian-citizen rates), with a daily floor for safari-type trips
    buffer = 10 % for shopping, tips and small surprises

It does NOT include getting to / from the destination. It is an estimate — real costs change with the traveller.
`compute()` is mirrored line-for-line by `estimate()` in static/js/plan.js, so the page can recalculate instantly.
"""
import re

import recommender

TIERS = ("budget", "comfort", "premium")
TIER_LABELS = {"budget": "Budget", "comfort": "Comfort", "premium": "Premium"}
TIER_NOTES = {
    "budget": "Hostels & guesthouses, local eateries, buses and shared rides",
    "comfort": "3-star hotels, good restaurants, cabs and autos",
    "premium": "4–5★ & heritage stays, fine dining, private cars",
}

TIER_SHORT = {"budget": "Hostels · local eats", "comfort": "3★ hotels · cabs", "premium": "4–5★ · private cars"}

ROOM_SIZE = 2                       # travellers sharing one room
CAB_SIZE = 4                        # travellers sharing one cab / auto
BUFFER = 0.10
TRANSPORT_MULT = (0.7, 1.0, 1.6)    # cheaper local options  ·  as planned  ·  private / AC vehicles
SINGLE_ROOM = (0.65, 0.85, 0.95)    # a solo traveller: dorm bed / single room vs a full double

# Per destination type, for (budget, comfort, premium):
#   stay  = one double room per night      food  = per person per day (all meals + chai/snacks)
#   local = per person per day for rides not between itinerary stops (hotel ↔ first/last stop)
#   floor = minimum paid activities per day (safaris cost more than a ticket line suggests)
RATES = {
    # national guides put budget travel near ₹1,300–4,000/day, mid-range ₹3,400–7,000, high-end ₹7,500–13,500 per person
    "general":   dict(label="trips across India",       stay=(1200, 3500, 9000),  food=(600, 1300, 3000), local=(150, 400, 900),   floor=(0, 0, 0)),
    "metro":     dict(label="big-city trips",           stay=(1500, 4500, 11000), food=(700, 1500, 3500), local=(200, 500, 1100),  floor=(0, 0, 0)),
    # Jaipur: budget rooms ₹1,000–2,000, local meals ~₹500, fine dining up to ₹1,500
    "heritage":  dict(label="heritage-city trips",      stay=(1500, 4000, 10000), food=(800, 1500, 3000), local=(200, 450, 1000),  floor=(0, 0, 0)),
    # Varanasi: hostels ₹400–700, budget hotels ₹800–1,500, mid ₹2,000–5,000, food ₹400–700 budget / ₹800–1,500 mid per day
    "spiritual": dict(label="pilgrimage & spiritual-city trips", stay=(1100, 3000, 8000), food=(550, 1100, 2500), local=(120, 300, 800), floor=(0, 0, 0)),
    # Goa: budget rooms ₹800–1,500, casual meal ~₹800, scooter ₹300–500/day, car with driver ₹3,000–5,000/day
    "beach":     dict(label="beach trips",              stay=(1500, 4500, 11000), food=(700, 1500, 3200), local=(350, 600, 1200),  floor=(0, 0, 0)),
    # Munnar: lodges ₹700–1,000, 3-day packages ₹10,500–15,700; Manali: rooms ₹1,200–4,000, food ₹500–1,500/day
    "hills":     dict(label="hill-station trips",       stay=(1300, 3500, 9000),  food=(650, 1200, 2600), local=(200, 500, 1100),  floor=(0, 0, 0)),
    # Ladakh: guesthouses ₹2,500–3,800 (for two), mid ₹4,000–8,000; taxis ₹3,500–5,500/day; food ₹500–1,200/day
    "highland":  dict(label="high-altitude trips",      stay=(2000, 5000, 11000), food=(750, 1300, 2800), local=(500, 900, 1600),  floor=(0, 0, 0)),
    # Andaman: rooms ₹800–2,000 budget, ₹2,500–6,000 mid; ferries ₹150–975; scuba ₹4,500–6,500
    "islands":   dict(label="island trips",             stay=(2000, 5500, 12000), food=(800, 1500, 3200), local=(400, 800, 1500),  floor=(0, 0, 0)),
    # Ranthambore / Corbett: rooms ₹2,500–5,000, shared canter ~₹3,000 + tax, jungle portion ₹10,000–22,000 pp
    "wildlife":  dict(label="wildlife & safari trips",  stay=(2500, 5500, 12000), food=(700, 1400, 3000), local=(300, 600, 1200),  floor=(1200, 3000, 6000)),
}

# ---------- which kind of destination is it? ----------
_NAMED = (
    ("islands", ("andaman", "port blair", "havelock", "swaraj dweep", "neil island", "lakshadweep", "agatti", "kavaratti")),
    ("wildlife", ("ranthambore", "corbett", "kaziranga", "bandhavgarh", "kanha", "pench", "tadoba", "gir", "sasan gir", "bandipur",
                  "nagarhole", "sundarbans", "periyar", "thekkady", "nameri", "manas", "satpura", "panna", "jawai")),
    ("highland", ("leh", "ladakh", "spiti", "kaza", "nubra", "pangong", "kargil", "tawang", "zuluk", "lachung", "lachen", "gurudongmar")),
    ("spiritual", ("varanasi", "banaras", "kashi", "rishikesh", "haridwar", "ayodhya", "mathura", "vrindavan", "tirupati", "puri",
                   "dwarka", "rameswaram", "madurai", "pushkar", "bodh gaya", "gaya", "shirdi", "amarnath", "kedarnath", "badrinath", "somnath")),
    ("beach", ("goa", "gokarna", "varkala", "kovalam", "pondicherry", "puducherry", "mahabalipuram", "digha", "marari", "alibaug", "tarkarli", "diu", "daman")),
    ("hills", ("munnar", "manali", "shimla", "ooty", "kodaikanal", "darjeeling", "mussoorie", "nainital", "coorg", "madikeri", "wayanad", "kasol",
               "dharamshala", "mcleod", "dalhousie", "gangtok", "shillong", "gulmarg", "pahalgam", "srinagar", "kasauli", "mount abu", "lonavala",
               "mahabaleshwar", "araku", "yercaud", "chikmagalur", "auli", "chopta", "pelling", "kalimpong")),
    ("heritage", ("jaipur", "udaipur", "jodhpur", "jaisalmer", "bikaner", "chittorgarh", "agra", "taj mahal", "fatehpur sikri", "hampi", "khajuraho",
                  "mysuru", "mysore", "amritsar", "lucknow", "gwalior", "orchha", "bhopal", "hyderabad old", "mandu", "ajanta", "ellora", "konark",
                  "mahabalipuram", "thanjavur", "hampi")),
    ("metro", ("delhi", "new delhi", "mumbai", "bengaluru", "bangalore", "kolkata", "chennai", "hyderabad", "pune", "ahmedabad", "gurugram", "gurgaon", "noida")),
)
_NAMED_RE = [(p, re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b", re.I)) for p, names in _NAMED]
_STATE = {
    "Goa": "beach", "Delhi": "metro", "Ladakh": "highland", "Arunachal Pradesh": "highland", "Lakshadweep": "islands",
    "Andaman and Nicobar Islands": "islands", "Himachal Pradesh": "hills", "Uttarakhand": "hills", "Sikkim": "hills",
    "Jammu and Kashmir": "hills", "Meghalaya": "hills",
}
_TAG_ORDER = (("wildlife", "wildlife"), ("snow", "highland"), ("beach", "beach"), ("hills", "hills"), ("spiritual", "spiritual"), ("heritage", "heritage"))


def profile_for(place, state=None):
    """Pick the rate profile: named place → state → themes of the place → general."""
    for profile, rx in _NAMED_RE:
        if rx.search(place or ""):
            return profile
    if state in _STATE:
        return _STATE[state]
    tags = recommender.tags_for(place or "")
    for tag, profile in _TAG_ORDER:
        if tag in tags:
            return profile
    return "general"


# ---------- travel mode (single source of truth for icons + cost sharing) ----------
def travel_mode(text):
    s = (text or "").lower()
    if any(k in s for k in ("flight", "fly", "airport")):
        return "plane"
    if "bus" in s:
        return "bus"
    if any(k in s for k in ("train", "metro", "rail")):
        return "train"
    if any(k in s for k in ("walk", "foot")):
        return "walk"
    return "car"


# ---------- the calculation ----------
def _r10(x):
    return int(x / 10 + 0.5) * 10


def _r100(x):
    return int(x / 100 + 0.5) * 100


def client_model(plan, days, place=None, state=None):
    """Everything the browser needs to recompute the estimate for any traveller count / style."""
    profile = profile_for(place or plan.get("place", ""), state or plan.get("state"))
    rates = RATES[profile]
    shared = fixed = entry = 0
    for d in plan.get("days", []):
        for s in d.get("stops", []):
            entry += s.get("entryFee", 0)
            if travel_mode(s.get("travel")) == "car":
                shared += s.get("transportCost", 0)
            else:
                fixed += s.get("transportCost", 0)
    return {
        "profile": profile, "label": rates["label"], "days": days, "nights": max(days - 1, 0),
        "entry": entry, "stopShared": shared, "stopFixed": fixed,
        "roomSize": ROOM_SIZE, "cabSize": CAB_SIZE, "buffer": BUFFER,
        "single": dict(zip(TIERS, SINGLE_ROOM)),
        "rates": {t: {"stay": rates["stay"][i], "food": rates["food"][i], "local": rates["local"][i], "tmult": TRANSPORT_MULT[i]}
                  for i, t in enumerate(TIERS)},
        "floor": dict(zip(TIERS, rates["floor"])),
    }


def compute(m, travelers=2, style="comfort"):
    """Per-person estimate. Mirrors `estimate()` in static/js/plan.js — keep the two in step."""
    n = max(1, int(travelers))
    r = m["rates"][style]
    rooms = -(-n // m["roomSize"])                                   # ceil
    single = m["single"][style] if n == 1 else 1
    cab = (-(-n // m["cabSize"])) / n
    parts = {
        "stay": _r10((rooms * r["stay"] * single * m["nights"]) / n) if m["nights"] else 0,
        "food": _r10(r["food"] * m["days"]),
        "local": _r10(r["tmult"] * (m["stopShared"] * cab + m["stopFixed"]) + r["local"] * m["days"] * cab),
        "entry": _r10(max(m["entry"], m["floor"][style] * m["days"])),
    }
    subtotal = sum(parts.values())
    parts["buffer"] = _r10(subtotal * m["buffer"])
    total = subtotal + parts["buffer"]
    per_person = _r100(total)
    return {
        "travelers": n, "style": style, "parts": parts, "total": total,
        "per_person": per_person, "low": _r100(total * 0.85), "high": _r100(total * 1.2),
        "group": per_person * n, "per_day": _r100(total / max(m["days"], 1)),
    }


# ---------- where the numbers come from (shown in the app) ----------
SOURCES = {
    "tis": ("How much does it cost to travel in India?", "Travel India Smart", "https://www.travelindiasmart.com/trip-planning/cost-of-travel-india"),
    "ind": ("Cost of travelling in India by traveller type", "India Someday", "https://indiasomeday.com/?p=2780"),
    "agoda": ("5-day Goa trip cost", "Agoda travel guides", "https://www.agoda.com/travel-guides/india/goa/budget-bliss-5-day-goa-trip-cost-under-%E2%82%B930000"),
    "tata": ("Goa trip package cost", "Tata Capital blog", "https://tatacapital.com/blog/loan-for-travel/goa-trip-package-cost"),
    "jaipur": ("Jaipur trip cost guide", "Triveni Cabs", "https://www.trivenicabs.in/jaipur-trip-cost-from-delhi"),
    "munnar": ("Munnar budget travel guide", "TrekGo", "https://trekgo.in/blog/munnar-budget-travel-guide"),
    "manali": ("Manali trip cost", "Travel Coffee", "https://travelcoffee.in/blog/manali-trip-cost"),
    "ladakh": ("Cost or budget of a Leh Ladakh trip", "Discover with Dheeraj", "https://discoverwithdheeraj.com/how-to-calculate-cost-or-budget-for-leh-ladakh-trip/"),
    "andaman": ("Andaman travel budget guide", "Go2Andaman", "https://www.go2andaman.com/andaman-travel-budget-guide/"),
    "sotc": ("How much does an Andaman trip cost?", "SOTC", "https://www.sotc.in/blog/?p=11822"),
    "varanasi": ("Varanasi trip cost guide", "Triveni Cabs", "https://www.trivenicabs.in/varanasi-trip-cost-from-delhi"),
    "solo": ("Varanasi at a glance: daily budgets", "SoloGuides", "https://sologuides.com/varanasi"),
    "wild": ("Indian wildlife safaris on a budget", "Curly Tales", "https://curlytales.com/africa-safari-too-expensiveindian-jungle-escapes-for-a-wild-holiday-under/"),
    "taj": ("Ranthambore tiger safari prices", "Taj Hotels", "https://www.tajhotels.com/en-in/hotels/taj-sawai-ranthambore/places-to-visit/ranthambore-tiger-safari"),
}
_SOURCE_IDS = {
    "general": ("tis", "ind"), "metro": ("tis", "ind"), "heritage": ("jaipur", "tis"), "spiritual": ("varanasi", "solo"),
    "beach": ("agoda", "tata"), "hills": ("munnar", "manali"), "highland": ("ladakh", "ind"), "islands": ("andaman", "sotc"),
    "wildlife": ("wild", "taj"),
}


def sources_for(profile):
    """The pages this profile's rates were checked against, plus the national baselines."""
    ids = list(_SOURCE_IDS.get(profile, ())) + [i for i in ("tis", "ind") if i not in _SOURCE_IDS.get(profile, ())]
    return [dict(zip(("title", "site", "url"), SOURCES[i])) for i in ids]


def google_url(place):
    from urllib.parse import quote_plus
    return "https://www.google.com/search?q=" + quote_plus(f"{place} trip budget per person travel blog")
