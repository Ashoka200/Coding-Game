"""Ownership and flow intelligence: the read must follow the numbers, and
absent data must produce gaps rather than a confident story."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from advisor.ownership import analyse, digest_deals, pledge_read  # noqa: E402

QUARTERS = ["Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"]


def sh(prom, fii, dii, pub):
    return {"Promoters": prom, "FIIs": fii, "DIIs": dii, "Public": pub}


def test_promoter_selling_is_caught_and_graded():
    read = analyse("X", sh([62, 60, 57, 54, 52], [12, 12, 12, 12, 12],
                           [10, 10, 10, 10, 10], [16, 18, 21, 24, 26]), QUARTERS)
    assert any(f.startswith("promoter_selling:high") for f in read.flags)
    assert any("cut their stake" in f for f in read.findings)
    assert read.smart_money_score < 40           # heavy insider selling drags it down

    mild = analyse("Y", sh([62, 62, 61.5, 61, 60.5], [12] * 5, [10] * 5, [16] * 5), QUARTERS)
    assert any(f == "promoter_selling:medium" for f in mild.flags)


def test_promoter_buying_reads_as_the_honest_signal():
    read = analyse("X", sh([50, 52, 54, 55, 56], [12] * 5, [10] * 5, [28, 26, 24, 23, 22]),
                   QUARTERS)
    assert not any("promoter_selling" in f for f in read.flags)
    assert any("most honest signal" in f for f in read.findings)
    assert read.smart_money_score > 60


def test_distribution_to_retail_is_the_headline_finding():
    # institutions out, public in — stock moving to uninformed hands
    read = analyse("X", sh([50] * 5, [15, 14, 12, 11, 10], [12, 11, 10, 9, 8],
                           [23, 25, 28, 30, 32]), QUARTERS)
    assert read.flow == "distribution"
    assert "distribution_to_retail" in read.flags
    assert any("informed hands to uninformed" in f for f in read.findings)


def test_accumulation_is_the_mirror_image():
    read = analyse("X", sh([50] * 5, [10, 11, 13, 14, 15], [8, 9, 10, 11, 12],
                           [32, 30, 27, 25, 23]), QUARTERS)
    assert read.flow == "accumulation"
    assert read.smart_money_score > 55


def test_fii_out_dii_in_is_named_as_a_transfer_not_an_endorsement():
    read = analyse("X", sh([50] * 5, [20, 18, 16, 15, 14], [10, 12, 14, 15, 16],
                           [20] * 5), QUARTERS)
    assert any("transfer of opinion" in f for f in read.findings)


def test_low_promoter_holding_is_flagged():
    read = analyse("X", sh([24] * 5, [20] * 5, [20] * 5, [36] * 5), QUARTERS)
    assert "low_promoter_holding" in read.flags
    assert any("control is comfortable" in f for f in read.findings)


def test_stable_ownership_says_so_plainly():
    read = analyse("X", sh([50] * 5, [15] * 5, [12] * 5, [23] * 5), QUARTERS)
    assert read.flow == "stable"
    assert read.flags == []
    assert 45 <= read.smart_money_score <= 55
    assert any("broadly unchanged" in f for f in read.findings)


def test_missing_data_produces_a_gap_not_a_story():
    read = analyse("X", None)
    assert read.flow == "unknown"
    assert read.smart_money_score is None
    assert "shareholding pattern" in read.unknowns
    assert any("nothing can be said" in f for f in read.findings)

    partial = analyse("X", {"Promoters": [50, 51, 52]})
    assert partial.smart_money_score is not None      # works with what exists
    assert "FIIs" in partial.unknowns                 # and names what is missing


def test_pledge_severity_and_direction():
    assert pledge_read(None)["known"] is False
    assert "pledge" in pledge_read(None)["note"].lower()

    clean = pledge_read(0)
    assert clean["flags"] == [] and "No promoter shares pledged" in clean["note"]

    extreme = pledge_read(65)
    assert "pledge_extreme" in extreme["flags"]
    assert "force lenders to sell" in extreme["note"]

    rising = pledge_read(30, previous_percent=20)
    assert "pledge_high" in rising["flags"] and "pledge_rising" in rising["flags"]
    assert "matters more than the level" in rising["note"]


def test_bulk_deals_summarise_direction_and_repeat_buyers():
    deals = [
        {"date": "2026-08-01", "client": "Alpha Fund", "type": "BUY", "quantity": 100000},
        {"date": "2026-08-09", "client": "Alpha Fund", "type": "BUY", "quantity": 150000},
        {"date": "2026-08-12", "client": "Beta LLP", "type": "SELL", "quantity": 50000},
    ]
    d = digest_deals(deals)
    assert d["count"] == 3 and d["buy_count"] == 2
    assert d["net_quantity"] == 200000 and d["direction"] == "net buying"
    assert d["repeat_participants"] == ["Alpha Fund"]
    assert "returning is more informative" in d["note"]

    assert digest_deals([])["count"] == 0
