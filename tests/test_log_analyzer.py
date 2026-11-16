import config
from tools.log_analyzer import analyze_logs, parse_lines, search_error_patterns


def _sample(name):
    return (config.SAMPLE_LOGS_DIR / name).read_text(encoding="utf-8")


def test_payment_log_patterns_and_counts():
    a = analyze_logs(_sample("inc001_payment_service.log"))
    ids = [p["id"] for p in a["patterns"]]
    specific = [i for i in ids if i not in ("slow_transaction", "payment_errors")]
    assert specific[0] == "db_pool_pressure"
    assert "db_timeout" in ids
    assert a["error_count"] > 0 and a["warning_count"] > 0
    assert a["time_range"]["start"].startswith("2026-11-12T10:")
    assert "java.sql.SQLTransientConnectionException" in a["exceptions"]
    # counts are real: every reported pattern count matches the lines actually tagged
    lines = parse_lines(_sample("inc001_payment_service.log"))
    for p in a["patterns"]:
        assert p["count"] == sum(1 for l in lines if p["id"] in l.patterns)


def test_each_scenario_has_its_distinguishing_pattern():
    expected = {"inc002_order_service.log": "downstream_timeout", "inc003_inventory_service.log": "memory_pressure",
                "inc004_notification_service.log": "config_error"}
    for name, pattern in expected.items():
        assert pattern in [p["id"] for p in analyze_logs(_sample(name))["patterns"]]


def test_no_fabricated_timestamps_or_counts():
    a = analyze_logs("ERROR something broke\nERROR something broke\nINFO fine")
    assert a["time_range"] is None
    assert a["error_count"] == 2 and a["total_lines"] == 3
    assert a["repeated_messages"][0]["count"] == 2


def test_empty_log():
    a = analyze_logs("")
    assert a["total_lines"] == 0 and a["patterns"] == []


def test_search_by_pattern_and_keyword():
    text = _sample("inc002_order_service.log")
    assert search_error_patterns(text, "retries")["match_count"] > 0
    kw = search_error_patterns(text, "shipping-quote")
    assert kw["match_count"] > 0 and all("shipping-quote" in l.lower() for l in kw["lines"])


def test_healthy_metrics_are_not_flagged_as_pressure():
    a = analyze_logs("2026-01-01T00:00:00Z INFO [svc] JVM heap used=41% gc_pause_ms=12\n"
                     "2026-01-01T00:00:01Z INFO [svc] cpu usage 38%")
    assert a["patterns"] == []
