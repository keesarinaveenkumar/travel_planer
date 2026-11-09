/* NARADA YATRA — page logic: lazy photos, search, state filter, rail, plan loading. */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  /* ---------- lazy single photos: .ph[data-photo] ---------- */
  const photoCache = {};
  function fallback(el, name) {
    const d = document.createElement("div");
    d.className = "ph__fallback";
    d.textContent = name;
    el.appendChild(d);
  }
  function fillPhoto(el) {
    const q = el.dataset.photo, name = el.dataset.name || q;
    photoCache[q] = photoCache[q] || fetch("/api/photo?q=" + encodeURIComponent(q) + "&name=" + encodeURIComponent(name))
      .then((r) => r.json()).then((j) => j.url).catch(() => null);
    photoCache[q].then((url) => {
      const sk = $(".ph__skeleton", el); if (sk) sk.remove();
      if (!url) return fallback(el, name);
      const img = new Image();
      img.className = "ph__img"; img.alt = name; img.referrerPolicy = "no-referrer";
      img.onload = () => img.classList.add("is-loaded");
      img.onerror = () => { img.remove(); fallback(el, name); };
      img.src = url;
      el.appendChild(img);
    });
  }
  const photoIO = "IntersectionObserver" in window
    ? new IntersectionObserver((entries) => entries.forEach((e) => {
        if (e.isIntersecting) { photoIO.unobserve(e.target); fillPhoto(e.target); }
      }), { rootMargin: "300px 0px" })
    : null;
  function scanPhotos(root) {
    $$(".ph[data-photo]:not([data-seen])", root).forEach((el) => {
      el.dataset.seen = "1";
      photoIO ? photoIO.observe(el) : fillPhoto(el);
    });
  }
  scanPhotos(document);
  new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach((n) => n.nodeType === 1 && scanPhotos(n))))
    .observe(document.body, { childList: true, subtree: true });

  /* ---------- search with suggestions ---------- */
  function initSearch(form) {
    const input = $("input[name=place]", form), list = $(".suggest", form);
    let hits = [], active = -1;
    function close() { list.hidden = true; active = -1; }
    function mark() { $$("button", list).forEach((b, i) => b.classList.toggle("is-active", i === active)); }
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      list.innerHTML = "";
      if (q.length < 2) return close();
      hits = window.ALL_PLACES.filter((p) => (p.place + " " + p.state).toLowerCase().includes(q)).slice(0, 7);
      hits.forEach((m) => {
        const b = document.createElement("button");
        b.type = "button";
        b.innerHTML = "<span></span><small></small>";
        b.firstChild.textContent = m.place; b.lastChild.textContent = m.state;
        b.addEventListener("click", () => { input.value = m.place; form.requestSubmit(); });
        list.appendChild(b);
      });
      list.hidden = hits.length === 0; active = -1;
    });
    input.addEventListener("keydown", (e) => {
      if (list.hidden) return;
      if (e.key === "ArrowDown") { e.preventDefault(); active = (active + 1) % hits.length; mark(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); active = (active - 1 + hits.length) % hits.length; mark(); }
      else if (e.key === "Enter" && active > -1) { e.preventDefault(); input.value = hits[active].place; form.requestSubmit(); }
      else if (e.key === "Escape") close();
    });
    document.addEventListener("click", (e) => { if (!form.contains(e.target)) close(); });
  }
  $$("form.searchbar").forEach(initSearch);

  /* ---------- destination rail arrows ---------- */
  $$("[data-rail-btn]").forEach((b) => b.addEventListener("click", () => {
    const rail = $("[data-rail]"), dir = b.dataset.railBtn === "next" ? 1 : -1;
    rail.scrollBy({ left: dir * Math.min(rail.clientWidth * 0.8, 640), behavior: "smooth" });
  }));

  /* ---------- states page: live filter + region chips ---------- */
  const filter = $("#state-filter");
  if (filter) {
    const cards = $$("[data-state-card]"), chips = $$("[data-region-chip]"), counter = $("#state-count"), empty = $("#state-empty");
    let region = "all";
    function apply() {
      const q = filter.value.trim().toLowerCase();
      let shown = 0;
      cards.forEach((c) => {
        const ok = (region === "all" || c.dataset.region === region) && c.dataset.name.includes(q);
        const was = !c.hidden;
        c.hidden = !ok;
        if (ok) { shown++; if (!was) { c.classList.remove("card-in"); void c.offsetWidth; c.classList.add("card-in"); } }
      });
      counter.textContent = shown + (shown === 1 ? " place to start from" : " states & territories");
      empty.hidden = shown !== 0;
    }
    filter.addEventListener("input", apply);
    chips.forEach((ch) => ch.addEventListener("click", () => {
      region = ch.dataset.regionChip;
      chips.forEach((c) => c.classList.toggle("is-on", c === ch));
      apply();
    }));
  }

  /* ---------- plan page ---------- */
  const box = $("#plan");
  if (box) {
    const { place, days, travelers, style } = box.dataset;
    const loading = $("#plan-loading"), errBox = $("#plan-error"), msg = $(".journey__msg");
    const msgs = (msg.dataset.msgs || "").split("|");
    let mi = 0;
    // the loader's vehicle changes each lap: plane → car → bus
    const veh = $(".journey__veh");
    if (veh) veh.addEventListener("animationiteration", (e) => { if (e.target === veh) veh.dataset.v = (+veh.dataset.v + 1) % 3; });   // ignore the wheels' own spin events
    const ticker = setInterval(() => {
      msg.classList.add("swap");
      setTimeout(() => { mi = (mi + 1) % msgs.length; msg.textContent = msgs[mi]; msg.classList.remove("swap"); }, 300);
    }, 2200);

    async function run() {
      loading.hidden = false; errBox.hidden = true;
      try {
        const r = await fetch("/plan/content?place=" + encodeURIComponent(place) + "&days=" + days + "&travelers=" + travelers + "&style=" + style);
        if (!r.ok) { let m = "Something went wrong. Please try again."; try { m = (await r.json()).error || m; } catch (_) {} throw new Error(m); }
        box.innerHTML = await r.text();
        const meta = $("#plan-meta");
        if (meta) {
          box.dataset.state = meta.dataset.state;
          $("#state-label").textContent = meta.dataset.state;
          const season = $("#season-chip");
          if (meta.dataset.season && season) { season.textContent = "Best: " + meta.dataset.season; season.hidden = false; }
        }
        window.dispatchEvent(new Event("plan:ready"));
      } catch (e) {
        $("p", errBox).textContent = e.message;
        errBox.hidden = false;
      } finally { loading.hidden = true; clearInterval(ticker); }
    }
    $("#plan-retry").addEventListener("click", run);
    run();

    const hotels = $("#hotels");
    fetch("/plan/hotels?place=" + encodeURIComponent(place)).then(async (r) => {
      if (!r.ok) { let m = "Hotels couldn't be loaded right now."; try { m = (await r.json()).error || m; } catch (_) {} throw new Error(m); }
      hotels.innerHTML = await r.text();
    }).catch((e) => {
      hotels.innerHTML = "";
      const p = document.createElement("p"); p.className = "muted"; p.textContent = e.message; hotels.appendChild(p);
    });

    const save = $("#save-trip");
    save.addEventListener("click", async () => {
      await fetch("/api/trip", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ place, state: box.dataset.state || null }) });
      save.querySelector("span").textContent = "Saved to my trips ✓";
      save.classList.remove("pop"); void save.offsetWidth; save.classList.add("pop");
    });
  }
})();
