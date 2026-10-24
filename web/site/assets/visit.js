/* Orbit's own visit counter (what it shows: orbit.easya.cz/admin/). No cookies and nothing stored in the browser: one
   random id per page load, kept in memory. It sends to /api/hit.php, and nowhere else, which parts of the page were on
   the screen and for how long, how much of the video played, and clicks on download, copy, GitHub and the FAQ.
   A visit starts only when the page is really on screen (not a background tab, not a prerender), and "Do Not Track" or
   Global Privacy Control in the browser means nothing at all is sent. */
(function () {
  "use strict";
  var nav = navigator, doc = document;
  if (nav.doNotTrack === "1" || window.doNotTrack === "1" || nav.globalPrivacyControl === true) return;
  if (!nav.sendBeacon || !window.IntersectionObserver || !window.crypto || !crypto.getRandomValues) return;

  var ENDPOINT = "/api/hit.php";
  var SECTIONS = ["top", "povely", "diktovani", "soukromi", "claude", "pozadavky", "instalace", "otazky", "konec"];
  var id = "", bytes = new Uint8Array(10);
  crypto.getRandomValues(bytes);
  for (var i = 0; i < bytes.length; i++) id += (bytes[i] + 256).toString(16).slice(1);

  var started = false, t0 = 0, acted = false, beats = 0, demo = 0, sent = {};
  var visible = false, visSince = 0, visMs = 0;
  var dwell = {}, cur = null, curSince = 0;              // section -> [first seen (ms after start), ms on screen]
  var vSec = 0, vSound = 0, vMax = 0;

  function send(o) {
    o.id = id;
    try { nav.sendBeacon(ENDPOINT, new Blob([JSON.stringify(o)], { type: "text/plain" })); } catch (e) {}
  }

  function referrer() {
    try {
      var u = new URL(doc.referrer);
      return u.host === location.host ? "" : u.protocol + "//" + u.host + u.pathname;
    } catch (e) { return ""; }
  }

  function begin() {
    if (started || doc.visibilityState !== "visible" || doc.prerendering) return;
    started = visible = true;
    t0 = visSince = curSince = Date.now();
    var q = new URLSearchParams(location.search);
    send({
      k: "start", r: referrer(), u: (q.get("utm_source") || q.get("ref") || "").slice(0, 40),
      h: location.hash.slice(0, 31), wd: nav.webdriver ? 1 : 0
    });
    watchSections();
    setInterval(function () {               // every 30 s while seen, every 5 min after half an hour
      if (visible && (beats++ < 60 || beats % 10 === 0)) snapshot();
    }, 30000);
  }

  // which part of the page is in the middle of the screen, and since when
  function account(now) {
    if (cur && visible) dwell[cur][1] += now - curSince;
    curSince = now;
  }
  function enter(name) {
    var now = Date.now();
    account(now);
    cur = name;
    if (!dwell[name]) dwell[name] = [now - t0, 0];
  }
  function watchSections() {
    var io = new IntersectionObserver(function (entries) {
      for (var j = entries.length - 1; j >= 0; j--) {
        if (entries[j].isIntersecting) { enter(entries[j].target.id); break; }
      }
    }, { rootMargin: "-50% 0px -50% 0px" });
    SECTIONS.forEach(function (s) { var el = doc.getElementById(s); if (el) io.observe(el); });
  }

  function snapshot(leaving) {      // leaving: the page went away or out of sight, so "on the web now" ends here
    if (!started) return;
    var now = Date.now();
    account(now);
    if (visible) { visMs += now - visSince; visSince = now; }
    var s = {};
    for (var k in dwell) s[k] = [Math.round(dwell[k][0]), Math.round(dwell[k][1])];
    send({ k: "end", s: s, vt: Math.round(visMs), vs: Math.round(vSec), va: Math.round(vSound), vm: vMax, i: acted ? 1 : 0, dm: demo, x: leaving ? 1 : 0 });
  }

  doc.addEventListener("visibilitychange", function () {
    if (doc.visibilityState === "hidden") {
      if (started && visible) { snapshot(true); visible = false; }
    } else if (!started) {
      begin();
    } else if (!visible) {
      visible = true; visSince = curSince = Date.now();
      snapshot();
    }
  });
  addEventListener("pagehide", function () { if (started && visible) { snapshot(true); visible = false; } });
  if (doc.prerendering) doc.addEventListener("prerenderingchange", begin);

  // a person scrolls, moves the mouse or touches the screen; a robot that only loads the page doesn't
  function human() { acted = true; }
  ["wheel", "touchstart", "keydown", "pointerdown"].forEach(function (t) { addEventListener(t, human, { passive: true, capture: true }); });
  addEventListener("pointermove", function (e) { if (e.movementX || e.movementY) human(); }, { passive: true, capture: true });

  function ev(name, meta, once) {
    begin();
    if (!started) return;
    acted = true;
    var key = name + "|" + (meta || "");
    if (once && sent[key]) return;
    sent[key] = 1;
    send({ k: "ev", e: name, m: meta || "", at: Date.now() - t0 });
  }
  function place(el) {
    if (el.closest("nav")) return "menu";
    if (el.closest("#stageCta")) return "video";
    if (el.closest("#top")) return "uvod";
    if (el.closest("#instalace")) return "instalace";
    if (el.closest("#otazky")) return "otazky";
    if (el.closest("#konec")) return "konec";
    if (el.closest("footer")) return "paticka";
    return "jinde";
  }

  doc.addEventListener("click", function (e) {
    var el = e.target && e.target.closest ? e.target.closest("a, button") : null;
    if (!el) return;
    if (el.matches("a[download]")) return ev("download", place(el));
    if (el.matches("[data-copy]")) return ev("copy", (/Cmd$/.test(el.getAttribute("data-copy")) ? "prikaz" : "zadani") + ":" + place(el));
    if (el.matches('a[href$="install.ps1"]')) return ev("script_view", "", true);
    if (el.matches('a[href*="github.com/"]')) return ev("github", /\/issues/.test(el.href) ? "issues" : place(el));
    if (el.id === "soundBtn") return ev("video_sound", "");
    if (el.matches(".feat button")) return ev("feature", el.closest(".feat").getAttribute("data-scene") || "", true);
    if (el.matches(".themes button")) return ev("theme", el.getAttribute("data-theme") || "", true);
    if (el.matches("a[href^='http']")) { try { ev("link", new URL(el.href).host); } catch (x) {} }
  }, true);

  // hovering a feature for a while plays its scene in the panel: that counts as having looked at it
  doc.querySelectorAll(".feat").forEach(function (f) {
    var timer = 0;
    f.addEventListener("pointerenter", function (e) {
      if (e.pointerType !== "mouse") return;
      timer = setTimeout(function () { ev("feature", f.getAttribute("data-scene") || "", true); }, 1200);
    });
    f.addEventListener("pointerleave", function () { clearTimeout(timer); });
  });

  doc.addEventListener("toggle", function (e) {      // FAQ: toggle doesn't bubble, capture still sees it
    var d = e.target;
    if (d && d.tagName === "DETAILS" && d.open && d.closest("#otazky")) {
      var s = d.querySelector("summary");
      ev("faq", s ? s.textContent.trim().slice(0, 70) : "", true);
    }
  }, true);

  doc.addEventListener("copy", function () {          // the prompt or the command selected and copied by hand
    var sel = doc.getSelection && doc.getSelection();
    var node = sel && sel.anchorNode;
    var el = node && (node.nodeType === 1 ? node : node.parentElement);
    if (el && el.closest && el.closest("#ciPrompt, #ciCmd, #heroPrompt, #heroCmd")) ev("copy", "rucne", true);
  });

  var mic = doc.getElementById("demoMic");
  if (mic) mic.addEventListener("pointerdown", function () { if (!demo++) ev("demo", ""); });

  var video = doc.getElementById("heroVideo");
  if (video) {
    var last = null;
    video.addEventListener("timeupdate", function () {
      var t = video.currentTime;
      if (last !== null && t > last && t - last < 1.5 && visible) {
        vSec += t - last;
        if (!video.muted && video.volume > 0) {
          vSound += t - last;
          if (video.duration) vMax = Math.max(vMax, Math.round(t / video.duration * 100));
        }
      }
      last = t;
    });
    video.addEventListener("seeking", function () { last = null; });
  }

  begin();
})();
