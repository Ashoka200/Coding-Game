# The data layer runs in the cloud

The backfill does **not** need your laptop. It runs on Netlify, which can reach
the data sources, and stores history in Netlify Blobs so the whole system has
real series to work with — 200-day averages, market breadth, backtests — rather
than a single snapshot.

## One-time: populate the store

```bash
curl -X POST "https://advisor-360-live.netlify.app/api/backfill-background"
```

That fetches ~10 years of daily history for the tracked universe plus the Nifty
and Bank Nifty indices, and writes it to the store. It runs as a Netlify
*background* function, so it has a 15-minute budget rather than the usual 10
seconds.

Check how it went — this is the honest answer, not a guess:

```bash
curl "https://advisor-360-live.netlify.app/api/data-status"
curl "https://advisor-360-live.netlify.app/api/data-status?symbol=RELIANCE"
```

It reports how many symbols are stored, which source supplied the universe, the
last few runs with their failures, and whether the store is `ready`.

Useful parameters while testing:

| Parameter | Effect |
|---|---|
| `?limit=20` | only the first 20 symbols — a quick smoke test |
| `?range=2y` | shorter history, much faster |
| `?merge=1` | keep what is stored and append only new sessions |

## Ongoing: it tops itself up

`nightly-ingest.mjs` is a **scheduled function** running 13:15 UTC on weekdays
(18:45 IST, after the close). It pulls the last three months and merges them
into the stored series, so history stays current with no cron on your machine.

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
