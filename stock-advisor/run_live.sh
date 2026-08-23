#!/usr/bin/env bash
# Bring the 360° Stock Advisor live in one command (run from stock-advisor/).
# Safe to re-run: every step is idempotent.
set -euo pipefail
cd "$(dirname "$0")"

echo "== installing dependencies =="
pip install -q -r requirements.txt

cd src
echo "== initializing database =="
python -m advisor.cli init-db

echo "== syncing Nifty 500 universe =="
python -m advisor.cli update-universe

if [ "${1:-}" = "--backfill" ]; then
  echo "== backfilling 10y price history (one-time, ~15 min) =="
  python -m advisor.cli update-prices --backfill
else
  echo "== updating recent prices (pass --backfill on first run) =="
  python -m advisor.cli update-prices
fi

echo "== official bhavcopy cross-check =="
python -m advisor.cli ingest-bhavcopy || true   # holiday-safe

echo "== fundamentals snapshot =="
python -m advisor.cli fetch-fundamentals

echo "== status =="
python -m advisor.cli status

echo "== today's digest =="
python -m advisor.cli digest

cat <<'EOF'

Live. Next steps:
  streamlit run src/dashboard.py                     # web dashboard
  python -m advisor.cli risk                         # portfolio VaR/stress (after adding holdings)
  python -m advisor.cli walkforward                  # validate the strategy on YOUR data
  export ANTHROPIC_API_KEY=... && python -m advisor.cli report RELIANCE
  export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... # then: python -m advisor.cli notify

Nightly cron (18:30 IST weekdays):
  30 18 * * 1-5 cd $(pwd) && python -m advisor.cli update-prices && python -m advisor.cli ingest-bhavcopy && python -m advisor.cli notify
EOF
