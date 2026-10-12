"""Tests for live Spansh neutron plotting with offline fallback (Task 4)."""
from __future__ import annotations


def test_live_fallback_on_timeout(monkeypatch):
    import ed_monitor.neutron as neutron
    monkeypatch.setattr(neutron, "_fetch_live", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    result = neutron.plot_neutron_live("Sol", "Colonia")
    assert result["source"] == "offline" and "fallback" in result["notice"].lower()


def test_live_success_returns_live_source(monkeypatch):
    import ed_monitor.neutron as neutron
    route = [{"system": "Sol", "neutron": False, "distance": 0.0, "jumps": 0}]
    monkeypatch.setattr(neutron, "_fetch_live", lambda *a, **k: {"route": route})
    result = neutron.plot_neutron_live("Sol", "Colonia")
    assert result["source"] == "live"
    assert result["ok"] is True
    assert result["route"] == route
    assert isinstance(result["notice"], str) and result["notice"]


def test_live_fallback_on_generic_error(monkeypatch):
    import ed_monitor.neutron as neutron
    monkeypatch.setattr(neutron, "_fetch_live", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    result = neutron.plot_neutron_live("Sol", "Colonia")
    assert result["source"] == "offline" and "fallback" in result["notice"].lower()
    assert result["ok"] is False
    assert result["route"] is None
