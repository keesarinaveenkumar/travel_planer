import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as narada  # noqa: E402
import maps  # noqa: E402
import requests  # noqa: E402
import recommender  # noqa: E402
from client import PlannerError  # noqa: E402

FAKE_PLAN = {
    "place": "Goa", "state": "Goa", "overview": "Sun and sand.", "bestSeason": "Nov-Feb", "lat": 15.3, "lng": 74.0,
    "days": [{"day": "1", "title": "Beaches", "stops": [
        {"name": "Baga Beach", "time": "09:00 AM", "durationHrs": 2, "distanceKm": 0, "travel": "-", "note": "Swim", "entryFee": 0, "transportCost": 0, "mealCost": "150"},
        {"name": "Fort Aguada", "time": "01:00 PM", "durationHrs": 1.5, "distanceKm": 8, "travel": "Cab 20 min", "note": "Views", "entryFee": 25, "transportCost": 300, "mealCost": 200.4},
    ]}],
    "foods": [{"name": "Fish Curry", "description": "Spicy", "where": "Panaji"}],
    "shopping": [{"area": "Anjuna Market", "buy": "Crafts", "tip": "Bargain"}],
    "mustVisit": ["Baga Beach"], "tips": ["Carry sunscreen"],
}
FAKE_HOTELS = [{"name": "Taj", "address": "Goa", "rating": 4.6, "reviews": 12345, "priceLevel": "PRICE_LEVEL_EXPENSIVE",
                "priceFrom": 12000, "priceTo": 20000, "currency": "INR", "mapsUrl": "https://maps.example/taj", "photo": None}]
PHOTOS = [{"url": f"https://img.example/{i}.jpg", "credit": "A. Traveller", "source": "Google Maps"} for i in range(5)]


def plan():
    return json.loads(json.dumps(FAKE_PLAN))


def png_is_fully_transparent(data):
    """Decode a PNG by hand and confirm every pixel has alpha 0."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat = 8, b""
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        tag, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            w, h, _depth, ctype = struct.unpack(">IIBB", body[:10])
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    raw, stride = zlib.decompress(idat), 1 + w * 4
    return ctype == 6 and all(raw[y * stride + 1 + x * 4 + 3] == 0 for y in range(h) for x in range(w))


class AppTests(unittest.TestCase):
    def setUp(self):
        narada.app.testing = True
        self.c = narada.app.test_client()

    def test_pages_render(self):
        self.assertIn(b"Plan a journey to", self.c.get("/").data)
        self.assertEqual(self.c.get("/states").status_code, 200)
        self.assertIn(b"Kerala", self.c.get("/state/kerala").data)
        self.assertEqual(self.c.get("/plan?place=Hampi&days=2").status_code, 200)

    def test_brand_and_responsive_shell(self):
        home = self.c.get("/").get_data(as_text=True)
        self.assertIn("NARADA YATRA", home)
        self.assertNotIn("Yatra", home)
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1"', home)

    def test_tab_icon_is_blank_and_replaces_any_old_one(self):
        home = self.c.get("/").get_data(as_text=True)
        self.assertRegex(home, r'<link rel="icon" type="image/png" href="/static/blank\.png\?v=\d+">')   # a NEW address
        self.assertNotIn("data:,", home)
        for url in ("/favicon.ico", "/static/blank.png"):
            r = self.c.get(url)
            self.assertEqual((r.status_code, r.mimetype), (200, "image/png"))
            self.assertTrue(png_is_fully_transparent(r.data), url)
            r.close()
        self.assertEqual(self.c.get("/favicon.ico").headers["Cache-Control"], "no-cache")

    def test_static_files_are_version_stamped(self):
        home = self.c.get("/").get_data(as_text=True)
        for f in ("css/site.css", "js/app.js", "js/gallery.js", "js/motion.js", "blank.png"):
            self.assertRegex(home, r"/static/" + f.replace(".", r"\.") + r"\?v=\d+")

    def test_motion_and_static_assets(self):
        home = self.c.get("/").get_data(as_text=True)
        for hook in ("data-reveal", "data-parallax", "data-tilt", "data-rotate", "data-count", "data-route", "data-spatial",
                     'class="aurora"', 'class="clouds"', 'class="road"', "plane--a", "veh--bus", "veh--car", "nav__lens", "glass", "clay",
                     'id="progress"', 'id="wipe"', 'id="to-top"', 'id="lightbox"', "js/motion.js", "js/gallery.js", "css/site.css"):
            self.assertIn(hook, home)
        for f in ("css/site.css", "js/app.js", "js/gallery.js", "js/motion.js"):
            self.assertEqual(self.c.get("/static/" + f).status_code, 200)
        css = self.c.get("/static/css/site.css"); self.assertIn("prefers-reduced-motion", css.get_data(as_text=True)); css.close()

    def test_not_found(self):
        self.assertEqual(self.c.get("/state/nope").status_code, 404)
        self.assertEqual(self.c.get("/this-route-does-not-exist").status_code, 404)

    def test_states_page_filters_markup(self):
        body = self.c.get("/states").get_data(as_text=True)
        self.assertEqual(body.count("data-state-card"), 36)
        self.assertIn('data-region-chip="south"', body)
        self.assertEqual(narada.REGION_OF["Kerala"], "south")

    def test_plan_content_costs_and_galleries(self):
        with mock.patch("trip.ask_json", return_value=plan()):
            r = self.c.get("/plan/content?place=Goa&days=1")
        body = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Fort Aguada", body)
        self.assertIn("₹150", body)            # string cost coerced to int
        self.assertIn("₹675", body)            # 0+0+150 + 25+300+200
        self.assertIn('id="day-1"', body)      # day "1" (string) coerced to int
        # photo galleries: 2 stops + 1 dish + 1 market
        self.assertEqual(body.count("data-gallery"), 4)
        self.assertIn('data-q="Baga Beach, Goa, India"', body)
        self.assertIn('data-q="Panaji, Goa, India"', body)
        self.assertIn('data-q="Anjuna Market, Goa, India"', body)

    def test_travel_mode_icons_and_timeline_car(self):
        pl = plan()
        pl["days"][0]["stops"] = [dict(pl["days"][0]["stops"][0], name=f"Stop {i}", travel=tr) for i, tr in
                                  enumerate(["-", "Bus 30 min", "Flight 1 h", "Walk 5 min", "Cab 20 min"])]
        with mock.patch("trip.ask_json", return_value=pl):
            body = self.c.get("/plan/content?place=Goa&days=1").get_data(as_text=True)
        for marker in ("M8 6v6M15 6v6", "M17.8 19.2", 'circle cx="13" cy="4"', "M19 17h2c.6"):   # bus, plane, walk, car
            self.assertIn(marker, body)
        self.assertIn("timeline__car", body)

    def test_hotels_have_no_gallery(self):
        with mock.patch("maps.find_hotels", return_value=FAKE_HOTELS):
            body = self.c.get("/plan/hotels?place=Goa").get_data(as_text=True)
        self.assertIn("Upscale · ₹₹₹", body)
        self.assertIn("₹12,000 – ₹20,000 per night", body)
        self.assertNotIn("data-gallery", body)

    def test_plan_errors(self):
        self.assertEqual(self.c.get("/plan/content?place=G&days=1").status_code, 400)
        with mock.patch("trip.ask_json", side_effect=PlannerError("The trip planner is not configured.")):
            r = self.c.get("/plan/content?place=Goa&days=1")
        self.assertEqual((r.status_code, r.get_json()["error"]), (502, "The trip planner is not configured."))

    def test_history_and_recommendations(self):
        with mock.patch("trip.ask_json", return_value=plan()):
            self.c.get("/plan/content?place=Goa&days=1")
        self.c.post("/api/trip", json={"place": "Goa", "state": "Goa"})
        home = self.c.get("/").get_data(as_text=True)
        self.assertIn("Recommended for you", home)
        self.assertIn("1 saved trips", home)
        self.c.post("/api/history/clear")
        self.assertNotIn("Recommended for you", self.c.get("/").get_data(as_text=True))

    def test_photo_api_falls_back_to_wikipedia(self):
        with mock.patch("maps.find_photo", side_effect=maps.MapsError("x")), \
             mock.patch("maps.wiki_photo", return_value="https://img/x.jpg"):
            self.assertEqual(self.c.get("/api/photo?q=Hampi,%20India&name=Hampi").get_json()["url"], "https://img/x.jpg")

    def test_photos_api(self):
        with mock.patch("maps.photos_for", return_value=PHOTOS) as m:
            j = self.c.get("/api/photos?q=Baga%20Beach,%20Goa&name=Baga%20Beach&n=99").get_json()
        self.assertEqual(len(j["photos"]), 5)
        self.assertEqual(m.call_args.args, ("Baga Beach, Goa", "Baga Beach", 8))   # n is capped at 8
        self.assertEqual(self.c.get("/api/photos?q=a").get_json(), {"photos": []})

    def test_inr_format(self):
        self.assertEqual(narada.inr(1234567), "₹12,34,567")
        self.assertEqual(narada.inr(999), "₹999")
        self.assertEqual(narada.inr(0), "₹0")


class HardeningTests(unittest.TestCase):
    def setUp(self):
        narada.app.testing = True
        self.c = narada.app.test_client()

    def test_bad_values_cannot_break_the_home_page(self):
        self.c.post("/api/trip", json={"place": "Goa", "state": {"x": 1}})                  # was: home page returned 500
        self.c.post("/api/trip", json={"place": "P" * 5000, "state": "S" * 5000})
        self.assertEqual(self.c.get("/").status_code, 200)
        with self.c.session_transaction() as s:
            for e in s["narada-history-v1"]:
                self.assertLessEqual(len(e["place"]), 80)
                self.assertTrue(e["state"] is None or len(e["state"]) <= 60)

    def test_a_damaged_cookie_heals_itself(self):
        with self.c.session_transaction() as s:
            s["narada-history-v1"] = [{"place": "Goa", "state": {"x": 1}, "kind": "trip", "ts": 1}, "junk", {"place": 5}, {"place": "x"}, None]
        home = self.c.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("1 saved trips", home.get_data(as_text=True))

    def test_trip_needs_a_text_place(self):
        for bad in (123, ["Goa"], None, "a"):
            self.assertEqual(self.c.post("/api/trip", json={"place": bad}).status_code, 400, bad)

    def test_plan_survives_oddly_shaped_planner_data(self):
        odd = {"place": ["x"], "state": 5, "days": ["Day one", {"day": "x", "stops": ["text", {"name": "Real stop", "entryFee": None, "durationHrs": "2 hours"}]}],
               "foods": ["Fish curry", {"name": "Dosa"}], "shopping": "none", "mustVisit": [{"a": 1}, "Fort"], "tips": None}
        with mock.patch("trip.ask_json", return_value=odd):
            r = self.c.get("/plan/content?place=Goa&days=1")
        body = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Real stop", body)
        self.assertIn("Dosa", body)
        self.assertIn('id="day-1"', body)

    def test_unexpected_planner_failure_is_json_not_an_error_page(self):
        with mock.patch("trip.ask_json", side_effect=RuntimeError("boom")):
            r = self.c.get("/plan/content?place=Goa&days=1")
        self.assertEqual((r.status_code, r.mimetype), (502, "application/json"))
        self.assertIn("error", r.get_json())

    def test_photos_fall_back_when_google_is_unreachable(self):
        maps._photos_cache.clear()
        with mock.patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "k"}), \
             mock.patch("requests.post", side_effect=requests.ConnectionError("offline")), \
             mock.patch("maps.wiki_photos", return_value=PHOTOS[:3]):
            self.assertEqual(len(maps.photos_for("q-net", "n-net", 4)), 3)
            self.assertEqual(self.c.get("/api/photos?q=Hampi%2C%20India&name=Hampi").status_code, 200)

    def test_caches_stay_bounded(self):
        cache = {}
        for i in range(maps.CACHE_LIMIT * 2):
            maps._remember(cache, i, i)
        self.assertEqual(len(cache), maps.CACHE_LIMIT)
        self.assertIn(maps.CACHE_LIMIT * 2 - 1, cache)          # newest kept, oldest dropped

    def test_secret_key_is_random_and_stable(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SECRET_KEY", None)
            path = os.path.join(d, ".secret_key")
            k1 = narada.load_secret_key(path)
            self.assertEqual(len(k1), 64)
            self.assertEqual(narada.load_secret_key(path), k1)                        # same key next start-up
            os.environ["SECRET_KEY"] = "change-me"                                    # the placeholder is not accepted
            self.assertEqual(narada.load_secret_key(path), k1)
            os.environ["SECRET_KEY"] = "a-real-long-random-value"
            self.assertEqual(narada.load_secret_key(path), "a-real-long-random-value")
        self.assertNotEqual(narada.app.secret_key, "dev-secret-change-me")


class PhotoFallbackTests(unittest.TestCase):
    def setUp(self):
        maps._photos_cache.clear()

    def test_google_first_then_commons_top_up_without_duplicates(self):
        google = PHOTOS[:1]
        commons = [PHOTOS[0]] + [{"url": f"https://commons/{i}.jpg", "credit": "C", "source": "Wikimedia Commons"} for i in range(5)]
        with mock.patch("maps.find_photos", return_value=google), mock.patch("maps.wiki_photos", return_value=commons):
            out = maps.photos_for("q1", "n1", 5)
        self.assertEqual(len(out), 5)
        self.assertEqual(out[0]["source"], "Google Maps")
        self.assertEqual(len({p["url"] for p in out}), 5)

    def test_google_failure_uses_commons_only(self):
        with mock.patch("maps.find_photos", side_effect=maps.MapsError("denied")), \
             mock.patch("maps.wiki_photos", return_value=PHOTOS[:3]):
            self.assertEqual(len(maps.photos_for("q2", "n2", 4)), 3)

    def test_enough_google_photos_skips_commons(self):
        with mock.patch("maps.find_photos", return_value=PHOTOS), mock.patch("maps.wiki_photos") as w:
            maps.photos_for("q3", "n3", 5)
        w.assert_not_called()


class RecommenderTests(unittest.TestCase):
    def test_empty_history(self):
        self.assertEqual(recommender.recommend_places([]), [])

    def test_state_cap_and_exclusion(self):
        from collections import Counter
        recs = recommender.recommend_places([{"place": "Goa", "state": "Goa", "kind": "trip", "ts": 1}], 6)
        self.assertNotIn("goa", [r["place"].lower() for r in recs])
        self.assertTrue(all(n <= 2 for n in Counter(r["state"] for r in recs).values()))


if __name__ == "__main__":
    unittest.main()
