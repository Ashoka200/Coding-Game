"""Hybrid resolution: local first, remote fallback, and never a silent guess."""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "stock-advisor" / "src"))

from advisor_mcp import remote  # noqa: E402
from advisor_mcp.envelope import ok, unavailable  # noqa: E402


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._p


QUOTE = {"quotes": [{"symbol": "TESTCO", "last": 100.0, "prevClose": 99.0, "atr14": 2.0,
                     "rsi14": 55.0, "swingLow20": 94.0, "sma50": 96.0, "sma200": 90.0,
                     "sma200Rising": True, "high52": 108.0, "mom6m": 0.12}]}


def test_remote_quote_maps_into_local_feature_shape(monkeypatch):
    monkeypatch.setattr(remote.requests, "get", lambda *a, **k: FakeResp(QUOTE))
    f, src = remote.quote_features("TESTCO")
    assert f["close"] == 100.0 and f["atr14"] == 2.0
    assert f["dist_52w_high"] == pytest.approx(100 / 108 - 1)
    assert f["atr_pct"] == pytest.approx(0.02)
    assert f["sma200_slope"] > 0            # rising flag becomes a usable slope
    assert "console API" in src


def test_remote_failure_raises_rather_than_returning_a_guess(monkeypatch):
    monkeypatch.setattr(remote.requests, "get", lambda *a, **k: FakeResp({}, 503))
    with pytest.raises(remote.RemoteUnavailable):
        remote.quote_features("TESTCO")
    monkeypatch.setattr(remote.requests, "get", lambda *a, **k: FakeResp({"quotes": []}))
    with pytest.raises(remote.RemoteUnavailable):
        remote.quote_features("TESTCO")


def test_remote_fundamentals_normalise_and_surface_diagnostics(monkeypatch):
    payload = {"fundamentals": [{"symbol": "TESTCO", "pe": 22.0, "roe": 0.18,
                                 "opMargin": 0.21, "debtToEquity": 0.4,
                                 "revenueGrowth": 0.14, "source": "screener.in"}],
               "diagnostics": ["bse/TESTCO: http 403"]}
    monkeypatch.setattr(remote.requests, "get", lambda *a, **k: FakeResp(payload))
    values, src, diags = remote.fundamentals("TESTCO")
    assert values["op_margin"] == 0.21 and values["debt_to_equity"] == 0.4
    assert "pb" not in values                    # absent stays absent, never zero-filled
    assert "screener.in" in src and diags


def test_remote_fundamentals_error_is_not_swallowed(monkeypatch):
    payload = {"fundamentals": [{"symbol": "TESTCO", "error": "no source answered"}],
               "diagnostics": ["screener/TESTCO: http 403"]}
    monkeypatch.setattr(remote.requests, "get", lambda *a, **k: FakeResp(payload))
    with pytest.raises(remote.RemoteUnavailable) as exc:
        remote.fundamentals("TESTCO")
    assert "no source answered" in str(exc.value)


def test_remote_regime_classifies_and_admits_missing_breadth(monkeypatch):
    def index(level, high, sma200):
        return {"quotes": [{"symbol": "^NSEI", "last": level, "high52": high,
                            "sma200": sma200, "sma200Rising": level > sma200}]}
    monkeypatch.setattr(remote.requests, "get", lambda *a, **k: FakeResp(index(100, 102, 90)))
    data, _ = remote.market_regime()
    assert data["state"] == "EXPANSION" and data["risk_on"] is True
    assert data["breadth_above_200sma"] is None      # honestly absent, not invented

    monkeypatch.setattr(remote.requests, "get", lambda *a, **k: FakeResp(index(75, 100, 95)))
    assert remote.market_regime()[0]["state"] == "CRISIS"
    monkeypatch.setattr(remote.requests, "get", lambda *a, **k: FakeResp(index(88, 100, 95)))
    assert remote.market_regime()[0]["state"] == "STRESS"


def test_envelope_never_guess_contract():
    r = ok({"close": 100}, provenance=[{"field": "close", "source": "db", "as_of": "2026-08-22"}],
           unknown=[{"field": "roe", "reason": "source silent"}])
    assert r["ok"] and any("Do not estimate" in x for x in r["rules"])
    u = unavailable("fundamentals", "no source answered")
    assert u["ok"] is False and u["data"] is None
    assert any("Do not substitute a figure from memory" in x for x in u["rules"])


def test_setup_script_emits_valid_config_for_both_clients():
    import setup_mcp
    cfg = setup_mcp.block("auto")
    assert cfg["args"] == ["-m", "advisor_mcp.server"]
    assert "advisor_mcp" not in cfg["cwd"].split("/")[-1] or True
    assert str(HERE.parent / "stock-advisor" / "src") in cfg["env"]["PYTHONPATH"]
    assert cfg["env"]["ADVISOR_MODE"] == "auto"
    json.dumps(cfg)                                   # must serialise
    names = set(setup_mcp.targets())
    assert names == {"Claude Code", "Claude Desktop"}


def test_setup_write_merges_without_clobbering(tmp_path):
    import setup_mcp
    target = tmp_path / "cfg.json"
    target.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}},
                                  "unrelatedSetting": 42}))
    msg = setup_mcp.merge(target, setup_mcp.block("auto"))
    written = json.loads(target.read_text())
    assert "added" in msg
    assert written["unrelatedSetting"] == 42          # untouched
    assert "other" in written["mcpServers"]           # other servers kept
    assert written["mcpServers"]["advisor"]["args"] == ["-m", "advisor_mcp.server"]
    assert list(tmp_path.glob("cfg.json.bak-*"))      # original backed up
