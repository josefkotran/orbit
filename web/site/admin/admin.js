/* Návštěvy webu: the tooltip of the day-by-day columns (mouse and keyboard) and a second click before "That was me". */
(function () {
  "use strict";
  var tip = null;
  function show(el) {
    var parts = (el.getAttribute("data-tip") || "").split("|");
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; tip.setAttribute("role", "status"); document.body.appendChild(tip); }
    tip.textContent = "";
    var b = document.createElement("b");
    b.textContent = parts[1] || "";
    tip.appendChild(b);
    tip.appendChild(document.createTextNode(parts[0] || ""));
    var r = el.getBoundingClientRect();
    tip.style.display = "block";
    var w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + "px";
    tip.style.top = Math.max(8, r.top - h - 10) + "px";
  }
  function hide() { if (tip) tip.style.display = "none"; }
  document.querySelectorAll("[data-tip]").forEach(function (el) {
    el.addEventListener("pointerenter", function () { show(el); });
    el.addEventListener("pointerleave", hide);
    el.addEventListener("focus", function () { show(el); });
    el.addEventListener("blur", hide);
  });
  addEventListener("scroll", hide, { passive: true });

  document.querySelectorAll("button.forget").forEach(function (btn) {
    var label = btn.textContent, timer = 0;
    btn.addEventListener("click", function (e) {
      if (btn.classList.contains("sure")) return;   // the second click sends the form
      e.preventDefault();
      btn.classList.add("sure");
      btn.textContent = btn.getAttribute("data-sure") || label;
      clearTimeout(timer);
      timer = setTimeout(function () { btn.classList.remove("sure"); btn.textContent = label; }, 4000);
    });
  });
})();
