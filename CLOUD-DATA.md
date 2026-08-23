# The data layer runs in the cloud

The backfill does **not** need your laptop. It runs on Netlify, which can reach
the data sources, and stores history in Netlify Blobs so the whole system has
real series to work with — 200-day averages, market breadth, backtests — rather
than a single snapshot.

## It populates itself

Opening the site is enough. When any data endpoint finds the store empty and no
job running, it starts the backfill in the background — the request is never
delayed, and if the store is ever wiped it refills on the next visit.

To start it deliberately:

```bash
curl -X POST "https://advisor-360-live.netlify.app/api/backfill-background"
```

## Bigger than one invocation, so the job resumes

A full Nifty 500 × 10-year pull does not fit in a single function run. The work
is a **resumable job**: each run processes symbols until its time budget is
nearly spent, saves a cursor, and re-invokes itself to continue. Progress is
written after every batch, so a crashed runner loses nothing — a resume picks up
exactly where it stopped.

If a run ever stalls, continue it with:

```bash
curl -X POST "https://advisor-360-live.netlify.app/api/backfill-background?resume=1"
```

Check how it went — this is the honest answer, not a guess:

```bash
curl "https://advisor-360-live.netlify.app/api/data-status"
curl "https://advisor-360-live.netlify.app/api/data-status?symbol=RELIANCE"
```

It reports live job progress (`done`, `failed`, `percent`, and whether the state
is running/finished/stalled), how many symbols are stored, which source supplied
the universe, the last few runs with their failures, and whether the store is
`ready`.

A symbol that fails is recorded as failed and **never written with substituted
data** — the store holds only real bars.

Useful parameters while testing:

| Parameter | Effect |
|---|---|
| `?limit=20` | only the first 20 symbols — a quick smoke test |
| `?range=2y` | shorter history, much faster |
| `?merge=1` | keep what is stored and append only new sessions |

## It also starts itself, hourly

`nightly-ingest.mjs` is a **scheduled function running every hour**, but it does
almost nothing most of the time. Each run decides:

| Store state | Action |
|---|---|
| empty or thin (<20 symbols) | start a full 10-year backfill |
| a job already in progress | continue it from its cursor |
| populated but stale (>20h) | short merge top-up |
| populated and fresh | return immediately, touching no upstream |

That last row is what makes hourly scheduling polite: a current store costs one
cheap metadata read per hour and **no upstream requests at all**. The empty-store
row is what makes the system self-starting — nobody has to visit the site or run
a command, and a wiped store refills within the hour.

## Protecting the endpoint

Set `ADVISOR_ADMIN_TOKEN` in the Netlify site's environment variables and the
backfill endpoint requires it:

```bash
curl -X POST "https://advisor-360-live.netlify.app/api/backfill-background?token=YOUR_TOKEN"
```

Without the variable set the endpoint is open — fine while you are setting up,
worth locking down afterwards so a public URL cannot be used to hammer the
upstream source.

## What this changes

| | Before | Now |
|---|---|---|
| History | one snapshot per request | ~10 years stored |
| Depends on | upstream answering at request time | the store; upstream only at ingest |
| Backfill runs on | your laptop | Netlify |
| Breadth, backtests | local database only | available from the store |
| Staying current | your own cron | scheduled function |

The local Python database is still supported and still richer — point-in-time
fundamentals, the decision journal, your portfolio. But it is no longer required
to get the system working.
