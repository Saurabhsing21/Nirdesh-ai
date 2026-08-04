from __future__ import annotations

from scripts.latency_replay import distribution


def test_replay_distribution_withholds_p99_below_100_valid_turns() -> None:
    summary = distribution([float(value) for value in range(1, 100)])

    assert summary["n"] == 99
    assert summary["p50"] == 50
    assert summary["p99"] is None


def test_replay_distribution_reports_p99_at_100_valid_turns() -> None:
    summary = distribution([float(value) for value in range(1, 101)])

    assert summary["n"] == 100
    assert summary["p50"] == 50.5
    assert summary["p90"] == 90.1
    assert summary["p95"] == 95.05
    assert summary["p99"] == 99.01
