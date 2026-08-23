#!/usr/bin/env bash
# Bring the 360° Stock Advisor live. Safe to re-run: every step is idempotent.
#   bash run_live.sh --backfill   # first run: pulls 10 years of history
#   bash run_live.sh              # daily: recent prices only
#
# A step that fails does not abort the rest — a source can be down without the
# whole run being pointless. Failures are collected and reported at the end.
set -uo pipefail
cd "$(dirname "$0")"

FAILED=()
step() {                       # step "label" cmd...
  local label="$1"; shift
  echo "== $label =="
  if "$@"; then return 0; fi
  echo "   ^ '$label' did not complete."
  FAILED+=("$label")
  return 1
}

echo "== installing dependencies =="
pip install -q -r requirements.txt || echo "   (dependency install had problems; continuing)"

cd src
step "initialise database"      python -m advisor.cli init-db
step "sync Nifty 500 universe"  python -m advisor.cli update-universe

if [ "${1:-}" = "--backfill" ]; then
  step "backfill 10y price history (one-time, ~15 min)" \
       python -m advisor.cli update-prices --backfill
else
  step "update recent prices"   python -m advisor.cli update-prices
fi

step "official bhavcopy cross-check" python -m advisor.cli ingest-bhavcopy
step "fundamentals snapshot"         python -m advisor.cli fetch-fundamentals

echo "== status =="
python -m advisor.cli status || true

if [ ${#FAILED[@]} -eq 0 ]; then
  echo
  echo "== today's digest =="
  python -m advisor.cli digest || true
  cat <<'EOF'

Live. Next steps:
  streamlit run ../src/dashboard.py                  # web dashboard
  python -m advisor.cli screen --book investing      # ranked candidates
  python -m advisor.cli plan new --amount 1000000    # a full portfolio proposal
  python -m advisor.cli risk                         # VaR, stress, correlation
  export ANTHROPIC_API_KEY=... && python -m advisor.cli report RELIANCE
  export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... && python -m advisor.cli notify

Nightly cron (18:30 IST weekdays), from this directory:
  30 18 * * 1-5 cd $(pwd) && python -m advisor.cli update-prices && python -m advisor.cli ingest-bhavcopy && python -m advisor.cli notify
EOF
else
  echo
  echo "Finished with ${#FAILED[@]} step(s) incomplete:"
  for f in "${FAILED[@]}"; do echo "  - $f"; done
  cat <<'EOF'

Whatever succeeded IS stored — nothing was guessed to fill the gaps, so the
database holds only real data and re-running fills in the rest.

Most common cause: a data source refusing the connection (403) because of a
VPN, a corporate proxy, or throttling of your IP. Try again on a normal home
connection, or wait and re-run this script.
EOF
  exit 1
fi
