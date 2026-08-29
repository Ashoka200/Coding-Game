/* The tape.

   One poller for the whole page. Screens do not fetch prices — they tag an
   element with the symbol it shows (`data-live-ltp="RELIANCE"`) and the tape
   writes into it, flashing green or red on a change. That way every price on
   every screen moves together and no screen can forget to update.

   Three rules this file exists to enforce:
     1. Nothing is called "live" unless the exchange is open AND a source
        actually answered. Otherwise the label says what it really is —
        a close, a delayed feed, or nothing at all.
     2. Polling stops when the market closes and when the tab is hidden.
        A background tab burning requests helps nobody.
     3. Every displayed price carries the time it was struck, in IST. */
(function () {
  "use strict";

  var U = window.ADV_COMPANY;
  var num = U ? U.num : function (n) { return n == null ? "—" : n.toFixed(2); };

  var INTERVALS = { fast: 2000, normal: 5000, slow: 15000 };
  var tracked = {};              // symbol -> refcount
  var subs = [];
  var timer = null, inFlight = false;

  var L = {
    last: {},                    // symbol -> quote
    indices: [],
    market: null,
    servedAt: null,
    paused: false,
    speed: "normal",
    feedMode: "http",            // "http" polling, or "websocket" when a broker streams
    feedSource: null,
    ok: null,                    // did the most recent poll return prices?
  };

  /* ---------- what the tape is currently doing ---------- */
  function status() {
    if (L.paused) return { dot: "mut", text: "Paused" };
    if (!L.market) return { dot: "mut", text: "Connecting…" };
    if (!L.market.live) {
      return { dot: "mut", text: L.market.state === "weekend" ? "Weekend — last close"
               : "Closed — last close" };
    }
    var anyExt = Object.keys(L.last).some(function (s) { return L.last[s].extended; });
    if (anyExt && L.market && L.market.extended) {
      return { dot: "warn",
               text: (L.market.state === "pre_market" ? "Pre-market" : "After hours") +
                     " · thin" };
    }
    if (L.feedMode === "websocket") {
      return { dot: "up", text: (L.market.state === "pre_open" ? "Pre-open" : "Streaming") +
               " · every tick" };
    }
    if (L.ok === false) return { dot: "down", text: "Feed unavailable" };
    var delayed = Object.keys(L.last).some(function (s) { return L.last[s].delayed; });
    if (delayed) return { dot: "warn", text: "Delayed feed" };
    var M2 = window.ADV_MARKETS;
    var clock = L.market.ist || L.market.et || "";
    var zone = L.market.zone || (M2 ? M2.current().clockLabel : "IST");
    return { dot: "up", text: (L.market.state === "pre_open" ? "Pre-open" : "Live") +
             " · " + clock + " " + zone };
  }

  function paintStatus() {
    var host = document.getElementById("tape");
    if (!host) return;
    var s = status();
    var src = L.last[Object.keys(L.last)[0]];
    host.className = "tape " + s.dot;
    host.innerHTML = '<span class="dot"></span><span class="t">' + esc(s.text) + "</span>" +
      (src && src.exchange && L.market && L.market.live
        ? '<span class="src">' + esc(src.exchange) + "</span>" : "");
    host.title = L.market ? L.market.label + (L.servedAt ? " · fetched " +
      new Date(L.servedAt).toLocaleTimeString("en-IN") : "") : "";
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c];
    });
  }

  /* ---------- writing prices into whatever is on screen ---------- */
  function paintPrices() {
    document.querySelectorAll("[data-live-ltp]").forEach(function (n) {
      var q = L.last[n.getAttribute("data-live-ltp")];
      if (!q || q.ltp == null) return;
      var shown = n.getAttribute("data-shown");
      var next = num(q.ltp);
      if (shown === next) return;
      n.textContent = next;
      if (shown != null) flash(n, +next.replace(/,/g, "") >= +shown.replace(/,/g, ""));
      n.setAttribute("data-shown", next);
    });
    document.querySelectorAll("[data-live-at]").forEach(function (n) {
      var q = L.last[n.getAttribute("data-live-at")];
      if (!q) { n.textContent = ""; return; }
      // The exchange's own clock, not ours. If it did not send one, say which
      // source answered rather than implying a precision we do not have.
      n.textContent = q.tickTime
        ? (L.market && L.market.live ? "as of " : "last traded ") + q.tickTime +
          " · " + (q.exchange || "")
        : (q.exchange || "") + (q.delayed ? " · delayed" : "");
    });
    document.querySelectorAll("[data-live-chg]").forEach(function (n) {
      var q = L.last[n.getAttribute("data-live-chg")];
      if (!q || q.pChange == null) return;
      n.textContent = (q.pChange >= 0 ? "+" : "") + (q.pChange * 100).toFixed(2) + "%";
      n.classList.toggle("pos", q.pChange >= 0);
      n.classList.toggle("neg", q.pChange < 0);
    });
  }

  function flash(node, up) {
    node.classList.remove("tick-up", "tick-down");
    void node.offsetWidth;                       // restart the animation
    node.classList.add(up ? "tick-up" : "tick-down");
  }

  /* ---------- the poll ---------- */
  function symbols() {
    return Object.keys(tracked).filter(function (s) { return tracked[s] > 0; });
  }

  function poll() {
    if (inFlight || L.paused) return Promise.resolve();
    var syms = symbols();
    if (!syms.length) return Promise.resolve();
    inFlight = true;
    // Which feed to poll is the market's decision, not the tape's.
    var M = window.ADV_MARKETS;
    var url = M ? M.current().api.live(encodeURIComponent(syms.slice(0, 60).join(",")))
                : "/api/live?index=1&symbols=" + encodeURIComponent(syms.slice(0, 60).join(","));
    return fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var got = 0;
        (d.quotes || []).forEach(function (q) {
          if (q.error || q.ltp == null) return;
          // Never overwrite a broker tick with a slower polled snapshot; the
          // poll exists at this point only to fill symbols the socket lacks.
          var have = L.last[q.symbol];
          if (L.feedMode === "websocket" && have && have.exchange === "Zerodha") { got++; return; }
          L.last[q.symbol] = q; got++;
        });
        L.indices = d.indices || L.indices;
        // index levels live in the same map as stocks, so the desk note can
        // bind to NIFTY50 exactly the way a table binds to RELIANCE
        (d.indices || []).forEach(function (i) { if (i.ltp != null) L.last[i.symbol] = i; });
        L.market = d.market || L.market;
        L.servedAt = d.servedAt;
        L.ok = got > 0;
        paintPrices(); paintStatus(); paintIndex();
        subs.forEach(function (fn) { try { fn(L); } catch (e) {} });
        schedule();
      })
      .catch(function () { L.ok = false; paintStatus(); schedule(); })
      .then(function () { inFlight = false; });
  }

  /* Next poll: the market's own clock decides. Closed markets are checked
     rarely, just often enough to notice the opening bell. */
  function schedule() {
    clearTimeout(timer);
    if (L.paused) return;
    var wait;
    // With a broker socket attached the poll is no longer how prices arrive.
    // It stays alive only to keep the market clock honest and to price anything
    // the broker did not return a token for — once every few minutes is plenty.
    if (L.feedMode === "websocket") wait = 5 * 60000;
    else if (!L.market) wait = INTERVALS[L.speed];
    else if (L.market.live) wait = INTERVALS[L.speed];
    else {
      var toOpen = (L.market.secondsToNextChange || 600) * 1000;
      wait = Math.min(Math.max(toOpen, 30000), 15 * 60000);
    }
    if (document.hidden) wait = Math.max(wait, 60000);   // a hidden tab idles
    timer = setTimeout(poll, wait);
  }

  /* ---------- the index strip in the masthead ---------- */
  function paintIndex() {
    var host = document.getElementById("indexstrip");
    if (!host || !L.indices || !L.indices.length) return;
    host.innerHTML = L.indices.map(function (i) {
      var up = (i.pChange || 0) >= 0;
      return '<span class="ix"><b>' + esc(i.name || i.symbol) + "</b>" +
        '<span class="v">' + num(i.ltp) + "</span>" +
        '<span class="c ' + (up ? "pos" : "neg") + '">' +
        (up ? "▲" : "▼") + " " + Math.abs((i.pChange || 0) * 100).toFixed(2) + "%</span></span>";
    }).join("");
  }

  /* ---------- ticks pushed in from a broker socket ---------- */
  /* A streamed tick is strictly better than a polled one: it is the broker's
     own feed, it carries the exchange timestamp, and it costs no request. It
     therefore overwrites whatever polling last wrote, never the other way
     round — see the guard in poll(). */
  L.pushTicks = function (quotes, source) {
    if (!quotes || !quotes.length) return;
    quotes.forEach(function (q) { if (q && q.ltp != null) L.last[q.symbol] = q; });
    L.feedSource = source || L.feedSource;
    L.ok = true;
    paintPrices(); paintStatus(); paintIndex();
    subs.forEach(function (fn) { try { fn(L); } catch (e) {} });
  };

  /* A feed announcing itself. Only a genuinely streaming socket takes over. */
  L.onFeedStatus = function (name, state) {
    var streaming = state && state.status === "streaming";
    var was = L.feedMode;
    L.feedMode = streaming ? "websocket" : "http";
    L.feedSource = streaming ? name : null;
    if (was !== L.feedMode) { paintStatus(); schedule(); }
    else paintStatus();
  };

  /* ---------- public surface ---------- */
  L.track = function (syms) {
    (syms || []).forEach(function (s) { tracked[s] = (tracked[s] || 0) + 1; });
    if (!timer && !inFlight) poll();
    return function release() {
      (syms || []).forEach(function (s) { tracked[s] = Math.max(0, (tracked[s] || 1) - 1); });
    };
  };
  L.subscribe = function (fn) { subs.push(fn); return function () {
    subs = subs.filter(function (f) { return f !== fn; }); }; };
  L.pause = function (on) {
    L.paused = on == null ? !L.paused : !!on;
    paintStatus();
    if (L.paused) clearTimeout(timer); else poll();
    return L.paused;
  };
  L.setSpeed = function (s) { if (INTERVALS[s]) { L.speed = s; schedule(); } };
  L.quote = function (sym) { return L.last[sym] || null; };
  /* Merge the live tick over a stored daily quote, so every screen can show a
     current price without losing the indicators only history can give. */
  L.merge = function (q) {
    if (!q) return q;
    var t = L.last[q.symbol];
    if (!t || t.ltp == null) return q;
    var out = {};
    for (var k in q) out[k] = q[k];
    out.last = t.ltp;
    if (t.prevClose != null) out.prevClose = t.prevClose;
    out.liveAt = t.tickTime || L.servedAt;
    out.liveSource = t.exchange;
    return out;
  };

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && !L.paused) poll(); else schedule();
  });
  document.addEventListener("DOMContentLoaded", function () {
    var t = document.getElementById("tape");
    if (t) t.addEventListener("click", function () { L.pause(); });
    paintStatus();
  });

  window.ADV_LIVE = L;
})();
