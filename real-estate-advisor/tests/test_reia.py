"""Offline tests: BeautifulSoup parsing, classification, corridor scoring,
legal engine verdicts, parcel evaluation, digest."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reia import config, db  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    yield


# ---------- monitor: BeautifulSoup parsing ----------

RSS_SAMPLE = """<?xml version="1.0"?><rss><channel>
<item><title>Cabinet approves Regional Ring Road northern arc land acquisition</title>
<link>https://x.gov/1</link><description>Notification under section 11 for villages near Toopran</description></item>
<item><title>Weather update for the week</title><link>https://x.gov/2</link>
<description>Rain expected</description></item>
</channel></rss>"""

HTML_SAMPLE = """<html><body><div class="news">
<a href="/notice/1">Foundation stone laid for Bhogapuram greenfield airport access highway near Visakhapatnam</a>
<a href="/notice/2">Home</a>
<a href="https://ap.gov.in/notice/3">APIIC approves allotment of land for pharma industrial park at Orvakal, Kurnool district</a>
</div></body></html>"""


def test_rss_and_html_parsing():
    from reia.monitor import parse_listing, parse_rss

    rss = parse_rss(RSS_SAMPLE)
    assert len(rss) == 2 and rss[0]["url"] == "https://x.gov/1"

    items = parse_listing(HTML_SAMPLE, "div.news a", "https://ap.gov.in")
    titles = [i["title"] for i in items]
    assert len(items) == 2                       # "Home" filtered (too short)
    assert any("Bhogapuram" in t for t in titles)
    assert items[0]["url"] == "https://ap.gov.in/notice/1"   # relative resolved


def test_classify_and_corridor_match_and_store():
    from reia.monitor import recent_events, store_items, parse_rss, parse_listing

    rss_items = parse_rss(RSS_SAMPLE)
    n = store_items(rss_items, "test_rss", "TG")
    assert n == 1                                # weather item dropped (no category)
    html_items = parse_listing(HTML_SAMPLE, "div.news a", "https://ap.gov.in")
    assert store_items(html_items, "test_html", "AP") == 2
    assert store_items(html_items, "test_html", "AP") == 0   # dedupe on re-sweep

    evs = recent_events(days=1)
    assert len(evs) == 3
    rrr = next(e for e in evs if "Ring Road" in e["title"])
    assert "highway_road" in rrr["categories"] and "acquisition" in rrr["categories"]
    assert "hyd-rrr-north" in rrr["corridors"]           # Toopran matched
    vizag = next(e for e in evs if "Bhogapuram" in e["title"])
    assert "vizag-bhogapuram" in vizag["corridors"]
    orvakal = next(e for e in evs if "Orvakal" in e["title"])
    assert "bengaluru-hyd" in orvakal["corridors"]


def test_sweep_survives_dead_sources(monkeypatch):
    from reia import monitor

    def dead_get(*a, **k):
        raise ConnectionError("site down")

    monkeypatch.setattr(monitor.requests, "get", dead_get)
    monkeypatch.setattr(monitor.time, "sleep", lambda s: None)
    results = monitor.sweep([{"name": "dead", "kind": "rss", "region": "AP",
                              "url": "https://dead.gov"}])
    assert "error" in str(results["dead"])       # logged, not raised


# ---------- corridor scoring ----------

def test_corridor_scoring_template():
    from reia.corridor import rank_corridors, score_corridor, set_inputs

    set_inputs("hyd-rrr-north", jobs_anchor=0.5, connectivity_delta=0.8,
               policy_persistence=0.7, supply_constraint=0.4, stage="B")
    set_inputs("amaravati", jobs_anchor=0.2, connectivity_delta=0.4,
               policy_persistence=0.3, supply_constraint=0.5, stage="A")

    rrr = score_corridor("hyd-rrr-north")
    # 0.5*30 + 0.8*25 + 0.7*15 + 0.4*10 + stage B 20 = 15+20+10.5+4+20 = 69.5
    assert rrr["score"] == pytest.approx(69.5)
    assert "core allocation" in rrr["stage_advice"]

    amv = score_corridor("amaravati")
    assert any("lottery-ticket" in f for f in amv["flags"])  # A + low persistence

    ranked = rank_corridors()
    assert ranked[0]["slug"] == "hyd-rrr-north"

    set_inputs("amaravati", stage="D")
    assert any("exit_stage" in f for f in score_corridor("amaravati")["flags"])


# ---------- legal engine ----------

def _clean_answers():
    from reia.legal import blank_answers
    return {k: True for k in blank_answers()}


def test_legal_verdicts():
    from reia.legal import evaluate

    clean = evaluate(_clean_answers())
    assert clean["verdict"] == "CLEAR_PENDING_LAWYER"
    assert clean["lawyer_questions"] == []
    assert "not legal advice" in clean["disclaimer"]

    veto = evaluate({**_clean_answers(), "not_assigned_land": False})
    assert veto["verdict"] == "VETO"
    assert "not_assigned_land" in veto["failed_veto"]

    resolve = evaluate({**_clean_answers(), "mutation_complete": False})
    assert resolve["verdict"] == "RESOLVE_FIRST"

    # silence is never clearance: unchecked VETO item blocks clearance
    partial = _clean_answers()
    partial["no_litigation"] = None
    unchecked = evaluate(partial)
    assert unchecked["verdict"] == "RESOLVE_FIRST"
    assert "no_litigation" in unchecked["unchecked"]
    assert any("eCourts" in q for q in unchecked["lawyer_questions"])

    # layout items only apply to layouts
    raw = evaluate({**_clean_answers(), "rera_registered": False}, "raw_land")
    assert raw["verdict"] == "CLEAR_PENDING_LAWYER"
    lay = evaluate({**_clean_answers(), "rera_registered": False}, "layout")
    assert lay["verdict"] == "RESOLVE_FIRST"


# ---------- parcel evaluator ----------

def test_parcel_evaluation_paths():
    from reia.corridor import set_inputs
    from reia.parcel import evaluate_parcel

    set_inputs("hyd-rrr-north", jobs_anchor=0.5, connectivity_delta=0.8,
               policy_persistence=0.7, supply_constraint=0.4, stage="B")

    # clean + strong thesis → proceed to lawyer
    good = evaluate_parcel("Toopran 2ac", "hyd-rrr-north", asking_price=10_000_000,
                           guidance_value=6_000_000, legal_answers=_clean_answers(),
                           expected_multiple=3.0, horizon_years=5)
    assert good["recommendation"].startswith("PROCEED TO LAWYER")
    assert good["benchmark"]["beats_equity"]

    # legal veto dominates everything
    veto = evaluate_parcel("Disputed plot", "hyd-rrr-north", asking_price=5_000_000,
                           guidance_value=5_000_000,
                           legal_answers={**_clean_answers(), "outside_ftl_buffer": False},
                           expected_multiple=10.0)
    assert veto["recommendation"].startswith("REJECT")

    # clean but weak return case → pass
    weak = evaluate_parcel("Fair plot", "hyd-rrr-north", asking_price=10_000_000,
                           guidance_value=9_000_000, legal_answers=_clean_answers(),
                           expected_multiple=1.5, horizon_years=5)
    assert weak["recommendation"].startswith("PASS")
    assert any("does not beat index equity" in n for n in weak["notes"])

    # stage D corridor → reject even if clean
    set_inputs("hyd-rrr-north", stage="D")
    mature = evaluate_parcel("Late entry", "hyd-rrr-north", asking_price=10_000_000,
                             guidance_value=8_000_000, legal_answers=_clean_answers(),
                             expected_multiple=3.0)
    assert mature["recommendation"].startswith("REJECT")

    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM parcels").fetchone()[0] == 4


# ---------- digest ----------

def test_digest_end_to_end():
    from reia.digest import build_digest
    from reia.monitor import parse_rss, store_items

    store_items(parse_rss(RSS_SAMPLE), "test_rss", "TG")
    text = build_digest()
    assert "Corridor ranking" in text and "public signals" in text
    assert "Ring Road" in text
    assert "not legal advice" in text


# ---------- AI layer (offline) ----------

def test_ai_requires_key_and_prompt_builds(monkeypatch):
    from reia.ai import build_system_prompt, parcel_report

    sp = build_system_prompt()
    assert "Hyderabad" in sp and "Encumbrance" in sp   # both knowledge docs loaded
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        parcel_report({"x": 1})
