from knowledge_manager.performance_hotspots import HotspotTimer, summarize_maintenance_states


def test_hotspot_timer_summarizes_named_sections(monkeypatch):
    perf_counter_values = iter([0.0, 0.01, 0.02, 0.05, 0.10, 0.14])
    monkeypatch.setattr(
        "knowledge_manager.performance_hotspots.time.perf_counter",
        lambda: next(perf_counter_values),
    )

    hotspots = HotspotTimer()

    with hotspots.section("search"):
        pass

    with hotspots.section("search"):
        pass

    with hotspots.section("admin_dashboard"):
        pass

    summary = hotspots.summary()

    assert summary == {
        "search": {"count": 2, "mean_ms": 20.0, "max_ms": 30.0},
        "admin_dashboard": {"count": 1, "mean_ms": 40.0, "max_ms": 40.0},
    }


def test_summarize_maintenance_states_counts_deferred_actions():
    summary = summarize_maintenance_states(
        [
            {"deferred": True, "action": "module_saved"},
            {"deferred": True, "action": "module_saved"},
            {"deferred": False, "action": "module_deleted"},
        ]
    )

    assert summary == {
        "total": 3,
        "deferred": 2,
        "inline": 1,
        "actions": {"module_saved": 2, "module_deleted": 1},
    }
