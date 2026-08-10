# 360° Stock Investor Advisory

AI-assisted decision-support for Indian equities. See `BUILD-PLAN.md` (architecture,
phases), `EXTENDED-ROADMAP.md` (ML/intraday/multi-user phases), and `knowledge/`
(the CFA/quant methodology the system enforces).

## Status

- **Phase 1 (data foundation): code complete** — universe, EOD prices (yfinance +
  official NSE bhavcopy cross-check), point-in-time fundamentals schema, decision
  journal with calibration reporting. Offline logic covered by `tests/`.
- Live NSE/Yahoo fetches require normal internet access (blocked in some sandboxes);
  run the commands below on your own machine.

## Getting started

```bash
cd stock-advisor
pip install -r requirements.txt

cd src
python -m advisor.cli init-db            # create ~/.advisor-data/advisor.db
python -m advisor.cli update-universe    # pull current Nifty 500 constituents
python -m advisor.cli update-prices --backfill   # 10y EOD history (first run, ~15 min)
python -m advisor.cli ingest-bhavcopy    # official NSE EOD for today (cross-check source)
python -m advisor.cli status             # sanity check
```

Nightly cron (after bhavcopy publishes, ~18:30 IST):

```cron
30 18 * * 1-5 cd /path/to/stock-advisor/src && python -m advisor.cli update-prices && python -m advisor.cli ingest-bhavcopy
```

Tests: `python -m pytest tests/ -q` (no network needed).

## Design decisions worth knowing

- **Survivorship-free by construction:** stocks leaving the index are marked
  inactive, never deleted — backtests see the graveyard.
- **Point-in-time fundamentals:** every value stored with the date it became known,
  so future backtests can't peek at restated numbers.
- **Two price sources:** yfinance (adjusted, convenient) cross-checked against the
  exchange's official bhavcopy; `cross_check()` flags divergences.
- **Journal-first:** `advisor.journal` exists from day one — every suggestion the
  system ever makes is logged before outcomes are known, and
  `calibration_report()` turns history into evidence for tuning conviction weights.
