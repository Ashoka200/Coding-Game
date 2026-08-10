"""Streamlit dashboard — run with: streamlit run src/dashboard.py

Four tabs: Regime · Screener · Portfolio · Stock (chart + engine payload + AI report).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st

from advisor import db, technical
from advisor.fundamentals import fundamental_score, latest_fundamentals
from advisor.portfolio import snapshot
from advisor.regime import compute_regime, last_state
from advisor.screener import _load_symbol_df, run_screen

st.set_page_config(page_title="360° Advisor", layout="wide")
st.title("360° Stock Investor Advisory")

tab_regime, tab_screen, tab_pf, tab_stock = st.tabs(
    ["Regime", "Screener", "Portfolio", "Stock"])

with tab_regime:
    r = compute_regime(prev_state=last_state())
    if r is None:
        st.warning("Insufficient data — run the backfill first.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("State", r.state)
        c2.metric("Breadth >200SMA", f"{r.breadth_200:.0%}")
        c3.metric("Drawdown", f"{r.index_drawdown:.1%}")
        if r.signals:
            st.write("Signals:", ", ".join(r.signals))
        if not r.risk_on():
            st.error("Risk-off playbook active: no new trading longs (module 10).")

with tab_screen:
    book = st.radio("Book", ["trading", "investing"], horizontal=True)
    capital = st.number_input("Capital (₹)", value=1_000_000, step=100_000)
    if st.button("Run screen"):
        res = run_screen(book=book, capital=capital)
        st.dataframe(res["candidates"], use_container_width=True)
        for p in res["plans"]:
            st.write(p.to_dict())

with tab_pf:
    snap = snapshot()
    st.metric("Total value", f"₹{snap['total_value']:,.0f}")
    st.metric("Open heat", f"{snap['heat_pct']:.1%}")
    for a in snap["alerts"]:
        st.error(a)
    if not snap["positions"].empty:
        st.dataframe(snap["positions"], use_container_width=True)
    if snap["sector_weights"]:
        st.bar_chart(pd.Series(snap["sector_weights"]))

with tab_stock:
    sym = st.text_input("NSE symbol", "RELIANCE").strip().upper()
    if sym:
        with db.connect() as conn:
            df = _load_symbol_df(conn, sym)
        if df.empty:
            st.warning("No data for this symbol.")
        else:
            st.line_chart(df["close"])
            f = technical.compute_features(df)
            if f:
                fund = latest_fundamentals(sym)
                fscore, flags = fundamental_score(fund)
                c1, c2, c3 = st.columns(3)
                c1.metric("Technical score", technical.technical_score(f))
                c2.metric("Fundamental score", fscore)
                c3.metric("Stage", technical.stage(f))
                st.write("Setups:", technical.detect_setups(f, fscore) or "none")
                st.write("Flags:", flags)
            if st.button("Generate AI 360° report"):
                from advisor.ai_report import generate_report
                try:
                    st.markdown(generate_report(sym))
                except RuntimeError as e:
                    st.error(str(e))
