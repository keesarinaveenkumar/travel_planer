/* NARADA YATRA — motion layer.
   scroll reveal · parallax · star-field · word rotator · count-up · tilt cards · cursor ring
   timeline progress + day scroll-spy · map toggle · header/progress/back-to-top · wipe page transitions.
   Everything calms down for visitors who prefer reduced motion. */
(function () {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const fine = matchMedia("(hover: hover) and (pointer: fine)").matches;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const root = document.documentElement;

  /* ---------- scroll reveal ---------- */
  const revealIO = !reduce && "IntersectionObserver" in window
    ? new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); revealIO.unobserve(e.target); } }),
        { threshold: 0.12, rootMargin: "0px 0px -6% 0px" })
    : null;
  const watch = (el) => { if (!el.classList.contains("in")) revealIO ? revealIO.observe(el) : el.classList.add("in"); };

  /* ---------- count-up ---------- */
  function countUp(el) {
    const target = +el.dataset.count, pre = el.dataset.prefix || "", suf = el.dataset.suffix || "";
    if (reduce) { el.textContent = pre + target.toLocaleString("en-IN") + suf; return; }
    const t0 = performance.now(), dur = 1500;
    (function tick(t) {
      const p = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3);
      el.textContent = pre + Math.round(target * e).toLocaleString("en-IN") + suf;
      if (p < 1) requestAnimationFrame(tick);
    })(t0);
  }
  const countIO = "IntersectionObserver" in window
    ? new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { countIO.unobserve(e.target); countUp(e.target); } }), { threshold: 0.6 })
    : null;

  /* ---------- per-element setup (also runs on content injected later) ---------- */
  function scan(node) {
    const within = (sel) => (node.matches && node.matches(sel) ? [node] : []).concat($$(sel, node));
    within("[data-reveal]").forEach(watch);
    within("[data-count]:not([data-cu])").forEach((el) => { el.dataset.cu = 1; countIO ? countIO.observe(el) : countUp(el); });
    if (fine && !reduce) within("[data-tilt]:not([data-tl])").forEach((el) => {
      el.dataset.tl = 1;
      el.addEventListener("pointermove", (e) => {
        const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
        el.style.setProperty("--ry", ((x - 0.5) * 12).toFixed(2) + "deg");
        el.style.setProperty("--rx", ((0.5 - y) * 12).toFixed(2) + "deg");
        el.style.setProperty("--mx", (x * 100).toFixed(1) + "%");
        el.style.setProperty("--my", (y * 100).toFixed(1) + "%");
      });
      el.addEventListener("pointerleave", () => { el.style.setProperty("--rx", "0deg"); el.style.setProperty("--ry", "0deg"); });
    });
    refresh();
  }
  new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach((n) => n.nodeType === 1 && scan(n))))
    .observe(document.body, { childList: true, subtree: true });

  /* ---------- rotating destination word ---------- */
  $$("[data-rotate]").forEach((el) => {
    const words = el.dataset.rotate.split("|"); let i = 0;
    if (reduce) return;
    setInterval(() => {
      el.classList.add("out");
      setTimeout(() => {
        i = (i + 1) % words.length; el.textContent = words[i];
        el.classList.remove("out"); el.classList.add("pre"); void el.offsetWidth; el.classList.remove("pre");
      }, 450);
    }, 2600);
  });

  /* ---------- scroll-linked work ---------- */
  const header = $("#site-header"), bar = $("#progress"), toTop = $("#to-top");
  let layers = $$("[data-parallax]"), lastY = scrollY, queued = false, activeLink = null;

  function timelines() {
    const mid = innerHeight * 0.62;
    $$("[data-timeline]").forEach((tl) => {
      const r = tl.getBoundingClientRect();
      const pn = Math.min(Math.max((mid - r.top) / r.height, 0), 1);
      tl.style.setProperty("--p", (pn * 100).toFixed(1) + "%");
      tl.style.setProperty("--pn", pn.toFixed(3));
      $$("[data-stop]", tl).forEach((s) => s.classList.toggle("is-lit", s.getBoundingClientRect().top + 40 < mid));
    });
  }
  function placeBar(link) {
    const nav = link.parentElement, b = $(".daynav__bar", nav);
    b.style.width = link.offsetWidth + "px";
    b.style.transform = "translateX(" + link.offsetLeft + "px)";
    b.classList.remove("goo"); void b.offsetWidth; b.classList.add("goo");
    if (nav.scrollWidth > nav.clientWidth) nav.scrollTo({ left: link.offsetLeft - nav.clientWidth / 2 + link.offsetWidth / 2, behavior: "smooth" });
  }
  function spy() {
    const links = $$(".daynav__link");
    if (!links.length) return;
    let cur = links[0];
    links.forEach((l) => { const sec = document.getElementById(l.dataset.spy); if (sec && sec.getBoundingClientRect().top <= innerHeight * 0.32) cur = l; });
    if (cur !== activeLink) {
      links.forEach((l) => l.classList.toggle("active", l === cur));
      activeLink = cur; placeBar(cur);
    }
  }
  function routes() {
    $$("[data-route]").forEach((w) => {
      const r = w.getBoundingClientRect();
      const p = Math.min(Math.max((innerHeight * 0.8 - r.top) / (r.height + innerHeight * 0.25), 0), 1);
      w.style.setProperty("--pn", p.toFixed(3));
      $$(".route__dot", w).forEach((d) => d.classList.toggle("on", p >= parseFloat(d.dataset.at) - 0.04));
    });
  }
  function frame() {
    queued = false;
    const y = scrollY, max = root.scrollHeight - innerHeight;
    bar.style.transform = "scaleX(" + (max > 0 ? Math.min(y / max, 1) : 0) + ")";
    header.classList.toggle("scrolled", y > 8);
    const dy = y - lastY;
    if (Math.abs(dy) > 2) {
      if (dy > 0 && y > 160 && !header.contains(document.activeElement)) header.classList.add("hide");
      else if (dy < 0) header.classList.remove("hide");
      lastY = y;
    }
    if (y <= 160) header.classList.remove("hide");
    root.classList.toggle("hdr-hide", header.classList.contains("hide"));
    toTop.classList.toggle("show", y > 700);
    timelines(); spy(); routes();
    if (reduce) return;
    layers.forEach((el) => {
      const host = el.closest("[data-parallax-host]") || el.parentElement, r = host.getBoundingClientRect();
      if (r.bottom < -80 || r.top > innerHeight + 80) return;
      const p = Math.min(Math.max(-r.top, 0), r.height);
      el.style.transform = "translate3d(0," + (p * parseFloat(el.dataset.parallax)).toFixed(1) + "px,0)";
      if ("fade" in el.dataset) el.style.opacity = (1 - 0.88 * (p / r.height)).toFixed(2);
    });
  }
  function refresh() { layers = $$("[data-parallax]"); activeLink = null; if (!queued) { queued = true; requestAnimationFrame(frame); } }
  addEventListener("scroll", refresh, { passive: true });
  addEventListener("resize", refresh);
  addEventListener("plan:ready", () => setTimeout(refresh, 60));
  toTop.addEventListener("click", () => scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" }));

  /* ---------- cursor ring (desktop only) ---------- */
  const cur = $("#cursor");
  if (cur && fine && !reduce) {
    let x = -100, y = -100, tx = -100, ty = -100;
    addEventListener("pointermove", (e) => {
      tx = e.clientX; ty = e.clientY; cur.classList.add("on");
      cur.classList.toggle("is-link", !!e.target.closest("a,button,input,select,[data-tilt],.gt"));
    }, { passive: true });
    document.addEventListener("pointerleave", () => cur.classList.remove("on"));
    (function loop() { x += (tx - x) * 0.2; y += (ty - y) * 0.2; cur.style.transform = "translate3d(" + x + "px," + y + "px,0)"; requestAnimationFrame(loop); })();
  }

  /* ---------- click ripple ---------- */
  document.addEventListener("pointerdown", (e) => {
    if (reduce || e.button > 0) return;
    const t = e.target.closest(".ripple");
    if (!t) return;
    const r = t.getBoundingClientRect(), d = Math.max(r.width, r.height) * 2.2, dot = document.createElement("span");
    dot.className = "ripple-dot";
    dot.style.cssText = "width:" + d + "px;height:" + d + "px;left:" + (e.clientX - r.left - d / 2) + "px;top:" + (e.clientY - r.top - d / 2) + "px";
    t.appendChild(dot);
    dot.addEventListener("animationend", () => dot.remove());
    setTimeout(() => dot.remove(), 900);
  });

  /* ---------- map toggle (loads the map only when asked) ---------- */
  document.addEventListener("click", (e) => {
    const b = e.target.closest(".maptoggle");
    if (!b) return;
    const panel = b.nextElementSibling, inner = panel.firstElementChild, open = panel.classList.toggle("open");
    b.setAttribute("aria-expanded", open);
    if (open && !inner.firstChild) {
      const f = document.createElement("iframe");
      f.src = b.dataset.mapSrc; f.title = "Map"; f.loading = "lazy"; f.referrerPolicy = "no-referrer-when-downgrade";
      inner.appendChild(f);
    }
    $("span", b).textContent = open ? "Hide map" : b.dataset.label;
  });

  /* ---------- wipe page transitions ---------- */
  const wipe = $("#wipe"), page = $("#page");
  if (root.classList.contains("arriving")) {
    const go = () => requestAnimationFrame(() => {
      wipe.classList.add("exit"); root.classList.remove("arriving");
      setTimeout(() => wipe.classList.remove("exit"), 750);
    });
    reduce ? root.classList.remove("arriving") : go();
  }
  document.addEventListener("click", (e) => {
    if (reduce || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest("a[href]");
    if (!a || (a.target && a.target !== "_self") || a.hasAttribute("download")) return;
    const u = new URL(a.href, location.href);
    if (u.origin !== location.origin || (u.pathname === location.pathname && u.search === location.search)) return;
    e.preventDefault();
    try { sessionStorage.setItem("wipe", "1"); } catch (_) {}
    wipe.classList.add("cover");
    setTimeout(() => { location.href = u.href; }, 480);
  });
  document.addEventListener("submit", () => {
    if (reduce) return;
    try { sessionStorage.setItem("wipe", "1"); } catch (_) {}
    wipe.classList.add("cover");
  });
  addEventListener("pageshow", (e) => { if (e.persisted) { wipe.classList.remove("cover"); root.classList.remove("arriving"); } });

  /* ---------- spatial depth: hero layers follow the pointer ---------- */
  const hero = $("[data-spatial]");
  if (hero && fine && !reduce) {
    hero.addEventListener("pointermove", (e) => {
      const r = hero.getBoundingClientRect();
      hero.style.setProperty("--mx", (((e.clientX - r.left) / r.width) * 2 - 1).toFixed(3));
      hero.style.setProperty("--my", (((e.clientY - r.top) / r.height) * 2 - 1).toFixed(3));
    });
    hero.addEventListener("pointerleave", () => { hero.style.setProperty("--mx", 0); hero.style.setProperty("--my", 0); });
  }

  /* ---------- liquid glass: a specular highlight follows the pointer ---------- */
  if (fine && !reduce) {
    document.addEventListener("pointermove", (e) => {
      const g = e.target.closest && e.target.closest(".glass,.glass-lite");
      if (!g) return;
      const r = g.getBoundingClientRect();
      g.style.setProperty("--sx", e.clientX - r.left + "px");
      g.style.setProperty("--sy", e.clientY - r.top + "px");
    }, { passive: true });
  }

  /* ---------- nav lens: a glass pill glides to the link you hover ---------- */
  const nav = $(".nav"), lens = $(".nav__lens");
  if (nav && lens) {
    const links = $$("a:not(.btn)", nav), current = () => links.find((l) => l.classList.contains("active"));
    function to(l) {
      if (!l) { lens.style.opacity = 0; return; }
      lens.style.opacity = 1;
      lens.style.width = l.offsetWidth + "px";
      lens.style.transform = "translateX(" + l.offsetLeft + "px)";
      lens.classList.remove("goo"); void lens.offsetWidth; lens.classList.add("goo");
    }
    links.forEach((l) => { l.addEventListener("pointerenter", () => to(l)); l.addEventListener("focus", () => to(l)); });
    nav.addEventListener("pointerleave", () => to(current()));
    addEventListener("resize", () => to(current()));
    (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(() => to(current()));
    to(current());
  }

  scan(document);
  frame();
})();
