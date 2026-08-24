/* Zerodha Kite Ticker — a real tick stream, straight from the broker.

   The browser opens the socket itself. Nothing proxies it, so ticks arrive as
   fast as Zerodha sends them and the site's serverless budget is untouched.

   On the credential: the API secret lives only in the Netlify function that
   performs the login exchange. What reaches this file is a day-long access
   token, held in sessionStorage so it dies with the tab, and never written to
   any server. There is no endpoint that will hand out your broker token,
   because the token is never stored anywhere to be handed out.

   Deliberately absent: order placement. This access token *can* place orders,
   and that is exactly why nothing here will. Market data in, nothing out. */
(function () {
  "use strict";

  var WS = "wss://ws.kite.trade";
  var KEY_TOKEN = "kite_access_token", KEY_KEY = "kite_api_key", KEY_USER = "kite_user";

  var K = {
    connected: false, status: "off", detail: null, user: null,
    tokenBySymbol: {}, symbolByToken: {},
  };
  var ws = null, want = [], retries = 0, retryTimer = null, closedByUs = false;

  /* ---------- credential handling ---------- */
  function store(k, v) { try { sessionStorage.setItem(k, v); } catch (e) {} }
  function read(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
  function forget() {
    try { [KEY_TOKEN, KEY_KEY, KEY_USER].forEach(function (k) { sessionStorage.removeItem(k); }); }
    catch (e) {}
  }

  /* Read the token out of the URL fragment and scrub it from the address bar
     immediately, so it does not sit in the browser's visible history. */
  function absorbFragment() {
    var frag = window.location.hash.replace(/^#/, "");
    if (!frag) return null;
    var p = new URLSearchParams(frag);
    var err = p.get("kite_error");
    if (err) {
      history.replaceState(null, "", window.location.pathname + window.location.search);
      return { error: err };
    }
    var tok = p.get("kite");
    if (!tok) return null;
    store(KEY_TOKEN, tok);
    if (p.get("kite_key")) store(KEY_KEY, p.get("kite_key"));
    if (p.get("kite_user")) store(KEY_USER, p.get("kite_user"));
    history.replaceState(null, "", window.location.pathname + window.location.search);
    return { token: tok };
  }

  /* ---------- the binary protocol ----------
     A message is: int16 packet count, then for each packet an int16 length
     followed by that many bytes. All integers are big-endian and signed.
     A one-byte message is the server's heartbeat and carries no data. */

  // Prices arrive as integers scaled by the segment's own divisor.
  function divisorFor(token) {
    var segment = token & 0xff;
    if (segment === 3) return 10000000;     // NSE currency derivatives
    if (segment === 6) return 10000;        // BSE currency derivatives
    return 100;                             // everything else, paise
  }

  function parsePacket(dv, o, len) {
    var token = dv.getInt32(o);
    var div = divisorFor(token);
    var segment = token & 0xff;
    var isIndex = segment === 9;
    var px = function (off) { return dv.getInt32(o + off) / div; };
    var t = { token: token, tradable: !isIndex };

    if (len === 8) { t.ltp = px(4); return t; }        // LTP mode

    if (len === 28 || len === 32) {                    // an index
      t.ltp = px(4); t.dayHigh = px(8); t.dayLow = px(12);
      t.open = px(16); t.prevClose = px(20);
      if (len === 32) t.exchangeTime = dv.getInt32(o + 28);
      return t;
    }

    if (len === 44 || len === 184) {                   // a tradable instrument
      t.ltp = px(4);
      t.lastQty = dv.getInt32(o + 8);
      t.avgPrice = px(12);
      t.volume = dv.getInt32(o + 16);
      t.buyQty = dv.getInt32(o + 20);
      t.sellQty = dv.getInt32(o + 24);
      t.open = px(28); t.dayHigh = px(32); t.dayLow = px(36); t.prevClose = px(40);
      if (len === 184) {
        t.lastTradeTime = dv.getInt32(o + 44);
        t.oi = dv.getInt32(o + 48);
        t.exchangeTime = dv.getInt32(o + 60);
      }
      return t;
    }
    return null;                                       // a shape we do not know
  }

  function parseMessage(buf) {
    if (!buf || buf.byteLength < 2) return [];         // heartbeat
    var dv = new DataView(buf);
    var count = dv.getInt16(0), p = 2, out = [];
    for (var i = 0; i < count; i++) {
      if (p + 2 > buf.byteLength) break;
      var len = dv.getInt16(p); p += 2;
      if (len <= 0 || p + len > buf.byteLength) break;
      var t = parsePacket(dv, p, len);
      if (t) out.push(t);
      p += len;
    }
    return out;
  }

  /* ---------- turning ticks into what the tape expects ---------- */
  function toQuote(t) {
    var sym = K.symbolByToken[t.token];
    if (!sym || t.ltp == null) return null;
    var prev = t.prevClose != null && t.prevClose > 0 ? t.prevClose : null;
    return {
      symbol: sym,
      ltp: t.ltp,
      prevClose: prev,
      open: t.open != null && t.open > 0 ? t.open : null,
      dayHigh: t.dayHigh != null && t.dayHigh > 0 ? t.dayHigh : null,
      dayLow: t.dayLow != null && t.dayLow > 0 ? t.dayLow : null,
      volume: t.volume != null ? t.volume : null,
      change: prev != null ? t.ltp - prev : null,
      pChange: prev != null ? t.ltp / prev - 1 : null,
      exchange: "Zerodha",
      // The exchange's own clock when it sent one; otherwise say nothing rather
      // than passing our receive time off as a strike time.
      tickTime: t.exchangeTime ? istStamp(t.exchangeTime * 1000)
              : t.lastTradeTime ? istStamp(t.lastTradeTime * 1000) : null,
    };
  }

  function istStamp(ms) {
    try {
      return new Date(ms).toLocaleTimeString("en-IN",
        { hour12: false, timeZone: "Asia/Kolkata" }) + " IST";
    } catch (e) { return null; }
  }

  /* ---------- the socket ---------- */
  function setStatus(s, detail) {
    K.status = s; K.detail = detail || null;
    K.connected = s === "streaming";
    if (window.ADV_LIVE) window.ADV_LIVE.onFeedStatus("zerodha", K);
    paintButton();
  }

  function connect() {
    var token = read(KEY_TOKEN), key = read(KEY_KEY);
    if (!token || !key) { setStatus("off"); return Promise.resolve(false); }
    if (!want.length) { setStatus("idle", "nothing subscribed yet"); return Promise.resolve(false); }

    setStatus("resolving", "looking up instrument tokens");
    return fetch("/api/kite-instruments?symbols=" + encodeURIComponent(want.join(",")))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        K.tokenBySymbol = {}; K.symbolByToken = {};
        Object.keys(d.tokens || {}).forEach(function (sym) {
          var tok = d.tokens[sym].token;
          K.tokenBySymbol[sym] = tok; K.symbolByToken[tok] = sym;
        });
        var tokens = Object.values(K.tokenBySymbol);
        if (!tokens.length) { setStatus("error", "no instrument tokens resolved"); return false; }
        return open(key, token, tokens);
      })
      .catch(function (e) { setStatus("error", e.message); return false; });
  }

  function open(key, token, tokens) {
    closedByUs = false;
    setStatus("connecting", "opening the tick stream");
    ws = new WebSocket(WS + "?api_key=" + encodeURIComponent(key) +
                       "&access_token=" + encodeURIComponent(token));
    ws.binaryType = "arraybuffer";

    ws.onopen = function () {
      retries = 0;
      ws.send(JSON.stringify({ a: "subscribe", v: tokens }));
      // Full mode: the only mode that carries the exchange's own timestamp,
      // which the page needs in order to show when a price was actually struck.
      ws.send(JSON.stringify({ a: "mode", v: ["full", tokens] }));
      setStatus("streaming", tokens.length + " instruments");
    };

    ws.onmessage = function (ev) {
      if (typeof ev.data === "string") {
        // Kite reports subscription problems as JSON on the same socket.
        try {
          var m = JSON.parse(ev.data);
          if (m.type === "error") setStatus("error", m.data || "broker refused the subscription");
        } catch (e) {}
        return;
      }
      var quotes = parseMessage(ev.data).map(toQuote).filter(Boolean);
      if (quotes.length && window.ADV_LIVE) window.ADV_LIVE.pushTicks(quotes, "zerodha");
    };

    ws.onclose = function (ev) {
      if (closedByUs) { setStatus("off"); return; }
      // 1006 with no reason usually means the access token has expired — Kite
      // invalidates it every morning, so say that rather than retrying forever.
      if (ev.code === 1006 && retries >= 2) {
        forget();
        setStatus("expired", "the broker session ended — connect again");
        return;
      }
      setStatus("reconnecting", "attempt " + (retries + 1));
      var wait = Math.min(30000, 1000 * Math.pow(2, retries++));
      clearTimeout(retryTimer);
      retryTimer = setTimeout(connect, wait);
    };

    ws.onerror = function () { /* onclose always follows; report it there */ };
    return true;
  }

  function disconnect(alsoForget) {
    closedByUs = true;
    clearTimeout(retryTimer);
    if (ws) { try { ws.close(); } catch (e) {} ws = null; }
    if (alsoForget) forget();
    setStatus("off");
  }

  /* ---------- the button in the masthead ---------- */
  var LABEL = {
    off: "Connect Zerodha", idle: "Connect Zerodha", resolving: "Resolving…",
    connecting: "Connecting…", streaming: "Zerodha live", reconnecting: "Reconnecting…",
    expired: "Session ended — reconnect", error: "Zerodha error",
  };
  function paintButton() {
    var b = document.getElementById("kitebtn");
    if (!b) return;
    b.textContent = LABEL[K.status] || "Connect Zerodha";
    b.className = "kitebtn " + K.status;
    b.title = K.status === "streaming"
      ? "Streaming live ticks from Zerodha" + (K.user ? " as " + K.user : "") +
        (K.detail ? " · " + K.detail : "") + ". Click to disconnect."
      : (K.detail || "Connect your Zerodha account for real-time ticks");
  }

  /* ---------- public surface ---------- */
  K.have = function () { return !!(read(KEY_TOKEN) && read(KEY_KEY)); };
  K.connect = connect;
  K.disconnect = disconnect;
  K.setSymbols = function (syms) {
    var next = (syms || []).slice(0, 200);
    var changed = next.join(",") !== want.join(",");
    want = next;
    if (changed && K.status === "streaming") { disconnect(); connect(); }
    return want;
  };
  K.login = function () { window.location.href = "/api/kite-login"; };
  K._parseMessage = parseMessage;      // exercised by tests-kite.mjs
  K._toQuote = toQuote;

  var absorbed = absorbFragment();
  K.user = read(KEY_USER);
  if (absorbed && absorbed.error) setStatus("error", absorbed.error);

  document.addEventListener("DOMContentLoaded", function () {
    var b = document.getElementById("kitebtn");
    if (b) {
      b.addEventListener("click", function () {
        if (K.status === "streaming" || K.status === "reconnecting") disconnect(true);
        else if (K.have()) connect();
        else K.login();
      });
    }
    paintButton();
  });

  window.ADV_KITE = K;
})();
