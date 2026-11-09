import io
import json
import os
import sys
import time
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as narada  # noqa: E402
import budget  # noqa: E402
import packing  # noqa: E402
import pdfgen  # noqa: E402
import trip  # noqa: E402
from PIL import Image  # noqa: E402
from test_app import FAKE_HOTELS, FAKE_PLAN  # noqa: E402

try:
    import pypdf
except ImportError:                                   # pypdf is only needed to read PDFs back in these tests
    pypdf = None

needs_pypdf = unittest.skipUnless(pypdf, "pip install pypdf to run the PDF content tests")


def jpeg(w=800, h=600, colour=(60, 140, 220)):
    b = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(b, "JPEG")
    return b.getvalue()


def plan(stops=3, days=3, **over):
    raw = json.loads(json.dumps(FAKE_PLAN))
    base = raw["days"][0]["stops"]
    raw["days"] = [{"day": d, "title": f"Day {d}", "stops": [dict(base[i % 2], name=f"Stop {d}-{i}") for i in range(stops)]} for d in range(1, days + 1)]
    raw.update(over)
    return trip.normalize_plan(raw, "Goa")


def pdf_text(data):
    r = pypdf.PdfReader(io.BytesIO(data))
    return r, "\n".join(p.extract_text() for p in r.pages)


class NormalizeTests(unittest.TestCase):
    def test_cleaning_twice_changes_nothing(self):
        once = trip.normalize_plan(FAKE_PLAN, "Goa")
        self.assertEqual(trip.normalize_plan(once, "Goa"), once)         # a plan posted back for the PDF is the plan on screen

    def test_sizes_are_capped(self):
        raw = {"days": [{"stops": [{"name": "S" * 5000, "note": "n" * 9000}] * 40}] * 30, "foods": [{"name": "f"}] * 99, "tips": ["t"] * 99, "overview": "o" * 9000}
        p = trip.normalize_plan(raw, "X")
        self.assertEqual((len(p["days"]), len(p["days"][0]["stops"]), len(p["foods"]), len(p["tips"])), (trip.MAX_DAYS, trip.MAX_STOPS, trip.MAX_ITEMS, trip.MAX_ITEMS))
        self.assertLessEqual(len(p["days"][0]["stops"][0]["name"]), trip.NAME_LEN)
        self.assertLessEqual(len(p["overview"]), trip.PARA_LEN)


class TextAndImageTests(unittest.TestCase):
    def test_unsupported_characters_are_dropped_not_boxed(self):
        self.assertEqual(pdfgen._clean("Goa 🌴 नारद यात्रा ₹500 – ok"), "Goa ₹500 – ok")
        self.assertEqual(pdfgen._clean("Café Évora"), "Café Évora")
        self.assertEqual(pdfgen._clean(None), "")

    def test_markup_is_escaped(self):
        self.assertIn("&lt;b&gt;", pdfgen._x("<b>bold</b>"))
        self.assertIn('<font name="Symbols">★</font>', pdfgen._x("4.5 ★"))

    def test_only_trusted_image_hosts(self):
        ok = ["https://lh3.googleusercontent.com/a", "https://upload.wikimedia.org/x.jpg"]
        bad = ["http://lh3.googleusercontent.com/a", "https://evil.example/a.jpg", "https://googleusercontent.com.evil.example/a", "file:///etc/passwd", "", None, "https://localhost/a"]
        self.assertTrue(all(pdfgen._host_ok(u) for u in ok))
        self.assertFalse(any(pdfgen._host_ok(u) for u in bad))

    def test_prepare_image_crops_shrinks_and_rejects_junk(self):
        out = pdfgen.prepare_image(jpeg(3000, 2000), 4 / 3, 380)
        im = Image.open(io.BytesIO(out))
        self.assertEqual(im.width, 380)
        self.assertAlmostEqual(im.width / im.height, 4 / 3, delta=0.02)
        self.assertLess(len(out), 40_000)
        self.assertIsNone(pdfgen.prepare_image(b"not an image", 1.5, 300))
        self.assertIsNone(pdfgen.prepare_image(jpeg(10, 10), 1.5, 300))

    def test_download_refuses_big_files_wrong_types_and_untrusted_hosts(self):
        def resp(ctype="image/jpeg", chunks=(b"x" * 10,), ok=True):
            r = mock.Mock(ok=ok, headers={"Content-Type": ctype})
            r.iter_content.return_value = iter(chunks)
            return r
        url = "https://lh3.googleusercontent.com/a"
        with mock.patch("requests.get", return_value=resp()):
            self.assertEqual(pdfgen._download(url), b"x" * 10)
        with mock.patch("requests.get", return_value=resp(ctype="text/html")):
            self.assertIsNone(pdfgen._download(url))
        with mock.patch("requests.get", return_value=resp(chunks=[b"x" * 3_000_000] * 3)):
            self.assertIsNone(pdfgen._download(url))
        with mock.patch("requests.get") as g:
            self.assertIsNone(pdfgen._download("https://evil.example/a.jpg"))
            g.assert_not_called()

    def test_gather_images_returns_what_it_can_and_never_hangs(self):
        p = plan(stops=2, days=2)

        def fake(query, name, ratio, width):
            if "Stop 2-1" in name:
                time.sleep(3)                                       # one very slow photo
            if "Stop 1-0" in name:
                return None                                         # one missing photo
            return b"jpeg"
        started = time.time()
        with mock.patch("pdfgen._fetch_one", side_effect=fake):
            got = pdfgen.gather_images(p, deadline=0.6)
        self.assertLess(time.time() - started, 2.0)
        self.assertEqual(got["hero"], b"jpeg")
        self.assertIsNone(got[(0, 0)])
        self.assertNotIn((1, 1), got)


@needs_pypdf
class BuildTests(unittest.TestCase):
    def build(self, p=None, **kw):
        kw.setdefault("days", 3)
        return pdfgen.build_pdf(p or plan(), today=date(2026, 10, 24), **kw)

    def test_it_is_a_real_multi_page_pdf_with_the_plan_in_it(self):
        data = self.build(travelers=4, style="premium", hotels=FAKE_HOTELS)
        self.assertTrue(data.startswith(b"%PDF"))
        r, text = pdf_text(data)
        self.assertGreaterEqual(len(r.pages), 3)
        for needle in ("Goa", "Stop 1-0", "Stop 3-2", "Day by day", "Famous local food", "Anjuna Market", "Carry sunscreen", "Packing checklist", "Nearby hotels", "Taj"):
            self.assertIn(needle, text)
        self.assertIn("Page 1 of %d" % len(r.pages), text)

    def test_budget_in_the_pdf_matches_the_page(self):
        p = plan()
        model = budget.client_model(p, 3, p["place"], p["state"])
        est = budget.compute(model, 4, "premium")
        _, text = pdf_text(self.build(p, travelers=4, style="premium"))
        for value in (est["per_person"], est["group"], est["parts"]["stay"], est["parts"]["food"]):
            self.assertIn(narada.inr(value), text)
        self.assertIn("4 travelers", text)
        self.assertIn("Premium style", text)

    def test_the_not_accurate_caption_is_always_there(self):
        _, text = pdf_text(self.build())
        flat = " ".join(text.split())
        self.assertIn("The budget per person is not accurate", flat)
        self.assertIn("can change according to the traveler", flat)
        self.assertIn("Budget figures are estimates, not exact", flat)          # also in every footer

    def test_packed_items_are_shown_ticked(self):
        groups = packing.build("Goa", 3, FAKE_PLAN["bestSeason"])
        ids = [groups[0]["items"][0]["id"], groups[2]["items"][1]["id"]]
        _, text = pdf_text(self.build(packed=ids))
        self.assertEqual(text.count("☑"), 2)
        self.assertGreater(text.count("☐"), 10)
        self.assertIn("2 of", text)

    def test_photos_are_embedded_when_given_and_the_pdf_survives_without_them(self):
        p = plan(stops=2, days=2)
        photos = {"hero": pdfgen.prepare_image(jpeg(colour=(200, 90, 40)), 3.4, 1300), (0, 0): pdfgen.prepare_image(jpeg(colour=(30, 160, 90)), 4 / 3, 380),
                  (1, 1): pdfgen.prepare_image(jpeg(colour=(90, 40, 180)), 4 / 3, 380)}        # different pictures (identical ones are stored once)
        with_photos = self.build(p, days=2, images=photos)
        without = self.build(p, days=2)
        self.assertEqual(sum(len(pg.images) for pg in pypdf.PdfReader(io.BytesIO(with_photos)).pages), 3)
        self.assertEqual(sum(len(pg.images) for pg in pypdf.PdfReader(io.BytesIO(without)).pages), 0)
        self.assertGreater(len(with_photos), len(without))
        self.assertLess(len(with_photos), 400_000)

    def test_links_are_clickable(self):
        r = pypdf.PdfReader(io.BytesIO(self.build(hotels=FAKE_HOTELS)))
        urls = {a.get_object().get("/A", {}).get("/URI") for pg in r.pages for a in (pg.get("/Annots") or [])}
        self.assertTrue(any(u and u.startswith("https://www.google.com/maps/search/") for u in urls))
        self.assertTrue(any(u and u.startswith("https://www.google.com/search?q=") for u in urls))
        self.assertTrue(any(u and "travelindiasmart" in u for u in urls))
        self.assertIn("https://maps.example/taj", urls)

    def test_hostile_text_cannot_break_the_layout(self):
        evil = plan(overview="<b>unclosed <i>&amp; नमस्ते 🌴 " + "very long " * 200, tips=["<script>alert(1)</script>", "x" * 5000])
        evil["days"][0]["stops"][0]["name"] = "<para>Name & <b>more</b></para> ₹"
        _, text = pdf_text(self.build(evil))
        self.assertIn("<script>alert(1)</script>", text)                      # shown as plain text, never interpreted
        self.assertIn("₹", text)

    def test_a_full_ten_day_plan_stays_fast(self):
        big = plan(stops=trip.MAX_STOPS, days=trip.MAX_DAYS)
        started = time.time()
        data = self.build(big, days=10)
        self.assertLess(time.time() - started, 15)
        self.assertGreater(len(pypdf.PdfReader(io.BytesIO(data)).pages), 8)

    def test_single_day_and_solo_wording(self):
        _, text = pdf_text(self.build(plan(days=1), days=1, travelers=1))
        self.assertIn("1 day", text)
        self.assertIn("1 traveler", text)
        self.assertNotIn("1 travelers", text)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        narada.app.testing = True
        narada._pdf_hits.clear()
        self.c = narada.app.test_client()
        self.patches = [mock.patch("pdfgen.gather_images", return_value={}), mock.patch("maps.find_hotels", return_value=FAKE_HOTELS)]
        [p.start() for p in self.patches]

    def tearDown(self):
        [p.stop() for p in self.patches]

    def post(self, **over):
        body = {"place": "Goa", "days": 3, "travelers": 2, "style": "comfort", "plan": trip.normalize_plan(FAKE_PLAN, "Goa"), "packed": []}
        body.update(over)
        return self.c.post("/plan/pdf", json=body)

    def test_download_comes_back_as_a_pdf_file(self):
        r = self.post()
        self.assertEqual((r.status_code, r.mimetype), (200, "application/pdf"))
        self.assertEqual(r.headers["Content-Disposition"], 'attachment; filename="NARADA-YATRA_Goa_3-days.pdf"')
        self.assertTrue(r.data.startswith(b"%PDF"))
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        self.assertIn("1-day.pdf", self.post(days=1).headers["Content-Disposition"])

    def test_filename_is_safe_for_any_place(self):
        cd = self.post(place="Café Évora / ../../x").headers["Content-Disposition"]
        self.assertRegex(cd, r'^attachment; filename="NARADA-YATRA_[A-Za-z0-9-]+_3-days\.pdf"$')

    def test_bad_requests_get_clear_json_errors(self):
        for kw in ({"place": ""}, {"place": 5}, {"place": "x" * 200}, {"plan": {"days": []}}, {"plan": "nope"}, {"plan": None}):
            r = self.post(**kw)
            self.assertEqual((r.status_code, r.mimetype), (400, "application/json"), kw)
            self.assertIn("error", r.get_json())
        self.assertEqual(self.c.post("/plan/pdf", data="not json", content_type="text/plain").status_code, 400)
        self.assertEqual(self.c.post("/plan/pdf", json=[1, 2]).status_code, 400)

    def test_odd_numbers_are_clamped_not_trusted(self):
        r = self.post(days=999, travelers=-5, style="evil", packed="nope")
        self.assertEqual(r.status_code, 200)
        self.assertIn("10-days.pdf", r.headers["Content-Disposition"])

    def test_oversized_posts_are_refused(self):
        r = self.c.post("/plan/pdf", json={"place": "Goa", "plan": {"overview": "x" * 600_000}})
        self.assertEqual((r.status_code, r.mimetype), (413, "application/json"))

    def test_it_is_rate_limited(self):
        codes = [self.post().status_code for _ in range(10)]
        self.assertEqual(codes[:8], [200] * 8)
        self.assertEqual(codes[8:], [429, 429])
        self.assertIn("wait", self.post().get_json()["error"])

    def test_a_failure_is_reported_as_json(self):
        with mock.patch("pdfgen.make_pdf", side_effect=RuntimeError("boom")):
            r = self.post()
        self.assertEqual((r.status_code, r.mimetype), (500, "application/json"))
        self.assertIn("try again", r.get_json()["error"])

    def test_the_page_offers_the_download(self):
        shell = self.c.get("/plan?place=Goa&days=3").get_data(as_text=True)
        self.assertRegex(shell, r"<button[^>]*data-pdf disabled")                 # waits until there is a plan
        with mock.patch("trip.ask_json", return_value=json.loads(json.dumps(FAKE_PLAN))):
            body = self.c.get("/plan/content?place=Goa&days=3").get_data(as_text=True)
        self.assertIn("data-plan='", body)
        self.assertIn('id="offline"', body)
        self.assertIn("Download your plan as a PDF", body)
        self.assertIn("M12 4v11M7 11l5 5 5-5", body)                              # the download icon
        meta = json.loads(__import__("re").search(r"data-plan='([^']*)'", body).group(1).replace("&#34;", '"'))
        self.assertEqual(meta["place"], "Goa")
        self.assertEqual(trip.normalize_plan(meta, "Goa"), meta)                  # the page hands back exactly what it shows


if __name__ == "__main__":
    unittest.main()
