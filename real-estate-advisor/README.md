# Real Estate Investment Advisor (India)

Land-investment decision support: monitors public government activity, scores growth
corridors with the Hyderabad-pattern template, and screens parcels through an
advocate-grade legal checklist. See `BUILD-PLAN.md` and `knowledge/`.

## Status

- **Phase 1 (signal monitor): complete** — BeautifulSoup-based sweep of configured
  public sources (RSS + HTML listings), keyword event taxonomy, corridor matching,
  dedupe, dead-source tolerance. Source list in `src/reia/config.py` is a starting
  point — expect to tune CSS selectors after the first live run (government sites
  change markup without notice; failures are logged, never fatal).
- **Phase 2 (corridor scoring): complete** — the knowledge-01 template
  (jobs 30 / connectivity 25 / policy 15 / supply 10 / stage 20) with event-momentum
  tracking and stage-transition flags. Component inputs (0–1) are analyst-maintained
  via `set-corridor` — the honest design: committed-jobs and funded-connectivity
  judgments need a human reading the documents; the system stores, scores, ranks,
  and nags.
- **Phase 3 (parcel evaluation + legal engine): complete** — 21-item checklist
  (title chain, prohibited categories, litigation, possession, RERA), severity
  model (VETO / RESOLVE_FIRST / MONITOR), verdicts where *silence is never
  clearance* (unchecked veto items block), lawyer question-list generation, and
  return-case benchmarking vs index equity after holding costs and exit friction.
- **Phase 4 (AI layer): complete** — Claude event enrichment (severity, stage
  signal) and narrative parcel reports with the knowledge docs as doctrine
  (needs `ANTHROPIC_API_KEY`).
- **Digest**: weekly one-shot output of corridor ranking + notable signals +
  tracked parcels.
- 8 offline tests passing. Live sweeps need normal internet access.

## Usage

```bash
cd real-estate-advisor && pip install -r requirements.txt && cd src
python -m reia.cli init-db
python -m reia.cli sweep                 # fetch + classify all public sources
python -m reia.cli events --corridor hyd-rrr-north
python -m reia.cli set-corridor hyd-rrr-north --jobs 0.5 --conn 0.8 --policy 0.7 --supply 0.4 --stage B
python -m reia.cli corridors             # ranked scores
python -m reia.cli checklist > parcel.json   # blank legal checklist to fill
python -m reia.cli evaluate --file parcel.json
python -m reia.cli digest
```

Weekly cron: `0 8 * * 6 cd .../src && python -m reia.cli sweep && python -m reia.cli digest`

## The two hard rules (enforced in code)

1. **Public information only** — the monitor reads gazettes, releases, and tenders;
   nothing else is representable.
2. **The legal engine assists, never clears** — the best verdict is
   `CLEAR_PENDING_LAWYER`, every report carries the disclaimer, and unchecked
   veto-class items hold the parcel at `RESOLVE_FIRST`.
