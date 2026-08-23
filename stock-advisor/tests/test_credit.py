"""Credit and solvency: the formulas must be right, they must refuse to run
where they do not belong, and partial data must never produce a score."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from advisor.credit import (  # noqa: E402
    altman_z, assess, beneish_m, covenant_headroom, financial_sector_lens,
    maturity_wall, piotroski_f,
)

HEALTHY = {
    "working_capital": 300, "total_assets": 1000, "retained_earnings": 400,
    "ebit": 150, "market_cap": 2000, "total_liabilities": 400, "sales": 1200,
    "book_equity": 600,
}
STRESSED = {
    "working_capital": -80, "total_assets": 1000, "retained_earnings": -150,
    "ebit": 10, "market_cap": 120, "total_liabilities": 900, "sales": 400,
    "book_equity": 100,
}


# ---------- Altman ----------

def test_altman_separates_healthy_from_distressed():
    good = altman_z(HEALTHY)
    bad = altman_z(STRESSED)
    assert good.band == "safe" and good.value > 2.99
    assert bad.band == "distress" and bad.value < 1.81
    assert set(good.components) == {"x1_working_capital", "x2_retained_earnings",
                                    "x3_ebit", "x4_equity_to_liabilities",
                                    "x5_asset_turnover"}


def test_altman_refuses_to_run_on_a_bank():
    s = altman_z(HEALTHY, sector="Banks")
    assert s.applicable is False and s.value is None
    assert "leverage is their business model" in s.note


def test_altman_partial_data_returns_no_score():
    s = altman_z({k: v for k, v in HEALTHY.items() if k != "sales"})
    assert s.value is None and "sales" in s.missing
    assert "partial Z-score is not a Z-score" in s.note


def test_altman_double_prime_variant_for_non_manufacturers():
    s = altman_z(HEALTHY, manufacturer=False)
    assert s.name == "altman_z_double_prime"
    assert s.band in ("safe", "grey", "distress")
    assert "x5_asset_turnover" not in s.components      # no turnover term in Z''


# ---------- Beneish ----------

BEN_PREV = {"receivables": 100, "sales": 1000, "cogs": 700, "current_assets": 400,
            "ppe": 300, "securities": 50, "total_assets": 1000, "depreciation": 30,
            "sga": 100, "net_income": 80, "cfo": 90, "current_liabilities": 200,
            "long_term_debt": 200}


def test_beneish_flags_receivables_running_ahead_of_sales():
    manipulator = dict(BEN_PREV, receivables=260, sales=1150, net_income=140, cfo=20)
    s = beneish_m(manipulator, BEN_PREV)
    assert s.value is not None
    assert s.components["DSRI"] > 1.5           # receivables ballooning vs sales
    assert s.components["TATA"] > 0             # profit not arriving as cash
    assert s.band == "flagged"
    assert "screen, not a verdict" in s.note


def test_beneish_clean_company_is_not_flagged():
    steady = dict(BEN_PREV, sales=1050, receivables=104, net_income=84, cfo=95)
    s = beneish_m(steady, BEN_PREV)
    assert s.band == "clean" and s.value < -1.78


def test_beneish_needs_both_years_complete():
    s = beneish_m({k: v for k, v in BEN_PREV.items() if k != "sga"}, BEN_PREV)
    assert s.value is None and "sga" in s.missing
    assert "partial M-score is not an M-score" in s.note


# ---------- Piotroski ----------

def test_piotroski_scores_improvement_and_reports_coverage():
    prev = {"net_income": 50, "total_assets": 1000, "cfo": 60, "long_term_debt": 300,
            "current_assets": 400, "current_liabilities": 250, "shares_outstanding": 100,
            "sales": 900, "cogs": 650}
    cur = {"net_income": 90, "total_assets": 1050, "cfo": 130, "long_term_debt": 250,
           "current_assets": 460, "current_liabilities": 240, "shares_outstanding": 100,
           "sales": 1050, "cogs": 730}
    s = piotroski_f(cur, prev)
    assert s.value >= 7 and s.band == "strong"
    assert s.components["accruals_healthy"] is True
    assert s.components["leverage_falling"] is True
    assert "9 of 9" not in (s.note or "") or s.value <= 9


def test_piotroski_says_when_tests_could_not_be_computed():
    prev = {"net_income": 50, "total_assets": 1000}
    cur = {"net_income": 90, "total_assets": 1050}
    s = piotroski_f(cur, prev)
    assert s.value is not None                     # works with what exists
    assert "could not be computed" in s.note       # and admits the rest
    assert len(s.components) < 9


# ---------- debt profile ----------

def test_maturity_wall_bands_and_shortfall_language():
    comfy = maturity_wall(debt_due_12m=100, cash=150, cfo=120)
    assert comfy["band"] == "comfortable" and comfy["coverage"] == pytest.approx(2.7)

    short = maturity_wall(debt_due_12m=500, cash=100, cfo=150)
    assert short["band"] == "shortfall"
    assert "available right up until it isn't" in short["note"]

    unknown = maturity_wall(None, 100, 100)
    assert unknown["known"] is False
    assert "notes to accounts" in unknown["note"]


def test_covenant_headroom_measures_the_fall_before_breach():
    h = covenant_headroom(net_debt=200, ebitda=100, interest=25)
    lev = h["measures"]["net_debt_to_ebitda"]
    assert lev["value"] == pytest.approx(2.0) and lev["breached"] is False
    # leverage limit 3.0: EBITDA may fall to 200/3 = 66.7, i.e. about 33%
    assert lev["ebitda_fall_before_breach"] == pytest.approx(0.333, abs=0.002)
    cov = h["measures"]["interest_cover"]
    assert cov["value"] == pytest.approx(4.0)
    # cover limit 2.0: EBITDA may fall to 50, i.e. 50%
    assert cov["ebitda_fall_before_breach"] == pytest.approx(0.50)
    assert h["tightest_headroom"] == pytest.approx(0.333, abs=0.002)


def test_covenant_breach_is_called_out():
    h = covenant_headroom(net_debt=500, ebitda=100, interest=80)
    assert h["measures"]["net_debt_to_ebitda"]["breached"] is True
    assert "already breached" in h["note"]

    none = covenant_headroom(net_debt=100, ebitda=None, interest=10)
    assert "cannot be measured" in none["note"]


def test_thin_headroom_is_named_as_a_solvency_risk():
    h = covenant_headroom(net_debt=280, ebitda=100, interest=40)
    assert h["tightest_headroom"] < 0.20
    assert "ordinary bad year becomes a solvency event" in h["note"]


# ---------- financial sector ----------

def test_bank_lens_uses_bank_metrics():
    weak = financial_sector_lens({"capital_adequacy_ratio": 0.09, "gross_npa_ratio": 0.08,
                                  "net_npa_ratio": 0.035, "provision_coverage_ratio": 0.55})
    assert set(weak["flags"]) == {"capital_adequacy_ratio_weak", "gross_npa_ratio_weak",
                                  "net_npa_ratio_weak", "provision_coverage_ratio_weak"}
    strong = financial_sector_lens({"capital_adequacy_ratio": 0.17, "gross_npa_ratio": 0.02,
                                    "net_npa_ratio": 0.005, "provision_coverage_ratio": 0.80})
    assert strong["flags"] == []
    missing = financial_sector_lens({})
    assert "cannot be judged without them" in missing["note"]


# ---------- synthesis ----------

def test_assess_on_a_stressed_corporate_raises_serious_risk():
    cur = dict(STRESSED, debt_due_12m=400, cash=50, cfo=30, net_debt=800,
               ebitda=60, interest=55)
    read = assess("X", cur, sector="Metals")
    assert "altman_distress" in read.flags
    assert "maturity_wall_shortfall" in read.flags
    assert read.verdict.startswith("serious credit risk")
    assert any("permanently" in read.verdict for _ in [1])


def test_assess_on_a_bank_switches_lens_entirely():
    read = assess("HDFCBANK", {"capital_adequacy_ratio": 0.18, "gross_npa_ratio": 0.013,
                               "net_npa_ratio": 0.004, "provision_coverage_ratio": 0.75},
                  sector="Banks")
    assert read.sector_kind == "financial"
    assert any("leverage is the business model" in f for f in read.findings)
    z = next(s for s in read.scores if s.name == "altman_z")
    assert z.applicable is False


def test_assess_names_what_it_could_not_check():
    read = assess("X", dict(HEALTHY, ebitda=150, interest=20, net_debt=100))
    assert "prior-year statements (needed for Beneish and Piotroski)" in read.unknowns
    assert "debt maturing within a year" in read.unknowns
