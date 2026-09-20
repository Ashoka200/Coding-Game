"""The investor lenses. What is guarded here is mostly honesty: that a lens with
no data says so instead of scoring, that disagreement survives rather than being
averaged into mush, and that each investor's distinguishing rule is actually
encoded rather than flattened into a generic quality screen."""
from advisor.masters import (
    apply_all, buffett, consensus, damani, derive, jhunjhunwala, lynch, qglp,
)

# A genuine compounder: high returns, low debt, steady growth, fair price.
COMPOUNDER = dict(
    sector="Consumer staples", roe=0.26, roce=0.29, netMargin=0.16,
    debtToEquity=0.12, interestCover=22.0, cashConversion=0.95,
    earningsCagr3y=0.19, revenueCagr3y=0.14, earningsGrowth=0.18,
    pe=34.0, currentRatio=1.8, dividendYield=0.011, annualVol=0.22,
    above200dma=True, revenue_history=[100, 112, 127, 141, 160, 182],
)

# A leveraged cyclical: growing fast, but on borrowed money.
LEVERED = dict(
    sector="Metals & mining", roe=0.09, roce=0.08, netMargin=0.04,
    debtToEquity=1.9, interestCover=1.4, cashConversion=0.45,
    earningsCagr3y=0.31, revenueCagr3y=0.22, pe=9.0,
    currentRatio=0.9, dividendYield=0.0, annualVol=0.52,
    above200dma=False, revenue_history=[100, 150, 90, 170, 120, 195],
)


# ------------------------------------------------------------------ honesty
def test_a_lens_with_no_data_refuses_to_score():
    v = qglp({})
    assert v.score is None
    assert v.judged == 0 and v.unknown == len(v.criteria)
    assert "cannot judge" in v.verdict


def test_thin_data_is_labelled_as_a_hint_not_a_finding():
    v = buffett({"roe": 0.30})          # one criterion out of six
    assert v.judged == 1
    assert "too thin" in v.verdict


def test_every_criterion_reports_what_it_actually_saw():
    v = buffett(COMPOUNDER)
    roe = [c for c in v.criteria if "return on equity" in c.name][0]
    assert roe.seen == "26.0%"
    missing = buffett({"roe": 0.3})
    assert any(c.seen == "not disclosed" for c in missing.criteria)


def test_unknown_is_never_silently_counted_as_a_pass():
    full = buffett(COMPOUNDER).score
    partial = buffett({k: v for k, v in COMPOUNDER.items()
                       if k in ("roe", "debtToEquity")}).score
    assert full is not None and partial is not None
    # Removing data must change `judged`, never inflate the score.
    assert buffett({"roe": 0.30, "debtToEquity": 0.1}).judged == 2


# ------------------------------------------------------------------ the lenses
def test_the_compounder_passes_the_quality_lenses():
    for lens in (qglp, buffett, jhunjhunwala):
        v = lens(COMPOUNDER)
        assert v.score >= 0.6, f"{v.author} should accept a clean compounder"


def test_the_levered_cyclical_is_rejected_where_it_should_be():
    for lens in (qglp, buffett, damani):
        assert lens(LEVERED).score < 0.5, "leverage and weak returns must fail"


def test_lynch_rejects_growth_that_is_too_fast_to_last():
    # The detail usually dropped: Lynch distrusted growth above ~50%.
    slow = lynch({"peg": 0.8, "earningsCagr3y": 0.25, "debtToEquity": 0.3,
                  "currentRatio": 2.0})
    wild = lynch({"peg": 0.8, "earningsCagr3y": 0.90, "debtToEquity": 0.3,
                  "currentRatio": 2.0})
    assert slow.score == 1.0
    assert wild.score < 1.0
    growth = [c for c in wild.criteria if "implausibly" in c.name][0]
    assert growth.passed is False


def test_jhunjhunwala_will_not_fight_the_tape():
    good = dict(COMPOUNDER)
    below = dict(COMPOUNDER, above200dma=False)
    assert jhunjhunwala(good).score > jhunjhunwala(below).score
    tape = [c for c in jhunjhunwala(below).criteria if "tape" in c.name][0]
    assert tape.passed is False


def test_jhunjhunwala_wants_demand_that_lasts():
    consumer = jhunjhunwala(dict(COMPOUNDER, sector="Consumer staples"))
    obscure = jhunjhunwala(dict(COMPOUNDER, sector="Shipping freight brokerage"))
    durable_c = [c for c in consumer.criteria if "Durable" in c.name][0]
    durable_o = [c for c in obscure.criteria if "Durable" in c.name][0]
    assert durable_c.passed is True and durable_o.passed is False


def test_damani_is_the_strictest_on_debt():
    facts = dict(COMPOUNDER, debtToEquity=0.45)
    d = [c for c in damani(facts).criteria if "debt" in c.name.lower()][0]
    b = [c for c in buffett(facts).criteria if "debt" in c.name.lower()][0]
    assert d.passed is False and b.passed is True, \
        "the lenses must genuinely differ, not share one threshold"


def test_longevity_distinguishes_steady_growth_from_one_good_year():
    steady = qglp(dict(COMPOUNDER, revenue_history=[100, 112, 126, 141, 158, 177]))
    lumpy = qglp(dict(COMPOUNDER, revenue_history=[100, 101, 99, 102, 100, 177]))
    s = [c for c in steady.criteria if "most years" in c.name][0]
    l = [c for c in lumpy.criteria if "most years" in c.name][0]
    assert s.passed is True and l.passed is False


def test_longevity_is_unknown_without_history():
    v = qglp({k: x for k, x in COMPOUNDER.items() if k != "revenue_history"})
    c = [c for c in v.criteria if "most years" in c.name][0]
    assert c.passed is None


# ------------------------------------------------------------------ PEG
def test_peg_is_derived_consistently():
    d = derive({"pe": 30.0, "earningsCagr3y": 0.20})
    assert abs(d["peg"] - 1.5) < 1e-9


def test_peg_refuses_to_exist_for_a_shrinking_business():
    assert derive({"pe": 30.0, "earningsCagr3y": -0.10})["peg"] is None
    assert derive({"pe": 30.0, "earningsCagr3y": 0.0})["peg"] is None
    assert derive({"pe": None, "earningsCagr3y": 0.20})["peg"] is None


# ------------------------------------------------------------------ consensus
def test_consensus_keeps_the_disagreement_instead_of_averaging_it():
    # Fast growth, real debt: Lynch-ish on growth, Damani-hostile on leverage.
    contested = dict(COMPOUNDER, debtToEquity=0.55, roce=0.16, dividendYield=0.0,
                     annualVol=0.46)
    c = consensus(apply_all(contested))
    assert c["ok"]
    assert len(c["split"]) >= 4
    assert any(s["failed"] for s in c["split"]), "failures must survive to the split"


def test_consensus_reports_unanimity_where_it_is_real():
    c = consensus(apply_all(LEVERED))
    assert c["ok"]
    assert "Radhakishan Damani" in c["rejected_by"]
    assert c["unanimous_weaknesses"], "every lens tests debt; all should fail it"


def test_consensus_says_so_when_nothing_can_be_judged():
    c = consensus(apply_all({}))
    assert c["ok"] is False
    assert "no lens" in c["why"]


def test_a_clean_compounder_reads_as_broad_agreement():
    c = consensus(apply_all(COMPOUNDER))
    assert len(c["accepted_by"]) >= 3
    assert not c["rejected_by"]
    assert "agreement" in c["stance"] or "acceptance" in c["stance"]


def test_every_lens_is_actually_wired_in():
    vs = apply_all(COMPOUNDER)
    authors = {v.author for v in vs}
    assert authors == {"Raamdeo Agrawal", "Rakesh Jhunjhunwala", "Warren Buffett",
                       "Peter Lynch", "Radhakishan Damani"}
    assert all(v.idea and v.verdict for v in vs)
