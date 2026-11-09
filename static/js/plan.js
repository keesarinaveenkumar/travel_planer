/* NARADA YATRA — plan page extras: live trip budget (travelers + travel style) and the packing checklist. */
(function () {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const money = (n) => "₹" + Math.round(n).toLocaleString("en-IN");
  const r10 = (x) => Math.floor(x / 10 + 0.5) * 10;
  const r100 = (x) => Math.floor(x / 100 + 0.5) * 100;

  /* The same maths as budget.compute() on the server — keep the two in step. */
  function estimate(m, n, style) {
    const r = m.rates[style];
    const rooms = Math.ceil(n / m.roomSize);
    const single = n === 1 ? m.single[style] : 1;
    const cab = Math.ceil(n / m.cabSize) / n;
    const parts = {
      stay: m.nights ? r10((rooms * r.stay * single * m.nights) / n) : 0,
      food: r10(r.food * m.days),
      local: r10(r.tmult * (m.stopShared * cab + m.stopFixed) + r.local * m.days * cab),
      entry: r10(Math.max(m.entry, m.floor[style] * m.days)),
    };
    const subtotal = parts.stay + parts.food + parts.local + parts.entry;
    parts.buffer = r10(subtotal * m.buffer);
    const total = subtotal + parts.buffer, pp = r100(total);
    return { parts, total, pp, low: r100(total * 0.85), high: r100(total * 1.2), group: pp * n, perDay: r100(total / Math.max(m.days, 1)) };
  }
  window.NaradaBudget = { estimate };                       // also lets the tests compare it with the server

  function tween(el, to, fmt) {
    const from = el._v == null ? to : el._v;
    el._v = to;
    cancelAnimationFrame(el._raf);
    if (reduce || from === to) { el.textContent = fmt(to); return; }
    const t0 = performance.now(), dur = 550;
    (function step(t) {
      const p = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(from + (to - from) * e);
      if (p < 1) el._raf = requestAnimationFrame(step);
    })(t0);
  }

  /* ---------- budget panel ---------- */
  function initBudget(root) {
    const box = $("[data-budget]", root);
    if (!box || box.dataset.ready) return;
    box.dataset.ready = "1";
    const m = JSON.parse(box.dataset.model);
    let n = +box.dataset.n, style = box.dataset.style;
    const pp = $("[data-pp]", box), range = $("[data-range]", box), group = $("[data-group]", box), perday = $("[data-perday]", box);
    const nText = $("[data-n-text]", box), nOut = $("[data-n-out]", box), dec = $("[data-n-dec]", box), inc = $("[data-n-inc]", box);
    const lens = $(".seg__lens", box), segs = $$(".seg__btn", box);
    const bars = Object.fromEntries($$("[data-bar]", box).map((e) => [e.dataset.bar, e]));
    const rows = Object.fromEntries($$("[data-part]", box).map((e) => [e.dataset.part, e]));

    function placeLens(animate) {
      const on = segs.find((b) => b.classList.contains("is-on"));
      if (!on) return;
      lens.style.width = on.offsetWidth + "px";
      lens.style.transform = "translateX(" + on.offsetLeft + "px)";
      if (animate) { lens.classList.remove("goo"); void lens.offsetWidth; lens.classList.add("goo"); }
    }
    function render() {
      const e = estimate(m, n, style);
      tween(pp, e.pp, money); tween(group, e.group, money); tween(perday, e.perDay, money);
      range.textContent = money(e.low) + " – " + money(e.high);
      nText.textContent = n + (n > 1 ? " travelers" : " traveler"); nOut.textContent = n;
      dec.disabled = n <= 1; inc.disabled = n >= 10;
      for (const k in e.parts) {
        const share = e.total ? (e.parts[k] * 100) / e.total : 0;
        bars[k].style.setProperty("--w", share.toFixed(1) + "%");
        tween($("[data-val]", rows[k]), e.parts[k], money);
        $("[data-pct]", rows[k]).textContent = Math.round(share) + "%";
      }
      $$("[data-rate=stay]", box).forEach((el) => (el.textContent = money(m.rates[style].stay)));
      $$("[data-rate=food]", box).forEach((el) => (el.textContent = money(m.rates[style].food)));
      box.dataset.n = n; box.dataset.style = style;
      try { const u = new URL(location.href); u.searchParams.set("travelers", n); u.searchParams.set("style", style); history.replaceState(null, "", u); } catch (_) {}
      const chip = $("#travelers-chip span"); if (chip) chip.textContent = n + (n > 1 ? " travelers" : " traveler");
      const sel = $("form.searchbar select[name=travelers]"); if (sel) sel.value = n;
      const plan = $("#plan"); if (plan) { plan.dataset.travelers = n; plan.dataset.style = style; }
    }
    const segNote = $("[data-seg-note]", box);
    function pick(s, focus) {
      style = s;
      segs.forEach((b) => { const on = b.dataset.style === s; b.classList.toggle("is-on", on); b.setAttribute("aria-checked", on); if (on && focus) b.focus(); });
      segNote.textContent = (segs.find((b) => b.dataset.style === s) || {}).dataset.note || "";
      placeLens(true); render();
    }
    dec.addEventListener("click", () => { if (n > 1) { n--; render(); } });
    inc.addEventListener("click", () => { if (n < 10) { n++; render(); } });
    segs.forEach((b) => b.addEventListener("click", () => pick(b.dataset.style)));
    $(".seg", box).addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      e.preventDefault();
      const order = segs.map((b) => b.dataset.style), i = order.indexOf(style);
      pick(order[(i + (e.key === "ArrowRight" ? 1 : order.length - 1)) % order.length], true);
    });
    addEventListener("resize", () => placeLens(false));
    (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(() => placeLens(false));

    // start from the server's numbers, then count up once when the panel scrolls into view
    const first = estimate(m, n, style);
    [pp, group, perday].forEach((el, i) => (el._v = [first.pp, first.group, first.perDay][i]));
    placeLens(false); render();
    if ("IntersectionObserver" in window && !reduce) {
      const io = new IntersectionObserver((es) => {
        if (!es[0].isIntersecting) return;
        io.disconnect();
        [pp, group, perday].forEach((el) => (el._v = 0));
        $$("[data-val]", box).forEach((el) => (el._v = 0));
        render();
      }, { threshold: 0.4 });
      io.observe(box);
    }

    // optional live blog results (the server answers 204 when no Google search key is configured)
    const guides = $("#guides");
    if (guides) {
      fetch("/plan/guides?place=" + encodeURIComponent(guides.dataset.place))
        .then((r) => (r.status === 200 ? r.text() : ""))
        .then((html) => { html ? (guides.innerHTML = html) : guides.remove(); })
        .catch(() => guides.remove());
    }
  }

  /* ---------- packing checklist ---------- */
  function initPack(root) {
    const box = $("[data-pack]", root);
    if (!box || box.dataset.ready) return;
    box.dataset.ready = "1";
    const key = box.dataset.key, boxes = $$("input[data-pack-id]", box), total = boxes.length;
    let saved = [];
    try { saved = JSON.parse(localStorage.getItem(key) || "[]"); } catch (_) {}
    const set = new Set(Array.isArray(saved) ? saved : []);
    boxes.forEach((b) => { b.checked = set.has(b.dataset.packId); });
    const fill = $("[data-pack-fill]", box), count = $("[data-pack-count]", box), msg = $("[data-pack-msg]", box);
    function render() {
      const done = boxes.filter((b) => b.checked).length, pct = total ? (done / total) * 100 : 0;
      fill.style.width = pct + "%";
      box.style.setProperty("--pp", pct + "%");
      count.textContent = done;
      box.classList.toggle("done", total > 0 && done === total);
      msg.textContent = total > 0 && done === total ? "— all packed, have a great trip!" : "";
    }
    boxes.forEach((b) => b.addEventListener("change", () => {
      b.checked ? set.add(b.dataset.packId) : set.delete(b.dataset.packId);
      try { localStorage.setItem(key, JSON.stringify([...set])); } catch (_) {}
      render();
    }));
    $("[data-pack-reset]", box).addEventListener("click", () => {
      boxes.forEach((b) => (b.checked = false)); set.clear();
      try { localStorage.removeItem(key); } catch (_) {}
      render();
    });
    render();
  }

  /* ---------- download the whole plan as a PDF ---------- */
  function toast(message) {
    const el = document.createElement("div");
    el.className = "toast"; el.setAttribute("role", "alert"); el.textContent = message;
    document.body.appendChild(el);
    requestAnimationFrame(() => el.classList.add("show"));
    setTimeout(() => { el.classList.remove("show"); setTimeout(() => el.remove(), 450); }, 5500);
  }
  async function downloadPdf(btn) {
    const buttons = $$("[data-pdf]");
    if (buttons.some((b) => b.dataset.busy)) return;
    const meta = $("#plan-meta"), plan = $("#plan");
    if (!meta || !meta.dataset.plan || !plan) return;
    const labels = buttons.map((b) => [$("span", b), $("span", b).textContent]);
    buttons.forEach((b) => { b.dataset.busy = "1"; b.classList.add("is-busy"); $("span", b).textContent = "Preparing your PDF…"; });
    try {
      const budgetBox = $("[data-budget]"), packBox = $("[data-pack]");
      let packed = [];
      try { packed = JSON.parse(localStorage.getItem(packBox ? packBox.dataset.key : "") || "[]"); } catch (_) {}
      const r = await fetch("/plan/pdf", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          place: plan.dataset.place, days: +plan.dataset.days,
          travelers: budgetBox ? +budgetBox.dataset.n : +plan.dataset.travelers,
          style: budgetBox ? budgetBox.dataset.style : plan.dataset.style,
          plan: JSON.parse(meta.dataset.plan), packed: Array.isArray(packed) ? packed : [],
        }),
      });
      if (!r.ok) {
        let m = "Couldn't create the PDF. Please try again.";
        try { m = (await r.json()).error || m; } catch (_) {}
        throw new Error(m);
      }
      const blob = await r.blob();
      const found = /filename="?([^";]+)"?/.exec(r.headers.get("Content-Disposition") || "");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = found ? found[1] : "narada-yatra-plan.pdf";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 8000);
      buttons.forEach((b) => { b.classList.remove("is-busy"); $("span", b).textContent = "Downloaded ✓"; });    // spinner off the moment the file is delivered
      await new Promise((res) => setTimeout(res, 2200));
    } catch (e) {
      toast(e.message || "Couldn't create the PDF. Please try again.");
    } finally {
      buttons.forEach((b) => { delete b.dataset.busy; b.classList.remove("is-busy"); });
      labels.forEach(([el, text]) => { el.textContent = text; });
    }
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-pdf]");
    if (b && !b.disabled) downloadPdf(b);
  });

  function init() {
    initBudget(document); initPack(document);
    $$("[data-pdf]").forEach((b) => { b.disabled = false; });          // the hero button waits until there is a plan to export
  }
  addEventListener("plan:ready", init);
  document.addEventListener("DOMContentLoaded", init);
})();
