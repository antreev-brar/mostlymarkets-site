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
    var rows = $$(".feed .card");
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
      while (n && !n.classList.contains("day")) { if (n.classList.contains("card") && !n.hidden) any = true; n = n.nextElementSibling; }
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
      var g = (svg.getAttribute("data-g") || "0,1").split(",").map(Number), vb = svg.viewBox.baseVal;
      var hv = svg.querySelector(".hv"); if (!hv) return;
      var line = hv.querySelector(".hl"), dot = hv.querySelector(".hd");
      var n = data.v.length;
      var pts = svg.querySelector(".ln.s0").getAttribute("d").slice(1).split(" L");
      function move(ev) {
        var r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) / r.width * vb.width;
        var i = Math.round((x - g[0]) / (g[1] - g[0]) * (n - 1)); i = Math.max(0, Math.min(n - 1, i));
        if (data.v[i] == null) return;
        var pt = pts[Math.min(i, pts.length - 1)].split(","), px = +pt[0];
        line.setAttribute("x1", px); line.setAttribute("x2", px); dot.setAttribute("cx", px); dot.setAttribute("cy", pt[1]);
        hv.style.display = "block";
        var fr = fig.getBoundingClientRect();
        tip.hidden = false; tip.innerHTML = fmtD(data.d[i]) + " &nbsp;<b>" + fmtV(data.v[i], data.u) + "</b>";
        tip.style.left = (r.left - fr.left + px / vb.width * r.width) + "px";
        tip.style.top = (r.top - fr.top + (+pt[1]) / vb.height * r.height) + "px";
      }
      function out() { hv.style.display = "none"; tip.hidden = true; }
      svg.addEventListener("pointermove", move); svg.addEventListener("pointerdown", move);
      svg.addEventListener("pointerleave", out);
    });
  });

  /* tooltips on bars and quadrant points */
  var tipEl = null, tipOwner = null;
  function showTip(el) {
    var host = el.closest("figure, .quad"); if (!host) return;
    if (!tipEl || tipEl.parentNode !== host) {
      if (tipEl) tipEl.remove();
      tipEl = document.createElement("div"); tipEl.className = "tip"; host.appendChild(tipEl);
    }
    var t = el.getAttribute("data-tip"), i = t.indexOf(": ");
    tipEl.innerHTML = i > -1 ? esc(t.slice(0, i)) + " &nbsp;<b>" + esc(t.slice(i + 2)) + "</b>" : esc(t);
    var hr = host.getBoundingClientRect(), shape = el.querySelector("path, rect:not(.hit)") || el, er = shape.getBoundingClientRect();
    var x = er.left - hr.left + er.width / 2, y = er.top - hr.top;
    tipEl.style.left = Math.max(70, Math.min(hr.width - 70, x)) + "px"; tipEl.style.top = y + "px"; tipEl.hidden = false;
    tipOwner = el;
  }
  function hideTip() { if (tipEl) tipEl.hidden = true; tipOwner = null; }
  document.addEventListener("pointerover", function (e) {
    var el = e.target.closest && e.target.closest("[data-tip]"); if (el && e.pointerType === "mouse") showTip(el);
  });
  document.addEventListener("pointerout", function (e) {
    var el = e.target.closest && e.target.closest("[data-tip]");
    if (el && e.pointerType === "mouse" && !el.contains(e.relatedTarget)) hideTip();
  });
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[data-tip]");
    if (!el) { hideTip(); return; }
    if (matchMedia("(hover: none)").matches && tipOwner !== el) { e.preventDefault(); showTip(el); }
  });

  /* stock page section nav */
  var sn = $(".secnav");
  if (sn && "IntersectionObserver" in window) {
    var links = $$("a", sn), secs = links.map(function (a) { return document.getElementById(a.getAttribute("href").slice(1)); });
    var io = new IntersectionObserver(function () {
      var best = 0;
      secs.forEach(function (s, i) { if (s && s.getBoundingClientRect().top < 160) best = i; });
      links.forEach(function (a, i) { a.classList.toggle("on", i === best); });
    }, { rootMargin: "-140px 0px -55% 0px", threshold: [0, 1] });
    secs.forEach(function (s) { if (s) io.observe(s); });
  }

  /* recency: every timestamp says how long ago, ticking; fresh stories say New; stories since your last visit get a dot */
  var WDS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  function nyParts(d) {
    var p = {}; new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: false, weekday: "short" }).formatToParts(d).forEach(function (x) { p[x.type] = x.value; });
    return { day: p.year + "-" + p.month + "-" + p.day, h: +p.hour % 24, m: +p.minute, wd: p.weekday };
  }
  function rel(iso) {
    var t = new Date(iso).getTime(), s = (Date.now() - t) / 1000;
    if (isNaN(t) || s < -300) return null;
    if (s < 60) return "Just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 6 * 3600) { var h = Math.floor(s / 3600), m = Math.round((s - h * 3600) / 60); return h + "h " + (m ? m + "m " : "") + "ago"; }
    var a = nyParts(new Date(t)), n = nyParts(new Date()), y = nyParts(new Date(Date.now() - 864e5));
    var hh = a.h % 12 || 12, tm = hh + ":" + (a.m < 10 ? "0" : "") + a.m + (a.h < 12 ? " a.m." : " p.m.");
    if (a.day === n.day) return Math.round(s / 3600) + "h ago";
    if (a.day === y.day) return "Yesterday, " + tm;
    if (s < 6 * 864e5) return a.wd + ", " + tm;
    return null;
  }
  var NEW_H = 6;
  var lastVisit = (function () {
    var prev = null;
    try { prev = sessionStorage.getItem("mm-prev-visit"); } catch (e) {}
    if (prev === null) { prev = String(store.get("mm-last-visit", "")); try { sessionStorage.setItem("mm-prev-visit", prev); } catch (e) {} }
    store.set("mm-last-visit", Date.now());
    return +prev || 0;
  })();
  function paintTimes() {
    $$("time[data-rel]").forEach(function (el) { var r = rel(el.getAttribute("datetime")); if (r) el.textContent = r; });
    $$("[data-pub]").forEach(function (el) {
      var t = new Date(el.getAttribute("data-pub")).getTime(), age = (Date.now() - t) / 36e5;
      el.classList.toggle("is-new", age >= -0.1 && age < NEW_H);
      el.classList.toggle("unseen", lastVisit > 0 && t > lastVisit);
    });
    var n = nyParts(new Date()), y = nyParts(new Date(Date.now() - 864e5));
    $$(".day[data-day]").forEach(function (d) {
      var k = d.getAttribute("data-day"), sp = d.querySelector("span");
      if (!sp.getAttribute("data-full")) sp.setAttribute("data-full", sp.textContent);
      sp.textContent = k === n.day ? "Today · " + sp.getAttribute("data-full") : k === y.day ? "Yesterday · " + sp.getAttribute("data-full") : sp.getAttribute("data-full");
    });
    var st = $("[data-mstatus]");
    if (st) {
      var hol = (($(".mstrip") || {}).getAttribute ? $(".mstrip").getAttribute("data-hol") : "") || "";
      var mins = n.h * 60 + n.m, wk = WDS.indexOf(n.wd) > 0 && WDS.indexOf(n.wd) < 6 && hol.indexOf(n.day) < 0;
      var lab = "Markets closed", cls = "";
      if (wk && mins >= 570 && mins < 960) { lab = "Markets open"; cls = "open"; }
      else if (wk && mins >= 240 && mins < 570) { lab = "Pre-market"; cls = "ext"; }
      else if (wk && mins >= 960 && mins < 1200) { lab = "After hours"; cls = "ext"; }
      st.className = "ms-st " + cls; st.querySelector("span").textContent = lab;
    }
  }
  paintTimes();
  setInterval(paintTimes, 30000);

  /* live quotes (refreshed by the data job every 15 minutes) */
  var live = $$("[data-live]"), mk = $$("[data-mk]");
  if (live.length || mk.length) {
    fetch(B + "data/quotes.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (q) {
      if (!q) return;
      mk.forEach(function (el) {
        var x = (q.m || {})[el.getAttribute("data-mk")]; if (!x || x[0] == null) return;
        var kind = el.getAttribute("data-k");
        if (kind === "chg" && x[1] != null) {
          el.textContent = (x[1] >= 0 ? "▲ " : "▼ ") + Math.abs(x[1]).toFixed(2) + "%";
          el.className = x[1] >= 0 ? "up" : "down";
        } else if (kind === "lvl") el.textContent = x[0].toFixed(2) + "%";
      });
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
    var h = s.map(function (x) {
      var lg = x[3] ? '<span class="lg"><img src="' + B + 'static/logos/' + x[0] + '.png" alt=""></span>' : '<span class="lg"><b>' + esc(x[0].slice(0, 4)) + '</b></span>';
      var rt = x[4] ? '<span class="rt good">' + esc(x[4]) + "</span>" : "";
      return '<a href="' + B + 'stocks/' + x[0] + '/">' + lg + '<b>' + x[0] + "</b>" + esc(x[1]) + rt + '<span class="sec">' + esc(x[2]) + "</span></a>";
    }).join("");
    h += n.map(function (x) { return '<a href="' + B + x[1] + '">' + esc(x[0]) + '<span class="sec">' + esc(x[2]) + "</span></a>"; }).join("");
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
  /* Discover: show a whole group */
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-more]"); if (!b) return;
    var g = b.closest(".grp"); g.classList.toggle("open");
    b.textContent = g.classList.contains("open") ? "Show fewer" : "Show all " + g.querySelectorAll(".sk").length;
  });

  /* copy a take's link */
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-copy]"); if (!b) return;
    var url = b.getAttribute("data-copy");
    function done() { b.textContent = "Link copied"; b.classList.add("ok"); setTimeout(function () { b.textContent = "Copy link"; b.classList.remove("ok"); }, 2200); }
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, function () { toast(url); }); else toast(url);
  });

  /* stories: tap-through slides (templates rendered by the build) */
  var groups = $$("template.stg");
  if (groups.length) {
    var seen = store.get("mm-seen-stories", []);
    var rail = $(".rail-in");
    function paintSeen() {
      $$(".ring[data-story-open]").forEach(function (r) { r.classList.toggle("seen", seen.indexOf(r.getAttribute("data-story-open")) > -1); });
    }
    if (rail) {  // unseen first, like every stories rail
      $$(".ring", rail).filter(function (r) { return seen.indexOf(r.getAttribute("data-story-open")) > -1; })
        .forEach(function (r) { rail.appendChild(r); });
    }
    paintSeen();
    var ov, bars, hd, stage, gi = 0, si = 0, t0 = 0, elapsed = 0, paused = false, raf = 0, DUR = 7000, down = null;
    function slidesOf(g) { return $$(".sl", g.content); }
    function markSeen(g) {
      var id = g.getAttribute("data-id");
      if (seen.indexOf(id) < 0) { seen.push(id); seen = seen.slice(-60); store.set("mm-seen-stories", seen); }
    }
    function build() {
      ov = document.createElement("div"); ov.className = "stv"; ov.setAttribute("role", "dialog"); ov.setAttribute("aria-modal", "true"); ov.setAttribute("aria-label", "Stories");
      ov.innerHTML = '<button class="stv-nav p" type="button" aria-label="Previous">‹</button><div class="stv-fr"><div class="stv-bars"></div><div class="stv-hd"></div>' +
        '<div class="stv-stage"></div><div class="stv-tap p"></div><div class="stv-tap n"></div></div><button class="stv-nav n" type="button" aria-label="Next">›</button>';
      document.body.appendChild(ov);
      bars = $(".stv-bars", ov); hd = $(".stv-hd", ov); stage = $(".stv-stage", ov);
      $(".stv-nav.p", ov).addEventListener("click", prev); $(".stv-nav.n", ov).addEventListener("click", next);
      ov.addEventListener("click", function (e) {
        if (e.target === ov) close();
        if (e.target.closest(".stv-x")) close();
      });
      var fr = $(".stv-fr", ov);
      fr.addEventListener("pointerdown", function (e) {
        if (e.target.closest("a, button")) return;
        down = { x: e.clientX, y: e.clientY, t: Date.now(), zone: e.target.closest(".stv-tap") }; paused = true;
      });
      fr.addEventListener("pointerup", function (e) {
        if (!down) return;
        var dx = e.clientX - down.x, dy = e.clientY - down.y, dt = Date.now() - down.t, z = down.zone; down = null; paused = false;
        if (dy > 90 && Math.abs(dy) > Math.abs(dx)) { close(); return; }
        if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) { if (dx < 0) nextGroup(); else prevGroup(); return; }
        if (dt < 300 && Math.abs(dx) < 12 && Math.abs(dy) < 12 && z) { if (z.classList.contains("p")) prev(); else next(); }
      });
      fr.addEventListener("pointercancel", function () { down = null; paused = false; });
    }
    function show() {
      var g = groups[gi], sl = slidesOf(g);
      bars.innerHTML = sl.map(function (_, i) { return '<i><b style="width:' + (i < si ? 100 : 0) + '%"></b></i>'; }).join("");
      hd.innerHTML = "";
      hd.appendChild(g.content.querySelector(".stg-av").cloneNode(true));
      var nm = document.createElement("span"); nm.innerHTML = esc(g.getAttribute("data-name")) + " <small>" + esc(g.getAttribute("data-when")) + "</small>";
      hd.appendChild(nm);
      var x = document.createElement("button"); x.className = "stv-x"; x.type = "button"; x.setAttribute("aria-label", "Close"); x.innerHTML = "×"; hd.appendChild(x);
      stage.innerHTML = ""; stage.appendChild(sl[si].cloneNode(true));
      elapsed = 0; t0 = performance.now();
      if (si === sl.length - 1) markSeen(g);
    }
    function tick(now) {
      if (!paused && !document.hidden) elapsed += now - t0;
      t0 = now;
      var b = bars.children[si] && bars.children[si].firstChild;
      if (b) b.style.width = Math.min(100, elapsed / DUR * 100) + "%";
      if (elapsed >= DUR) next();
      raf = requestAnimationFrame(tick);
    }
    function next() { if (si < slidesOf(groups[gi]).length - 1) { si++; show(); } else nextGroup(); }
    function prev() { if (si > 0) { si--; show(); } else prevGroup(); }
    function nextGroup() { markSeen(groups[gi]); if (gi < groups.length - 1) { gi++; si = 0; show(); } else close(); }
    function prevGroup() { if (gi > 0) { gi--; si = 0; } show(); }
    function open(id) {
      if (!ov) build();
      gi = 0; groups.forEach(function (g, i) { if (g.getAttribute("data-id") === id) gi = i; });
      si = 0; ov.classList.add("on"); document.documentElement.style.overflow = "hidden"; paused = false;
      show(); cancelAnimationFrame(raf); t0 = performance.now(); raf = requestAnimationFrame(tick);
      try { history.pushState({ stv: 1 }, ""); } catch (e) {}
      $(".stv-nav.n", ov).focus({ preventScroll: true });
    }
    function close(fromPop) {
      if (!ov || !ov.classList.contains("on")) return;
      ov.classList.remove("on"); document.documentElement.style.overflow = ""; cancelAnimationFrame(raf);
      paintSeen();
      if (fromPop !== true && history.state && history.state.stv) history.back();
    }
    window.addEventListener("popstate", function () { close(true); });
    document.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-story-open]"); if (!b) return;
      e.preventDefault(); open(b.getAttribute("data-story-open"));
    });
    document.addEventListener("keydown", function (e) {
      if (!ov || !ov.classList.contains("on")) return;
      if (e.key === "ArrowRight") next(); else if (e.key === "ArrowLeft") prev(); else if (e.key === "Escape") close();
    });
  }
})();
