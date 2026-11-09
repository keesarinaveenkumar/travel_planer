"""Smart packing checklist: what to pack for *this* destination, season and trip length."""
import re

import recommender

_SEASON = {
    "rain": re.compile(r"monsoon|rain", re.I),                  # only when the season text says so — most "best seasons" are dry
    "cold": re.compile(r"winter|cold|snow|\b(?:nov|dec|jan|feb)\w*", re.I),
    "hot": re.compile(r"summer|hot|\b(?:mar|apr|may)\w*", re.I),
}


def _slug(label):
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def build(place, days, season="", tags=None):
    """Return [{"title", "items": [{"id", "label", "note"}]}], tailored by themes (beach, hills, wildlife…) and season."""
    t = set(tags) if tags is not None else set(recommender.tags_for(place))
    rain, cold, hot = (bool(rx.search(season or "")) for rx in _SEASON.values())
    tropical = bool(t & {"beach"})                              # warm all year, even in Nov–Feb
    cold = ("snow" in t) or (cold and not tropical)
    hot = hot or tropical
    sunny = hot or bool(t & {"beach", "heritage", "wildlife"}) or "snow" in t

    docs = [
        ("Photo ID (Aadhaar, passport or licence)", "Carry the original and keep a photo on your phone"),
        ("Tickets & hotel bookings", "Save offline copies in case the signal drops"),
        ("Cash in small notes + UPI ready", "Small stalls and autos often don't take cards"),
        ("Emergency contacts written down", ""),
    ]
    if "wildlife" in t:
        docs.append(("Safari booking & matching ID", "Permits are checked against your ID at the gate"))

    health = [
        ("Personal medicines & prescriptions", ""),
        ("Basic first-aid: plasters, ORS, pain relief", ""),
        ("Hand sanitiser & wet wipes", ""),
        ("Reusable water bottle", "Refill instead of buying plastic"),
    ]
    if sunny:
        health.append(("Sunscreen & lip balm", ""))
    if t & {"beach", "wildlife", "lakes"} or rain:
        health.append(("Mosquito repellent", ""))
    if t & {"hills", "snow"}:
        health.append(("Motion-sickness tablets", "Mountain roads wind a lot"))
    if "snow" in t:
        health.append(("Altitude precautions (ask your doctor)", "Go slow on day one and drink plenty of water"))

    clothes = [("Comfortable walking shoes", "You'll be on your feet at most stops"), ("Innerwear & sleepwear", ""),
               ("Comfortable everyday clothes", "Easy layers you can mix and match")]
    if hot or not cold:
        clothes.append(("Light, breathable cotton clothes", ""))
    if t & {"hills"} or cold:
        clothes.append(("Warm jacket or fleece", "Evenings get cool in the hills and in winter"))
    if "snow" in t:
        clothes += [("Thermals, gloves, cap & scarf", ""), ("Waterproof boots with good grip", "")]
    if "beach" in t:
        clothes += [("Swimwear & quick-dry towel", ""), ("Flip-flops", "")]
    if t & {"spiritual", "heritage"}:
        clothes += [("Modest outfit for temples", "Shoulders and knees covered"), ("Easy slip-on footwear", "Shoes come off at many temples")]
    if "wildlife" in t:
        clothes += [("Earth-tone clothes (no bright colours)", "Bright colours can spook wildlife")]
    if sunny:
        clothes.append(("Hat & sunglasses", ""))
    if rain:
        clothes += [("Rain jacket or compact umbrella", ""), ("Quick-dry spare clothes", "")]
    if days >= 6:
        clothes.append(("Laundry bag & detergent sheets", "A week or more: wash once and pack lighter"))

    gadgets = [("Phone & charger", ""), ("Power bank", "Long days of maps and photos drain batteries"), ("Offline maps downloaded", "Mountains and islands lose signal")]
    if t & {"heritage", "wildlife", "beach", "hills", "snow", "nature"}:
        gadgets.append(("Camera", "Check the memory card and battery"))
    if "wildlife" in t:
        gadgets.append(("Binoculars", ""))
    if t & {"beach", "lakes"} or rain:
        gadgets.append(("Waterproof pouch for phone & valuables", ""))
    if cold:
        gadgets.append(("Keep a power bank warm", "Cold drains batteries fast"))

    seen, groups = set(), []
    for title, rows in (("Documents & money", docs), ("Health & hygiene", health), ("Clothes & shoes", clothes), ("Gadgets", gadgets)):
        items = []
        for label, note in rows:
            i = _slug(label)
            if i not in seen:
                seen.add(i)
                items.append({"id": i, "label": label, "note": note})
        groups.append({"title": title, "items": items})
    return groups
