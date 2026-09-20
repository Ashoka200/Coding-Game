/* The statistics of movement.

   A port of advisor/stats.py, because the browser has to answer the same three
   questions the engine does — can noise reach this stop, do the odds beat the
   breakeven the ratio demands, and is the return you want actually reachable.

   The last one matters most. A return target is not a preference; it is a claim
   about a Sharpe ratio, and that claim can be checked. This file checks it. */
(function () {
  "use strict";

  var TRADING_DAYS = 250;

  function normCdf(x) {
    // Abramowitz & Stegun 7.1.26 — accurate to ~1e-7, which is far finer than
    // anything downstream of it deserves to be trusted to.
    var s = x < 0 ? -1 : 1, z = Math.abs(x) / Math.SQRT2;
    var t = 1 / (1 + 0.3275911 * z);
    var y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t
            - 0.284496736) * t + 0.254829592) * t * Math.exp(-z * z);
    return 0.5 * (1 + s * y);
  }
  function invNorm(p) {
    // Acklam's inverse normal, good to ~1e-9 across the useful range.
    var a=[-39.69683028665376,220.9460984245205,-275.9285104469687,
           138.3577518672690,-30.66479806614716,2.506628277459239];
    var b=[-54.47609879822406,161.5858368580409,-155.6989798598866,
           66.80131188771972,-13.28068155288572];
    var c=[-0.007784894002430293,-0.3223964580411365,-2.400758277161838,
           -2.549732539343734,4.374664141464968,2.938163982698783];
    var d=[0.007784695709041462,0.3224671290700398,2.445134137142996,
           3.754408661907416];
    var pl=0.02425, q, r;
    if (p < pl) { q = Math.sqrt(-2*Math.log(p));
      return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) /
             ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1); }
    if (p > 1-pl) { q = Math.sqrt(-2*Math.log(1-p));
      return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) /
              ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1); }
    q = p-0.5; r = q*q;
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q /
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1);
  }

  /* ---------- how this stock moves ---------- */
  function describe(closes) {
    var r = [];
    for (var i = 1; i < closes.length; i++) {
      var a = closes[i - 1], b = closes[i];
      if (a > 0 && b > 0) r.push(Math.log(b / a));
    }
    if (r.length < 60) return null;
    var n = r.length, mean = r.reduce(function (s, x) { return s + x; }, 0) / n;
    var v = r.reduce(function (s, x) { return s + (x - mean) * (x - mean); }, 0) / (n - 1);
    var sd = Math.sqrt(v);
    if (!sd) return null;
    var m4 = r.reduce(function (s, x) { return s + Math.pow(x - mean, 4); }, 0) / n;
    var tails = r.filter(function (x) { return Math.abs(x - mean) > 3 * sd; }).length;
    return {
      n: n, dailyMean: mean, dailyVol: sd,
      annualVol: sd * Math.sqrt(TRADING_DAYS),
      annualDrift: mean * TRADING_DAYS,
      excessKurtosis: m4 / Math.pow(sd, 4) - 3,
      tailDays: tails,
      tailDaysIfNormal: n * 2 * (1 - normCdf(3)),
    };
  }

  /* ---------- can noise reach this stop? ----------
     Reflection principle: the chance of TOUCHING a level is twice the chance of
     closing beyond it. Traders reason about the close and are then puzzled by
     how often they are stopped out of a position that ends higher. */
  function noiseStop(stopPct, dailyVol, days) {
    days = days || 20;
    if (!(stopPct > 0) || !(dailyVol > 0)) return 1;
    var sigma = dailyVol * Math.sqrt(days);
    var d = Math.abs(Math.log(1 - Math.min(stopPct, 0.99)));
    return Math.min(1, Math.max(0, 2 * (1 - normCdf(d / sigma))));
  }
  function minSafeStop(dailyVol, days, tolerate) {
    days = days || 20; tolerate = tolerate == null ? 0.25 : tolerate;
    if (!(dailyVol > 0)) return 0;
    var sigma = dailyVol * Math.sqrt(days);
    return 1 - Math.exp(-invNorm(1 - tolerate / 2) * sigma);
  }

  /* ---------- target before stop ---------- */
  function barrier(entry, target, stop, drift, vol) {
    if (!(entry > 0) || !(target > entry) || !(stop > 0) || !(stop < entry)) return null;
    var a = Math.log(target / entry), b = -Math.log(stop / entry);
    if (!(a > 0) || !(b > 0)) return null;
    var p;
    if (vol > 0 && Math.abs(drift || 0) > 1e-12) {
      var k = 2 * drift / (vol * vol);
      var num = 1 - Math.exp(k * b), den = Math.exp(-k * a) - Math.exp(k * b);
      p = den === 0 || !isFinite(num / den) ? b / (a + b) : num / den;
    } else {
      p = b / (a + b);            // driftless: the gambler's-ruin result
    }
    p = Math.min(1, Math.max(0, p));
    var rr = a / b, be = 1 / (1 + rr);
    return { pTarget: p, pStop: 1 - p, rr: rr, breakeven: be,
             edge: p - be, expectancyR: p * rr - (1 - p) };
  }

  /* ---------- how much to risk ---------- */
  function kelly(win, rr) {
    if (!(rr > 0)) return 0;
    return Math.max(0, win - (1 - win) / rr);
  }
  function sizing(win, rr, cap) {
    cap = cap == null ? 0.02 : cap;
    var full = kelly(win, rr), quarter = full / 4;
    return { full: full, quarter: quarter, recommended: Math.min(quarter, cap),
             capped: quarter > cap };
  }

  /* ---------- is the return you want reachable? ----------
     The ceiling: at optimal leverage the best long-run compound growth any
     strategy can reach is Sharpe squared over two, per year. Invert it and a
     return target names the Sharpe ratio it demands — which turns an argument
     about ambition into arithmetic. */
  function feasible(targetDaily, startCapital, worldGdpInr) {
    startCapital = startCapital || 1000000;
    worldGdpInr = worldGdpInr || 9e15;
    var gD = Math.log1p(targetDaily);
    var gA = gD * TRADING_DAYS;
    var sharpe = gA > 0 ? Math.sqrt(2 * gA) : 0;
    var days = targetDaily > 0 && worldGdpInr > startCapital
      ? Math.log(worldGdpInr / startCapital) / gD : null;
    var verdict, tone;
    if (sharpe <= 1)        { verdict = "reachable — this is what a disciplined, ordinary process produces"; tone = "up"; }
    else if (sharpe <= 2.5) { verdict = "demanding but real — the range excellent systematic funds occupy"; tone = "warn"; }
    else if (sharpe <= 7)   { verdict = "beyond any documented fund except Medallion, which closed to outside money because it could not scale"; tone = "down"; }
    else                    { verdict = "not reachable — beyond the best record in the industry's history, and no amount of leverage closes the gap"; tone = "down"; }
    return {
      targetDaily: targetDaily,
      targetAnnual: Math.expm1(gA),
      requiredSharpe: sharpe,
      daysToWorldGdp: days,
      verdict: verdict, tone: tone,
      atSharpe2Daily: Math.expm1(2 / TRADING_DAYS),
      atSharpe2Annual: Math.expm1(2),
    };
  }

  /* ---------- grade one trade plan ---------- */
  function gradeTrade(entry, target, stop, prof, days) {
    var stopPct = (entry - stop) / entry;
    var noise = prof ? noiseStop(stopPct, prof.dailyVol, days) : null;
    var odds = barrier(entry, target, stop, prof ? prof.dailyMean : 0,
                       prof ? prof.dailyVol : 0);
    if (!odds) return { ok: false };
    var flags = [];
    if (noise != null && noise > 0.35) {
      flags.push("Noise alone reaches this stop " + Math.round(noise * 100) +
        "% of the time. Widen it and buy fewer shares — do not tighten it.");
    }
    if (prof && prof.excessKurtosis > 3) {
      flags.push("Returns are fat-tailed here, so the stop can be gapped through " +
        "overnight. Position size, not the stop, is what really caps the loss.");
    }
    return { ok: true, stopPct: stopPct, noise: noise, odds: odds,
             minSafeStop: prof ? minSafeStop(prof.dailyVol, days) : null,
             sizing: sizing(odds.pTarget, odds.rr), flags: flags };
  }

  window.ADV_STATS = {
    describe: describe, noiseStop: noiseStop, minSafeStop: minSafeStop,
    barrier: barrier, kelly: kelly, sizing: sizing, feasible: feasible,
    gradeTrade: gradeTrade, normCdf: normCdf, invNorm: invNorm,
  };
})();
