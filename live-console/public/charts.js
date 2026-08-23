/* Hand-built SVG charts. No library: the artifact CSP blocks CDNs, and a
   charting dependency would import someone else's opinions about what a
   financial chart should look like.

   House rules, applied everywhere:
   - the data is the ink; grid lines and axes stay faint
   - every series is legible in both themes, using tokens rather than literals
   - the most recent point is emphasised, because it is the one you act on
   - a chart with too little data says so instead of drawing a misleading line */
(function () {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";

  function el(tag, attrs) {
    var node = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) {
      node.setAttribute(k, attrs[k]);
    });
    return node;
  }

  function svg(width, height, cls) {
    var s = el("svg", {
      viewBox: "0 0 " + width + " " + height,
      width: "100%", height: height,
      preserveAspectRatio: "none", class: cls || "chart",
      role: "img",
    });
    s.style.display = "block";
    return s;
  }

  function extent(values) {
    var clean = values.filter(function (v) { return v != null && isFinite(v); });
    if (!clean.length) return null;
    var lo = Math.min.apply(null, clean), hi = Math.max.apply(null, clean);
    if (lo === hi) { lo -= 1; hi += 1; }
    return [lo, hi];
  }

  function scaler(domain, range) {
    var d0 = domain[0], d1 = domain[1], r0 = range[0], r1 = range[1];
    return function (v) { return r0 + ((v - d0) / (d1 - d0)) * (r1 - r0); };
  }

  function empty(message, height) {
    var box = document.createElement("div");
    box.className = "chart-empty";
    box.style.height = (height || 160) + "px";
    box.textContent = message;
    return box;
  }

  function niceTicks(lo, hi, count) {
    var span = hi - lo;
    var step = Math.pow(10, Math.floor(Math.log10(span / (count || 4))));
    var err = (span / (count || 4)) / step;
    if (err >= 7.5) step *= 10; else if (err >= 3) step *= 5; else if (err >= 1.5) step *= 2;
    var out = [], t = Math.ceil(lo / step) * step;
    for (; t <= hi; t += step) out.push(t);
    return out;
  }

  function fmtCompact(v) {
    var a = Math.abs(v);
    if (a >= 1e7) return (v / 1e7).toFixed(1) + " Cr";
    if (a >= 1e5) return (v / 1e5).toFixed(1) + " L";
    if (a >= 1000) return (v / 1000).toFixed(1) + "k";
    return Math.round(v).toLocaleString("en-IN");
  }

  /* ---------------- price chart with reference lines ---------------- */
  /* opts: { dates, close, sma200, exitPrice, entryPrice, height } */
  function priceChart(opts) {
    var close = (opts.close || []).filter(function (v) { return v != null; });
    if (close.length < 20) {
      return empty("Not enough price history stored to draw this yet.", opts.height);
    }
    var H = opts.height || 260, W = 900;
    var padL = 6, padR = 62, padT = 12, padB = 22;

    var refs = [opts.exitPrice, opts.entryPrice].filter(function (v) {
      return v != null && isFinite(v); });
    var ex = extent(close.concat(refs, (opts.sma200 || []).filter(Boolean)));
    var x = scaler([0, close.length - 1], [padL, W - padR]);
    var y = scaler([ex[0], ex[1]], [H - padB, padT]);

    var s = svg(W, H);
    s.setAttribute("preserveAspectRatio", "none");

    // horizontal grid, kept faint so the price line dominates
    niceTicks(ex[0], ex[1], 4).forEach(function (t) {
      s.appendChild(el("line", { x1: padL, x2: W - padR, y1: y(t), y2: y(t),
                                 class: "gridline" }));
      var label = el("text", { x: W - padR + 8, y: y(t) + 4, class: "axis" });
      label.textContent = fmtCompact(t);
      s.appendChild(label);
    });

    // 200-day average, drawn beneath the price
    if (opts.sma200 && opts.sma200.some(Boolean)) {
      var mad = "";
      opts.sma200.forEach(function (v, i) {
        if (v == null) return;
        mad += (mad ? "L" : "M") + x(i) + "," + y(v);
      });
      s.appendChild(el("path", { d: mad, class: "series-avg", fill: "none" }));
    }

    // the price itself, with a soft area beneath it
    var line = "", area = "";
    close.forEach(function (v, i) {
      line += (i ? "L" : "M") + x(i) + "," + y(v);
    });
    area = line + "L" + x(close.length - 1) + "," + (H - padB) + "L" + x(0) + "," + (H - padB) + "Z";
    s.appendChild(el("path", { d: area, class: "series-area" }));
    s.appendChild(el("path", { d: line, class: "series-price", fill: "none" }));

    // reference lines: exit price is the one that matters most
    function reference(value, cls, label) {
      if (value == null || !isFinite(value)) return;
      s.appendChild(el("line", { x1: padL, x2: W - padR, y1: y(value), y2: y(value),
                                 class: cls }));
      var t = el("text", { x: padL + 4, y: y(value) - 5, class: "ref-label " + cls });
      t.textContent = label + " " + fmtCompact(value);
      s.appendChild(t);
    }
    reference(opts.entryPrice, "ref-entry", "your cost");
    reference(opts.exitPrice, "ref-exit", "exit price");

    // emphasise the latest point — it is the one you act on
    var lastX = x(close.length - 1), lastY = y(close[close.length - 1]);
    s.appendChild(el("circle", { cx: lastX, cy: lastY, r: 3.5, class: "series-last" }));

    var wrap = document.createElement("div");
    wrap.className = "chartwrap";
    wrap.appendChild(s);
    if (opts.dates && opts.dates.length) {
      var foot = document.createElement("div");
      foot.className = "chart-foot";
      foot.innerHTML = "<span>" + opts.dates[0] + "</span><span>" +
                       opts.dates[opts.dates.length - 1] + "</span>";
      wrap.appendChild(foot);
    }
    return wrap;
  }

  /* ---------------- grouped bars, for revenue and profit ---------------- */
  /* opts: { labels, series: [{name, values, cls}], height } */
  function barChart(opts) {
    var series = (opts.series || []).filter(function (s) {
      return (s.values || []).some(function (v) { return v != null; }); });
    if (!series.length) return empty("No figures available for this chart.", opts.height);

    var H = opts.height || 190, W = 900;
    var padL = 6, padR = 62, padT = 14, padB = 26;
    var all = series.reduce(function (acc, s) { return acc.concat(s.values); }, []);
    var ex = extent(all.concat([0]));
    var n = Math.max.apply(null, series.map(function (s) { return s.values.length; }));
    var y = scaler([Math.min(ex[0], 0), ex[1]], [H - padB, padT]);
    var slot = (W - padL - padR) / n;
    var barW = Math.max(3, (slot * 0.68) / series.length);

    var s = svg(W, H);
    niceTicks(Math.min(ex[0], 0), ex[1], 3).forEach(function (t) {
      s.appendChild(el("line", { x1: padL, x2: W - padR, y1: y(t), y2: y(t), class: "gridline" }));
      var lab = el("text", { x: W - padR + 8, y: y(t) + 4, class: "axis" });
      lab.textContent = fmtCompact(t);
      s.appendChild(lab);
    });
    var zero = y(0);
    s.appendChild(el("line", { x1: padL, x2: W - padR, y1: zero, y2: zero, class: "gridline-zero" }));

    series.forEach(function (ser, si) {
      ser.values.forEach(function (v, i) {
        if (v == null) return;
        var xPos = padL + i * slot + (slot - barW * series.length) / 2 + si * barW;
        var top = Math.min(y(v), zero), h = Math.abs(y(v) - zero);
        s.appendChild(el("rect", { x: xPos, y: top, width: barW - 1,
                                   height: Math.max(1, h), class: ser.cls || "bar" }));
      });
    });

    var wrap = document.createElement("div");
    wrap.className = "chartwrap";
    wrap.appendChild(s);
    var legend = document.createElement("div");
    legend.className = "chart-legend";
    legend.innerHTML = series.map(function (ser) {
      return '<span><i class="swatch ' + (ser.cls || "bar") + '"></i>' + ser.name + "</span>";
    }).join("") + (opts.labels && opts.labels.length
      ? '<span class="muted" style="margin-left:auto">' + opts.labels[0] + " → " +
        opts.labels[opts.labels.length - 1] + "</span>" : "");
    wrap.appendChild(legend);
    return wrap;
  }

  /* ---------------- stacked area, for ownership over time ---------------- */
  /* opts: { labels, bands: [{name, values, cls}], height } */
  function stackChart(opts) {
    var bands = (opts.bands || []).filter(function (b) {
      return (b.values || []).some(function (v) { return v != null; }); });
    if (!bands.length) return empty("No shareholding history available.", opts.height);

    var H = opts.height || 170, W = 900;
    var padL = 6, padR = 46, padT = 10, padB = 22;
    var n = Math.max.apply(null, bands.map(function (b) { return b.values.length; }));
    if (n < 2) return empty("Only one quarter of shareholding — no trend to draw.", opts.height);
    var x = scaler([0, n - 1], [padL, W - padR]);
    var y = scaler([0, 100], [H - padB, padT]);

    var s = svg(W, H);
    [0, 25, 50, 75, 100].forEach(function (t) {
      s.appendChild(el("line", { x1: padL, x2: W - padR, y1: y(t), y2: y(t), class: "gridline" }));
      var lab = el("text", { x: W - padR + 6, y: y(t) + 4, class: "axis" });
      lab.textContent = t + "%";
      s.appendChild(lab);
    });

    var baseline = new Array(n).fill(0);
    bands.forEach(function (band) {
      var top = "", bottom = "";
      for (var i = 0; i < n; i++) {
        var v = band.values[i] == null ? 0 : band.values[i];
        var upper = baseline[i] + v;
        top += (i ? "L" : "M") + x(i) + "," + y(upper);
        baseline[i] = upper;
      }
      for (var j = n - 1; j >= 0; j--) {
        bottom += "L" + x(j) + "," + y(baseline[j] - (band.values[j] == null ? 0 : band.values[j]));
      }
      s.appendChild(el("path", { d: top + bottom + "Z", class: band.cls || "band" }));
    });

    var wrap = document.createElement("div");
    wrap.className = "chartwrap";
    wrap.appendChild(s);
    var legend = document.createElement("div");
    legend.className = "chart-legend";
    legend.innerHTML = bands.map(function (b) {
      return '<span><i class="swatch ' + (b.cls || "band") + '"></i>' + b.name + "</span>";
    }).join("") + (opts.labels && opts.labels.length
      ? '<span class="muted" style="margin-left:auto">' + opts.labels[0] + " → " +
        opts.labels[opts.labels.length - 1] + "</span>" : "");
    wrap.appendChild(legend);
    return wrap;
  }

  /* ---------------- valuation band: where price sits vs fair value ------- */
  /* opts: { price, low, base, high } */
  function valuationBand(opts) {
    if (opts.base == null) return empty("No valuation could be computed.", 96);
    var H = 96, W = 900, padL = 10, padR = 10;
    var lo = Math.min(opts.low != null ? opts.low : opts.base * 0.7, opts.price) * 0.92;
    var hi = Math.max(opts.high != null ? opts.high : opts.base * 1.3, opts.price) * 1.08;
    var x = scaler([lo, hi], [padL, W - padR]);
    var s = svg(W, H);
    var trackY = 46;

    s.appendChild(el("rect", { x: padL, y: trackY - 7, width: W - padL - padR,
                               height: 14, rx: 7, class: "band-track" }));
    if (opts.low != null && opts.high != null) {
      s.appendChild(el("rect", { x: x(opts.low), y: trackY - 7,
                                 width: Math.max(2, x(opts.high) - x(opts.low)),
                                 height: 14, rx: 7, class: "band-fair" }));
    }
    // fair value marker
    s.appendChild(el("line", { x1: x(opts.base), x2: x(opts.base), y1: trackY - 15,
                               y2: trackY + 15, class: "band-base" }));
    var fv = el("text", { x: x(opts.base), y: trackY - 21, class: "band-label",
                          "text-anchor": "middle" });
    fv.textContent = "fair value " + fmtCompact(opts.base);
    s.appendChild(fv);

    // where the price actually is
    s.appendChild(el("circle", { cx: x(opts.price), cy: trackY, r: 7, class: "band-price" }));
    var pl = el("text", { x: x(opts.price), y: trackY + 30, class: "band-label price",
                          "text-anchor": "middle" });
    pl.textContent = "price " + fmtCompact(opts.price);
    s.appendChild(pl);

    var wrap = document.createElement("div");
    wrap.className = "chartwrap";
    wrap.appendChild(s);
    return wrap;
  }

  /* ---------------- sparkline, for inline use in tables ---------------- */
  function sparkline(values, cls) {
    var clean = (values || []).filter(function (v) { return v != null && isFinite(v); });
    if (clean.length < 3) {
      var span = document.createElement("span");
      span.className = "muted";
      span.textContent = "—";
      return span;
    }
    var W = 88, H = 22, ex = extent(clean);
    var x = scaler([0, clean.length - 1], [1, W - 1]);
    var y = scaler([ex[0], ex[1]], [H - 2, 2]);
    var s = svg(W, H, "spark");
    s.setAttribute("width", W);
    s.setAttribute("preserveAspectRatio", "none");
    var d = "";
    clean.forEach(function (v, i) { d += (i ? "L" : "M") + x(i) + "," + y(v); });
    s.appendChild(el("path", { d: d, class: cls || "spark-line", fill: "none" }));
    s.appendChild(el("circle", { cx: x(clean.length - 1), cy: y(clean[clean.length - 1]),
                                 r: 2, class: "spark-last" }));
    return s;
  }

  window.ADV_CHARTS = {
    priceChart: priceChart, barChart: barChart, stackChart: stackChart,
    valuationBand: valuationBand, sparkline: sparkline, empty: empty,
    fmtCompact: fmtCompact,
  };
})();
