/* NARADA YATRA — photo galleries + lightbox.
   Every [data-gallery] (day stops, food, shopping) loads its photos when it nears the viewport;
   clicking a photo opens the full-screen viewer. Hotels intentionally have no gallery. */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const cache = new Map();

  function load(q, name, n) {
    const key = q + "|" + name + "|" + n;
    if (!cache.has(key)) {
      cache.set(key, fetch("/api/photos?q=" + encodeURIComponent(q) + "&name=" + encodeURIComponent(name) + "&n=" + n)
        .then((r) => r.json()).then((j) => j.photos || []).catch(() => []));
    }
    return cache.get(key);
  }

  /* ---------- render one gallery ---------- */
  function render(el, photos) {
    const grid = $(".gallery__grid", el), count = $("[data-count-label]", el), label = el.dataset.label;
    grid.className = "gallery__grid";
    grid.innerHTML = "";
    if (!photos.length) {
      count.textContent = "No photos yet";
      const p = document.createElement("p");
      p.className = "gallery__empty";
      const a = document.createElement("a");
      a.href = "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(el.dataset.q);
      a.target = "_blank"; a.rel = "noreferrer"; a.textContent = "view it on Google Maps";
      p.append("We couldn't find photos for this place — ", a, ".");
      grid.appendChild(p);
      return;
    }
    count.textContent = photos.length + (photos.length === 1 ? " photo" : " photos") + " · tap to view";
    const shown = photos.slice(0, 4);
    grid.classList.add("g" + shown.length);
    shown.forEach((p, i) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "gt"; b.style.setProperty("--d", i * 70 + "ms");
      b.setAttribute("aria-label", "Open photo " + (i + 1) + " of " + photos.length + " — " + label);
      const img = new Image();
      img.src = p.url; img.alt = label; img.loading = "lazy"; img.referrerPolicy = "no-referrer";
      img.onerror = () => b.remove();
      b.appendChild(img);
      if (i === 3 && photos.length > 4) {
        const more = document.createElement("span");
        more.className = "gt__more"; more.textContent = "+" + (photos.length - 4);
        b.appendChild(more);
      }
      b.addEventListener("click", () => open(photos, i, label, b));
      grid.appendChild(b);
    });
  }

  function hydrate(el) {
    load(el.dataset.q, el.dataset.name, el.dataset.n || 5).then((photos) => render(el, photos));
  }
  const io = "IntersectionObserver" in window
    ? new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { io.unobserve(e.target); hydrate(e.target); } }), { rootMargin: "300px 0px" })
    : null;
  function scan(root) {
    root.querySelectorAll("[data-gallery]:not([data-seen])").forEach((el) => {
      el.dataset.seen = "1";
      io ? io.observe(el) : hydrate(el);
    });
  }
  scan(document);
  new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach((n) => n.nodeType === 1 && scan(n))))
    .observe(document.body, { childList: true, subtree: true });

  /* ---------- lightbox ---------- */
  const lb = $("#lightbox");
  if (!lb) return;
  const img = $(".lightbox__img", lb), title = $(".lightbox__title", lb), credit = $(".lightbox__credit", lb);
  const counter = $(".lightbox__count", lb), thumbs = $(".lightbox__thumbs", lb), stage = $(".lightbox__stage", lb);
  let list = [], idx = 0, opener = null, label = "";

  function show(i) {
    idx = (i + list.length) % list.length;
    const p = list[idx];
    img.classList.remove("is-ready");
    const next = new Image();
    next.onload = () => { img.src = p.url; img.alt = label; requestAnimationFrame(() => img.classList.add("is-ready")); };
    next.onerror = () => { img.src = p.url; img.classList.add("is-ready"); };
    next.src = p.url;
    title.textContent = label;
    credit.textContent = "Photo: " + p.credit + " · " + p.source;
    counter.textContent = idx + 1 + " / " + list.length;
    Array.from(thumbs.children).forEach((t, k) => {
      t.classList.toggle("is-active", k === idx);
      if (k === idx) t.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
    });
    [idx + 1, idx - 1].forEach((k) => { const pre = new Image(); pre.src = list[(k + list.length) % list.length].url; });
  }

  function open(photos, i, name, from) {
    list = photos; label = name; opener = from;
    thumbs.innerHTML = "";
    photos.forEach((p, k) => {
      const b = document.createElement("button");
      b.type = "button"; b.setAttribute("aria-label", "Show photo " + (k + 1));
      const t = new Image(); t.src = p.url; t.alt = ""; t.referrerPolicy = "no-referrer";
      b.appendChild(t);
      b.addEventListener("click", () => show(k));
      thumbs.appendChild(b);
    });
    const multi = photos.length > 1;
    $(".lightbox__nav--prev", lb).hidden = !multi; $(".lightbox__nav--next", lb).hidden = !multi; thumbs.hidden = !multi;
    lb.hidden = false;
    document.documentElement.classList.add("lb-open");
    requestAnimationFrame(() => { lb.classList.add("is-open"); $(".lightbox__close", lb).focus({ preventScroll: true }); });
    show(i);
  }

  function close() {
    if (lb.hidden) return;
    lb.classList.remove("is-open");
    document.documentElement.classList.remove("lb-open");
    setTimeout(() => { lb.hidden = true; img.removeAttribute("src"); }, 320);
    if (opener) opener.focus({ preventScroll: true });
  }

  lb.addEventListener("click", (e) => {
    if (e.target.closest("[data-lb-close]")) close();
    else if (e.target.closest("[data-lb-prev]")) show(idx - 1);
    else if (e.target.closest("[data-lb-next]")) show(idx + 1);
  });
  document.addEventListener("keydown", (e) => {
    if (lb.hidden) return;
    if (e.key === "Escape") close();
    else if (e.key === "ArrowRight") show(idx + 1);
    else if (e.key === "ArrowLeft") show(idx - 1);
    else if (e.key === "Tab") {                       // keep focus inside the viewer
      const f = Array.from(lb.querySelectorAll("button")).filter((b) => !b.hidden && b.offsetParent !== null);
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  // swipe on touch screens
  let sx = null;
  stage.addEventListener("pointerdown", (e) => { sx = e.clientX; });
  stage.addEventListener("pointerup", (e) => {
    if (sx === null) return;
    const dx = e.clientX - sx; sx = null;
    if (Math.abs(dx) > 50) show(idx + (dx < 0 ? 1 : -1));
  });
})();
