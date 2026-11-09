"""NARADA YATRA — Smart Travel Planner for India (Flask port of the TanStack Start app)."""
import os
import secrets
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory, url_for


def _load_env(path=".env"):
    p = Path(__file__).with_name(path)
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

import history as hist  # noqa: E402  (needs env loaded first for consistency)
import budget  # noqa: E402
import guides  # noqa: E402
import maps  # noqa: E402
import packing  # noqa: E402
import pdfgen  # noqa: E402
from client import PlannerError  # noqa: E402
from data import ALL_PLACES, STATES, STATES_BY_SLUG  # noqa: E402
from recommender import REGION_OF, recommend_places, top_interests  # noqa: E402
from trip import normalize_plan, plan_trip  # noqa: E402
from util import inr, slug  # noqa: E402

app = Flask(__name__)
def load_secret_key(path=None):
    """SECRET_KEY if you set a real one; otherwise a random key created once and kept in .secret_key."""
    env = os.getenv("SECRET_KEY")
    if env and env != "change-me":
        return env
    p = Path(path) if path else Path(__file__).with_name(".secret_key")
    try:
        if p.exists() and len(p.read_text().strip()) >= 32:
            return p.read_text().strip()
        key = secrets.token_hex(32)
        p.write_text(key)
        try:
            p.chmod(0o600)
        except OSError:
            pass
        return key
    except OSError:                      # read-only folder: a fresh key for this run
        return secrets.token_hex(32)


app.secret_key = load_secret_key()
app.config["MAX_CONTENT_LENGTH"] = 500_000          # the biggest request the app ever expects is a plan posted for the PDF
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 365

FEATURED = ["Taj Mahal", "Hampi", "Munnar", "Jaisalmer", "Varanasi", "Leh"]


# ---------- template helpers ----------
def _map_key():
    return os.getenv("GOOGLE_MAPS_BROWSER_KEY")


def map_src(q, zoom=13):
    key = _map_key()
    if key:
        return f"https://www.google.com/maps/embed/v1/place?key={key}&q={quote(q)}&zoom={zoom}&region=IN"
    return f"https://maps.google.com/maps?q={quote(q)}&z={zoom}&output=embed"


def dir_src(frm, to):
    key = _map_key()
    if key:
        return f"https://www.google.com/maps/embed/v1/directions?key={key}&origin={quote(frm)}&destination={quote(to)}&region=IN"
    return map_src(to)


def asset(path):
    """Static file URL with a version stamp, so browsers never keep serving an outdated CSS/JS/icon."""
    try:
        v = int((Path(app.static_folder) / path).stat().st_mtime)
    except OSError:
        v = 0
    return url_for("static", filename=path, v=v)


app.jinja_env.globals["asset"] = asset
app.jinja_env.filters["inr"] = inr
app.jinja_env.filters["price_label"] = lambda v: maps.PRICE_LABELS.get(v, v)
REGIONS = ["north", "south", "east", "west", "northeast", "central", "islands"]
app.jinja_env.globals.update(map_src=map_src, dir_src=dir_src, inr=inr, STATES=STATES, REGIONS=REGIONS, travel_mode=budget.travel_mode,
                             TIERS=budget.TIERS, TIER_LABELS=budget.TIER_LABELS, TIER_NOTES=budget.TIER_NOTES, TIER_SHORT=budget.TIER_SHORT,
                             region_of=lambda name: REGION_OF.get(name, ""))


@app.context_processor
def inject_places():
    return {"all_places": [{"place": p["place"], "state": p["state"]} for p in ALL_PLACES], "year": datetime.now().year}


# ---------- pages ----------
@app.get("/")
def index():
    h = hist.get_history()
    trips = sum(1 for e in h if e["kind"] == "trip")
    return render_template(
        "index.html", history=h, trips=trips, recs=recommend_places(h),
        interests=top_interests(h), featured=FEATURED, states=STATES[:12], place_count=len(ALL_PLACES),
    )


@app.get("/states")
def states():
    return render_template("states.html", states=STATES)


@app.get("/state/<slug>")
def state_page(slug):
    state = STATES_BY_SLUG.get(slug)
    if not state:
        abort(404)
    return render_template("state.html", s=state)


def _traveler_args():
    """How many people (1–10, default 2) and which travel style — always something safe to compute with."""
    try:
        travelers = min(10, max(1, int(request.args.get("travelers", 2))))
    except ValueError:
        travelers = 2
    style = request.args.get("style")
    return travelers, style if style in budget.TIERS else "comfort"


@app.get("/plan")
def plan():
    place = (request.args.get("place") or "Jaipur").strip() or "Jaipur"
    try:
        days = min(10, max(1, int(request.args.get("days", 3))))
    except ValueError:
        days = 3
    travelers, style = _traveler_args()
    return render_template("plan.html", place=place[:80], days=days, travelers=travelers, style=style, saved=hist.is_trip(place))


@app.get("/plan/content")
def plan_content():
    place = (request.args.get("place") or "").strip()
    try:
        days = int(request.args.get("days", 3))
    except ValueError:
        days = 3
    if not (2 <= len(place) <= 80) or not (1 <= days <= 10):
        return jsonify(error="Please enter a valid place and 1–10 days."), 400
    try:
        data = plan_trip(place, days, (request.args.get("interests") or "")[:200])
    except PlannerError as e:
        return jsonify(error=str(e)), 502
    except Exception:                    # never answer the page with a raw error document
        app.logger.exception("plan_trip failed for %r", place)
        return jsonify(error="The planner returned an unexpected answer. Please try again."), 502
    hist.add_history(place, data.get("state"))
    travelers, style = _traveler_args()
    model = budget.client_model(data, days, place, data.get("state"))
    return render_template(
        "_plan_content.html", data=data, place=place, days=days, model=model, tier=style,
        est=budget.compute(model, travelers, style), sources=budget.sources_for(model["profile"]),
        google_url=budget.google_url(place), live_guides=guides.configured(),
        packing=packing.build(place, days, data.get("bestSeason", "")),
    )


_pdf_hits = {}


def _too_many_pdfs(ip, limit=8, window=60):
    """A small per-visitor limit: every PDF can trigger photo and hotel look-ups."""
    now = time.time()
    q = _pdf_hits.setdefault(ip or "?", deque())
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    if len(_pdf_hits) > 500:
        for k in [k for k, v in _pdf_hits.items() if not v or now - v[-1] > window]:
            _pdf_hits.pop(k, None)
    return False


def _clamped(value, lo, hi, default):
    try:
        return min(hi, max(lo, int(value)))
    except (TypeError, ValueError):
        return default


@app.post("/plan/pdf")
def plan_pdf():
    """Turn the plan the visitor is looking at into a PDF download (the plan comes from the page, so it is exactly what they see)."""
    body = request.get_json(silent=True)
    place = body.get("place") if isinstance(body, dict) else None
    if not isinstance(place, str) or not (2 <= len(place.strip()) <= 80):
        return jsonify(error="Please reload the page and try again."), 400
    place = place.strip()
    days, travelers = _clamped(body.get("days"), 1, 10, 3), _clamped(body.get("travelers"), 1, 10, 2)
    style = body.get("style") if body.get("style") in budget.TIERS else "comfort"
    plan = normalize_plan(body.get("plan"), place)
    if not plan["days"]:
        return jsonify(error="There is no itinerary to export yet."), 400
    if _too_many_pdfs(request.remote_addr):
        return jsonify(error="That's a lot of downloads in a minute — please wait a moment and try again."), 429
    packed = body.get("packed")
    packed = [x[:80] for x in packed if isinstance(x, str)][:300] if isinstance(packed, list) else []
    try:
        data = pdfgen.make_pdf(plan, days=days, travelers=travelers, style=style, packed=packed)
    except Exception:
        app.logger.exception("PDF export failed for %r", place)
        return jsonify(error="Couldn't create the PDF. Please try again."), 500
    resp = Response(data, mimetype="application/pdf")
    resp.headers["Content-Disposition"] = f'attachment; filename="NARADA-YATRA_{slug(plan["place"])}_{days}-day{"s" if days != 1 else ""}.pdf"'
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="That plan is too large to export."), 413


@app.get("/plan/guides")
def plan_guides():
    """Live traveller-budget articles (only when a Google search key is configured)."""
    place = (request.args.get("place") or "").strip()
    if not (2 <= len(place) <= 80):
        return jsonify(error="Invalid place."), 400
    results = guides.search_guides(place)
    if not results:
        return "", 204
    return render_template("_guides.html", results=results)


@app.get("/plan/hotels")
def plan_hotels():
    place = (request.args.get("place") or "").strip()
    if not (2 <= len(place) <= 80):
        return jsonify(error="Invalid place."), 400
    try:
        hotels = maps.find_hotels(place)
    except maps.MapsError as e:
        return jsonify(error=str(e)), 502
    return render_template("_hotels.html", hotels=hotels)


# ---------- small JSON APIs ----------
@app.get("/api/photo")
def api_photo():
    q = (request.args.get("q") or "").strip()
    name = (request.args.get("name") or q).strip()
    if len(q) < 2:
        return jsonify(url=None)
    url = None
    try:
        url = maps.find_photo(q[:120])
    except maps.MapsError:
        pass
    return jsonify(url=url or maps.wiki_photo(name[:120]))


@app.get("/api/photos")
def api_photos():
    """Several photos (with credits) for one place — feeds the photo galleries."""
    q = (request.args.get("q") or "").strip()[:140]
    name = (request.args.get("name") or q).strip()[:100]
    try:
        n = min(8, max(1, int(request.args.get("n", 5))))
    except ValueError:
        n = 5
    if len(q) < 2:
        return jsonify(photos=[])
    return jsonify(photos=maps.photos_for(q, name, n))


@app.post("/api/trip")
def api_save_trip():
    body = request.get_json(silent=True) or {}
    place = body.get("place")
    if not isinstance(place, str) or len(place.strip()) < 2:
        return jsonify(ok=False), 400
    hist.mark_trip(place, body.get("state"))
    return jsonify(ok=True)


@app.post("/api/history/clear")
def api_clear_history():
    hist.clear_history()
    return redirect(url_for("index"))


@app.get("/favicon.ico")
def favicon():
    """A fully transparent icon, so a browser never falls back to (or keeps showing) an old one."""
    resp = send_from_directory(app.static_folder, "blank.png", mimetype="image/png")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(_):
    return render_template("500.html"), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=os.getenv("FLASK_DEBUG") == "1")
