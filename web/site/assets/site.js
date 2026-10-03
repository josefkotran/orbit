/* Orbit – orbit.easya.cz. Everything that moves on the page.
   One frame loop (gsap.ticker) drives the star field, the kinetic type, the orrery and the waves. */
(function () {
  "use strict";
  var html = document.documentElement;
  var gsap = window.gsap, ScrollTrigger = window.ScrollTrigger;
  if (!gsap || !ScrollTrigger) { html.classList.remove("js"); return; }  // the page still reads fine without motion
  gsap.registerPlugin(ScrollTrigger);

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var finePointer = window.matchMedia("(pointer: fine)").matches;
  var canHover = window.matchMedia("(hover: hover)").matches;
  if (reduce) html.classList.add("reduce");
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var clamp = function (v, a, b) { return v < a ? a : v > b ? b : v; };
  var lerp = function (a, b, t) { return a + (b - a) * t; };
  var czNum = function (v, d) { return v.toFixed(d).replace(".", ","); };
  function rng(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; var t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

  /* ---------- pointer ---------- */
  var ptr = { x: innerWidth / 2, y: innerHeight * 0.4, nx: 0.5, ny: 0.4, mouse: false, seen: false };
  addEventListener("pointermove", function (e) {
    ptr.x = e.clientX; ptr.y = e.clientY; ptr.nx = e.clientX / innerWidth; ptr.ny = e.clientY / innerHeight;
    ptr.mouse = e.pointerType === "mouse"; ptr.seen = true;
  }, { passive: true });
  document.addEventListener("pointerleave", function () { ptr.seen = false; });

  /* ---------- theme: the same three colours as in the app ---------- */
  var THEMES = { blue: [91, 157, 255], violet: [167, 139, 250], teal: [45, 212, 191] };
  var accent = THEMES[html.dataset.theme] || THEMES.blue;
  var themeButtons = $$(".themes button");
  function markTheme() { themeButtons.forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.theme === html.dataset.theme)); }); }
  markTheme();
  themeButtons.forEach(function (b) {
    b.addEventListener("click", function () {
      var name = b.dataset.theme;
      html.dataset.theme = name; accent = THEMES[name]; markTheme();
      try { localStorage.setItem("orbit-theme", name); } catch (e) {}
      space.flash = 1;
    });
  });

  /* ---------- smooth scroll ---------- */
  var lenis = null, velocity = 0, lastY = scrollY;
  if (!reduce && window.Lenis) {
    lenis = new window.Lenis({ lerp: 0.085, smoothWheel: true });
    lenis.on("scroll", function (e) { velocity = e.velocity; ScrollTrigger.update(); });
    gsap.ticker.add(function (time) { lenis.raf(time * 1000); });
    gsap.ticker.lagSmoothing(0);
  }
  $$('a[href^="#"]').forEach(function (a) {
    a.addEventListener("click", function (e) {
      var id = a.getAttribute("href");
      var target = id === "#top" ? document.body : $(id);
      if (!target) return;
      e.preventDefault();
      if (lenis) lenis.scrollTo(id === "#top" ? 0 : target, { offset: -40, duration: 1.6 });
      else target.scrollIntoView({ behavior: reduce ? "auto" : "smooth" });
    });
  });
  function scrollPos() { return lenis ? lenis.scroll : scrollY; }

  /* ---------- star field: stars fly towards you, faster when you scroll, warp over the main button;
                 while the headline listens, they line up into a voice wave ---------- */
  var space = { cv: $("#space"), stars: [], w: 0, h: 0, dpr: 1, cam: [0, 0], warp: 0, warpTo: 0, intro: reduce ? 0 : 1, flash: 0, listen: 0 };
  space.ctx = space.cv.getContext("2d");
  function star(z) { return { x: (Math.random() * 2 - 1) * 1.8, y: (Math.random() * 2 - 1) * 1.15, z: z, tint: Math.random() < 0.16, s: 0.55 + Math.random() * 1.1, b: Math.random() * 2 - 1 }; }
  function sizeSpace() {
    space.dpr = Math.min(devicePixelRatio || 1, 1.5); space.w = innerWidth; space.h = innerHeight;
    space.cv.width = Math.round(space.w * space.dpr); space.cv.height = Math.round(space.h * space.dpr);
    space.ctx.setTransform(space.dpr, 0, 0, space.dpr, 0, 0);
    var n = Math.round(clamp(space.w * space.h / 1500, 320, 1100));
    space.stars = [];
    for (var i = 0; i < n; i++) space.stars.push(star(0.04 + Math.random() * 0.96));
  }
  sizeSpace();
  function drawSpace(dt, t) {
    var c = space.ctx, w = space.w, h = space.h, cx = w / 2, cy = h * 0.46, f = Math.max(w, h) * 0.42;
    space.warp = lerp(space.warp, space.warpTo, 0.06);
    space.intro = Math.max(0, space.intro - dt * 0.0011);
    space.flash = Math.max(0, space.flash - dt * 0.002);
    space.cam[0] = lerp(space.cam[0], (ptr.nx - 0.5) * 0.16, 0.04);
    space.cam[1] = lerp(space.cam[1], (ptr.ny - 0.45) * 0.1, 0.04);
    var band = space.listen, amp = 26 + voice.level * 150, bandY = h * 0.42;
    var speed = (reduce ? 0 : 0.00022 + Math.min(Math.abs(velocity) * 0.00006, 0.012) + space.warp * 0.022 +
      space.intro * space.intro * 0.04) * (1 - band * 0.85) * dt / 16.7;
    c.clearRect(0, 0, w, h);
    var ar = accent[0], ag = accent[1], ab = accent[2], streak = speed > 0.0016 && band < 0.05;
    for (var i = 0; i < space.stars.length; i++) {
      var s = space.stars[i], pz = s.z;
      s.z -= speed;
      if (s.z <= 0.03) { space.stars[i] = s = star(1); pz = 1; }
      var k = f / s.z, x = cx + (s.x - space.cam[0]) * k, y = cy + (s.y - space.cam[1]) * k;
      if (x < -60 || x > w + 60 || y < -60 || y > h + 60) { space.stars[i] = star(1); continue; }
      var near = 1 - s.z, a = clamp(near * 1.15 + 0.06, 0, 1) * (s.tint ? 1 : 0.9);
      if (band > 0.01) {  // the voice wave: two travelling sines, its height follows the level
        var wy = bandY + Math.sin(x * 0.0105 + t * 0.0034) * amp + Math.sin(x * 0.027 - t * 0.0052) * amp * 0.35 + s.b * (8 + amp * 0.18);
        y = lerp(y, wy, band * 0.92); a = lerp(a, 0.35 + near * 0.65, band);
      }
      var col = s.tint || band > 0.5 && i % 3 === 0 ? ar + "," + ag + "," + ab : "226,233,255";
      if (streak) {
        var k2 = f / Math.min(1, pz + speed * 5), x2 = cx + (s.x - space.cam[0]) * k2, y2 = cy + (s.y - space.cam[1]) * k2;
        c.strokeStyle = "rgba(" + col + "," + a + ")"; c.lineWidth = Math.max(0.6, near * 2.2 * s.s);
        c.beginPath(); c.moveTo(x2, y2); c.lineTo(x, y); c.stroke();
      } else {
        var r = near * near * 2.4 * s.s + 0.35 + band * 0.5;
        c.fillStyle = "rgba(" + col + "," + a + ")";
        if (r < 1.1) c.fillRect(x - r / 2, y - r / 2, r, r);
        else { c.beginPath(); c.arc(x, y, r * 0.7, 0, 6.2832); c.fill(); }
      }
    }
    if (space.flash > 0) { c.fillStyle = "rgba(" + ar + "," + ag + "," + ab + "," + (space.flash * 0.08) + ")"; c.fillRect(0, 0, w, h); }
  }
  var resizeT;
  addEventListener("resize", function () { clearTimeout(resizeT); resizeT = setTimeout(function () { sizeSpace(); sizeCanvases(); placeHeroSide(); ScrollTrigger.refresh(); if (reduce) drawSpace(16, 0); }, 180); });
  $$("[data-warp]").forEach(function (el) {
    el.addEventListener("pointerenter", function () { space.warpTo = 1; });
    el.addEventListener("pointerleave", function () { space.warpTo = 0; });
    el.addEventListener("focus", function () { space.warpTo = 1; });
    el.addEventListener("blur", function () { space.warpTo = 0; });
  });

  /* ---------- cursor ---------- */
  var cursor = $("#cursor"), cDot = $(".cursor-dot"), cRing = $(".cursor-ring"), cLabel = $(".cursor-label");
  var ring = { x: ptr.x, y: ptr.y };
  var useCursor = finePointer && !reduce;
  if (useCursor) {
    html.classList.add("has-cursor");
    document.addEventListener("pointerover", function (e) {
      var t = e.target.closest && e.target.closest("a, button, summary, [data-cursor], .spot, .cmd");
      var label = t && t.getAttribute("data-cursor");
      cursor.classList.toggle("is-hover", !!t && !label);
      cursor.classList.toggle("is-label", !!label);
      if (label) cLabel.textContent = listening ? "Mluv" : label;
    });
    addEventListener("pointerdown", function () { cursor.classList.add("is-down"); });
    addEventListener("pointerup", function () { cursor.classList.remove("is-down"); });
  }
  function drawCursor() {
    if (!useCursor) return;
    cursor.style.opacity = ptr.seen ? 1 : 0;
    ring.x = lerp(ring.x, ptr.x, 0.2); ring.y = lerp(ring.y, ptr.y, 0.2);
    cDot.style.transform = "translate3d(" + ptr.x + "px," + ptr.y + "px,0)";
    cRing.style.transform = "translate3d(" + ring.x + "px," + ring.y + "px,0)";
    if (listening) cursor.style.setProperty("--lv", voice.level.toFixed(3));
  }

  /* ---------- magnetic buttons ---------- */
  if (finePointer && !reduce) {
    $$("[data-magnetic]").forEach(function (el) {
      var lbl = el.querySelector(".lbl");
      el.addEventListener("pointermove", function (e) {
        var r = el.getBoundingClientRect(), dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
        el.style.setProperty("--bx", (e.clientX - r.left) + "px"); el.style.setProperty("--by", (e.clientY - r.top) + "px");
        gsap.to(el, { x: dx * 0.3, y: dy * 0.4, duration: 0.5, ease: "power3.out" });
        if (lbl) gsap.to(lbl, { x: dx * 0.12, y: dy * 0.16, duration: 0.5, ease: "power3.out" });
      });
      el.addEventListener("pointerleave", function () {
        gsap.to(el, { x: 0, y: 0, duration: 1.1, ease: "elastic.out(1, 0.35)" });
        if (lbl) gsap.to(lbl, { x: 0, y: 0, duration: 1.1, ease: "elastic.out(1, 0.35)" });
      });
    });
  }

  /* ---------- spotlight + tilt ---------- */
  $$(".spot").forEach(function (el) {
    var tilt = finePointer && !reduce;
    el.addEventListener("pointermove", function (e) {
      var r = el.getBoundingClientRect(), px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
      el.style.setProperty("--mx", px * 100 + "%"); el.style.setProperty("--my", py * 100 + "%");
      if (tilt) gsap.to(el, { rotateY: (px - 0.5) * 6, rotateX: (0.5 - py) * 6, transformPerspective: 900, duration: 0.6, ease: "power2.out" });
    });
    el.addEventListener("pointerleave", function () { if (tilt) gsap.to(el, { rotateY: 0, rotateX: 0, duration: 0.9, ease: "power3.out" }); });
  });

  /* ---------- kinetic type: Anybody's weight (and a little width) follows the cursor, a passing wave and the voice ---------- */
  var KIN = {
    hero: { base: [108, 640], near: [8, 190], radius: 0.16, wave: [5, 60], listen: [14, 230] },
    h2: { base: [100, 600], near: [0, 150], radius: 0.11, wave: [0, 0] },
    mark: { base: [132, 700], near: [0, 140], radius: 0.16, wave: [0, 70] }
  };
  var kinetics = [];
  $$("[data-kinetic]").forEach(function (el) {
    var cfg = KIN[el.dataset.kinetic], text = el.textContent.trim();
    el.textContent = "";
    var sr = document.createElement("span"); sr.className = "sr"; sr.textContent = text; el.appendChild(sr);
    var vis = document.createElement("span"); vis.setAttribute("aria-hidden", "true"); el.appendChild(vis);
    var chars = [], brk = el.dataset.break ? +el.dataset.break : -1;
    text.split(" ").forEach(function (word, wi, all) {
      var w = document.createElement("span"); w.className = "w";
      Array.from(word).forEach(function (ch) {
        var s = document.createElement("span"); s.className = "ch"; s.textContent = ch; w.appendChild(s);
        chars.push({ el: s, i: chars.length, cur: cfg.base.slice(), a: reduce ? 1 : 0, cx: 0, cy: 0, seed: Math.random() * 100 });
      });
      vis.appendChild(w);
      if (wi === brk - 1) vis.appendChild(document.createElement("br"));
      else if (wi < all.length - 1) vis.appendChild(document.createTextNode(" "));
    });
    el.classList.add("split");
    var k = { el: el, cfg: cfg, chars: chars, visible: false, shown: reduce, listen: 0 };
    chars.forEach(function (c) { apply(c); });
    kinetics.push(k);
  });
  function apply(c) {  // the axes are always real values; the reveal is only opacity, rise and blur
    c.el.style.fontVariationSettings = '"wdth" ' + clamp(c.cur[0], 50, 150).toFixed(1) + ', "wght" ' + clamp(c.cur[1], 100, 900).toFixed(0);
    var a = c.a;
    if (a < 1) {
      c.el.style.opacity = a.toFixed(3);
      c.el.style.transform = "translateY(" + ((1 - a) * 0.28).toFixed(3) + "em)";
      c.el.style.filter = "blur(" + ((1 - a) * 9).toFixed(2) + "px)";
    } else if (c.el.style.opacity !== "") { c.el.style.opacity = ""; c.el.style.transform = ""; c.el.style.filter = ""; }
  }
  var kinIO = new IntersectionObserver(function (es) {
    es.forEach(function (e) { kinetics.forEach(function (k) { if (k.el === e.target) k.visible = e.isIntersecting; }); });
  }, { rootMargin: "80px" });
  kinetics.forEach(function (k) { kinIO.observe(k.el); });
  function showKinetic(k, delay) {
    if (k.shown) return; k.shown = true;
    gsap.to(k.chars, { a: 1, duration: 1.1, ease: "power3.out", stagger: 0.035, delay: delay || 0, onUpdate: function () { if (!k.visible) k.chars.forEach(apply); } });
  }
  kinetics.forEach(function (k) {
    if (k.cfg === KIN.hero) return;
    ScrollTrigger.create({ trigger: k.el, start: "top 88%", once: true, onEnter: function () { showKinetic(k); } });
  });
  var voice = { level: 0, target: 0 };  // simulated speech level, 0..1
  function speak(on) {
    if (on) { if (Math.random() < 0.09) voice.target = Math.random() < 0.18 ? 0.08 : 0.35 + Math.random() * 0.65; }
    else voice.target = 0;
    voice.level = lerp(voice.level, voice.target, on ? 0.2 : 0.08);
    return voice.level;
  }
  function drawKinetics(t) {
    for (var n = 0; n < kinetics.length; n++) {
      var k = kinetics[n];
      if (!k.visible || reduce) continue;
      var cfg = k.cfg, chars = k.chars, R = innerWidth * cfg.radius;
      for (var i = 0; i < chars.length; i++) {           // read everything first: one layout per frame
        var r = chars[i].el.getBoundingClientRect(); chars[i].cx = r.left + r.width / 2; chars[i].cy = r.top + r.height / 2;
      }
      k.listen = lerp(k.listen, cfg.listen && listening ? 1 : 0, 0.12);
      for (i = 0; i < chars.length; i++) {
        var c = chars[i], tw = cfg.base[0], tg = cfg.base[1];
        var wave = Math.sin(t * 0.0016 - c.i * 0.55);
        tw += cfg.wave[0] * wave; tg += cfg.wave[1] * wave;
        if (ptr.seen && ptr.mouse) {
          var dx = ptr.x - c.cx, dy = (ptr.y - c.cy) * 1.6, infl = Math.exp(-(dx * dx + dy * dy) / (R * R));
          tw += cfg.near[0] * infl; tg += cfg.near[1] * infl;
        }
        if (k.listen > 0.01) {
          var jig = Math.sin(t * 0.021 + c.seed) * 0.5 + Math.sin(t * 0.0137 + c.seed * 2.3) * 0.5;
          tw += k.listen * voice.level * cfg.listen[0] * jig; tg += k.listen * voice.level * cfg.listen[1] * (0.4 + 0.6 * Math.abs(jig));
        }
        c.cur[0] = lerp(c.cur[0], tw, 0.16); c.cur[1] = lerp(c.cur[1], tg, 0.16);
        apply(c);
      }
    }
  }

  /* ---------- hero: the text block sits right of "pusť.", measured; hold the headline (or Space) and it listens ---------- */
  var hero = $("#heroTitle"), heroGrid = $("#heroGrid"), heroSide = $("#heroSide"), listening = false;
  function placeHeroSide() {
    if (innerWidth <= 1100) { heroSide.style.removeProperty("--side-left"); return; }
    var words = hero.querySelectorAll(".w"), last = words[words.length - 1];
    if (!last) return;
    var fs = parseFloat(getComputedStyle(hero).fontSize);
    var right = last.getBoundingClientRect().right - heroGrid.getBoundingClientRect().left;
    heroSide.style.setProperty("--side-left", Math.round(right + fs * 0.42) + "px");
  }
  function setListening(on) {
    if (listening === on) return;
    listening = on; html.classList.toggle("listening", on);
    cursor.classList.toggle("is-rec", on);
    cLabel.textContent = on ? "Mluv" : "Podrž";
  }
  hero.addEventListener("pointerdown", function (e) { e.preventDefault(); setListening(true); });
  addEventListener("pointerup", function () { setListening(false); });
  addEventListener("pointercancel", function () { setListening(false); });
  addEventListener("keydown", function (e) {
    if (e.code !== "Space" || e.repeat) return;
    var tag = (document.activeElement && document.activeElement.tagName) || "";
    if (/^(INPUT|TEXTAREA|BUTTON|A|SUMMARY|SELECT)$/.test(tag) || scrollPos() > innerHeight * 0.6) return;
    e.preventDefault(); setListening(true);
  });
  addEventListener("keyup", function (e) { if (e.code === "Space") setListening(false); });
  hero.addEventListener("contextmenu", function (e) { e.preventDefault(); });

  /* ---------- page load: arrive out of hyperspace, the headline assembles ---------- */
  var heroK = kinetics.filter(function (k) { return k.cfg === KIN.hero; })[0];
  if (heroK) { heroK.visible = true; showKinetic(heroK, reduce ? 0 : 0.3); }
  if (reduce) gsap.set(".rv", { opacity: 1, y: 0 });
  else {
    gsap.set(".rv", { opacity: 0, y: 30 });
    gsap.to(".hero .rv", { opacity: 1, y: 0, duration: 1.2, ease: "expo.out", stagger: 0.1, delay: 0.85 });
    ScrollTrigger.batch(".rv:not(.hero .rv)", {
      start: "top 90%", once: true,
      onEnter: function (els) { gsap.to(els, { opacity: 1, y: 0, duration: 1.1, ease: "expo.out", stagger: 0.08, overwrite: true }); }
    });
  }

  /* ---------- nav: background once scrolled, hides going down, comes back going up; the logo's moon orbits ---------- */
  var nav = $("#nav"), moonF = $("#moonFront"), moonB = $("#moonBack"), navY = -1, navDir = 0;
  function drawNav() {
    var y = scrollPos();
    if (Math.abs(y - navY) < 0.5) return;
    navDir = y > navY ? 1 : -1; navY = y;
    nav.classList.toggle("scrolled", y > 20);
    nav.classList.toggle("hidden", navDir > 0 && y > 500);
    var max = Math.max(1, document.documentElement.scrollHeight - innerHeight);
    var a = 0.7 + y / max * Math.PI * 4, x = 16 + 13 * Math.cos(a), yy = 16 + 4.6 * Math.sin(a), front = Math.sin(a) >= 0;
    moonF.setAttribute("cx", x.toFixed(2)); moonF.setAttribute("cy", yy.toFixed(2)); moonF.style.opacity = front ? 1 : 0;
    moonB.setAttribute("cx", x.toFixed(2)); moonB.setAttribute("cy", yy.toFixed(2)); moonB.setAttribute("opacity", front ? 0 : 0.8);
  }
  $$(".nav-links a").forEach(function (a) {
    var sec = $(a.getAttribute("href"));
    if (sec) ScrollTrigger.create({ trigger: sec, start: "top 50%", end: "bottom 50%", toggleClass: { targets: a, className: "active" } });
  });

  /* ---------- stage: tilts up into place as you scroll; the halo turns ---------- */
  var stage = $("#stage"), orrery = $("#orrery");
  if (!reduce) {
    if (!orrery) gsap.fromTo(stage, { rotateX: 24, scale: 0.86, y: 70, transformOrigin: "50% 100%" }, {
      rotateX: 0, scale: 1, y: 0, ease: "none",
      scrollTrigger: { trigger: "#stageWrap", start: "top 98%", end: "top 22%", scrub: 0.6 }
    });
    else gsap.fromTo(orrery, { scale: 1.08, opacity: 0.6 }, { scale: 0.94, opacity: 1, ease: "none",
      scrollTrigger: { trigger: "#stageWrap", start: "top bottom", end: "bottom top", scrub: 0.6 } });
    gsap.to("#haloRings", { rotation: -16, svgOrigin: "630 280", ease: "none", scrollTrigger: { trigger: "#stageWrap", start: "top bottom", end: "bottom top", scrub: 1 } });
  }

  /* orrery (until the video exists): satellites on tilted orbits, the plane leans towards the cursor */
  var plane = $("#plane"), trails = $("#trails"), haloSat = $("#haloSat");
  var ORBITS = [[265, 100], [455, 170], [650, 242]], TILT = -9 * Math.PI / 180;
  var sats = orrery ? $$(".sat", orrery).map(function (el) {
    var s = { el: el, orbit: ORBITS[+el.dataset.orbit], period: +el.dataset.period, ang: +el.dataset.phase, spd: 1, hover: false, trail: [] };
    el.addEventListener("pointerenter", function () { s.hover = true; });
    el.addEventListener("pointerleave", function () { s.hover = false; });
    el.addEventListener("focus", function () { s.hover = true; });
    el.addEventListener("blur", function () { s.hover = false; });
    return s;
  }) : [];
  var stageVisible = true;
  new IntersectionObserver(function (es) { stageVisible = es[0].isIntersecting; }).observe($("#stageWrap"));
  var tilt = { x: 0, y: 0 };
  function sizeCanvases() {
    [trails, $("#wave")].forEach(function (cv) {
      if (!cv) return;
      var r = cv.getBoundingClientRect(), d = Math.min(devicePixelRatio || 1, 2);
      cv.width = Math.max(1, Math.round(r.width * d)); cv.height = Math.max(1, Math.round(r.height * d));
      cv.getContext("2d").setTransform(d, 0, 0, d, 0, 0);
    });
  }
  sizeCanvases();
  var haloAng = 2.2;
  function drawOrrery(dt) {
    haloAng += reduce ? 0 : dt * 0.00005 * (1 + Math.min(Math.abs(velocity) * 0.05, 4));
    if (haloSat) { haloSat.setAttribute("cx", (630 + 620 * Math.cos(haloAng)).toFixed(1)); haloSat.setAttribute("cy", (280 + 122 * Math.sin(haloAng)).toFixed(1)); }
    if (!orrery || !stageVisible) return;
    var r = stage.getBoundingClientRect(), inside = ptr.seen && ptr.x > r.left && ptr.x < r.right && ptr.y > r.top && ptr.y < r.bottom;
    tilt.x = lerp(tilt.x, inside ? ((ptr.y - r.top) / r.height - 0.5) * -10 : 0, 0.06);
    tilt.y = lerp(tilt.y, inside ? ((ptr.x - r.left) / r.width - 0.5) * 12 : 0, 0.06);
    plane.style.transform = "perspective(1400px) rotateX(" + tilt.x.toFixed(2) + "deg) rotateY(" + tilt.y.toFixed(2) + "deg)";
    var W = r.width, H = r.height, ctx = trails.getContext("2d");
    ctx.clearRect(0, 0, W, H);
    var boost = 1 + Math.min(Math.abs(velocity) * 0.06, 5);
    sats.forEach(function (s) {
      s.spd = lerp(s.spd, s.hover ? 0 : 1, 0.08);
      if (!reduce) s.ang += dt / 1000 * 2 * Math.PI / s.period * s.spd * boost;
      var dx = s.orbit[0] * Math.cos(s.ang), dy = s.orbit[1] * Math.sin(s.ang);
      var x = 800 + dx * Math.cos(TILT) - dy * Math.sin(TILT), y = 450 + dx * Math.sin(TILT) + dy * Math.cos(TILT);
      var depth = (Math.sin(s.ang) + 1) / 2, px = x / 1600 * W, py = y / 900 * H;
      s.el.style.transform = "translate(-50%,-50%) translate(" + px.toFixed(1) + "px," + py.toFixed(1) + "px) scale(" + (0.78 + depth * 0.26).toFixed(3) + ")";
      s.el.style.zIndex = Math.sin(s.ang) >= 0 ? 6 : 2;
      s.el.style.opacity = (0.5 + depth * 0.5).toFixed(3);
      s.trail.push([px, py]); if (s.trail.length > 46) s.trail.shift();
      for (var i = 1; i < s.trail.length; i++) {
        var a = i / s.trail.length;
        ctx.strokeStyle = "rgba(" + accent[0] + "," + accent[1] + "," + accent[2] + "," + (a * 0.55 * (0.4 + depth * 0.6)).toFixed(3) + ")";
        ctx.lineWidth = a * 2.6; ctx.beginPath(); ctx.moveTo(s.trail[i - 1][0], s.trail[i - 1][1]); ctx.lineTo(s.trail[i][0], s.trail[i][1]); ctx.stroke();
      }
    });
  }

  /* hero video: muted loop, one button starts it over with sound; paused while off screen */
  var video = $("#heroVideo"), soundBtn = $("#soundBtn");
  if (video && soundBtn) {
    // A decode error (e.g. a GPU's VP9 decoder refusing the WebM) doesn't make Chrome try the next <source>: switch to MP4.
    var mp4 = video.querySelector('source[type="video/mp4"]'), fellBack = false;
    var toMp4 = function () {
      if (fellBack || !mp4 || /\.mp4(\?|$)/.test(video.currentSrc || "")) return;
      fellBack = true;
      var at = video.currentTime || 0, wasPlaying = !video.paused || video.autoplay;
      video.src = mp4.src; video.load();
      video.addEventListener("loadedmetadata", function () {
        if (at) video.currentTime = at;
        if (wasPlaying && !reduce) video.play().catch(function () {});
      }, { once: true });
    };
    video.addEventListener("error", toMp4);
    $$("source", video).forEach(function (s) { s.addEventListener("error", toMp4); });
    if (reduce) { video.removeAttribute("autoplay"); video.pause(); soundBtn.querySelector("span").textContent = "Přehrát video"; }
    var finished = false;
    soundBtn.addEventListener("click", function () {
      finished = false; video.currentTime = 0; video.muted = false; video.loop = false; video.controls = true; video.play(); soundBtn.hidden = true;
    });

    /* the download button drawn at the end of the video can't be clicked: a real one flies in from above, lands
       exactly on it and floats there while that scene is on (65.2–74.9 s); after a full play-through it stays */
    var cta = $("#stageCta"), ctaRing = $("#ctaRing"), ctaOn = false, CTA_IN = 64.15, CTA_OUT = 74.8, END_FRAME = 70;
    gsap.set(cta, { xPercent: -50, yPercent: -50 });
    var showCta = function () {
      ctaOn = true; cta.classList.add("on"); gsap.killTweensOf(cta);
      if (reduce) { gsap.to(cta, { opacity: 1, duration: 0.4 }); return; }
      gsap.fromTo(cta, { y: -stage.offsetHeight * 0.85, opacity: 0, rotation: -7, scale: 0.86 },
        { y: 0, opacity: 1, rotation: 0, scale: 1, duration: 0.8, ease: "back.out(1.45)", onComplete: function () {
          gsap.fromTo(ctaRing, { scale: 1, opacity: 0.9 }, { scale: 1.55, opacity: 0, duration: 0.9, ease: "power2.out" });
        } });
    };
    var hideCta = function (fast) {
      ctaOn = false; gsap.killTweensOf(cta);
      gsap.to(cta, { y: reduce ? 0 : -50, opacity: 0, duration: fast ? 0.15 : 0.5, ease: "power2.in", onComplete: function () { if (!ctaOn) cta.classList.remove("on"); } });
    };
    var syncCta = function () {
      var t = video.currentTime, want = finished || (t >= CTA_IN && t < CTA_OUT);
      if (want && !ctaOn) showCta(); else if (!want && ctaOn) hideCta(t < CTA_IN - 5);
    };
    video.addEventListener("timeupdate", syncCta);
    video.addEventListener("seeked", syncCta);
    video.addEventListener("ended", function () {  // with sound it doesn't loop: stop on the closing shot, keep the button
      finished = true; video.currentTime = END_FRAME; video.pause();
      soundBtn.querySelector("span").textContent = "Přehrát znovu"; soundBtn.hidden = false; syncCta();
    });
    new IntersectionObserver(function (es) {
      if (!es[0].isIntersecting) video.pause();
      else if (video.muted && !reduce) video.play().catch(function () {});
    }, { threshold: 0.15 }).observe(video);
  }

  /* ---------- spoken commands: the marquee, pushed by the scroll; hover (or tap) a command to see what it does ---------- */
  var track = $("#marqueeTrack"), mq = { x: 0, dir: 1, slow: 1, slowTo: 1, w: 0 }, cmdWord = $("#cmdWord"), cmdText = $("#cmdText");
  if (track) {
    track.innerHTML += track.innerHTML + track.innerHTML;
    mq.w = track.scrollWidth / 3;
    var marquee = $("#marquee"), cmds = $$(".cmd", track), autoIx = 0, autoT = null;
    var showCmd = function (el) {
      cmds.forEach(function (c) { c.classList.toggle("on", c.textContent === el.textContent); });
      cmdWord.textContent = el.textContent;
      gsap.fromTo(cmdText, { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.35, ease: "power2.out" });
      cmdText.textContent = el.dataset.say;
    };
    cmds.forEach(function (c) {
      c.addEventListener("pointerenter", function () { if (canHover) showCmd(c); });
      c.addEventListener("click", function () { showCmd(c); clearInterval(autoT); });
    });
    marquee.addEventListener("pointerenter", function () { if (canHover) mq.slowTo = 0.15; });
    marquee.addEventListener("pointerleave", function () { mq.slowTo = 1; });
    if (!canHover) {  // phones: the captions take turns by themselves while the section is in view
      ScrollTrigger.create({ trigger: "#povely", start: "top 80%", end: "bottom 20%",
        onToggle: function (self) {
          clearInterval(autoT);
          if (self.isActive) autoT = setInterval(function () { showCmd(cmds[autoIx++ % 4]); }, 3200);
        } });
    }
  }
  function drawMarquee(dt) {
    if (!track || reduce) return;
    if (Math.abs(velocity) > 0.2) mq.dir = velocity > 0 ? 1 : -1;
    mq.slow = lerp(mq.slow, mq.slowTo, 0.06);
    mq.x -= (0.05 + Math.min(Math.abs(velocity) * 0.09, 3)) * mq.dir * mq.slow * dt;
    if (mq.w) { if (mq.x <= -mq.w) mq.x += mq.w; if (mq.x > 0) mq.x -= mq.w; }
    track.style.transform = "translate3d(" + mq.x.toFixed(1) + "px,0,0)";
  }

  /* ---------- dictation: scroll through one dictation; afterwards (or on phones) hold the mic yourself ---------- */
  var mic = $("#demoMic"), status = $("#demoStatus"), typed = $("#typed"), ph = $("#ph");
  var clock = $("#clock"), clockLbl = $("#clockLbl"), bigClock = $("#bigClock"), chunk1 = $("#chunk1"), chunk2 = $("#chunk2");
  var tlItems = $$("#tl li"), tlFill = $("#tlFill"), wave = $("#wave"), level = $("#demoLevel");
  var SENTENCE = "Ahoj Petře, posílám ti nabídku na čtvrtek. Kdyby ti něco nesedělo, ozvi se.";
  var LINES = [
    "Schůzka se přesouvá na pátek v 10:30, místnost zůstává stejná.",
    "Uprav prosím tabulku tak, aby se DPH počítalo zvlášť, a pošli mi náhled.",
    SENTENCE
  ];
  var IDLE = "Podrž mikrofon a pak ho pusť.";
  var demo = { state: "idle", manual: false, pressedAt: 0, timers: [], line: 0, waveHist: [], waveAcc: 0 };
  function setClock(t, lbl) { clock.textContent = t; if (bigClock) bigClock.textContent = t; if (lbl) clockLbl.textContent = lbl; }
  function setMic(s) { demo.state = s; mic.dataset.state = s; }
  function setStatus(t, warn) { if (status.textContent !== t) status.textContent = t; status.classList.toggle("warn", !!warn); }
  function setText(t, flash) {
    ph.hidden = !!t;
    if (typed.dataset.t === t) return;
    typed.dataset.t = t; typed.textContent = "";
    if (t) { var s = document.createElement("span"); s.className = "ins" + (flash ? " flash" : ""); s.textContent = t; typed.appendChild(s); if (flash) requestAnimationFrame(function () { requestAnimationFrame(function () { s.classList.remove("flash"); }); }); }
  }
  function later(fn, ms) { demo.timers.push(setTimeout(fn, ms)); }
  var audio = null;
  function beep(freq) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      var o = audio.createOscillator(), gn = audio.createGain(), now = audio.currentTime;
      o.type = "sine"; o.frequency.value = freq; gn.gain.setValueAtTime(0, now);
      gn.gain.linearRampToValueAtTime(0.05, now + 0.01); gn.gain.exponentialRampToValueAtTime(0.0001, now + 0.12);
      o.connect(gn); gn.connect(audio.destination); o.start(now); o.stop(now + 0.14);
    } catch (e) { /* silence is fine */ }
  }
  function press() {
    if (demo.state !== "idle") return;
    demo.manual = true; demo.timers.forEach(clearTimeout); demo.timers = [];
    demo.pressedAt = performance.now();
    setMic("opening"); setStatus("Otevírám mikrofon…");
    later(function () { if (demo.state !== "opening") return; beep(880); setMic("recording"); setStatus("Poslouchám…"); }, 70);
  }
  function release() {
    if (demo.state !== "opening" && demo.state !== "recording") return;
    var held = performance.now() - demo.pressedAt;
    if (held < 300) {
      setMic("idle"); setStatus("Drž déle. Nahrávky kratší než 0,3 s Orbit nepřepisuje.", true);
      later(function () { demo.manual = false; if (demo.state === "idle") setStatus(IDLE); }, 3000); return;
    }
    later(function () {
      beep(660); setMic("busy"); setStatus("Přepisuji…");
      later(function () {
        var line = LINES[demo.line++ % LINES.length];
        setText(line, true); setMic("idle"); setStatus("Vloženo. Zkus další větu.");
        later(function () { demo.manual = false; if (demo.state === "idle") setStatus(IDLE); }, 3200);
      }, 900 + Math.random() * 500);
    }, 250);
  }
  mic.addEventListener("pointerdown", function (e) { e.preventDefault(); try { mic.setPointerCapture(e.pointerId); } catch (err) {} press(); });
  mic.addEventListener("pointerup", release);
  mic.addEventListener("pointercancel", release);
  mic.addEventListener("lostpointercapture", release);
  mic.addEventListener("contextmenu", function (e) { e.preventDefault(); });
  mic.addEventListener("keydown", function (e) { if (e.key === " " || e.key === "Enter") { e.preventDefault(); if (!e.repeat) press(); } });
  mic.addEventListener("keyup", function (e) { if (e.key === " " || e.key === "Enter") { e.preventDefault(); release(); } });
  mic.addEventListener("blur", release);

  var STEPS = [0, 0.14, 0.28, 0.62, 0.8], lastStep = -1;
  function dictScroll(p) {
    tlFill.style.setProperty("--p", p.toFixed(3));
    var step = 0;
    for (var i = 0; i < STEPS.length; i++) if (p >= STEPS[i]) step = i;
    tlItems.forEach(function (li, i) { li.classList.toggle("on", i <= step); });
    if (demo.manual) return;
    var local = step < 4 ? (p - STEPS[step]) / (STEPS[step + 1] - STEPS[step]) : (p - STEPS[4]) / (1 - STEPS[4]);
    if (step === 0) {
      setMic(local > 0.55 ? "opening" : "idle"); setText(""); setClock("0,0 s", "od stisku klávesy");
      chunk1.className = "chunk"; chunk2.className = "chunk"; setStatus(local > 0.55 ? "Otevírám mikrofon…" : "Stiskneš klávesu.");
    } else if (step === 1) {
      setMic("recording"); setText(""); setClock("0,1 s", "od stisku klávesy"); chunk1.className = "chunk"; chunk2.className = "chunk";
      setStatus("Pípnutí: mikrofon opravdu posílá zvuk.");
    } else if (step === 2) {
      setMic("recording"); setText(""); setClock(czNum(0.1 + local * 6.2, 1) + " s", "od stisku klávesy");
      chunk1.className = "chunk" + (local > 0.3 ? " on" : "") + (local > 0.62 ? " done" : "");
      chunk2.className = "chunk" + (local > 0.7 ? " on" : "");
      setStatus(local > 0.62 ? "Mluvíš dál. První věta je už přepsaná." : "Mluvíš. Hotové věty se přepisují už teď.");
    } else if (step === 3) {
      setMic(local < 0.4 ? "recording" : "busy"); setText("");
      setClock(local < 0.4 ? "+" + czNum(local / 0.4 * 0.25, 2) + " s" : "+" + czNum(0.25 + (local - 0.4) / 0.6 * 1.35, 1) + " s", "po puštění klávesy");
      chunk1.className = "chunk on done"; chunk2.className = "chunk on" + (local > 0.9 ? " done" : "");
      setStatus(local < 0.4 ? "Pustíš. Ještě čtvrt vteřiny nahrává." : "Přepisuje se poslední věta…");
    } else {
      setMic("idle"); setText(SENTENCE, lastStep !== 4); setClock("+1,6 s", "po puštění klávesy");
      chunk1.className = "chunk on done"; chunk2.className = "chunk on done";
      setStatus("Text je v okně. Teď zkus sám: podrž mikrofon.");
    }
    lastStep = step;
  }
  var pinned = !reduce && innerWidth >= 1000 && innerHeight >= 680;
  if (pinned) {
    $("#dictPin").classList.add("pinned");
    ScrollTrigger.create({ trigger: "#dictPin", start: "top top", end: "+=240%", pin: true, scrub: true, onUpdate: function (self) { dictScroll(self.progress); } });
    dictScroll(0);
  } else {
    tlItems.forEach(function (li) { li.classList.add("on"); }); tlFill.style.setProperty("--p", 1);
    setClock("+1,6 s", "po puštění klávesy"); setText(SENTENCE);
    chunk1.className = "chunk on done"; chunk2.className = "chunk on done";
  }
  function drawWave() {
    if (!wave) return;
    var on = demo.state === "recording", dt = 16.7;
    var lv = speak(on || listening);
    level.style.transform = "scale(" + (1.06 + lv * 0.45).toFixed(3) + ")";
    demo.waveAcc += dt;
    while (demo.waveAcc > 45) { demo.waveAcc -= 45; demo.waveHist.push(on ? lv : 0); if (demo.waveHist.length > 64) demo.waveHist.shift(); }
    var r = wave.getBoundingClientRect(); if (r.bottom < 0 || r.top > innerHeight) return;
    var ctx = wave.getContext("2d"), W = r.width, H = r.height, n = 64, bw = W / n;
    ctx.clearRect(0, 0, W, H);
    for (var i = 0; i < n; i++) {
      var v = demo.waveHist[demo.waveHist.length - n + i] || 0, hh = Math.max(2, v * H * 0.9);
      ctx.fillStyle = on ? "rgba(255,77,90," + (0.35 + v * 0.65) + ")" : "rgba(" + accent.join(",") + ",.35)";
      ctx.fillRect(i * bw + bw * 0.2, (H - hh) / 2, bw * 0.6, hh);
    }
  }

  /* ---------- privacy: the sentence lights up word by word; packets flow, none gets out ---------- */
  var scrub = $("#scrub");
  if (scrub) {
    var words = scrub.textContent.split(/ +/); scrub.textContent = "";
    var spans = words.map(function (w, i) { var s = document.createElement("span"); s.className = "sw"; s.textContent = w; scrub.appendChild(s); if (i < words.length - 1) scrub.appendChild(document.createTextNode(" ")); return s; });
    if (!reduce) ScrollTrigger.create({
      trigger: scrub, start: "top 82%", end: "bottom 38%", scrub: true,
      onUpdate: function (self) { var n = self.progress * spans.length * 1.05; spans.forEach(function (s, i) { s.style.opacity = clamp(n - i, 0.14, 1); }); }
    });
  }
  var flow = $("#flow"), packetsG = $("#packets"), flowVisible = false, packets = [], spawnT = 0, escapeT = 0;
  var fp = ["#fp1", "#fp2", "#fp3"].map(function (s) { var p = $(s); return { el: p, len: p.getTotalLength() }; });
  if (flow) new IntersectionObserver(function (es) { flowVisible = es[0].isIntersecting; }).observe(flow);
  function packet(kind) {
    var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("r", kind === "out" ? 5 : 4.5); c.setAttribute("fill", kind === "out" ? "#FF4D5A" : "var(--accent)");
    packetsG.appendChild(c);
    packets.push({ el: c, seg: kind === "out" ? 2 : 0, t: 0, kind: kind, back: false });
  }
  function drawFlow(dt) {
    if (!flow || !flowVisible || reduce || flow.getBoundingClientRect().width === 0) return;
    spawnT += dt; escapeT += dt;
    if (spawnT > 520) { spawnT = 0; packet("in"); }
    if (escapeT > 3800) { escapeT = 0; packet("out"); }
    for (var i = packets.length - 1; i >= 0; i--) {
      var p = packets[i], seg = fp[p.seg], v = p.kind === "out" ? 0.0011 : 0.0016;
      p.t += (p.back ? -v * 1.4 : v) * dt;
      if (p.kind === "in" && p.t >= 1) {
        if (p.seg === 0) { p.seg = 1; p.t = 0; gsap.fromTo("#gpuNode rect", { attr: { "stroke-opacity": 1 } }, { attr: { "stroke-opacity": 0.7 }, duration: 0.6 }); }
        else { p.el.remove(); packets.splice(i, 1); continue; }
      }
      if (p.kind === "out" && !p.back && p.t >= 1) { p.back = true; p.t = 1; gsap.fromTo("#barrierFlash", { attr: { opacity: 0.45, r: 14 } }, { attr: { opacity: 0, r: 40 }, duration: 0.7, ease: "power2.out" }); }
      if (p.kind === "out" && p.back && p.t <= 0.35) { p.el.remove(); packets.splice(i, 1); continue; }
      var pt = seg.el.getPointAtLength(clamp(p.t, 0, 1) * seg.len);
      p.el.setAttribute("cx", pt.x.toFixed(1)); p.el.setAttribute("cy", pt.y.toFixed(1));
      p.el.setAttribute("opacity", p.back ? clamp((p.t - 0.35) / 0.4, 0, 1) : 1);
    }
  }

  /* ---------- Claude Code panel: each feature plays its own little scene ---------- */
  var W = {
    panel: $("#wPanel"), agent: $("#wAgent"), note: $("#wNote"), noteText: $("#wNoteText"),
    bar1: $("#wBar1"), bar2: $("#wBar2"), pct1: $("#wPct1"), pct2: $("#wPct2"),
    s1: $("#s1"), s2: $("#s2"), s3: $("#s3"), status: $("#fStatus"), you: $("#fYou"), reply: $("#fReply"),
    target: $("#fTarget"), tName: $("#fTName"), tFolder: $("#fTFolder"), tStatus: $("#fTStatus"), msg: $("#fMsg"), url: $("#fUrl"),
    bubble: $("#bubble"), bIcon: $("#bIcon"), bTitle: $("#bTitle"), bNote: $("#bNote"), bText: $("#bText"), speaker: $("#wSpeaker"),
    slot: $(".w-slot")
  };
  var SC = { working: ["#5B9DFF", "pracuje"], waiting: ["#F5A524", "čeká na tebe"], done: ["#3DD68C", "hotovo"] };
  function session(row, state, flash) {
    var dot = row.querySelector(".dot"), st = row.querySelector(".st");
    dot.style.background = SC[state][0]; dot.style.color = SC[state][0]; dot.classList.toggle("pulse-dot", state === "working");
    st.textContent = SC[state][1]; st.style.color = state === "waiting" ? SC.waiting[0] : "";
    if (flash) { row.classList.add("flash"); setTimeout(function () { row.classList.remove("flash"); }, 900); }
  }
  function limits(p1, p2) {
    [[W.bar1, W.pct1, p1], [W.bar2, W.pct2, p2]].forEach(function (b) {
      b[0].style.width = b[2] + "%"; b[1].textContent = Math.round(b[2]) + " %";
      b[0].style.background = b[2] >= 90 ? "#E5484D" : b[2] >= 70 ? "#F5A524" : "";
    });
  }
  function feed(o) {
    o = o || {};
    W.status.textContent = o.status || ""; W.status.style.color = o.statusColor || "#9AA1AD";
    W.you.textContent = o.you || ""; W.reply.textContent = o.reply || "";
    W.target.hidden = !o.tName; W.tName.textContent = o.tName || ""; W.tFolder.textContent = o.tFolder || "";
    W.tStatus.textContent = o.tStatus || ""; W.tStatus.style.color = o.tColor || "#9AA1AD";
    W.msg.hidden = !o.msg; W.msg.textContent = o.msg || ""; W.url.hidden = !o.url; W.url.textContent = o.url || "";
    W.agent.className = "w-agent" + (o.chip ? " " + o.chip : "");
  }
  function bubble(o) {
    if (!o) { W.bubble.classList.remove("on"); W.speaker.classList.remove("reading"); W.slot.classList.remove("busy"); return; }
    W.bIcon.textContent = o.icon; W.bIcon.style.background = o.color; W.bTitle.textContent = o.title;
    W.bNote.textContent = o.note; W.bNote.style.color = o.color; W.bText.textContent = o.text;
    W.bubble.classList.add("on"); W.slot.classList.add("busy"); W.speaker.classList.toggle("reading", !!o.read);
  }
  var IDLE_FEED = { you: "Ty: Co dělá relace s ceníkem?", reply: "Doplňuje ceny do tabulky, zbývají jí dvě kategorie." };
  function baseline(keepFeed) {
    limits(42, 18); W.noteText.textContent = "2 h 14 min"; W.note.classList.remove("warn");
    session(W.s1, "working"); session(W.s2, "waiting"); session(W.s3, "working");
    feed(keepFeed ? IDLE_FEED : null); bubble(null);
  }
  function typeInto(tl, el, text, at, dur) {
    var o = { n: 0 };
    tl.to(o, { n: text.length, duration: dur || text.length * 0.028, ease: "none", onUpdate: function () { el.textContent = text.slice(0, Math.round(o.n)); } }, at);
  }
  var ZONES = { limity: ["limits"], relace: ["sessions"], bubliny: ["sessions"], artefakty: [], agent: ["agent", "sessions"], chrome: ["agent"] };
  var SCENES = {
    limity: function (tl) {
      tl.call(function () { limits(0, 0); });
      tl.to({}, { duration: 0.2 });
      tl.call(function () { limits(42, 18); });
      tl.call(function () { W.noteText.textContent = "2 h 13 min"; }, null, 1.6);
      tl.call(function () { limits(71, 19); W.note.classList.add("warn"); W.noteText.textContent = "dojde v 14:20"; }, null, 2.8);
      tl.to({}, { duration: 3.2 });
    },
    relace: function (tl) {
      tl.call(function () { session(W.s3, "done", true); }, null, 1.2);
      tl.call(function () { W.s2.classList.add("flash"); }, null, 2.6);
      tl.call(function () { W.s2.classList.remove("flash"); session(W.s2, "working", false); }, null, 3.6);
      tl.call(function () { session(W.s1, "done", true); }, null, 4.8);
      tl.to({}, { duration: 2 });
    },
    bubliny: function (tl) {
      tl.call(function () { session(W.s3, "done", true); }, null, 0.9);
      tl.call(function () { bubble({ icon: "✓", color: "#3DD68C", title: "Překlad katalogu", note: "hotovo", text: "Katalog je přeložený, má 48 stran. Zkontroluj prosím názvy kolekcí, dvě jsem nechal v angličtině.", read: true }); }, null, 1.3);
      tl.call(function () { W.speaker.classList.remove("reading"); }, null, 5.4);
      tl.call(function () { bubble(null); }, null, 6.4);
      tl.to({}, { duration: 1 });
    },
    artefakty: function (tl) {
      tl.call(function () { bubble({ icon: "i", color: "#5B9DFF", title: "Artefakt z relace eshop", note: "předčítám", text: "Ceník na rok 2027 má 214 položek. Nejvíc zdražují povlečení, v průměru o 4,8 procenta.", read: true }); }, null, 0.8);
      tl.call(function () { W.speaker.classList.remove("reading"); W.bNote.textContent = "přečteno"; }, null, 5.6);
      tl.call(function () { bubble(null); }, null, 6.6);
      tl.to({}, { duration: 1 });
    },
    agent: function (tl) {
      tl.call(function () { feed({ status: "Poslouchám…", statusColor: "#FF4D5A", chip: "listen" }); }, null, 0.3);
      typeInto(tl, W.you, "Ty: Napiš do relace s přihlášením, ať přidá test na zapomenuté heslo.", 0.5, 1.8);
      tl.call(function () { W.agent.className = "w-agent"; W.status.textContent = "Přemýšlím…"; W.status.style.color = "#9AA1AD"; }, null, 2.5);
      typeInto(tl, W.reply, "Pošlu to do relace Oprava přihlášení ve složce portal. Mám to poslat?", 3.4, 1.4);
      tl.call(function () {
        W.status.textContent = "Mám? Řekni „jo“"; W.status.style.color = "#F5A524"; W.agent.className = "w-agent confirm";
        W.target.hidden = false; W.tName.textContent = "→ Oprava přihlášení"; W.tFolder.textContent = "portal";
        W.tStatus.textContent = "čeká na tvoje „jo“"; W.tStatus.style.color = "#F5A524";
        W.msg.hidden = false; W.msg.textContent = "Přidej test na obnovu zapomenutého hesla.";
      }, null, 5);
      tl.call(function () { W.you.textContent = "Ty: Jo."; W.agent.className = "w-agent listen"; W.status.textContent = "Poslouchám…"; W.status.style.color = "#FF4D5A"; }, null, 7);
      tl.call(function () { W.agent.className = "w-agent"; W.status.textContent = ""; W.tStatus.textContent = "odesláno ✓"; W.tStatus.style.color = "#3DD68C"; session(W.s2, "working", true); }, null, 7.9);
      tl.to({}, { duration: 2.4 });
    },
    chrome: function (tl) {
      tl.call(function () { feed({ status: "Poslouchám…", statusColor: "#FF4D5A", chip: "listen" }); }, null, 0.3);
      typeInto(tl, W.you, "Ty: Otevři mi v Chromu objednávku 82.", 0.5, 1.1);
      tl.call(function () { W.agent.className = "w-agent"; W.status.textContent = "Přemýšlím…"; W.status.style.color = "#9AA1AD"; }, null, 1.8);
      typeInto(tl, W.reply, "Otevírám objednávku 82, našel jsem ji v historii Chromu.", 2.6, 1.1);
      tl.call(function () {
        W.status.textContent = ""; W.target.hidden = false; W.tName.textContent = "→ Objednávka #82"; W.tFolder.textContent = "Chrome";
        W.tStatus.textContent = "otevírám…"; W.tStatus.style.color = "#9AA1AD"; W.url.hidden = false; W.url.textContent = "obchod.cz/admin/objednavka?id=82";
      }, null, 3.9);
      tl.call(function () { W.tStatus.textContent = "otevřeno ✓"; W.tStatus.style.color = "#3DD68C"; }, null, 4.9);
      tl.to({}, { duration: 2.6 });
    }
  };
  var feats = $$(".feat"), featWrap = $("#features"), sceneTl = null, activeScene = null, hoverScene = null, scrollScene = "limity";
  function playScene(name) {
    if (name === activeScene) return;
    activeScene = name;
    feats.forEach(function (f) { f.classList.toggle("on", f.dataset.scene === name); });
    featWrap.classList.toggle("has-active", !!name);
    $$(".w-zone", W.panel).forEach(function (z) { z.classList.toggle("lit", (ZONES[name] || []).indexOf(z.dataset.zone) >= 0); });
    W.panel.classList.toggle("focus", !!(ZONES[name] || []).length);
    if (sceneTl) sceneTl.kill();
    var agentScene = name === "agent" || name === "chrome";
    baseline(!agentScene);
    if (reduce) return;
    sceneTl = gsap.timeline({ repeat: -1, repeatDelay: 0.6, onRepeat: function () { baseline(!agentScene); } });
    SCENES[name](sceneTl);
  }
  baseline(true);
  var narrow = innerWidth < 1000;
  feats.forEach(function (f) {
    f.addEventListener("pointerenter", function () { if (!canHover) return; hoverScene = f.dataset.scene; playScene(hoverScene); });
    f.addEventListener("pointerleave", function () { hoverScene = null; });
    f.addEventListener("focus", function () { playScene(f.dataset.scene); });
    f.addEventListener("click", function () { playScene(f.dataset.scene); });
    ScrollTrigger.create({ trigger: f, start: narrow ? "top 82%" : "top 58%", end: narrow ? "bottom 82%" : "bottom 58%",
      onToggle: function (self) { if (self.isActive) { scrollScene = f.dataset.scene; if (!hoverScene) playScene(scrollScene); } } });
  });
  ScrollTrigger.create({ trigger: "#claude", start: "top 70%", end: "bottom top", onEnter: function () { playScene(scrollScene); }, onLeave: function () { if (sceneTl) sceneTl.pause(); }, onEnterBack: function () { if (sceneTl) sceneTl.resume(); } });

  /* ---------- accuracy: numbers count up, bars grow ---------- */
  $$("#acc .val").forEach(function (el) {
    var to = parseFloat(el.dataset.count), unit = el.dataset.unit, o = { v: 0 };
    var bar = el.closest(".bar-row").querySelector(".track i");
    if (reduce) return;
    gsap.set(bar, { "--s": 0 });
    ScrollTrigger.create({
      trigger: el, start: "top 88%", once: true, onEnter: function () {
        gsap.to(o, { v: to, duration: 1.6, ease: "expo.out", onUpdate: function () { el.textContent = czNum(o.v, 1) + unit.replace(" ", " "); } });
        gsap.to(bar, { "--s": 1, duration: 1.6, ease: "expo.out" });
      }
    });
  });

  /* ---------- install: a satellite travels the ruler as you scroll, each step lights up as it passes ---------- */
  var instPath = $("#instPath"), instSat = $("#instSat"), steps = $$("#steps li");
  if (instPath) {
    var L = instPath.getTotalLength();
    instPath.style.strokeDasharray = L; instPath.style.strokeDashoffset = reduce ? 0 : L;
    var setRuler = function (p) {
      instPath.style.strokeDashoffset = (L * (1 - p)).toFixed(1);
      if (instSat) instSat.style.left = (p * 100).toFixed(2) + "%";
      steps.forEach(function (s, i) { s.classList.toggle("on", p >= (s.offsetLeft / s.parentElement.offsetWidth) - 0.005); });
    };
    if (reduce) setRuler(1);
    else ScrollTrigger.create({ trigger: "#install", start: "top 80%", end: "bottom 45%", scrub: 0.5, onUpdate: function (self) { setRuler(self.progress); } });
  }

  /* ---------- FAQ: answers slide open ---------- */
  $$("#faq details").forEach(function (d) {
    var sum = d.querySelector("summary"), ans = d.querySelector(".ans");
    sum.addEventListener("click", function (e) {
      if (reduce) return;
      e.preventDefault();
      if (d.open) gsap.to(ans, { height: 0, opacity: 0, duration: 0.45, ease: "power3.inOut", onComplete: function () { d.open = false; gsap.set(ans, { clearProps: "all" }); ScrollTrigger.refresh(); } });
      else { d.open = true; gsap.fromTo(ans, { height: 0, opacity: 0 }, { height: "auto", opacity: 1, duration: 0.6, ease: "expo.out", onComplete: function () { ScrollTrigger.refresh(); } }); }
    });
  });

  /* ---------- the one loop ---------- */
  var last = performance.now();
  function frame() {
    var now = performance.now(), dt = Math.min(now - last, 50); last = now;
    if (!lenis) { velocity = (scrollY - lastY) / Math.max(dt, 1) * 16; lastY = scrollY; }
    if (document.hidden) return;
    space.listen = lerp(space.listen, listening ? 1 : 0, listening ? 0.07 : 0.05);
    drawWave();
    drawSpace(dt, now);
    drawNav();
    drawCursor();
    drawKinetics(now);
    drawOrrery(dt);
    drawMarquee(dt);
    drawFlow(dt);
  }
  ScrollTrigger.sort();  // triggers made before the pinned dictation would otherwise ignore its extra scroll length
  ScrollTrigger.refresh();
  placeHeroSide();
  if (reduce) { drawSpace(16, 0); drawNav(); addEventListener("scroll", drawNav, { passive: true }); kinetics.forEach(function (k) { k.chars.forEach(apply); }); drawOrrery(0); }
  else gsap.ticker.add(frame);
  addEventListener("load", function () { ScrollTrigger.refresh(); sizeCanvases(); placeHeroSide(); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { placeHeroSide(); ScrollTrigger.refresh(); if (track) mq.w = track.scrollWidth / 3; });
})();
