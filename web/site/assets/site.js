/* Orbit – orbit.easya.cz. Everything that moves on the page.
   One frame loop (gsap.ticker) drives the star field, the kinetic type, the orrery and the waves. */
(function () {
  "use strict";
  var html = document.documentElement;
  var gsap = window.gsap, ScrollTrigger = window.ScrollTrigger;
  if (!gsap || !ScrollTrigger) { html.classList.remove("js"); return; }  // the page still reads fine without motion
  gsap.registerPlugin(ScrollTrigger);
  html.classList.add("ready");  // the head script's failsafe stands down

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
  // Firefox never fires pointerleave on document: html too, and a window that loses focus
  var unseen = function () { ptr.seen = false; };
  document.addEventListener("pointerleave", unseen); html.addEventListener("pointerleave", unseen); addEventListener("blur", unseen);

  /* ---------- theme: the same three colours as in the app ---------- */
  var THEMES = { blue: [91, 157, 255], violet: [167, 139, 250], teal: [45, 212, 191] };
  var THEME_BG = { blue: "#04060C", violet: "#06040C", teal: "#020908" }, THEME_ORDER = ["blue", "violet", "teal"];
  var accent = THEMES[html.dataset.theme] || THEMES.blue;
  var themeButtons = $$(".themes button"), pillDots = $$(".w-pill i"), themeMeta = $('meta[name="theme-color"]');
  function markTheme() {
    var name = html.dataset.theme;
    themeButtons.forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.theme === name)); });
    pillDots.forEach(function (d, i) { d.classList.toggle("on", THEME_ORDER[i] === name); });  // the app's own colour pill in the panel
    if (themeMeta && THEME_BG[name]) themeMeta.content = THEME_BG[name];
  }
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
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add(function (time) { lenis.raf(time * 1000); });
    gsap.ticker.lagSmoothing(0);
  }
  $$('a[href^="#"]').forEach(function (a) {
    a.addEventListener("click", function (e) {
      var id = a.getAttribute("href");
      var target = id === "#top" ? document.body : $(id);
      if (!target) return;
      e.preventDefault();
      // ease in and out, longer for longer trips; then focus moves there and the URL gets the hash
      if (lenis) {
        var to = id === "#top" ? 0 : target.getBoundingClientRect().top + scrollY - 40;
        var dur = clamp(0.9 + Math.abs(to - scrollPos()) / 5000, 1, 2.2);
        navHold = performance.now() + dur * 1000 + 200;
        lenis.scrollTo(to, { duration: dur, easing: function (t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; } });
      } else {
        navHold = performance.now() + (reduce ? 300 : 1500);
        target.scrollIntoView({ behavior: reduce ? "auto" : "smooth" });
      }
      if (id !== "#top") {
        if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
        target.focus({ preventScroll: true });
      }
      try { history.replaceState(null, "", id === "#top" ? location.pathname + location.search : id); } catch (err) {}
    });
  });
  function scrollPos() { return lenis ? lenis.scroll : scrollY; }
  var navHold = 0;  // until this time the nav stays shown, though an anchor trip goes down
  // keys, the scrollbar and middle-click autoscroll scroll natively: stop a wheel glide first, or Lenis drags the page back.
  // Any scroll input of the reader's own also ends the nav hold.
  addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.altKey || e.metaKey || !/^(PageDown|PageUp|ArrowDown|ArrowUp|Home|End| )$/.test(e.key)) return;
    var el = document.activeElement, tag = (el && el.tagName) || "";
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag) || el && el.isContentEditable || e.key === " " && /^(BUTTON|SUMMARY)$/.test(tag)) return;
    navHold = 0;
    if (lenis && lenis.isScrolling === "smooth") lenis.reset();
  }, true);
  if (lenis) addEventListener("pointerdown", function (e) {
    if (lenis.isScrolling === "smooth" && (e.button === 1 || e.clientX >= html.clientWidth)) lenis.reset();
  }, true);
  addEventListener("wheel", function () { navHold = 0; }, { passive: true });
  document.addEventListener("touchstart", function () { navHold = 0; }, { passive: true });  // a touch listener also lets iOS Safari show :active

  /* ---------- star field: stars fly towards you, faster when you scroll, warp over the main button ---------- */
  var space = { cv: $("#space"), stars: [], w: 0, h: 0, fh: 0, area: 0, dpr: 1, cam: [0, 0], warp: 0, warpTo: 0, intro: reduce ? 0 : 1, flash: 0,
    trail: reduce ? 0 : 0.24, hoverT: 0, q: [], qn: new Int32Array(100), cols: [], tintOf: null, lws: [0.7, 1.3, 2.2, 4] };
  space.ctx = space.cv.getContext("2d");
  for (var qi = 0; qi < 100; qi++) space.q.push([]);
  for (qi = 1; qi <= 10; qi++) space.cols[qi - 1] = "rgba(226,233,255," + qi / 10 + ")";
  function star(s, z, born) {  // fills a star in place, so a respawn allocates nothing; born 0 fades it in
    s.x = (Math.random() * 2 - 1) * 1.8; s.y = (Math.random() * 2 - 1) * 1.15; s.z = z;
    s.tint = Math.random() < 0.16; s.s = 0.55 + Math.random() * 1.1; s.b = Math.random() * 2 - 1; s.born = born;
    return s;
  }
  function perFrame(k, dt) { return 1 - Math.pow(1 - k, dt / 16.7); }  // a lerp factor given per 60 Hz frame, for any frame length
  function sizeSpace() {
    // the address bar of a phone only changes the height: keep the stars, the projection and the canvas size,
    // which is never less than CSS 100lvh (the height with the bar hidden)
    var cv = space.cv; cv.style.height = "";
    space.fh = Math.max(innerHeight, cv.offsetHeight, innerWidth === space.w ? space.fh : 0);
    space.w = innerWidth; space.h = space.fh; space.dpr = Math.min(devicePixelRatio || 1, 1.5);
    cv.style.height = space.h + "px";
    var bw = Math.round(space.w * space.dpr), bh = Math.round(space.h * space.dpr);
    if (cv.width !== bw || cv.height !== bh) { cv.width = bw; cv.height = bh; }
    space.ctx.setTransform(space.dpr, 0, 0, space.dpr, 0, 0);
    var area = space.w * space.h, n = Math.round(clamp(area / 1500, 320, 1100)), st = space.stars;
    if (Math.abs(area - space.area) > space.area * 0.4) { st.length = 0; space.area = area; }  // a very different window: a new field
    while (st.length > n) st.pop();
    while (st.length < n) st.push(star({}, 0.04 + Math.random() * 0.96, 1));
  }
  sizeSpace();
  function drawSpace(dt, t) {  // dt: the real frame time (up to 250 ms), so the stars travel exactly with the page
    var c = space.ctx, w = space.w, h = space.h, cx = w / 2, cy = h * 0.46, f = Math.max(w, h) * 0.42, st = space.stars, cam = space.cam;
    var dc = Math.min(dt, 50);  // the rest of the motion skips what doesn't fit in 50 ms, no jumps after a long frame
    space.warp = lerp(space.warp, space.warpTo, perFrame(0.06, dt));
    space.intro = Math.max(0, space.intro - dc * 0.0011);
    space.flash = Math.max(0, space.flash - dt * 0.002);
    var look = ptr.mouse && ptr.seen, ce = perFrame(0.04, dt);  // only a mouse moves the camera, a finger never does
    cam[0] = lerp(cam[0], look ? (ptr.nx - 0.5) * 0.16 : 0, ce);
    cam[1] = lerp(cam[1], look ? (ptr.ny - 0.45) * 0.1 : 0, ce);
    // z step per 60 Hz frame (velocity already is per 60 Hz frame): the frame length counts once, when the stars move
    var sv = reduce ? 0 : Math.min(Math.abs(velocity) * 0.00006, 0.012);
    var spd = reduce ? 0 : 0.00022 + space.warp * 0.022 + space.intro * space.intro * 0.04 + sv;
    var step = ((spd - sv) * dc + sv * dt) / 16.7, grow = dt / 400;
    // the trail (its length in z, not dependent on dt) grows with the speed and eases; it changes at most 1.4x per 60 Hz
    // frame, also in a long frame, so dots stretch into lines gradually and the field never switches at once
    var tz = lerp(space.trail, spd * 6 * clamp((spd - 0.0012) / 0.002, 0, 1), perFrame(0.2, dt));
    var lim = Math.pow(1.4, Math.min(dt, 25) / 16.7);
    tz = clamp(tz, space.trail / lim, Math.max(space.trail, 0.0003) * lim);
    space.trail = tz = tz < 0.0003 ? 0 : tz;
    var Q = space.q, N = space.qn, j, q, m, al;
    if (space.tintOf !== accent) { space.tintOf = accent; for (j = 1; j <= 10; j++) space.cols[9 + j] = "rgba(" + accent.join(",") + "," + j / 10 + ")"; }
    for (j = 0; j < 100; j++) N[j] = 0;
    for (var i = 0; i < st.length; i++) {
      var s = st[i];
      s.z -= step;
      if (s.z <= 0.03) star(s, 1, 0);
      if (s.born < 1) s.born = Math.min(1, s.born + grow);
      // the camera shift is projected no closer than z 0.35, near stars don't shoot sideways when the mouse moves
      var k = f / s.z, kc = f / Math.max(s.z, 0.35), x = cx + s.x * k - cam[0] * kc, y = cy + s.y * k - cam[1] * kc;
      var near = 1 - s.z, a = clamp(near * 1.15 + 0.06, 0, 1) * (s.tint ? 1 : 0.9);
      if (x < -60 || x > w + 60 || y < -60 || y > h + 60) { star(s, 1, 0); continue; }
      a *= s.born * clamp((s.z - 0.03) / 0.06, 0, 1);  // fade in after a respawn, fade out just before passing you
      var col = s.tint ? 10 : 0, r = near * near * 2.4 * s.s + 0.35, L = 0, x2 = x, y2 = y;
      if (tz > 0) {
        var z2 = Math.min(1, s.z + tz), k2 = f / z2, kc2 = f / Math.max(z2, 0.35);
        x2 = cx + s.x * k2 - cam[0] * kc2; y2 = cy + s.y * k2 - cam[1] * kc2;
        L = Math.sqrt((x - x2) * (x - x2) + (y - y2) * (y - y2));
      }
      if (L < 1.5) {
        al = Math.round(a * 10); if (!al) continue;
        j = col + al - 1; q = Q[j]; m = N[j]; q[m] = x; q[m + 1] = y; q[m + 2] = r; N[j] = m + 3;
      } else {  // the dot stretches into a line: as wide as the dot at first, thinner as it gets longer
        al = Math.round(a * clamp(90 / L, 0.5, 1) * 10); if (!al) continue;
        var lw = lerp(r < 1.1 ? r : r * 1.4, Math.max(0.6, Math.min(2.4, near * 2.2 * s.s)), clamp((L - 1.5) / 8, 0, 1));
        j = 20 + (col + al - 1) * 4 + (lw < 1 ? 0 : lw < 1.7 ? 1 : lw < 3 ? 2 : 3); q = Q[j]; m = N[j];
        q[m] = x2; q[m + 1] = y2; q[m + 2] = x; q[m + 3] = y; N[j] = m + 4;
      }
    }
    // one path and one fill or stroke per colour, alpha step (and line width)
    c.clearRect(0, 0, w, h); c.lineCap = "round";
    for (j = 0; j < 100; j++) {
      var n = N[j]; if (!n) continue;
      q = Q[j]; c.beginPath();
      if (j < 20) {
        for (m = 0; m < n; m += 3) {
          var rr = q[m + 2];
          if (rr < 1.1) c.rect(q[m] - rr / 2, q[m + 1] - rr / 2, rr, rr);
          else { c.moveTo(q[m] + rr * 0.7, q[m + 1]); c.arc(q[m], q[m + 1], rr * 0.7, 0, 6.2832); }
        }
        c.fillStyle = space.cols[j]; c.fill();
      } else {
        for (m = 0; m < n; m += 4) { c.moveTo(q[m], q[m + 1]); c.lineTo(q[m + 2], q[m + 3]); }
        c.strokeStyle = space.cols[(j - 20) >> 2]; c.lineWidth = space.lws[(j - 20) & 3]; c.stroke();
      }
    }
    if (space.flash > 0) { c.fillStyle = "rgba(" + accent.join(",") + "," + (space.flash * 0.08) + ")"; c.fillRect(0, 0, w, h); }
  }
  var resizeT, resizeW = innerWidth;
  addEventListener("resize", function () {
    clearTimeout(resizeT);
    resizeT = setTimeout(function () {
      var wide = innerWidth !== resizeW; resizeW = innerWidth;
      sizeSpace();
      // a new width re-measures; only the height is a phone's address bar, the layout stays. ScrollTrigger refreshes
      // by itself 200 ms after a resize (after this, and not for an address bar): a refresh here would run it twice
      if (wide) { sizeCanvases(); placeHeroSide(); }
      if (reduce) drawSpace(16, 0);
    }, 180);
  });
  // warp on a real hover (a mouse that moves onto the button and stays a moment) or keyboard focus; not when the page
  // scrolls a button under a resting cursor, not on a tap, not when the window gets its focus back. Safari sends
  // pointermove while the page scrolls under a resting mouse: ptr still holds the last position here (the window
  // listener runs after this one), so a move to the same point is not a move
  $$("[data-warp]").forEach(function (el) {
    el.addEventListener("pointermove", function (e) {
      if (e.pointerType !== "mouse" || space.hoverT || space.warpTo || e.clientX === ptr.x && e.clientY === ptr.y) return;
      space.hoverT = setTimeout(function () { space.hoverT = 0; space.warpTo = 1; }, 140);
    });
    el.addEventListener("pointerleave", function () { clearTimeout(space.hoverT); space.hoverT = 0; space.warpTo = 0; });
    el.addEventListener("focus", function () { try { if (el.matches(":focus-visible")) space.warpTo = 1; } catch (e) {} });
    el.addEventListener("blur", function () { space.warpTo = 0; });
  });
  addEventListener("blur", function () { clearTimeout(space.hoverT); space.hoverT = 0; space.warpTo = 0; });

  /* ---------- cursor ---------- */
  var cursor = $("#cursor"), cDot = $(".cursor-dot"), cRing = $(".cursor-ring"), cLabel = $(".cursor-label");
  var ring = { x: ptr.x, y: ptr.y }, cLast = { x: NaN, y: NaN, seen: null };
  // not in forced colours or high contrast: the dot would vanish there
  var useCursor = finePointer && !reduce && !window.matchMedia("(forced-colors: active), (prefers-contrast: more)").matches;
  if (useCursor) {
    addEventListener("pointermove", function first(e) {  // the native cursor goes only once a mouse is really here
      if (e.pointerType !== "mouse") return;
      html.classList.add("has-cursor"); removeEventListener("pointermove", first);
    }, { passive: true });
    document.addEventListener("pointerover", function (e) {
      var t = e.target.closest && e.target.closest("a, button, summary, [data-cursor], .spot, .cmd");
      var label = t && t.getAttribute("data-cursor");
      cursor.classList.toggle("is-hover", !!t && !label);
      cursor.classList.toggle("is-label", !!label);
      cursor.dataset.label = label || "";
      if (label) cLabel.textContent = label;
    });
    var up = function () { cursor.classList.remove("is-down"); };  // a link drag ends without pointerup
    addEventListener("pointerdown", function () { cursor.classList.add("is-down"); });
    addEventListener("pointerup", up); addEventListener("pointercancel", up); addEventListener("dragend", up); addEventListener("blur", up);
  }
  function drawCursor() {
    if (!useCursor) return;
    if (ptr.seen !== cLast.seen) {
      cLast.seen = ptr.seen; cursor.style.opacity = ptr.seen ? 1 : 0;
      if (ptr.seen) { ring.x = ptr.x; ring.y = ptr.y; }  // back in the window: the ring starts at the pointer, it doesn't fly over
    }
    if (ptr.x === cLast.x && ptr.y === cLast.y && Math.abs(ring.x - ptr.x) < 0.05 && Math.abs(ring.y - ptr.y) < 0.05) return;
    cLast.x = ptr.x; cLast.y = ptr.y;
    ring.x = lerp(ring.x, ptr.x, 0.2); ring.y = lerp(ring.y, ptr.y, 0.2);
    cDot.style.transform = "translate3d(" + ptr.x + "px," + ptr.y + "px,0)";
    cRing.style.transform = "translate3d(" + ring.x + "px," + ring.y + "px,0)";
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

  /* ---------- kinetic type: Anybody's weight (and a little width) follows the cursor and a passing wave ---------- */
  var KIN = {
    hero: { base: [108, 640], near: [8, 190], radius: 0.16, wave: [5, 60] },
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
    var k = { el: el, cfg: cfg, chars: chars, visible: false, shown: reduce };
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
      for (i = 0; i < chars.length; i++) {
        var c = chars[i], tw = cfg.base[0], tg = cfg.base[1];
        var wave = Math.sin(t * 0.0016 - c.i * 0.55);
        tw += cfg.wave[0] * wave; tg += cfg.wave[1] * wave;
        if (ptr.seen && ptr.mouse) {
          var dx = ptr.x - c.cx, dy = (ptr.y - c.cy) * 1.6, infl = Math.exp(-(dx * dx + dy * dy) / (R * R));
          tw += cfg.near[0] * infl; tg += cfg.near[1] * infl;
        }
        c.cur[0] = lerp(c.cur[0], tw, 0.16); c.cur[1] = lerp(c.cur[1], tg, 0.16);
        apply(c);
      }
    }
  }

  /* ---------- hero: the text block sits right of "pusť.", measured ---------- */
  var hero = $("#heroTitle"), heroGrid = $("#heroGrid"), heroSide = $("#heroSide");
  var HERO_FONT = '600 100px "Anybody"', HERO_TEXT = "Drž, mluv, pusť.";
  function placeHeroSide() {
    if (innerWidth <= 1100) { heroSide.style.removeProperty("--side-left"); return; }
    var words = hero.querySelectorAll(".w"), last = words[words.length - 1];
    if (!last) return;
    // until Anybody is here the CSS fallback (the same measure) stays, the stand-in font would move the text
    if (document.fonts && document.fonts.check && !document.fonts.check(HERO_FONT, HERO_TEXT)) return;
    // measure "pusť." at its widest breath (base + wave), not wherever the breathing happens to be
    var chs = last.querySelectorAll(".ch"), saved = [], i;
    for (i = 0; i < chs.length; i++) { saved.push(chs[i].style.fontVariationSettings); chs[i].style.fontVariationSettings = '"wdth" 113, "wght" 700'; }
    var fs = parseFloat(getComputedStyle(hero).fontSize);
    var right = last.getBoundingClientRect().right - heroGrid.getBoundingClientRect().left;
    for (i = 0; i < chs.length; i++) chs[i].style.fontVariationSettings = saved[i];
    heroSide.style.setProperty("--side-left", Math.round(right + fs * 0.42) + "px");
  }
  if (document.fonts && document.fonts.load) document.fonts.load(HERO_FONT, HERO_TEXT).then(placeHeroSide, placeHeroSide);

  /* ---------- page load: arrive out of hyperspace, the headline assembles ---------- */
  var heroK = kinetics.filter(function (k) { return k.cfg === KIN.hero; })[0];
  if (heroK) { heroK.visible = true; showKinetic(heroK, reduce ? 0 : 0.3); }
  if (reduce) gsap.set(".rv", { opacity: 1, y: 0 });
  else {
    gsap.set(".rv", { opacity: 0, y: 30 });
    gsap.to(".hero .rv", { opacity: 1, y: 0, duration: 1.2, ease: "expo.out", stagger: 0.1, delay: 0.85 });
    ScrollTrigger.batch(".rv:not(.hero .rv)", {
      start: "top 90%", once: true,
      onEnter: function (els) {
        els = els.filter(function (el) { return !el.rvFocused; });  // already shown by focus, don't restart it slower
        if (els.length) gsap.to(els, { opacity: 1, y: 0, duration: 1.1, ease: "expo.out", stagger: 0.08, overwrite: true });
      }
    });
    // Tab can land in a block that hasn't scrolled far enough to appear: show it now, never focus the invisible
    document.addEventListener("focusin", function (e) {
      var rv = e.target.closest && e.target.closest(".rv");
      if (!rv || parseFloat(getComputedStyle(rv).opacity) >= 1) return;
      rv.rvFocused = true;
      gsap.to(rv, { opacity: 1, y: 0, duration: 0.4, overwrite: true });
    });
  }

  /* ---------- nav: background once scrolled, hides going down, comes back going up; the logo's moon orbits ---------- */
  var nav = $("#nav"), moonF = $("#moonFront"), moonB = $("#moonBack"), navY = -1, navDir = 0, moonXY = "", moonSide = null;
  function drawNav() {
    var y = scrollPos();
    if (Math.abs(y - navY) < 0.5) return;
    navDir = y > navY ? 1 : -1; navY = y;
    nav.classList.toggle("scrolled", y > 20);
    nav.classList.toggle("hidden", navDir > 0 && y > 500 && performance.now() > navHold);
    var max = lenis ? Math.max(1, lenis.limit) : Math.max(1, html.scrollHeight - innerHeight);  // Lenis caches it: no layout per frame
    var a = 0.7 + y / max * Math.PI * 4, x = (16 + 13 * Math.cos(a)).toFixed(2), yy = (16 + 4.6 * Math.sin(a)).toFixed(2), front = Math.sin(a) >= 0;
    if (x + " " + yy !== moonXY) {
      moonXY = x + " " + yy;
      moonF.setAttribute("cx", x); moonF.setAttribute("cy", yy); moonB.setAttribute("cx", x); moonB.setAttribute("cy", yy);
    }
    if (front !== moonSide) { moonSide = front; moonF.style.opacity = front ? 1 : 0; moonB.setAttribute("opacity", front ? 0 : 0.8); }
  }
  // Tab scrolls natively to the focused element: that alone doesn't hide the nav
  addEventListener("focusin", function () { navHold = Math.max(navHold, performance.now() + 300); });
  $$(".nav-links a").forEach(function (a) {
    var sec = $(a.getAttribute("href"));
    // after the pinned dictation (made further down), or #diktovani's trigger would ignore its extra scroll length
    if (sec) ScrollTrigger.create({ trigger: sec, start: "top 50%", end: "bottom 50%", refreshPriority: -1, toggleClass: { targets: a, className: "active" } });
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
    if (!stageVisible) return;  // off screen: not even the halo's satellite
    haloAng += reduce ? 0 : dt * 0.00005 * (1 + Math.min(Math.abs(velocity) * 0.05, 4));
    if (haloSat) { haloSat.setAttribute("cx", (630 + 620 * Math.cos(haloAng)).toFixed(1)); haloSat.setAttribute("cy", (280 + 122 * Math.sin(haloAng)).toFixed(1)); }
    if (!orrery) return;
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

  /* hero video: a muted loop that plays while enough of it is on screen (never by itself with reduced motion or
     data saver); one button pauses it, the other starts it over with sound and the native controls */
  var video = $("#heroVideo"), soundBtn = $("#soundBtn"), pauseBtn = $("#pauseBtn");
  if (video && soundBtn && pauseBtn) {
    var still = reduce || !!(navigator.connection && navigator.connection.saveData);
    var want = false, userPaused = false, shown = 0, failed = false, finished = false;
    var play = function () { var p = video.play(); if (p && p.catch) p.catch(function () {}); };
    var autoplay = function () {
      if (failed || still || userPaused || !video.muted || shown < 0.35) return;
      want = true; play();
    };
    var fail = function () {  // neither file plays: the poster stays, the buttons that would do nothing go
      if (failed) return;
      failed = true; want = false; stage.classList.add("novideo");
    };
    // A decode error (e.g. a GPU's VP9 decoder refusing the WebM) doesn't make Chrome try the next <source>: switch to MP4.
    var mp4 = video.querySelector('source[type^="video/mp4"]'), fellBack = false;
    var onError = function () {
      if (fellBack || !mp4 || /\.mp4(\?|$)/.test(video.currentSrc || "")) { fail(); return; }
      fellBack = true;
      var at = video.currentTime || 0, wasPlaying = !video.paused || want;
      video.src = mp4.src; video.load();
      video.addEventListener("loadedmetadata", function () {
        if (at) video.currentTime = at;
        if (wasPlaying) play();
      }, { once: true });
    };
    video.addEventListener("error", onError);
    if (mp4) mp4.addEventListener("error", fail);  // the last <source> failed as well
    if (video.error) onError();  // both can fail before this script runs
    else if (video.networkState === video.NETWORK_NO_SOURCE) setTimeout(function () { if (video.networkState === video.NETWORK_NO_SOURCE && !video.readyState) fail(); }, 1500);
    if (!still) video.preload = "metadata";  // the HTML loads nothing (reduced motion, data saver); the rest get the start, so it begins at once

    var markPause = function () {  // what the video does, not what was asked: the browser may block autoplay
      var off = video.paused, label = off ? "Pustit" : "Zastavit";
      pauseBtn.classList.toggle("paused", off);
      pauseBtn.setAttribute("aria-label", label + " video"); pauseBtn.setAttribute("data-cursor", label);
      if (cursor.classList.contains("is-label") && pauseBtn.matches(":hover")) cLabel.textContent = label;
    };
    video.addEventListener("play", markPause);
    video.addEventListener("pause", markPause);
    markPause();
    pauseBtn.addEventListener("click", function () {  // stays paused, also after scrolling away and back
      userPaused = !video.paused;
      if (userPaused) { want = false; video.pause(); } else { want = true; play(); }
    });
    if (still) { pauseBtn.hidden = true; soundBtn.querySelector("span").textContent = "Přehrát video"; }
    soundBtn.addEventListener("click", function () {
      if (failed) return;
      finished = false; want = true; video.currentTime = 0; video.muted = false; video.loop = false; video.controls = true;
      stage.classList.add("with-controls"); soundBtn.hidden = pauseBtn.hidden = true;
      play(); video.focus(); syncCta();
    });

    /* the download button drawn at the end of the video can't be clicked: a real one flies in from above, lands
       exactly on it and floats there while that scene is on (65.2–74.9 s); after a full play-through it stays */
    var cta = $("#stageCta"), ctaRing = $("#ctaRing"), ctaOn = false, CTA_IN = 64.15, CTA_OUT = 74.8, END_FRAME = 70;
    gsap.set(cta, { xPercent: -50, yPercent: -50 });
    // the drawn one springs in at 65.3–65.7 s, up to 10 % past its size: this one swells with it, on the video's clock
    var ctaBtns = $$(".cta-btn", cta), popS = 1, POP = [[65.33, 1], [65.4, 1.06], [65.43, 1.08], [65.53, 1.08], [65.6, 1.06], [65.7, 1]];
    var pop = function () {
      var t = video.currentTime, s = 1;
      for (var i = 1; i < POP.length; i++) if (t >= POP[i - 1][0] && t < POP[i][0]) s = lerp(POP[i - 1][1], POP[i][1], (t - POP[i - 1][0]) / (POP[i][0] - POP[i - 1][0]));
      if (s === popS) return;
      popS = s; ctaBtns.forEach(function (b) { b.style.transform = s === 1 ? "" : "scale(" + s.toFixed(4) + ")"; });
    };
    var showCta = function () {
      ctaOn = true; cta.classList.add("on"); gsap.killTweensOf(cta); gsap.ticker.add(pop);
      if (reduce) { gsap.to(cta, { opacity: 1, duration: 0.4 }); return; }
      gsap.fromTo(cta, { y: -stage.offsetHeight * 0.85, opacity: 0, rotation: -7, scale: 0.86 },
        { y: 0, opacity: 1, rotation: 0, scale: 1, duration: 0.8, ease: "back.out(1.45)", onComplete: function () {
          gsap.fromTo(ctaRing, { scale: 1, opacity: 0.9 }, { scale: 1.55, opacity: 0, duration: 0.9, ease: "power2.out" });
        } });
    };
    var hideCta = function (fast) {
      ctaOn = false; gsap.killTweensOf(cta); gsap.ticker.remove(pop);
      gsap.to(cta, { y: reduce ? 0 : -50, opacity: 0, duration: fast ? 0.15 : 0.5, ease: "power2.in", onComplete: function () { if (!ctaOn) cta.classList.remove("on"); } });
    };
    var syncCta = function () {
      var t = video.currentTime, on = finished || (t >= CTA_IN && t < CTA_OUT);
      if (on && !ctaOn) showCta(); else if (!on && ctaOn) hideCta(t < CTA_IN - 5);
    };
    video.addEventListener("timeupdate", syncCta);
    video.addEventListener("seeked", syncCta);
    video.addEventListener("seeking", function () {  // scrubbed back from the closing shot: that scene is over
      if (finished && video.currentTime < CTA_IN) { finished = false; soundBtn.hidden = true; }
      syncCta();  // the seek itself can take a while
    });
    video.addEventListener("ended", function () {  // with sound it doesn't loop: stop on the closing shot, keep the button
      finished = true; video.currentTime = END_FRAME; video.pause();
      soundBtn.querySelector("span").textContent = "Přehrát znovu"; soundBtn.hidden = false; syncCta();
    });
    // hover: only the light follows the cursor, the button itself stays on the drawn one
    $$(".cta-btn", cta).forEach(function (b) {
      b.addEventListener("pointermove", function (e) {
        var r = b.getBoundingClientRect();
        b.style.setProperty("--bx", (e.clientX - r.left) + "px"); b.style.setProperty("--by", (e.clientY - r.top) + "px");
      });
    });
    new IntersectionObserver(function (es) {
      var e = es[es.length - 1];
      shown = e.isIntersecting ? e.intersectionRatio : 0;
      if (!e.isIntersecting) { want = false; video.pause(); } else autoplay();
    }, { threshold: [0, 0.35] }).observe(video);
  }

  /* ---------- spoken commands: the marquee, pushed by the scroll; hover a command (or pick a chip) to see what it does ---------- */
  var track = $("#marqueeTrack"), mq = { x: 0, dir: 1, slow: 1, slowTo: 1, w: 0, vis: false }, cmdWord = $("#cmdWord"), cmdText = $("#cmdText");
  if (track) {
    if (!reduce) track.innerHTML += track.innerHTML + track.innerHTML;  // reduced motion: one still copy, wrapped by CSS
    var marquee = $("#marquee"), cmds = $$(".cmd", track), chips = $$(".cmd-chips button"), caption = $(".cmd-caption");
    var autoIx = 0, autoT = null, autoOff = false, shown = "", capW = 0;
    // one copy's width, from the layout (offsetLeft ignores the transform); hover and resizes change it
    var mqPeriod = function () { mq.w = cmds.length > 4 ? cmds[4].offsetLeft - cmds[0].offsetLeft : 0; };
    mqPeriod();
    var showCmd = function (el, soft) {  // soft: only colour it, the wider axes would shift the layout under a phone's reader
      var t = el.textContent;
      cmds.forEach(function (c) { var me = c.textContent === t; c.classList.toggle("on", me && !soft); c.classList.toggle("lit", me && !!soft); });
      chips.forEach(function (b, i) { b.classList.toggle("on", cmds[i].textContent === t); });
      if (t === shown) return;
      shown = t; cmdWord.textContent = t; cmdText.textContent = el.dataset.say;
      if (!reduce) gsap.fromTo(cmdText, { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.35, ease: "power2.out" });
    };
    var stopAuto = function () { autoOff = true; clearInterval(autoT); };
    cmds.forEach(function (c) {
      c.addEventListener("pointerenter", function () { if (canHover) showCmd(c); });
      c.addEventListener("click", function () { showCmd(c); stopAuto(); });
    });
    chips.forEach(function (b, i) {  // the keyboard's (and screen reader's) way in: the marquee itself is aria-hidden
      var pick = function () { showCmd(cmds[i]); stopAuto(); };
      b.addEventListener("focus", pick);
      b.addEventListener("click", pick);
      b.addEventListener("pointerenter", function () { if (canHover) showCmd(cmds[i]); });
    });
    marquee.addEventListener("pointerenter", function () { if (canHover) mq.slowTo = 0.15; });
    marquee.addEventListener("pointerleave", function () { mq.slowTo = 1; });
    if (!canHover) {  // phones: the captions take turns by themselves while the section is in view
      ScrollTrigger.create({ trigger: "#povely", start: "top 80%", end: "bottom 20%",
        onToggle: function (self) {
          clearInterval(autoT);
          if (self.isActive && !autoOff) autoT = setInterval(function () { showCmd(cmds[autoIx++ % 4], true); }, 3200);
        } });
    }
    // the caption keeps the height of its longest explanation, so the rotation never moves the page
    var fitCaption = function (force) {
      if (!caption || (!force && caption.offsetWidth === capW)) return;
      capW = caption.offsetWidth; caption.style.minHeight = "";
      var word = cmdWord.textContent, text = cmdText.innerHTML, max = caption.offsetHeight;
      for (var i = 0; i < 4; i++) { cmdWord.textContent = cmds[i].textContent; cmdText.textContent = cmds[i].dataset.say; max = Math.max(max, caption.offsetHeight); }
      cmdWord.textContent = word; cmdText.innerHTML = text;
      caption.style.minHeight = max + "px";
    };
    fitCaption(true);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { fitCaption(true); mqPeriod(); });
    var mqT;
    addEventListener("resize", function () { clearTimeout(mqT); mqT = setTimeout(function () { mqPeriod(); fitCaption(); }, 200); });
    new IntersectionObserver(function (es) { mq.vis = es[0].isIntersecting; }).observe(marquee);
    // the italic is fetched once you scroll and the section is a screen away, or at once when it is already on screen
    // (tall screens); the class switches when the font is there, so the swap is one step
    var nearIO = new IntersectionObserver(function (es) {
      if (!es[0].isIntersecting) return;
      nearIO.disconnect();
      var swap = function () { marquee.classList.add("near"); mqPeriod(); };
      var near = function () {  // already on screen (a jump): fade through the swap instead of letting the words jerk
        if (!mq.vis || reduce) return swap();
        gsap.to(track, { opacity: 0, duration: 0.15, onComplete: function () { swap(); gsap.to(track, { opacity: 1, duration: 0.4, delay: 0.05 }); } });
      };
      if (document.fonts && document.fonts.load) document.fonts.load("italic 520 50px Anybody", "„Odešli.“ řš").then(near, near);
      else near();
    }, { rootMargin: "100% 0px" });
    var watchNear = function () { removeEventListener("scroll", watchNear); nearIO.observe(marquee); };
    if (scrollY > 0 || marquee.getBoundingClientRect().top < innerHeight) watchNear(); else addEventListener("scroll", watchNear, { passive: true });
  }
  function drawMarquee(dt) {
    if (!track || reduce || !mq.vis) return;
    if (Math.abs(velocity) > 0.2) mq.dir = velocity > 0 ? 1 : -1;
    mq.slow = lerp(mq.slow, mq.slowTo, 0.06);
    mq.x -= (0.05 + Math.min(Math.abs(velocity) * 0.09, 3)) * mq.dir * mq.slow * dt;
    if (mq.x <= -mq.w || mq.x > 0) {  // wrap by exactly one copy, measured now
      mqPeriod();
      if (mq.w) { if (mq.x <= -mq.w) mq.x += mq.w; if (mq.x > 0) mq.x -= mq.w; }
    }
    track.style.transform = "translate3d(" + mq.x.toFixed(1) + "px,0,0)";
  }

  /* ---------- dictation: scroll through one dictation; afterwards (or on phones) hold the mic yourself ---------- */
  var mic = $("#demoMic"), status = $("#demoStatus"), said = $("#demoSaid"), typed = $("#typed"), ph = $("#ph");
  var clock = $("#clock"), clockLbl = $("#clockLbl"), bigClock = $("#bigClock"), chunk1 = $("#chunk1"), chunk2 = $("#chunk2");
  var tlItems = $$("#tl li"), tlFill = $("#tlFill"), wave = $("#wave"), level = $("#demoLevel");
  var SENTENCE = "Ahoj Petře, posílám ti nabídku na čtvrtek. Kdyby ti něco nesedělo, ozvi se.";
  var LINES = [
    "Schůzka se přesouvá na pátek v\u00a010:30, místnost zůstává stejná.",
    "Uprav prosím tabulku tak, aby se DPH počítalo zvlášť, a\u00a0pošli mi náhled.",
    SENTENCE
  ];
  var IDLE = "Podrž mikrofon a\u00a0pak ho pusť.";
  var demo = { state: "idle", manual: false, held: false, pressedAt: 0, timers: [], line: 0, waveHist: [], waveAcc: 0, waveT: 0, lvl: "", fill: "" };
  // the scroll calls these every frame: touch the DOM only when something really changes
  function txt(el, t) { if (el && el.textContent !== t) el.textContent = t; }
  function cls(el, c) { if (el.className !== c) el.className = c; }
  function setClock(t, lbl, big) { txt(clock, t); txt(bigClock, big || t); if (lbl) txt(clockLbl, lbl); }
  function setMic(s) { demo.state = s; if (mic.dataset.state !== s) mic.dataset.state = s; }
  function setStatus(t, warn) { txt(status, t); status.classList.toggle("warn", !!warn); }
  function setFill(p) { var v = p.toFixed(3); if (v !== demo.fill) { demo.fill = v; tlFill.style.setProperty("--p", v); } }
  function setChunks(a, b) { cls(chunk1, "chunk" + a); cls(chunk2, "chunk" + b); }
  function setText(t, flash) {
    if (ph.hidden !== !!t) ph.hidden = !!t;
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
  function press() {  // a real press also takes over the state the scroll is playing
    if (demo.held || (demo.manual && demo.state !== "idle")) return false;
    demo.held = true; demo.manual = true; demo.timers.forEach(clearTimeout); demo.timers = [];
    demo.pressedAt = performance.now();
    setMic("opening"); setStatus("Otevírám mikrofon…");
    later(function () { if (demo.state !== "opening") return; beep(880); setMic("recording"); setStatus("Poslouchám…"); }, 70);
    return true;
  }
  function release() {  // pointerup and lostpointercapture both land here: only the first one counts
    if (!demo.held) return;
    demo.held = false;
    if (performance.now() - demo.pressedAt < 300) {
      demo.timers.forEach(clearTimeout); demo.timers = [];
      setMic("idle"); setStatus("Drž déle. Nahrávky kratší než 0,3\u00a0s Orbit nepřepisuje.", true);
      later(function () { demo.manual = false; if (demo.state === "idle") setStatus(IDLE); }, 3000); return;
    }
    later(function () {
      beep(660); setMic("busy"); setStatus("Přepisuji…");
      later(function () {
        var line = LINES[demo.line++ % LINES.length];
        setText(line, true); setMic("idle"); setStatus("Vloženo. Zkus další větu.");
        txt(said, "Vloženo: „" + line + "“");
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
  // a screen reader "clicks" with no pointer or key events (detail 0): play one dictation for it
  mic.addEventListener("click", function (e) { if (e.detail === 0 && press()) later(release, 1000); });

  var STEPS = [0, 0.14, 0.28, 0.62, 0.8], lastStep = -1;
  function dictScroll(p) {
    setFill(p);
    var step = 0;
    for (var i = 0; i < STEPS.length; i++) if (p >= STEPS[i]) step = i;
    tlItems.forEach(function (li, i) { li.classList.toggle("on", i <= step); });
    if (demo.manual) return;
    var local = step < 4 ? (p - STEPS[step]) / (STEPS[step + 1] - STEPS[step]) : (p - STEPS[4]) / (1 - STEPS[4]);
    if (step === 0) {
      setMic(local > 0.55 ? "opening" : "idle"); setText(""); setClock("0,0\u00a0s", "od stisku klávesy");
      setChunks("", ""); setStatus(local > 0.55 ? "Otevírám mikrofon…" : "Stiskneš klávesu.");
    } else if (step === 1) {
      setMic("recording"); setText(""); setClock("0,1\u00a0s", "od stisku klávesy"); setChunks("", "");
      setStatus("Pípnutí: mikrofon opravdu posílá zvuk.");
    } else if (step === 2) {
      setMic("recording"); setText(""); setClock(czNum(0.1 + local * 6.2, 1) + "\u00a0s", "od stisku klávesy");
      setChunks((local > 0.3 ? " on" : "") + (local > 0.62 ? " done" : ""), local > 0.7 ? " on" : "");
      setStatus(local > 0.62 ? "Mluvíš dál. První věta je už přepsaná." : "Mluvíš. Hotové věty se přepisují už teď.");
    } else if (step === 3) {
      var after = local < 0.4 ? local / 0.4 * 0.25 : 0.25 + (local - 0.4) / 0.6 * 1.35;  // seconds after letting go
      setMic(local < 0.4 ? "recording" : "busy"); setText("");
      setClock("+" + czNum(after, local < 0.4 ? 2 : 1) + "\u00a0s", "po puštění klávesy", "+" + czNum(after, 1) + "\u00a0s");
      setChunks(" on done", " on" + (local > 0.9 ? " done" : ""));
      setStatus(local < 0.4 ? "Pustíš. Ještě čtvrt vteřiny nahrává." : "Přepisuje se poslední věta…");
    } else {
      setMic("idle"); setText(SENTENCE, lastStep !== 4); setClock("+1,6\u00a0s", "po puštění klávesy");
      setChunks(" on done", " on done");
      setStatus("Text je v\u00a0okně. Teď to zkus: podrž mikrofon.");
    }
    lastStep = step;
  }
  function showStatic() {  // no pin (phones, small windows, reduced motion): the finished dictation
    lastStep = -1;
    tlItems.forEach(function (li) { li.classList.add("on"); }); setFill(1);
    setClock("+1,6\u00a0s", "po puštění klávesy"); setChunks(" on done", " on done");
    if (!demo.manual) { setMic("idle"); setText(SENTENCE); setStatus(IDLE); }
  }
  // the pin follows the window: resizing, rotating or zooming switches between the pinned and the static layout
  var dictPin = $("#dictPin"), pinOn = false;
  gsap.matchMedia().add("(min-width: 1000px) and (min-height: 720px) and (prefers-reduced-motion: no-preference)", function () {
    pinOn = true; dictPin.classList.add("pinned");
    ScrollTrigger.create({ trigger: dictPin, start: "top top", end: "+=240%", pin: true, scrub: true,
      onUpdate: function (self) { dictScroll(self.progress); }, onRefresh: function (self) { dictScroll(self.progress); } });
    ScrollTrigger.sort();  // made later than the triggers below it (after a resize): refresh it before them
    return function () { pinOn = false; dictPin.classList.remove("pinned"); showStatic(); };
  });
  if (!pinOn) showStatic();
  // the wave draws only while on screen; the observers give its size, so a frame reads no layout
  var waveCtx = wave && wave.getContext("2d"), waveOn = false, waveW = 0, waveH = 0, waveRO = !!window.ResizeObserver;
  if (wave) {
    new IntersectionObserver(function (es) { waveOn = es[es.length - 1].isIntersecting; }).observe(wave);
    if (waveRO) new ResizeObserver(function (es) { var r = es[es.length - 1].contentRect; waveW = r.width; waveH = r.height; }).observe(wave);
  }
  function drawWave() {
    if (!wave) return;
    var now = performance.now(), dt = demo.waveT ? Math.min(now - demo.waveT, 50) : 16.7;
    demo.waveT = now;
    var on = demo.state === "recording", lv = speak(on);
    var tf = "scale(" + (1.06 + lv * 0.45).toFixed(3) + ")";
    if (tf !== demo.lvl) { demo.lvl = tf; level.style.transform = tf; }
    demo.waveAcc += dt;
    while (demo.waveAcc > 45) { demo.waveAcc -= 45; demo.waveHist.push(on ? lv : 0); if (demo.waveHist.length > 64) demo.waveHist.shift(); }
    if (!waveOn) return;
    if (!waveRO) { waveW = wave.clientWidth; waveH = wave.clientHeight; }
    var ctx = waveCtx, W = waveW, H = waveH, n = 64, bw = W / n;
    if (!W) return;
    ctx.clearRect(0, 0, W, H);
    if (!on) ctx.fillStyle = "rgba(" + accent.join(",") + ",.35)";
    for (var i = 0; i < n; i++) {
      var v = demo.waveHist[demo.waveHist.length - n + i] || 0, hh = Math.max(2, v * H * 0.9);
      if (on) ctx.fillStyle = "rgba(255,77,90," + (0.35 + v * 0.65) + ")";
      ctx.fillRect(i * bw + bw * 0.2, (H - hh) / 2, bw * 0.6, hh);
    }
  }

  /* ---------- privacy: the sentence lights up word by word; packets flow, none gets out ---------- */
  var scrub = $("#scrub");
  if (scrub) {
    var words = scrub.textContent.split(/ +/); scrub.textContent = "";
    var spans = words.map(function (w, i) { var s = document.createElement("span"); s.className = "sw"; s.textContent = w; scrub.appendChild(s); if (i < words.length - 1) scrub.appendChild(document.createTextNode(" ")); return s; });
    if (!reduce) ScrollTrigger.create({
      trigger: scrub, start: "top 82%", end: "bottom 55%", scrub: true,
      onUpdate: function (self) { var n = self.progress * spans.length * 1.05; spans.forEach(function (s, i) { s.style.opacity = clamp(n - i, 0.28, 1); }); }
    });
  }
  var flow = $("#flow"), packetsG = $("#packets"), flowVisible = false, packets = [], spawnT = 0, escapeT = 0;
  var flowNarrow = window.matchMedia("(max-width:700px)"), gpuRect = $("#gpuNode rect"), barrierFlash = $("#barrierFlash");
  // 101 points per path, read once: getPointAtLength in the frame loop forced a layout per packet
  var fp = flow ? ["#fp1", "#fp2", "#fp3"].map(function (s) {
    var p = $(s), len = p.getTotalLength(), lut = [];
    for (var i = 0; i <= 100; i++) { var q = p.getPointAtLength(len * i / 100); lut.push(q.x, q.y); }
    return { el: p, lut: lut };
  }) : [];
  if (flow) new IntersectionObserver(function (es) { flowVisible = es[0].isIntersecting; }).observe(flow);
  function packet(kind) {
    var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("r", kind === "out" ? 5 : 4.5); c.setAttribute("fill", kind === "out" ? "#FF4D5A" : "var(--accent)");
    packetsG.appendChild(c);
    packets.push({ el: c, seg: kind === "out" ? 2 : 0, t: 0, kind: kind, back: false });
  }
  function drawFlow(dt) {
    if (!flow || !flowVisible || reduce || flowNarrow.matches) return;  // phones get the vertical SVG
    spawnT += dt; escapeT += dt;
    if (spawnT > 520) { spawnT = 0; packet("in"); }
    if (escapeT > 3800) { escapeT = 0; packet("out"); }
    for (var i = packets.length - 1; i >= 0; i--) {
      var p = packets[i], seg = fp[p.seg], v = p.kind === "out" ? 0.0011 : 0.0016;
      p.t += (p.back ? -v * 1.4 : v) * dt;
      if (p.kind === "in" && p.t >= 1) {
        if (p.seg === 0) { p.seg = 1; p.t = 0; gsap.fromTo(gpuRect, { attr: { "stroke-opacity": 1 } }, { attr: { "stroke-opacity": 0.7 }, duration: 0.6 }); }
        else { p.el.remove(); packets.splice(i, 1); continue; }
      }
      if (p.kind === "out" && !p.back && p.t >= 1) { p.back = true; p.t = 1; gsap.fromTo(barrierFlash, { attr: { opacity: 0.45, r: 14 } }, { attr: { opacity: 0, r: 40 }, duration: 0.7, ease: "power2.out" }); }
      if (p.kind === "out" && p.back && p.t <= 0.35) { p.el.remove(); packets.splice(i, 1); continue; }
      var f = clamp(p.t, 0, 1) * 100, j = Math.min(99, Math.floor(f)), k = f - j, l = seg.lut;
      p.el.setAttribute("cx", lerp(l[2 * j], l[2 * j + 2], k).toFixed(1)); p.el.setAttribute("cy", lerp(l[2 * j + 1], l[2 * j + 3], k).toFixed(1));
      p.el.setAttribute("opacity", p.back ? clamp((p.t - 0.35) / 0.4, 0, 1) : 1);
    }
  }

  /* ---------- Claude Code panel: each feature plays its own little scene ---------- */
  var W = {
    panel: $("#wPanel"), agent: $("#wAgent"), notes: $("#wNotes"), note: $("#wNote"), noteText: $("#wNoteText"),
    bar1: $("#wBar1"), bar2: $("#wBar2"), pct1: $("#wPct1"), pct2: $("#wPct2"),
    s1: $("#s1"), s2: $("#s2"), s3: $("#s3"), s4: $("#s4"), status: $("#fStatus"), you: $("#fYou"), reply: $("#fReply"),
    target: $("#fTarget"), tName: $("#fTName"), tFolder: $("#fTFolder"), tStatus: $("#fTStatus"), msg: $("#fMsg"), url: $("#fUrl"),
    bubble: $("#bubble"), bIcon: $("#bIcon"), bTitle: $("#bTitle"), bNote: $("#bNote"), bText: $("#bText"), speaker: $("#wSpeaker"),
    slot: $(".w-slot")
  };
  var SC = { working: ["#5B9DFF", "pracuje"], waiting: ["#F5A524", "čeká na tebe"], done: ["#3DD68C", "hotovo"] };
  function session(row, state, flash) {
    var dot = row.querySelector(".dot"), st = row.querySelector(".st");
    dot.style.background = SC[state][0]; dot.style.color = SC[state][0]; dot.classList.toggle("pulse-dot", state === "working");
    st.textContent = SC[state][1]; st.style.color = state === "waiting" ? SC.waiting[0] : "";
    if (flash) { row.classList.add("flash"); clearTimeout(row.flashT); row.flashT = setTimeout(function () { row.classList.remove("flash"); }, 900); }
  }
  function limits(p1, p2) {
    [[W.bar1, W.pct1, p1], [W.bar2, W.pct2, p2]].forEach(function (b) {
      b[0].style.width = b[2] + "%"; b[1].textContent = Math.round(b[2]) + "\u00a0%";
      b[0].style.background = b[2] >= 90 ? "#E5484D" : b[2] >= 70 ? "#F5A524" : "";
    });
  }
  function feed(o) {
    o = o || {};
    W.status.textContent = o.status || ""; W.status.style.color = o.statusColor || "#9AA1AD";
    W.you.textContent = o.you || ""; W.reply.textContent = o.reply || "";
    W.you.hidden = W.reply.hidden = !!o.tName && !o.you && !o.reply;  // Orbit's own question (a task): no exchange above it
    W.target.hidden = !o.tName; W.tName.textContent = o.tName || ""; W.tFolder.textContent = o.tFolder || "";
    W.tStatus.textContent = o.tStatus || ""; W.tStatus.style.color = o.tColor || "#9AA1AD";
    W.msg.hidden = !o.msg; W.msg.textContent = o.msg || ""; W.url.hidden = !o.url; W.url.textContent = o.url || "";
    W.agent.className = "w-agent" + (o.chip ? " " + o.chip : "");
  }
  function bubble(o) {
    W.bubble.classList.remove("press");
    if (!o) { W.bubble.classList.remove("on"); W.speaker.classList.remove("reading"); W.slot.classList.remove("busy"); return; }
    W.bIcon.textContent = o.icon; W.bIcon.style.background = o.color; W.bTitle.textContent = o.title;
    W.bNote.textContent = o.note; W.bNote.style.color = o.color; W.bText.textContent = o.text;
    W.bubble.classList.add("on"); W.slot.classList.add("busy"); W.speaker.classList.toggle("reading", !!o.read);
  }
  var IDLE_FEED = { you: "Ty: Co dělá relace s\u00a0ceníkem?", reply: "Doplňuje ceny do tabulky, zbývají jí dvě kategorie." };
  function baseline(keepFeed) {
    limits(42, 18); W.noteText.textContent = "2\u00a0h 14\u00a0min"; W.note.classList.remove("warn");
    [W.s1, W.s2, W.s3, W.s4].forEach(function (r) { clearTimeout(r.flashT); r.classList.remove("flash"); });  // a scene left mid-flash
    session(W.s1, "working"); session(W.s2, "waiting"); session(W.s3, "working"); W.s4.hidden = true;
    feed(keepFeed ? IDLE_FEED : null); bubble(null);
  }
  function typeInto(tl, el, text, at, dur) {
    var o = { n: 0 };
    tl.to(o, { n: text.length, duration: dur || text.length * 0.028, ease: "none", onUpdate: function () { el.textContent = text.slice(0, Math.round(o.n)); } }, at);
  }
  var ZONES = { limity: ["limits"], relace: ["sessions"], bubliny: ["sessions"], artefakty: [], agent: ["agent", "sessions"], chrome: ["agent"], poznamky: ["agent", "sessions"] };
  var SCENES = {
    limity: function (tl) {
      tl.call(function () { limits(0, 0); });
      tl.to({}, { duration: 0.2 });
      tl.call(function () { limits(42, 18); });
      tl.call(function () { W.noteText.textContent = "2\u00a0h 13\u00a0min"; }, null, 1.6);
      tl.call(function () { limits(71, 19); W.note.classList.add("warn"); W.noteText.textContent = "dojde v\u00a014:20"; }, null, 2.8);
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
      tl.call(function () { bubble({ icon: "✓", color: "#3DD68C", title: "Překlad katalogu", note: "hotovo", text: "Katalog je přeložený, má 48\u00a0stran. Zkontroluj prosím názvy kolekcí, dvě jsem nechal v\u00a0angličtině.", read: true }); }, null, 1.3);
      tl.call(function () { W.speaker.classList.remove("reading"); }, null, 5.4);
      tl.call(function () { bubble(null); }, null, 6.4);
      tl.to({}, { duration: 1 });
    },
    artefakty: function (tl) {
      tl.call(function () { bubble({ icon: "i", color: "#5B9DFF", title: "Artefakt z\u00a0relace eshop", note: "předčítám", text: "Ceník na rok 2027 má 214\u00a0položek. Nejvíc podraží povlečení, v\u00a0průměru o\u00a04,8\u00a0procenta.", read: true }); }, null, 0.8);
      tl.call(function () { W.speaker.classList.remove("reading"); W.bNote.textContent = "přečteno"; }, null, 5.6);
      tl.call(function () { bubble(null); }, null, 6.6);
      tl.to({}, { duration: 1 });
    },
    agent: function (tl) {
      tl.call(function () { feed({ status: "Poslouchám…", statusColor: "#FF4D5A", chip: "listen" }); }, null, 0.3);
      typeInto(tl, W.you, "Ty: Napiš do relace s\u00a0přihlášením, ať přidá test na zapomenuté heslo.", 0.5, 1.8);
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
      typeInto(tl, W.you, "Ty: Otevři mi v\u00a0Chromu objednávku\u00a082.", 0.5, 1.1);
      tl.call(function () { W.agent.className = "w-agent"; W.status.textContent = "Přemýšlím…"; W.status.style.color = "#9AA1AD"; }, null, 1.8);
      typeInto(tl, W.reply, "Otevírám objednávku\u00a082, našel jsem ji v\u00a0historii Chromu.", 2.6, 1.1);
      tl.call(function () {
        W.status.textContent = ""; W.target.hidden = false; W.tName.textContent = "→ Objednávka #82"; W.tFolder.textContent = "Chrome";
        W.tStatus.textContent = "otevírám…"; W.tStatus.style.color = "#9AA1AD"; W.url.hidden = false; W.url.textContent = "obchod.cz/admin/objednavka?id=82";
      }, null, 3.9);
      tl.call(function () { W.tStatus.textContent = "otevřeno ✓"; W.tStatus.style.color = "#3DD68C"; }, null, 4.9);
      tl.to({}, { duration: 2.6 });
    },
    // the notebook's active task: Orbit offers it (panel, bubble, voice), a click on the bubble opens its session
    poznamky: function (tl) {
      tl.call(function () {
        feed({ status: "Mám? Řekni „jo“", statusColor: "#F5A524", chip: "confirm", tName: "→ Úkol: Faktury za září", tFolder: "faktury",
               tStatus: "čeká na tvoje „jo“", tColor: "#F5A524", msg: "nová relace se zadáním úkolu" });
        bubble({ icon: "?", color: "#F5A524", title: "Úkol: Faktury za září", note: "čeká na tebe", text: "Otevřu pro něj novou relaci ve složce faktury. Klikni sem a začnu, nebo řekni agentovi „jo“.", read: true });
      }, null, 0.9);
      tl.call(function () { W.speaker.classList.remove("reading"); }, null, 3.9);
      tl.call(function () { W.bubble.classList.add("press"); }, null, 4.7);
      tl.call(function () { bubble(null); W.agent.className = "w-agent"; W.status.textContent = ""; W.tStatus.textContent = "otevírám…"; W.tStatus.style.color = "#9AA1AD"; }, null, 4.95);
      tl.call(function () { W.tStatus.textContent = "otevřeno ✓"; W.tStatus.style.color = "#3DD68C"; W.s4.hidden = false; session(W.s4, "working", true); }, null, 6);
      tl.to({}, { duration: 2.6 });
    }
  };
  var SNAP = { limity: 3, relace: 5, bubliny: 3, artefakty: 3, agent: 6, chrome: 5, poznamky: 3 };  // reduced motion: one still frame (s)
  var feats = $$(".feat"), featWrap = $("#features"), sceneTl = null, activeScene = null, hoverScene = null, scrollScene = "limity";
  function playScene(name) {
    if (name === activeScene) return;
    activeScene = name;
    feats.forEach(function (f) { var on = f.dataset.scene === name; f.classList.toggle("on", on); f.querySelector("button").setAttribute("aria-pressed", String(on)); });
    featWrap.classList.toggle("has-active", !!name);
    $$(".w-zone", W.panel).forEach(function (z) { z.classList.toggle("lit", (ZONES[name] || []).indexOf(z.dataset.zone) >= 0); });
    W.panel.classList.toggle("focus", !!(ZONES[name] || []).length);
    W.notes.classList.toggle("lit", name === "poznamky");
    if (sceneTl) sceneTl.kill();
    var agentScene = name === "agent" || name === "chrome" || name === "poznamky";
    baseline(!agentScene);
    sceneTl = gsap.timeline({ repeat: -1, repeatDelay: 0.6, onRepeat: function () { baseline(!agentScene); } });
    SCENES[name](sceneTl);
    if (reduce) sceneTl.seek(SNAP[name], false).pause();  // jump there, the calls on the way fire
  }
  baseline(true);
  // hover means the mouse really moved: pointerenter (and WebKit's fake moves) also fire when cards scroll under a resting cursor
  var lastMove = { x: -1, y: -1, real: false };
  addEventListener("pointermove", function (e) { lastMove.real = e.clientX !== lastMove.x || e.clientY !== lastMove.y; lastMove.x = e.clientX; lastMove.y = e.clientY; }, { capture: true, passive: true });
  // a focused or tapped feature keeps its scene while the browser scrolls it into view, until the reader scrolls on
  var heldScene = null, heldY = 0, heldT = 0, claudeST = null;
  var unhold = function () { heldScene = null; };  // not "release": the dictation demo above owns that name
  addEventListener("wheel", unhold, { passive: true });
  addEventListener("touchmove", unhold, { passive: true });
  addEventListener("keydown", function (e) { if (/^(Arrow|Page|Home|End)/.test(e.key)) unhold(); });
  // any other scroll (scrollbar, Space, autoscroll, a nav jump) lets go too: at the next card, or after a third of the screen
  function scrolledOn(min) {
    if (performance.now() - heldT < 300) { heldY = scrollY; return false; }  // the focus scroll itself
    return Math.abs(scrollY - heldY) > min;
  }
  addEventListener("scroll", function () {
    if (!heldScene || !scrolledOn(innerHeight / 3)) return;
    unhold();
    if (!hoverScene && claudeST && claudeST.isActive) playScene(scrollScene);
  }, { passive: true });
  feats.forEach(function (f) {
    var btn = f.querySelector("button"), pick = function () { heldScene = f.dataset.scene; heldY = scrollY; heldT = performance.now(); playScene(heldScene); };
    f.addEventListener("pointermove", function (e) {
      if (e.pointerType !== "mouse" || !lastMove.real || hoverScene === f.dataset.scene) return;
      hoverScene = f.dataset.scene; heldScene = null; playScene(hoverScene);
    });
    f.addEventListener("pointerleave", function () { hoverScene = null; });
    btn.addEventListener("focus", pick);
    btn.addEventListener("click", pick);
    btn.addEventListener("blur", function () { if (heldScene === f.dataset.scene) unhold(); });
    ScrollTrigger.create({ trigger: f, start: function () { return innerWidth < 1000 ? "top 82%" : "top 58%"; }, end: function () { return innerWidth < 1000 ? "bottom 82%" : "bottom 58%"; },
      onToggle: function (self) {
        if (!self.isActive) return;
        scrollScene = f.dataset.scene;
        if (heldScene && scrolledOn(24)) unhold();
        if (!hoverScene && !heldScene) playScene(scrollScene);
      } });
  });
  claudeST = ScrollTrigger.create({ trigger: "#claude", start: "top 70%", end: "bottom top", onEnter: function () { playScene(scrollScene); }, onLeave: function () { if (sceneTl) sceneTl.pause(); }, onEnterBack: function () { if (sceneTl && !reduce) sceneTl.resume(); } });
  // the panel never covers the features: when the screen is too short (zoom, phone landscape) it scrolls with the page
  var widget = $("#widget");
  function fitWidget() {
    var narrow = innerWidth <= 1000, vh = html.clientHeight, hgt = widget.getBoundingClientRect().height, free = narrow && hgt > vh * 0.6;
    widget.classList.toggle("free", free);
    widget.style.top = !narrow && hgt + 122 > vh ? Math.max(16, vh - hgt - 12) + "px" : "";  // short desktop window: the whole panel stays in view
    if (narrow && !free) featWrap.style.setProperty("--panel-b", Math.round(parseFloat(getComputedStyle(widget).top) + hgt) + "px");  // focus scrolls below it
    else featWrap.style.removeProperty("--panel-b");
  }
  fitWidget();
  addEventListener("resize", fitWidget);
  ScrollTrigger.addEventListener("refresh", fitWidget);
  // its infinite CSS animations (pulsing dots, speaker bars) stop while it is off screen
  widget.classList.add("off");
  new IntersectionObserver(function (es) { widget.classList.toggle("off", !es[0].isIntersecting); }).observe(widget);

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

  /* ---------- copy buttons (the prompt for Claude Code, the PowerShell one-liner) ---------- */
  var copyStatus = $("#copyStatus");
  $$("[data-copy]").forEach(function (btn) {
    var label = btn.querySelector("span"), t = null;
    var show = function (done, txt, ms, said) {
      btn.classList.toggle("done", done); label.textContent = txt; clearTimeout(t);
      if (copyStatus) copyStatus.textContent = said;
      t = setTimeout(function () { btn.classList.remove("done"); label.textContent = "Zkopírovat"; }, ms);
    };
    btn.addEventListener("click", function () {
      var src = $(btn.dataset.copy), text = src.textContent.replace(/\s+/g, " ").trim();  // \s also takes the nbsp
      var ok = function () { show(true, "Zkopírováno ✓", 2200, "Zkopírováno do schránky."); };
      var fallback = function () {  // no clipboard API (or it said no): copy the clean text through a hidden textarea
        var ta = document.createElement("textarea"), done = false;
        ta.value = text; ta.setAttribute("readonly", ""); ta.setAttribute("aria-hidden", "true");
        ta.style.cssText = "position:fixed;left:0;top:0;width:1px;height:1px;opacity:0;pointer-events:none";
        document.body.appendChild(ta);
        try { ta.focus({ preventScroll: true }); ta.select(); ta.setSelectionRange(0, text.length); done = document.execCommand("copy"); } catch (e) {}
        document.body.removeChild(ta);
        try { btn.focus({ preventScroll: true }); } catch (e) {}
        if (done) return ok();
        var r = document.createRange(), sel = getSelection();  // last resort: select it so Ctrl+C works
        r.selectNodeContents(src); sel.removeAllRanges(); sel.addRange(r);
        show(false, "Označeno, zkopíruj Ctrl+C", 5000, "Text je označený, zkopíruj ho Ctrl+C.");
      };
      if (copyStatus) copyStatus.textContent = "";
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, fallback);
      else fallback();
    });
  });

  /* ---------- FAQ: answers slide open; a click mid-way turns the running slide around ---------- */
  $$("#faq details").forEach(function (d) {
    var sum = d.querySelector("summary"), ans = d.querySelector(".ans"), tw = null, closing = false;
    sum.addEventListener("click", function (e) {
      if (reduce) return;
      e.preventDefault();
      if (tw) tw.kill();
      if (d.open && !closing) {
        closing = true;
        tw = gsap.to(ans, { height: 0, opacity: 0, duration: 0.45, ease: "power3.inOut", onComplete: function () {
          closing = false; tw = null; d.open = false; gsap.set(ans, { clearProps: "all" }); ScrollTrigger.refresh();
        } });
      } else {
        if (!d.open) { d.open = true; gsap.set(ans, { height: 0, opacity: 0 }); }
        closing = false;
        tw = gsap.to(ans, { height: "auto", opacity: 1, duration: 0.6, ease: "expo.out", onComplete: function () { tw = null; ScrollTrigger.refresh(); } });
      }
    });
  });

  /* ---------- the one loop ---------- */
  var last = performance.now();
  function frame() {
    var now = performance.now(), raw = now - last, dt = Math.min(raw, 50); last = now;
    // one velocity for the wheel, keys, the scrollbar and touch: signed px per 60 Hz frame, from where the page is
    var y = scrollPos(), dy = y - lastY; lastY = y;
    if (Math.abs(dy) > innerHeight * 0.8) dy = 0;  // a jump (End, Home) is a teleport, not a flight
    var v = clamp(dy / Math.max(raw, 1) * 16.7, -200, 200);
    velocity = lerp(velocity, v, 1 - Math.exp(-raw / (Math.abs(v) < Math.abs(velocity) ? 30 : 70)));  // eases in, stops sooner
    if (document.hidden) return;
    drawKinetics(now);  // first: its layout read comes before anything writes styles this frame
    drawWave();
    drawSpace(Math.min(raw, 250), now);
    drawNav();
    drawCursor();
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
