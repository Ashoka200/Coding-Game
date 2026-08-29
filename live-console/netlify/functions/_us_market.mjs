// The US market clock, in Eastern Time.
//
// India needed no daylight-saving logic; the US does, and hand-rolling it is
// how you end up an hour wrong twice a year. So the offset is never computed —
// it is asked of the platform's own timezone database via Intl, which knows
// that Eastern Time is UTC-5 until the second Sunday in March and UTC-4 after.
//
// Sessions, unlike India's single window, come in three:
//   04:00–09:30  pre-market      thin, wide spreads, and gaps that do not hold
//   09:30–16:00  regular         the only session this app calls "live"
//   16:00–20:00  after hours     where earnings reactions happen
// Extended-hours prices are real trades but a poor guide to the open, so they
// are labelled, never presented as the price.

const TZ = "America/New_York";

const PARTS = new Intl.DateTimeFormat("en-US", {
  timeZone: TZ, hour12: false, weekday: "short",
  year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit",
});

const WD = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

/** Wall-clock parts in New York for a given instant, DST included. */
export function etParts(d = new Date()) {
  const p = {};
  for (const { type, value } of PARTS.formatToParts(d)) p[type] = value;
  const hour = p.hour === "24" ? 0 : Number(p.hour);   // some ICU builds emit 24
  return {
    year: Number(p.year), month: Number(p.month), day: Number(p.day),
    weekday: WD[p.weekday],
    minutes: hour * 60 + Number(p.minute),
    seconds: Number(p.second),
    hhmmss: [hour, Number(p.minute), Number(p.second)]
      .map((n) => String(n).padStart(2, "0")).join(":"),
    // Which side of the DST change we are on — shown so a wrong hour is visible
    // rather than silent.
    offset: offsetMinutes(d),
  };
}

/** Minutes East of UTC for New York at this instant: -300 (EST) or -240 (EDT). */
function offsetMinutes(d) {
  const utc = new Date(d.toLocaleString("en-US", { timeZone: "UTC" }));
  const ny = new Date(d.toLocaleString("en-US", { timeZone: TZ }));
  return Math.round((ny - utc) / 60000);
}

const PRE   = 4 * 60;             // 04:00
const OPEN  = 9 * 60 + 30;        // 09:30
const CLOSE = 16 * 60;            // 16:00
const POST  = 20 * 60;            // 20:00

/**
 * What the US market is doing right now.
 *   weekend | closed | pre_market | open | after_hours
 * `live` is true only in the regular session — the one price that matters.
 */
export function usMarketState(d = new Date()) {
  const t = etParts(d);
  const zone = t.offset === -240 ? "EDT" : "EST";
  const base = { et: t.hhmmss, zone, offset: t.offset };

  if (t.weekday === 0 || t.weekday === 6) {
    return { ...base, state: "weekend", live: false, extended: false,
             label: "Weekend — US markets are closed" };
  }
  if (t.minutes < PRE) {
    return { ...base, state: "closed", live: false, extended: false,
             label: "Before the pre-market session" };
  }
  if (t.minutes < OPEN) {
    return { ...base, state: "pre_market", live: false, extended: true,
             label: "Pre-market — thin trading, wide spreads, gaps that often do not hold" };
  }
  if (t.minutes < CLOSE) {
    return { ...base, state: "open", live: true, extended: false, label: "Market open" };
  }
  if (t.minutes < POST) {
    return { ...base, state: "after_hours", live: false, extended: true,
             label: "After hours — where earnings reactions happen, on thin volume" };
  }
  return { ...base, state: "closed", live: false, extended: false, label: "US markets closed" };
}

/** Seconds until the next session boundary, so a client can idle. */
export function usSecondsToNextChange(d = new Date()) {
  const t = etParts(d);
  for (const m of [PRE, OPEN, CLOSE, POST]) {
    if (t.minutes < m) return (m - t.minutes) * 60 - t.seconds;
  }
  return (24 * 60 - t.minutes) * 60 - t.seconds;
}

/** IST wall clock for the same instant — the owner is in India, not New York. */
export function istFor(d = new Date()) {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata", hour12: false,
    hour: "2-digit", minute: "2-digit",
  }).format(d);
}
