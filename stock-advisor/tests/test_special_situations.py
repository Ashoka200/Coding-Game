"""Special situations: the arithmetic must be right, the Indian tax treatment
must be applied, and an unknown acceptance ratio must refuse to produce a return."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from advisor.special_situations import (  # noqa: E402
    buyback_tender, delisting, demerger, merger_arb, open_offer,
    retail_acceptance_advantage, rights_issue,
)


# ---------- buyback ----------

def test_buyback_without_acceptance_ratio_refuses_to_invent_a_return():
    s = buyback_tender("X", market_price=100, buyback_price=120)
    assert s.gross_return is None and s.net_return is None
    assert any(u["field"] == "acceptance_ratio" for u in s.unknowns)
    assert any("not the same thing" in r for r in s.risks)


def test_buyback_blends_accepted_and_stub_correctly():
    s = buyback_tender("X", market_price=100, buyback_price=120,
                       acceptance_ratio=0.5, expected_price_after=95,
                       post_oct_2024_tax=False)
    # 50% at 120 + 50% at 95 = 107.5 on a 100 cost
    assert s.gross_return == pytest.approx(0.075)
    assert s.net_return == pytest.approx(0.075)      # pre-2024 regime: no shareholder tax
    assert s.maths["blended_proceeds_per_share"] == pytest.approx(107.5)


def test_post_2024_tax_materially_reduces_the_return():
    kw = dict(symbol="X", market_price=100, buyback_price=120,
              acceptance_ratio=0.5, expected_price_after=95)
    old = buyback_tender(**kw, post_oct_2024_tax=False)
    new = buyback_tender(**kw, post_oct_2024_tax=True, slab_rate=0.30)
    assert new.net_return < old.net_return           # the 2024 change bites
    assert any("deemed dividend" in r or "dividend at your slab" in r for r in new.risks)
    # proceeds 60 taxed at 30% = 18 tax; loss shield 50*0.20 = 10; stub 47.5
    # net = 60 - 18 + 10 + 47.5 = 99.5 on 100 → -0.5%
    assert new.net_return == pytest.approx(-0.005, abs=1e-6)
    assert new.verdict.startswith("negative after tax")


def test_low_acceptance_is_called_what_it_is():
    s = buyback_tender("X", market_price=100, buyback_price=140,
                       acceptance_ratio=0.10, expected_price_after=96)
    assert any("arbitrage costume" in r for r in s.risks)


def test_retail_reservation_advantage():
    known = retail_acceptance_advantage(buyback_size_value=1_000_000_000,
                                        retail_tendered_value=120_000_000)
    assert known["acceptance_ratio"] == pytest.approx(1.0)     # reserved 150m > tendered 120m
    assert "retail edge" in known["note"]
    over = retail_acceptance_advantage(1_000_000_000, 600_000_000)
    assert over["acceptance_ratio"] == pytest.approx(0.25)
    unknown = retail_acceptance_advantage(1_000_000_000, None)
    assert unknown["acceptance_ratio"] is None


# ---------- open offer ----------

def test_open_offer_probability_weights_the_break_risk():
    s = open_offer("X", market_price=100, offer_price=115,
                   shares_sought_fraction=0.6, days_to_close=60,
                   deal_probability=0.9)
    assert s.gross_return > 0
    assert s.annualised > s.gross_return          # 60 days annualises up
    assert s.maths["probability_weighted_return"] < s.gross_return
    assert any("lapses" in r for r in s.risks)

    risky = open_offer("X", 100, 115, shares_sought_fraction=0.6,
                       days_to_close=60, deal_probability=0.4)
    assert risky.maths["probability_weighted_return"] < \
        s.maths["probability_weighted_return"]


# ---------- rights ----------

def test_rights_issue_terp_and_right_value():
    # 1-for-5 at 80 with market at 200: TERP = (5*200 + 1*80)/6 = 180
    s = rights_issue("X", cum_price=200, rights_price=80, ratio_new=1, ratio_held=5)
    assert s.maths["theoretical_ex_rights_price"] == pytest.approx(180.0)
    assert s.maths["value_of_one_right"] == pytest.approx(20.0)
    assert s.maths["dilution"] == pytest.approx(1 / 6, abs=1e-4)
    assert any("arithmetic, not a loss" in r for r in s.risks)
    assert any("Ignoring your entitlement IS a loss" in r for r in s.risks)


def test_rights_priced_above_market_is_worthless():
    s = rights_issue("X", cum_price=100, rights_price=110, ratio_new=1, ratio_held=4)
    assert s.maths["value_of_one_right"] == 0
    assert any("worthless" in r for r in s.risks)


# ---------- merger ----------

def test_merger_arb_spread_and_break_risk():
    # 1 target share gets 2 acquirer shares worth 60 each = 120 vs target at 100
    s = merger_arb("X", target_price=100, acquirer_price=60,
                   swap_ratio_target=1, swap_ratio_acquirer=2,
                   days_to_close=90, deal_probability=0.85)
    assert s.maths["implied_value_per_target_share"] == pytest.approx(120.0)
    assert s.gross_return == pytest.approx(0.20)
    assert s.maths["probability_weighted_return"] == pytest.approx(0.85 * 0.20 + 0.15 * -0.15)
    assert any("shorting the acquirer" in r for r in s.risks)


# ---------- delisting ----------

def test_delisting_refuses_to_predict_the_discovered_price():
    s = delisting("X", market_price=100, floor_price=110)
    assert s.gross_return is None
    assert any(u["field"] == "discovered_price" for u in s.unknowns)
    assert "lottery ticket" in s.verdict
    assert any("failed delisting" in r for r in s.risks)

    priced = delisting("X", 100, 110, indicative_price=150)
    assert priced.gross_return == pytest.approx(0.50)


# ---------- demerger ----------

def test_demerger_values_only_the_parts_it_can_and_names_the_rest():
    s = demerger("X", price_before=100, parts=[
        {"name": "retail", "value_per_share": 70},
        {"name": "telecom", "value_per_share": 55},
        {"name": "new energy", "value_per_share": None}])
    assert s.maths["sum_of_parts"] == pytest.approx(125)
    assert s.gross_return == pytest.approx(0.25)
    assert s.maths["unvalued_parts"] == ["new energy"]
    assert any("holding-company discount" in r for r in s.risks)

    empty = demerger("X", 100, [{"name": "a", "value_per_share": None}])
    assert empty.gross_return is None
    assert any(u["field"] == "part_values" for u in empty.unknowns)


def test_annualisation_makes_short_and_long_windows_comparable():
    quick = open_offer("X", 100, 104, shares_sought_fraction=1.0, days_to_close=30)
    slow = open_offer("X", 100, 104, shares_sought_fraction=1.0, days_to_close=300)
    assert quick.gross_return == pytest.approx(slow.gross_return)
    assert quick.annualised > slow.annualised     # same edge, much better if it is quick
