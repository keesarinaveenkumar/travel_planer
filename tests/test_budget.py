import json
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as narada  # noqa: E402
import budget  # noqa: E402
import guides  # noqa: E402
import packing  # noqa: E402
import requests  # noqa: E402
from test_app import FAKE_PLAN  # noqa: E402


def plan_for(place, state, stops=4, entry=100, transport=200):
    """A synthetic 3-day itinerary shaped like the planner's output."""
    return {"place": place, "state": state, "days": [
        {"day": d, "title": f"Day {d}", "stops": [
            {"name": f"Stop {i}", "entryFee": entry if i else 0, "transportCost": transport if i else 0,
             "travel": "Cab 15 min" if i % 2 else "Bus 20 min", "mealCost": 100, "durationHrs": 1, "distanceKm": 3, "time": "9 AM", "note": ""}
            for i in range(stops)]} for d in (1, 2, 3)]}


class DestinationTypeTests(unittest.TestCase):
    def test_famous_places_get_the_right_profile(self):
        cases = {("Baga Beach", "Goa"): "beach", ("Jaipur", "Rajasthan"): "heritage", ("Munnar", "Kerala"): "hills", ("Leh", "Ladakh"): "highland",
                 ("Havelock Island", "Andaman and Nicobar Islands"): "islands", ("Varanasi", "Uttar Pradesh"): "spiritual",
                 ("Ranthambore National Park", "Rajasthan"): "wildlife", ("Mumbai", "Maharashtra"): "metro", ("Kasol", "Himachal Pradesh"): "hills",
                 ("Somewhere Unknown", None): "general"}
        for (place, state), want in cases.items():
            self.assertEqual(budget.profile_for(place, state), want, place)

    def test_every_profile_has_complete_rates_and_sources(self):
        for name, r in budget.RATES.items():
            for k in ("stay", "food", "local", "floor"):
                self.assertEqual(len(r[k]), 3, (name, k))
            self.assertTrue(r["stay"][0] < r["stay"][1] < r["stay"][2] and r["food"][0] < r["food"][1] < r["food"][2], name)
            self.assertGreaterEqual(len(budget.sources_for(name)), 2)

    def test_travel_modes(self):
        for text, mode in [("Cab 20 min", "car"), ("Auto-rickshaw", "car"), ("Bus 30 min", "bus"), ("Flight 1 h", "plane"), ("Train", "train"),
                           ("Metro", "train"), ("Walk 5 min", "walk"), ("-", "car"), (None, "car")]:
            self.assertEqual(budget.travel_mode(text), mode, text)


class BudgetMathTests(unittest.TestCase):
    def model(self, place="Jaipur", state="Rajasthan", days=3, **kw):
        return budget.client_model(plan_for(place, state, **kw), days, place, state)

    def test_estimate_is_consistent(self):
        m = self.model()
        for style in budget.TIERS:
            for n in range(1, 11):
                c = budget.compute(m, n, style)
                self.assertEqual(c["total"], sum(c["parts"].values()))
                self.assertEqual(c["per_person"] % 100, 0)
                self.assertLess(c["low"], c["per_person"] + 1)
                self.assertLess(c["per_person"], c["high"])
                self.assertEqual(c["group"], c["per_person"] * n)

    def test_more_travellers_cost_less_each(self):
        m = self.model()
        pp = [budget.compute(m, n, "comfort")["per_person"] for n in (1, 2, 4, 8)]
        self.assertEqual(pp, sorted(pp, reverse=True))
        self.assertGreater(pp[0], pp[1] * 1.15)                   # solo pays noticeably more than a pair

    def test_style_ordering(self):
        m = self.model()
        b, c, p = (budget.compute(m, 2, s)["per_person"] for s in budget.TIERS)
        self.assertTrue(b < c < p)

    def test_day_trip_has_no_stay(self):
        m = budget.client_model(plan_for("Jaipur", "Rajasthan"), 1, "Jaipur", "Rajasthan")
        self.assertEqual(budget.compute(m, 2, "comfort")["parts"]["stay"], 0)

    def test_cabs_split_between_travellers_but_buses_do_not(self):
        shared = {"place": "X", "state": None, "days": [{"stops": [{"entryFee": 0, "transportCost": 1000, "travel": "Cab"}]}]}
        fixed = {"place": "X", "state": None, "days": [{"stops": [{"entryFee": 0, "transportCost": 1000, "travel": "Bus"}]}]}
        ms, mf = (budget.client_model(p, 1, "X") for p in (shared, fixed))
        self.assertEqual((ms["stopShared"], ms["stopFixed"], mf["stopShared"], mf["stopFixed"]), (1000, 0, 0, 1000))
        base = {k: budget.compute(m, 4, "comfort")["parts"]["local"] for k, m in (("cab", ms), ("bus", mf))}
        self.assertLess(base["cab"], base["bus"])

    def test_wildlife_trips_include_safari_costs(self):
        wild = budget.compute(self.model("Ranthambore", "Rajasthan", entry=0), 2, "comfort")
        plain = budget.compute(self.model("Jaipur", "Rajasthan", entry=0), 2, "comfort")
        self.assertGreater(wild["parts"]["entry"], plain["parts"]["entry"])

    def test_estimates_sit_inside_published_daily_ranges(self):
        """National guides put budget travel at ~₹1,300–4,000 a day, mid-range ~₹3,400–7,000 and high-end ~₹7,500–13,500 per person.
        Varanasi guides quote their own, lower bands (budget ~₹1,500–2,500, mid ~₹3,000–5,000), so that city is checked against those."""
        national = {"budget": (1300, 4000), "comfort": (3400, 7000), "premium": (7500, 13500)}
        varanasi = {"budget": (1300, 2600), "comfort": (3000, 5500), "premium": (6500, 13500)}
        for place, state, bands in [("Jaipur", "Rajasthan", national), ("Baga Beach", "Goa", national), ("Munnar", "Kerala", national),
                                    ("Somewhere", None, national), ("Varanasi", "Uttar Pradesh", varanasi)]:
            m = self.model(place, state)
            for style, (lo, hi) in bands.items():
                per_day = budget.compute(m, 2, style)["per_day"]
                self.assertTrue(lo <= per_day <= hi, f"{place} {style}: ₹{per_day}/day outside ₹{lo}–{hi}")

    def test_destination_types_rank_sensibly(self):
        comfort = {p: budget.compute(self.model(p, s, entry=0), 2, "comfort")["per_day"]
                   for p, s in [("Varanasi", "Uttar Pradesh"), ("Jaipur", "Rajasthan"), ("Leh", "Ladakh"), ("Ranthambore", "Rajasthan")]}
        self.assertEqual(min(comfort, key=comfort.get), "Varanasi")          # pilgrimage cities are the cheapest
        self.assertEqual(max(comfort, key=comfort.get), "Ranthambore")       # safari trips cost the most
        self.assertGreater(comfort["Leh"], comfort["Jaipur"])                # remote, high-altitude travel costs more


class SourcesAndGuidesTests(unittest.TestCase):
    def test_sources_are_real_links(self):
        for profile in budget.RATES:
            for s in budget.sources_for(profile):
                self.assertRegex(s["url"], r"^https://")
                self.assertTrue(s["title"] and s["site"])

    def test_google_link_is_encoded(self):
        url = budget.google_url("Hampi & Badami")
        self.assertTrue(url.startswith("https://www.google.com/search?q="))
        self.assertNotIn(" ", url)
        self.assertIn("%26", url)

    def test_guides_are_optional(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_SEARCH_API_KEY", None)
            self.assertFalse(guides.configured())
            self.assertEqual(guides.search_guides("Goa"), [])
            self.assertEqual(narada.app.test_client().get("/plan/guides?place=Goa").status_code, 204)

    def test_live_guides_are_cleaned_and_cached(self):
        guides._cache.clear()
        env = {"GOOGLE_SEARCH_API_KEY": "k", "GOOGLE_SEARCH_CX": "cx"}
        fake = mock.Mock(ok=True)
        fake.json.return_value = {"items": [
            {"title": "Goa trip cost", "displayLink": "blog.example", "snippet": "A  3-day\ntrip costs…", "link": "https://blog.example/goa"},
            {"title": "Bad", "displayLink": "x", "snippet": "", "link": "javascript:alert(1)"}]}
        with mock.patch.dict(os.environ, env), mock.patch("requests.get", return_value=fake) as g:
            r1 = guides.search_guides("Goa")
            guides.search_guides("Goa")
            self.assertEqual(len(r1), 1)                                 # the non-http link is dropped
            self.assertEqual(r1[0]["snippet"], "A 3-day trip costs…")
            self.assertEqual(g.call_count, 1)                            # second call came from the cache
            body = narada.app.test_client().get("/plan/guides?place=Goa").get_data(as_text=True)
            self.assertIn('rel="noopener noreferrer"', body)

    def test_guides_survive_network_errors(self):
        guides._cache.clear()
        with mock.patch.dict(os.environ, {"GOOGLE_SEARCH_API_KEY": "k", "GOOGLE_SEARCH_CX": "cx"}), \
             mock.patch("requests.get", side_effect=requests.ConnectionError("offline")):
            self.assertEqual(guides.search_guides("Goa"), [])


class PackingTests(unittest.TestCase):
    labels = staticmethod(lambda g: [i["label"].lower() for grp in g for i in grp["items"]])

    def test_lists_are_tailored(self):
        beach = self.labels(packing.build("Baga Beach", 3, "November to February"))
        snow = self.labels(packing.build("Leh", 7, "June to September"))
        wild = self.labels(packing.build("Ranthambore", 3, "October to April"))
        self.assertTrue(any("swimwear" in x for x in beach))
        self.assertFalse(any("warm jacket" in x for x in beach), "a Goa winter trip needs no parka")
        self.assertTrue(any("thermals" in x for x in snow) and any("altitude" in x for x in snow))
        self.assertTrue(any("binoculars" in x for x in wild) and any("safari" in x for x in wild))

    def test_rain_gear_only_when_the_season_says_monsoon(self):
        self.assertFalse(any("rain" in x for x in self.labels(packing.build("Leh", 3, "June to September"))))
        self.assertTrue(any("rain" in x for x in self.labels(packing.build("Munnar", 3, "Monsoon and September to March"))))

    def test_ids_are_unique_and_long_trips_get_laundry(self):
        g = packing.build("Jaipur", 7, "October to March")
        ids = [i["id"] for grp in g for i in grp["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 15)
        self.assertTrue(any("laundry" in x for x in self.labels(g)))
        self.assertFalse(any("laundry" in x for x in self.labels(packing.build("Jaipur", 3, ""))))


class PlanPageBudgetTests(unittest.TestCase):
    def setUp(self):
        narada.app.testing = True
        self.c = narada.app.test_client()

    def content(self, query="place=Goa&days=3&travelers=4&style=premium", plan=None):
        with mock.patch("trip.ask_json", return_value=json.loads(json.dumps(plan or FAKE_PLAN))):
            return self.c.get("/plan/content?" + query).get_data(as_text=True)

    def test_shell_reads_and_cleans_traveler_settings(self):
        body = self.c.get("/plan?place=Goa&days=3&travelers=4&style=premium").get_data(as_text=True)
        self.assertIn('data-travelers="4"', body)
        self.assertIn('data-style="premium"', body)
        self.assertRegex(body, r'<option value="4" selected>4 travelers</option>')
        bad = self.c.get("/plan?place=Goa&travelers=abc&style=evil").get_data(as_text=True)
        self.assertIn('data-travelers="2"', bad)
        self.assertIn('data-style="comfort"', bad)
        self.assertIn('data-travelers="10"', self.c.get("/plan?place=Goa&travelers=99").get_data(as_text=True))
        self.assertIn('data-travelers="1"', self.c.get("/plan?place=Goa&travelers=0").get_data(as_text=True))

    def test_search_bars_offer_a_travelers_choice(self):
        home = self.c.get("/").get_data(as_text=True)
        self.assertEqual(len(re.findall(r'<option value="\d+"[^>]*>\d+ travelers?</option>', home)), 10)
        self.assertIn('<option value="2" selected>2 travelers</option>', home)

    def test_budget_panel_shows_the_caption_numbers_and_sources(self):
        body = self.content()
        self.assertIn("The budget per person is not accurate.", body)
        self.assertIn("can change according to the traveler", body)
        model = json.loads(re.search(r"data-model='([^']*)'", body).group(1).replace("&#34;", '"'))
        est = budget.compute(model, 4, "premium")
        self.assertIn(narada.inr(est["per_person"]), body)
        self.assertIn(narada.inr(est["group"]), body)
        self.assertIn("4 travelers", body)
        self.assertGreaterEqual(body.count('target="_blank" rel="noopener noreferrer"'), 3)
        self.assertIn("https://www.google.com/search?q=", body)
        self.assertIn('data-pack ', body)
        self.assertIn('id="packing"', body)

    def test_changing_style_changes_the_server_numbers_too(self):
        cheap, dear = (self.content(f"place=Goa&days=3&travelers=2&style={s}") for s in ("budget", "premium"))
        self.assertNotEqual(re.search(r"data-pp>([^<]+)<", cheap).group(1), re.search(r"data-pp>([^<]+)<", dear).group(1))


if __name__ == "__main__":
    unittest.main()
