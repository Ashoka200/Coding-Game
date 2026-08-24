// The market clock, in IST, on the server.
//
// Everything about "live" depends on knowing whether the exchange is actually
// open. A price shown at 21:00 on a Sunday is not live and must not be dressed
// up as live — it is Friday's close, and the page says so.
//
// Weekday and time are computed here. Holidays are NOT hardcoded: a list I
// cannot verify would confidently mislabel a trading day. Instead the caller
// compares the exchange's own reported timestamp against now — a session that
// says "open" while the feed has not moved for minutes is reported as a stalled
// feed, which covers holidays, halts and outages alike without pretending to
// know next year's calendar.

const IST_OFFSET_MIN = 330;               // UTC+05:30, no DST, ever

/** Wall-clock parts in IST for a given instant. */
export function istParts(d = new Date()) {
  const ist = new Date(d.getTime() + (IST_OFFSET_MIN + d.getTimezoneOffset()) * 60000);
  return {
    year: ist.getFullYear(), month: ist.getMonth() + 1, day: ist.getDate(),
    weekday: ist.getDay(),                // 0 Sun … 6 Sat
    minutes: ist.getHours() * 60 + ist.getMinutes(),
    seconds: ist.getSeconds(),
    hhmmss: [ist.getHours(), ist.getMinutes(), ist.getSeconds()]
      .map((n) => String(n).padStart(2, "0")).join(":"),
  };
}

const PRE_OPEN = 9 * 60;                  // 09:00
const OPEN     = 9 * 60 + 15;             // 09:15
const CLOSE    = 15 * 60 + 30;            // 15:30
const POST     = 16 * 60;                 // 16:00 post-close session ends

/**
 * What the exchange is doing right now.
 *   weekend | pre_open | open | closing_auction | closed
 * `live` is the only flag the UI should trust to call a price "live".
 */
export function marketState(d = new Date()) {
  const t = istParts(d);
  if (t.weekday === 0 || t.weekday === 6) {
    return { state: "weekend", live: false, ist: t.hhmmss,
             label: "Weekend — the exchange is closed" };
  }
  if (t.minutes < PRE_OPEN) {
    return { state: "closed", live: false, ist: t.hhmmss,
             label: "Before the pre-open session" };
  }
  if (t.minutes < OPEN) {
    return { state: "pre_open", live: true, ist: t.hhmmss,
             label: "Pre-open auction — prices are indicative, not tradable" };
  }
  if (t.minutes < CLOSE) {
    return { state: "open", live: true, ist: t.hhmmss, label: "Market open" };
  }
  if (t.minutes < POST) {
    return { state: "closing_auction", live: false, ist: t.hhmmss,
             label: "Closed — settling the closing price" };
  }
  return { state: "closed", live: false, ist: t.hhmmss, label: "Market closed" };
}

/** Seconds until the next state change, so the client can idle instead of poll. */
export function secondsToNextChange(d = new Date()) {
  const t = istParts(d);
  const marks = [PRE_OPEN, OPEN, CLOSE, POST];
  for (const m of marks) {
    if (t.minutes < m) return (m - t.minutes) * 60 - t.seconds;
  }
  return (24 * 60 - t.minutes) * 60 - t.seconds;   // tomorrow's pre-open
}
