/* Mostly Markets: small, dependency-free behaviour. Everything degrades to the static page. */
(function () {
  "use strict";
  var B = document.documentElement.getAttribute("data-base") || "/";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var store = {
    get: function (k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  };

  /* theme */
  var tbtn = $("[data-theme-toggle]");
  if (tbtn) tbtn.addEventListener("click", function () {
    var cur = document.documentElement.getAttribute("data-theme") ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    var next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    store.set("mm-theme", next);
  });

  /* toast */
  var toastEl;
  function toast(msg) {
    if (!toastEl) { toastEl = document.createElement("div"); toastEl.className = "toast"; toastEl.setAttribute("role", "status"); document.body.appendChild(toastEl); }
    toastEl.textContent = msg; toastEl.classList.add("on");
    clearTimeout(toast.t); toast.t = setTimeout(function () { toastEl.classList.remove("on"); }, 2600);
  }

  /* follows */
  function follows() { return store.get("mm-follows", []); }
  function paintFollow() {
    var f = follows();
    $$("[data-follow]").forEach(function (b) {
      var on = f.indexOf(b.getAttribute("data-follow")) > -1;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
      var lab = b.querySelector("span");
      if (lab) lab.textContent = on ? "Following" : "Follow";
    });
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-follow]");
    if (!b) return;
    e.preventDefault();
    var t = b.getAttribute("data-follow"), f = follows(), i = f.indexOf(t);
    if (i > -1) { f.splice(i, 1); toast("Unfollowed " + t); }
    else { f.push(t); toast("Following " + t + ". Its stories now show under My stocks."); }
    store.set("mm-follows", f); paintFollow(); applyFilter();
  });
  paintFollow();

  /* feed filters */
  var current = "all";
  function applyFilter() {
    var rows = $$(".feed .row");
    if (!rows.length) return;
    var f = follows(), shown = 0;
    rows.forEach(function (r) {
      var type = r.getAttribute("data-type"), tks = (r.getAttribute("data-tickers") || "").split(" ");
      var ok = current === "all" ||
        (current === "mine" ? tks.some(function (t) { return f.indexOf(t) > -1; }) :
          current.split(",").indexOf(type) > -1);
      r.hidden = !ok; if (ok) shown++;
    });
    $$(".feed .day").forEach(function (d) {
      var n = d.nextElementSibling, any = false;
      while (n && !n.classList.contains("day")) { if (n.classList.contains("row") && !n.hidden) any = true; n = n.nextElementSibling; }
      d.hidden = !any;
    });
    var em = $(".feed .empty");
    if (em) {
      em.hidden = shown > 0;
      em.textContent = current === "mine" ?
        (f.length ? "No recent stories on the stocks you follow." : "Follow a stock from its page or any story, and its stories will collect here.") :
        "No stories of this kind on this page.";
    }
  }
  $$(".chips .chip").forEach(function (c) {
    c.addEventListener("click", function () {
      $$(".chips .chip").forEach(function (x) { x.setAttribute("aria-pressed", "false"); });
      c.setAttribute("aria-pressed", "true");
      current = c.getAttribute("data-filter");
      applyFilter();
    });
  });

  /* chart ranges on stock pages */
  $$(".ranges").forEach(function (g) {
    g.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      $$("button", g).forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      var want = b.getAttribute("data-r");
      $$(".rng-panel", g.parentNode).forEach(function (p) { p.hidden = p.getAttribute("data-r") !== want; });
    });
  });

  /* chart hover */
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function fmtV(v, u) {
    if (v == null) return "–";
    if (u === "$") return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (u === "%") return v.toFixed(2) + "%";
    if (u === "$bn") return "$" + v.toFixed(1) + "bn";
    return v.toLocaleString("en-US", { maximumFractionDigits: 2 }) + (u || "");
  }
  function fmtD(s) {
    if (!/^\d{4}-\d\d-\d\d$/.test(s)) return s;
    var p = s.split("-"); return +p[2] + " " + MON[+p[1] - 1] + " " + p[0];
  }
  $$(".hov[data-h]").forEach(function (h) {
    var data; try { data = JSON.parse(h.getAttribute("data-h")); } catch (e) { return; }
    var tip = document.createElement("div"); tip.className = "htip"; tip.hidden = true;
    var fig = h.querySelector("figure"); fig.appendChild(tip);
    $$("svg.cv", h).forEach(function (svg) {
      var key = svg.classList.contains("m") ? "m" : "d", g = data.g[key], vb = svg.viewBox.baseVal;
      var hv = svg.querySelector(".hv"); if (!hv) return;
      var line = hv.querySelector(".hl"), dot = hv.querySelector(".hd");
      var n = data.v.length;
      var vals = data.v.filter(function (v) { return v != null; });
      function move(ev) {
        var r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) / r.width * vb.width;
        var i = Math.round((x - g[0]) / (g[1] - g[0]) * (n - 1)); i = Math.max(0, Math.min(n - 1, i));
        if (data.v[i] == null) return;
        var px = g[0] + (g[1] - g[0]) * i / Math.max(1, n - 1);
        var ys = svg.querySelector(".ln").getAttribute("d");
        var pts = ys.slice(1).split(" L"), pt = pts[Math.min(i, pts.length - 1)].split(",");
        line.setAttribute("x1", px); line.setAttribute("x2", px); dot.setAttribute("cx", px); dot.setAttribute("cy", pt[1]);
        hv.style.display = "block";
        var fr = fig.getBoundingClientRect();
        tip.hidden = false; tip.innerHTML = fmtD(data.d[i]) + " &nbsp;<b>" + fmtV(data.v[i], data.u) + "</b>";
        tip.style.left = (r.left - fr.left + px / vb.width * r.width) + "px";
        tip.style.top = (r.top - fr.top + (+pt[1]) / vb.height * r.height) + "px";
      }
      function out() { hv.style.display = "none"; tip.hidden = true; }
      svg.addEventListener("pointermove", move); svg.addEventListener("pointerleave", out);
      svg.addEventListener("touchend", out);
    });
  });

  /* relative times */
  function rel(iso) {
    var t = new Date(iso).getTime(), s = (Date.now() - t) / 1000;
    if (isNaN(t) || s < 0 || s > 86400) return null;
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + " min ago";
    return Math.round(s / 3600) + "h ago";
  }
  $$("time[data-rel]").forEach(function (el) { var r = rel(el.getAttribute("datetime")); if (r) el.textContent = r; });

  /* live quotes (refreshed by the data job every 15 minutes) */
  var live = $$("[data-live]");
  if (live.length) {
    fetch(B + "data/quotes.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (q) {
      if (!q) return;
      live.forEach(function (el) {
        var x = q.q[el.getAttribute("data-live")]; if (!x) return;
        var kind = el.getAttribute("data-k");
        if (kind === "price") el.textContent = fmtV(x[0], "$");
        else if (kind === "chg") {
          el.textContent = (x[1] >= 0 ? "+" : "−") + Math.abs(x[1]).toFixed(2) + "%";
          el.className = el.className.replace(/\b(up|down)\b/g, "").trim() + " " + (x[1] >= 0 ? "up" : "down");
        } else if (kind === "asof") el.textContent = x[4];
        else if (kind === "ext") {
          if (x[2] == null) { el.hidden = true; return; }
          el.hidden = false;
          el.innerHTML = (x[5] || "After hours") + ": <span>" + fmtV(x[2], "$") + " (" + (x[3] >= 0 ? "+" : "−") + Math.abs(x[3]).toFixed(2) + "%)</span>";
        }
      });
    }).catch(function () {});
  }

  /* search */
  var sr = $(".srch"), idx = null;
  function openSearch() {
    if (!sr) return; sr.classList.add("open"); var i = $("input", sr); i.value = ""; i.focus(); draw("");
    if (!idx) fetch(B + "data/search.json").then(function (r) { return r.json(); }).then(function (d) { idx = d; draw(i.value); });
  }
  function closeSearch() { if (sr) sr.classList.remove("open"); }
  function draw(q) {
    var res = $(".res", sr); if (!idx) { res.innerHTML = '<div class="hint">Loading…</div>'; return; }
    q = q.trim().toLowerCase();
    if (!q) { res.innerHTML = '<div class="hint">Search a company, a ticker or a story.</div>'; return; }
    var s = idx.s.filter(function (x) { return x[0].toLowerCase() === q || x[0].toLowerCase().indexOf(q) === 0 || x[1].toLowerCase().indexOf(q) > -1; })
      .sort(function (a, b) { return (a[0].toLowerCase() === q ? -1 : 0) - (b[0].toLowerCase() === q ? -1 : 0); }).slice(0, 6);
    var n = idx.n.filter(function (x) { return x[0].toLowerCase().indexOf(q) > -1; }).slice(0, 6);
    var h = s.map(function (x) { return '<a href="' + B + 'stocks/' + x[0] + '/"><b>' + x[0] + "</b>" + esc(x[1]) + "<span>" + esc(x[2]) + "</span></a>"; }).join("");
    h += n.map(function (x) { return '<a href="' + B + x[1] + '">' + esc(x[0]) + "<span>" + esc(x[2]) + "</span></a>"; }).join("");
    res.innerHTML = h || '<div class="hint">Nothing found.</div>';
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  $$("[data-search]").forEach(function (b) { b.addEventListener("click", openSearch); });
  if (sr) {
    sr.addEventListener("click", function (e) { if (e.target === sr) closeSearch(); });
    $("input", sr).addEventListener("input", function (e) { draw(e.target.value); });
    $("input", sr).addEventListener("keydown", function (e) {
      if (e.key === "Enter") { var a = $(".res a", sr); if (a) location.href = a.href; }
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeSearch();
    if (e.key === "/" && !/input|textarea/i.test(document.activeElement.tagName)) { e.preventDefault(); openSearch(); }
  });

  /* sortable tables */
  $$("table.big[data-sort]").forEach(function (t) {
    $$("th", t).forEach(function (th, ci) {
      th.addEventListener("click", function () {
        var tb = t.tBodies[0], rows = $$("tr", tb), dir = th.getAttribute("data-dir") === "desc" ? 1 : -1;
        $$("th", t).forEach(function (x) { x.removeAttribute("data-dir"); });
        th.setAttribute("data-dir", dir === 1 ? "asc" : "desc");
        rows.sort(function (a, b) {
          var x = a.cells[ci].getAttribute("data-v") || a.cells[ci].textContent, y = b.cells[ci].getAttribute("data-v") || b.cells[ci].textContent;
          var nx = parseFloat(x), ny = parseFloat(y);
          if (!isNaN(nx) && !isNaN(ny)) return (nx - ny) * dir;
          return x.localeCompare(y) * dir;
        });
        rows.forEach(function (r) { tb.appendChild(r); });
      });
    });
  });
  var tf = $("[data-table-filter]");
  if (tf) tf.addEventListener("input", function () {
    var q = tf.value.trim().toLowerCase();
    $$("table.big tbody tr").forEach(function (r) { r.hidden = q && r.textContent.toLowerCase().indexOf(q) === -1; });
  });
})();
