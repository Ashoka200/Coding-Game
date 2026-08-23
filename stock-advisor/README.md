# 360° Stock Investor Advisory

AI-assisted decision-support for Indian equities. See `BUILD-PLAN.md` (architecture,
phases), `EXTENDED-ROADMAP.md` (ML/intraday/multi-user phases), and `knowledge/`
(the CFA/quant methodology the system enforces).

## Status

- **Phase 1 (data foundation): complete** — universe, EOD prices (yfinance +
  official NSE bhavcopy cross-check), point-in-time fundamentals, decision journal.
- **Phase 2 (engines): complete** — indicators, technical engine (stage analysis,
  4 setups, technical score), fundamental scorer (quality/growth/valuation/
  governance with veto flags), relative-strength ranking.
- **Phase 3 (levels + AI + dashboard): complete** — entry/stop/target/size
  calculator, Claude 360° report layer (knowledge modules as system prompt),
  Streamlit dashboard (`streamlit run src/dashboard.py`).
- **Phase 4 (backtest + portfolio + alerts): complete** — costed breakout
  backtester, portfolio tracker (heat, stops, sector caps), daily digest.
- **Phase 5 (paper trading): infrastructure ready** — journal every screen
  suggestion (`advisor.journal`), review `calibration_report()` quarterly. The
  2-3 month paper period itself is calendar time, not code.
- **Phase 6 (F&O): analytics complete** — Black-Scholes Greeks, implied vol, IVP,
  defined-risk strategy selector (banned structures unrepresentable). Live option
  -chain ingestion needs a broker API (next).
- **Phase 7 (execution)**: deliberately manual — the system outputs exact order
  plans; you place them. Broker-API automation only after the paper period.
- **Pro stack** (see `WALL-STREET-STACK.md`): multi-factor sector-neutral ranking
  with turnover hysteresis (`factors.py`), portfolio risk platform — shrinkage
  covariance, VaR/CVaR, crisis stress replay, diversification diagnostics
  (`risk.py`), walk-forward strategy validation (`walkforward.py`), Telegram
  push alerts (`notify.py`). One-command bootstrap: `bash run_live.sh --backfill`.
- All engine logic covered by offline tests (`python -m pytest tests/ -q`, 27 tests).
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

Daily use once data is loaded:

```bash
python -m advisor.cli regime                 # market regime state + signals
python -m advisor.cli screen --book trading  # ranked setups with trade plans
python -m advisor.cli screen --book investing
python -m advisor.cli backtest               # evidence: breakout stats, after costs
python -m advisor.cli fetch-fundamentals     # refresh fundamental snapshots (weekly)
python -m advisor.cli digest                 # the whole daily brief in one output
python -m advisor.cli report RELIANCE        # AI 360° report (ANTHROPIC_API_KEY)
python -m advisor.cli portfolio add --symbol RELIANCE --book investing --qty 10 --cost 2900 --stop 2600
streamlit run src/dashboard.py               # web dashboard
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
