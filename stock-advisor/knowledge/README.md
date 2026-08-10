# Knowledge Layer — the "50-year veteran" brain

This directory is the advisor's institutional knowledge base: CFA-curriculum and quant
portfolio-management methodology distilled into modules the system actually uses.

## How this makes the bot "experienced"

An LLM cannot be sent to study — but Claude is already trained on the CFA body of
knowledge, the quant finance literature, and decades of practitioner writing. Raw
knowledge is not the bottleneck; **discipline and consistency are**. A veteran differs
from a student not in what they know but in which techniques they reach for, in what
order, and what they refuse to do. These modules encode exactly that.

They are used two ways:

1. **System prompt for the AI synthesis layer.** When Claude writes a 360° report, the
   relevant modules are loaded as its operating doctrine — it must analyze *this way*,
   cite *these metrics*, respect *these risk rules*.
2. **Specification for the deterministic engines.** Every formula here (DCF, Piotroski,
   VaR, Kelly, ATR sizing, Greeks) is implemented in Python. The LLM never computes —
   it interprets computed numbers through this doctrine.

## Modules

| File | Covers | CFA level equivalent |
|---|---|---|
| `01-philosophy-and-process.md` | Investment policy, process discipline, the veteran's rules | L3 portfolio mgmt |
| `02-fundamental-valuation.md` | DCF, DDM, residual income, relative valuation, earnings quality | L2 equity |
| `03-portfolio-construction.md` | MPT, factor models, Black-Litterman intuition, rebalancing | L3 |
| `04-risk-management.md` | Position sizing, Kelly, VaR, drawdown control, correlation | L2/L3 + quant practice |
| `05-technical-and-trend.md` | Trend, momentum, mean reversion, volume, market structure | CMT-style practice |
| `06-quant-factors.md` | Value/momentum/quality/low-vol factors, Fama-French, factor timing | Quant PM practice |
| `07-derivatives-fno.md` | Options pricing intuition, Greeks, defined-risk strategies, hedging | L2 derivatives |
| `08-behavioral-finance.md` | Biases the system must counteract — in the market and in the user | L3 behavioral |
| `09-india-market-context.md` | NSE/BSE microstructure, SEBI rules, taxation, India-specific factors | Local practice |

## Rules for extending this layer

- Only add material that changes a decision the system makes.
- Every quantitative claim must be implementable and backtestable.
- When modules conflict (e.g. momentum says buy, valuation says avoid), module 01's
  conflict-resolution rules decide — never silently pick one.
