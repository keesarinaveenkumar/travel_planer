"""Content-based recommendation model (ported from src/lib/recommender.ts).

Each place becomes a feature vector (travel themes + region). A user profile vector is built
from past searches and saved trips (trips weigh more, recent activity weighs more). Places are
ranked by cosine similarity to the profile, with a popularity prior and a per-state diversity cap.
"""
import math
import re

from data import ALL_PLACES, STATES

TAGS = ["beach", "hills", "heritage", "spiritual", "wildlife", "adventure", "lakes", "city", "nature", "snow", "culture", "food"]
REGIONS = ["north", "south", "east", "west", "northeast", "central", "islands"]

REGION_OF = {
    "Andhra Pradesh": "south",
    "Karnataka": "south",
    "Kerala": "south",
    "Tamil Nadu": "south",
    "Telangana": "south",
    "Puducherry": "south",
    "Arunachal Pradesh": "northeast",
    "Assam": "northeast",
    "Manipur": "northeast",
    "Meghalaya": "northeast",
    "Mizoram": "northeast",
    "Nagaland": "northeast",
    "Sikkim": "northeast",
    "Tripura": "northeast",
    "Bihar": "east",
    "Jharkhand": "east",
    "Odisha": "east",
    "West Bengal": "east",
    "Goa": "west",
    "Gujarat": "west",
    "Maharashtra": "west",
    "Rajasthan": "west",
    "Dadra and Nagar Haveli and Daman and Diu": "west",
    "Chhattisgarh": "central",
    "Madhya Pradesh": "central",
    "Haryana": "north",
    "Himachal Pradesh": "north",
    "Punjab": "north",
    "Uttar Pradesh": "north",
    "Uttarakhand": "north",
    "Delhi": "north",
    "Chandigarh": "north",
    "Jammu and Kashmir": "north",
    "Ladakh": "north",
    "Andaman and Nicobar Islands": "islands",
    "Lakshadweep": "islands",
}

KEYWORDS = [
    (re.compile(r"beach|island|goa|kovalam|varkala|digha|gokarna|puri|diu|daman|havelock|neil|agatti|bangaram|kavaratti|gopalpur|visakhapatnam|kanyakumari|mahabalipuram", re.I), ["beach", "nature"]),
    (re.compile(r"hill|valley|manali|shimla|ooty|kodaikanal|munnar|coorg|darjeeling|mussoorie|nainital|dalhousie|shillong|gangtok|pelling|kalimpong|mount abu|chikmagalur|araku|pachmarhi|saputara|netarhat|mainpat|lonavala|mahabaleshwar|wayanad|tawang|bomdila|dirang|ziro|kohima|aizawl|champhai|dzukou|morni|jampui|ukhrul|cherrapunji|mawsynram", re.I), ["hills", "nature"]),
    (re.compile(r"fort|palace|tomb|minar|caves|hampi|khajuraho|konark|taj|agra|red fort|charminar|golconda|orchha|badami|sanchi|nalanda|ajanta|ellora|rani ki vav|gwalior|jaipur|udaipur|jodhpur|jaisalmer|bikaner|mysuru|thanjavur|warangal|sivasagar|unakoti|neermahal|ujjayanta|cellular|india gate|old goa|lepakshi|gandikota|sirpur|vikramshila|vaishali|chandni", re.I), ["heritage", "culture"]),
    (re.compile(r"temple|tirupati|varanasi|haridwar|rishikesh|kedarnath|badrinath|vaishno|somnath|dwarka|shirdi|ujjain|mathura|vrindavan|ayodhya|prayagraj|bodh gaya|rameswaram|madurai|amritsar|golden|kamakhya|deoghar|srisailam|puri|pushkar|udupi|rajgir|anandpur|kurukshetra|nashik|akshardham|lotus|majuli|auroville|namchi", re.I), ["spiritual", "culture"]),
    (re.compile(r"national park|sanctuary|kaziranga|gir|ranthambore|corbett|sundarbans|bandhavgarh|kanha|manas|betla|simlipal|namdapha|keibul|sultanpur|thekkady|barnawapara", re.I), ["wildlife", "nature"]),
    (re.compile(r"rishikesh|spiti|leh|ladakh|khardung|nubra|bir billing|kasol|auli|gulmarg|dudhsagar|dzukou|chitrakote|hundru|dawki|tsomgo|nathu la|kargil|sonamarg|living root|havelock", re.I), ["adventure"]),
    (re.compile(r"lake|loktak|chilika|dal|pangong|tso|sukhna|kumarakom|alleppey|nagarjuna|tsomgo|backwater", re.I), ["lakes", "nature"]),
    (re.compile(r"mumbai|delhi|kolkata|chennai|bengaluru|hyderabad|pune|ahmedabad|lucknow|gurugram|chandigarh|patna|ranchi|raipur|bhubaneswar|guwahati|imphal|agartala|ludhiana|jamshedpur|kochi|panaji|vijayawada|dimapur|port blair|itanagar|silvassa|rock garden|rose garden", re.I), ["city", "food"]),
    (re.compile(r"snow|gulmarg|auli|kedarnath|badrinath|spiti|leh|khardung|nathu la|tawang|lachung|yumthang|sonamarg|pahalgam|manali|tso moriri|pangong", re.I), ["snow"]),
    (re.compile(r"lucknow|hyderabad|amritsar|kolkata|delhi|chandni|mumbai|chennai|old goa|kochi|puducherry|patiala|indore|jaipur", re.I), ["food", "culture"]),
]

POPULAR = {"Taj Mahal", "Agra", "Jaipur", "Goa", "Manali", "Munnar", "Varanasi", "Leh", "Udaipur", "Rishikesh", "Hampi", "Darjeeling", "Srinagar", "Gangtok", "Alleppey", "Ooty", "Mysuru", "Shimla", "Kaziranga National Park", "Andaman", "Havelock Island", "Golden Temple", "Jaisalmer", "Mumbai", "Kochi"}
_PLACE_STATE = {p["place"].lower(): p["state"] for p in ALL_PLACES}


def tags_for(place):
    found = set()
    for pattern, tags in KEYWORDS:
        if pattern.search(place):
            found.update(tags)
    return found or {"culture", "nature"}


def vector_for(place, state):
    t = tags_for(place)
    v = [1.0 if tag in t else 0.0 for tag in TAGS]
    region = REGION_OF.get(state) if state else None
    return v + [0.6 if r == region else 0.0 for r in REGIONS]


def cosine(a, b):
    d = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a)
    nb = sum(y * y for y in b)
    return d / math.sqrt(na * nb) if na and nb else 0.0


def state_of(place):
    return _PLACE_STATE.get(place.lower())


def _weight(entry, i):
    return (3 if entry.get("kind") == "trip" else 1) * (0.85 ** i)


def recommend_places(history, limit=6):
    """history: list of {"place", "state", "kind", "ts"}, newest first."""
    if not history:
        return []
    profile = [0.0] * (len(TAGS) + len(REGIONS))
    tag_weight = {}
    for i, h in enumerate(history):
        w = _weight(h, i)
        v = vector_for(h["place"], h.get("state") or state_of(h["place"]))
        for k, x in enumerate(v):
            profile[k] += x * w
        for t in tags_for(h["place"]):
            tag_weight[t] = tag_weight.get(t, 0) + w

    seen = {h["place"].lower() for h in history}
    scored = []
    for p in ALL_PLACES:
        if p["place"].lower() in seen:
            continue
        sim = cosine(profile, vector_for(p["place"], p["state"]))
        score = sim + (0.08 if p["place"] in POPULAR else 0)
        shared = sorted((t for t in tags_for(p["place"]) if t in tag_weight), key=lambda t: -tag_weight[t])
        scored.append({"place": p["place"], "state": p["state"], "score": score, "tags": shared})
    scored.sort(key=lambda s: -s["score"])

    per_state, out = {}, []
    for s in scored:
        if per_state.get(s["state"], 0) >= 2:
            continue
        per_state[s["state"]] = per_state.get(s["state"], 0) + 1
        pct = round(s["score"] * 100)
        s["reason"] = (f"You enjoy {' & '.join(s['tags'][:2])} places — {pct}% match" if s["tags"]
                       else f"{pct}% match with your travel style")
        out.append(s)
        if len(out) >= limit:
            break
    return out


def top_interests(history):
    w = {}
    for i, h in enumerate(history):
        for t in tags_for(h["place"]):
            w[t] = w.get(t, 0) + _weight(h, i)
    return [t for t, _ in sorted(w.items(), key=lambda kv: -kv[1])[:4]]


STATE_COUNT = len(STATES)
