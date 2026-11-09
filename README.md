# NARADA YATRA — Python (Flask) edition

Smart travel planner for India: day-by-day itineraries with timings, distances and cost estimates,
**photo galleries for every stop, dish and market**, live Google Maps hotels, maps and a personalised recommender.

## Run locally
1. Python 3.10+
2. `pip install -r requirements.txt`
3. `cp .env.example .env` and fill in `PLANNER_API_KEY`, `PLANNER_BASE_URL`, `PLANNER_MODEL` and `GOOGLE_MAPS_API_KEY` (`SECRET_KEY` is optional — a random one is created and kept in `.secret_key`)
4. `python app.py` → open http://localhost:8080

Tests: `pip install -r requirements-dev.txt` once (adds `pypdf`, which the PDF tests use to read the file back), then `python -m unittest discover -s tests -v`

## Photo galleries
Day-wise stops, famous food and shopping areas each get a photo section (hotels do not). Photos load as you scroll,
come from Google Maps (author credited) with Wikimedia Commons as a fallback, and open in a full-screen viewer
(arrow keys, swipe, thumbnails, Esc to close). Server side this is one endpoint: `GET /api/photos?q=&name=&n=`.
Google Places photo requests are billed — galleries only load when they scroll into view, and results are cached in memory.

## Layout
| Path | Purpose |
| --- | --- |
| `app.py` | routes, JSON endpoints, error pages |
| `data.py`, `recommender.py`, `history.py` | states/places data, recommendation model, session history |
| `client.py`, `trip.py` | trip-planner service client and itinerary builder |
| `maps.py` | Google Places photos/hotels + Wikimedia fallback |
| `templates/` | Jinja pages (`_macros.html` holds icons, photo, gallery and search-bar macros) |
| `static/css/site.css` | design system ("Clear sky" palette): glass, liquid glass, clay and spatial depth + all animation styles |
| `static/js/app.js` | search, lazy photos, state filter, plan loading |
| `static/js/plan.js` | live budget (travelers + style) and the packing checklist |
| `static/js/gallery.js` | photo galleries + lightbox |
| `static/js/motion.js` | reveal, parallax, pointer depth, liquid-glass light + nav lens, route/timeline vehicles, tilt, count-up, scroll-spy, page transitions |

All motion respects `prefers-reduced-motion`. Fonts (DM Serif Display, Plus Jakarta Sans, Tiro Devanagari Hindi)
load from Google Fonts; maps, photos and hotels need an internet connection.

## Design language
**Palette — "Clear sky":** soft sky-blue and white, one cool accent (ocean blue → teal) and a touch of warm amber for small highlights.
All colours live as variables at the top of `static/css/site.css` (`--blue`, `--teal`, `--sun`, `--ink`, `--text`, `--muted`), so the whole look
can be re-tinted in one place. Text colours meet WCAG AA contrast.
- **Glass / liquid glass** (`.glass`, `.glass-lite`): header, search, day navigator, captions over photos, viewer controls. A specular
  highlight follows the pointer and a glass lens glides between nav links. `.glass` uses a real backdrop blur; `.glass-lite` skips the blur
  for long lists of cards to keep scrolling smooth.
- **Clay** (`.clay`, `.clay--gold|teal|rose|violet|ink`): buttons, icons, number badges, state tiles, timeline stops — puffy inset highlights.
- **Spatial depth**: soft pastel light behind everything, hero layers that shift with the pointer, cards that lift and tilt toward the cursor.
- **Moving vehicles** (all pure CSS/SVG): planes crossing the hero sky, a car and bus on the hero road, a plane that flies along the
  "how it works" route as you scroll, a car on every itinerary timeline, and a plane → car → bus loader. Each stop's travel chip shows
  an icon for its travel mode. All vehicles hold still under `prefers-reduced-motion`.

## Troubleshooting
**An old icon still shows in the browser tab?** The site now serves a fully transparent tab icon at a new, versioned address
(`/static/blank.png?v=…`), which makes browsers replace whatever they saved earlier. Browsers keep tab icons in their own cache, so if you
still see an old one: hard-refresh (Ctrl+Shift+R), or close the tab and reopen it, or clear "Cached images and files" for the site.

**Stale design after an update?** CSS, JS and the icon URLs carry a version stamp that changes whenever the files change, so a normal refresh is enough.

## Travelers, budget and packing
- **Travelers (1–10)** is chosen in the search bar and can be changed on the plan page. It is kept in the URL (`?travelers=3&style=premium`), so a link shares the exact setup.
- **Estimated budget per person** = stay + food + local transport + entry & activities + 10% buffer, for a *Budget*, *Comfort* or *Premium* style.
  Rooms are shared by 2 and cabs by up to 4, so bigger groups pay less each and solo travellers pay more. Getting to the destination is not included.
  The page always shows the caption that the figure is **not accurate** and changes with the traveler.
- **Where the numbers come from:** `budget.py` holds one rate table per destination type (beach, heritage, hills, high-altitude, islands,
  spiritual, wildlife, big city, general), cross-checked against published travel-blog and Google results; the pages used are listed on the plan page under
  "How this estimate is made". To retune, edit `RATES` in `budget.py` — the browser maths in `plan.js` reads the same numbers from the page, and the
  test-suite checks the two stay identical.
- **Compare with travel blogs:** a "Search Google" link always appears; set `GOOGLE_SEARCH_API_KEY` + `GOOGLE_SEARCH_CX` to also show live results inline.
- **Smart packing checklist:** built from the place's themes (beach, hills, snow, wildlife, temples…), its best season and the trip length; ticks are saved in the browser.

## Download the plan as a PDF
Every plan has a **Download PDF** button (top of the page, and again in the "Take it with you" card), so travelers can keep the plan on their phone and use it offline.
- **What's inside:** cover with the key numbers · estimated budget with the "not accurate" caption and the pages it was checked against · must-visit list ·
  day-by-day itinerary (times, costs, travel mode, photo and a Google Maps link for every stop) · food · shopping · tips · the packing checklist
  (items you ticked show as ☑) · nearby hotels · a notes page. It reflects the **traveler count and travel style currently chosen on the page**.
- **How it works:** the page posts the plan it is showing to `POST /plan/pdf`, so the PDF always matches the screen (the planner is not asked again).
  The server cleans the data with the same code used for planner answers, then draws the PDF with ReportLab (`pdfgen.py`).
- **Photos** are best effort: one per stop plus a cover photo, re-using what the galleries already loaded. They are only downloaded from trusted hosts (Google, Wikimedia),
  shrunk and compressed, and anything slow is skipped after about 18 seconds — the PDF is still delivered. Typical size: well under 1 MB.
- **Safety limits:** requests over 500 KB are refused, text lengths and the number of days/stops are capped, and each visitor can create 8 PDFs a minute.
- **Fonts:** the PDF uses bundled fonts (`assets/fonts`), so it looks the same everywhere and shows the ₹ sign correctly. Characters those fonts cannot draw
  (for example Devanagari or emoji) are left out of the PDF rather than shown as empty boxes.
