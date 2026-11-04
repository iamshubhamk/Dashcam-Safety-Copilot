"""The score formula and feedback rules: the numbers people will quote, so pinned exactly."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.config import REPO_ROOT
from app.services.scoring import RiskConfig, ScoredEvent, load_risk_config, score_trip

ALL_RAN = {t: "ran" for t in ("forward_collision", "obstacle_in_lane", "tailgating", "harsh_braking")}


@pytest.fixture
def cfg() -> RiskConfig:
    return load_risk_config(REPO_ROOT / "configs" / "risk.yaml")


def ev(i: int, t: str = "forward_collision", sev: str = "warning", peak: float = 10.0, ttc: float | None = 2.0):
    return ScoredEvent(i, t, sev, peak, ttc)


def test_shipped_config_loads_and_is_marked_provisional(cfg):
    assert cfg.version >= 1
    assert cfg.provisional is True  # r_half is not calibrated yet; reports must say so


def test_no_events_with_all_checks_is_a_perfect_score(cfg):
    r = score_trip(cfg, [], ALL_RAN, duration_s=1800, distance_km=None)
    assert r.score == 100.0 and r.risk_rate == 0.0
    assert r.not_checked == []
    assert sum(1 for f in r.feedback if f["kind"] == "positive") == 4


def test_rate_equal_to_r_half_scores_50(cfg):
    # 1 hour of video, per-hour exposure: R = total weight. Make total weight == r_half.per_hour.
    n = int(cfg.r_half.per_hour / cfg.type_weights["harsh_braking"])
    events = [ev(i, "harsh_braking") for i in range(n)]
    r = score_trip(cfg, events, ALL_RAN, duration_s=3600, distance_km=None)
    assert r.risk_rate == pytest.approx(cfg.r_half.per_hour)
    assert r.score == 50.0


def test_critical_counts_by_its_multiplier(cfg):
    warn = score_trip(cfg, [ev(1)], ALL_RAN, 3600, None)
    crit = score_trip(cfg, [ev(1, sev="critical")], ALL_RAN, 3600, None)
    assert crit.risk_rate == pytest.approx(warn.risk_rate * cfg.severity_multipliers["critical"])
    assert crit.score < warn.score


def test_uses_distance_when_gps_track_is_long_enough(cfg):
    r = score_trip(cfg, [ev(1)], ALL_RAN, duration_s=3600, distance_km=50)
    assert r.exposure_unit == "per_100_km" and r.exposure_value == 0.5
    assert r.risk_rate == pytest.approx(cfg.type_weights["forward_collision"] / 0.5)


def test_short_gps_track_falls_back_to_per_hour(cfg):
    r = score_trip(cfg, [ev(1)], ALL_RAN, duration_s=3600, distance_km=cfg.min_distance_km / 2)
    assert r.exposure_unit == "per_hour"


def test_short_video_uses_the_exposure_floor(cfg):
    # 2 minutes would otherwise turn one warning into 30 per hour.
    r = score_trip(cfg, [ev(1)], ALL_RAN, duration_s=120, distance_km=None)
    assert r.exposure_value == cfg.min_exposure_hours


def test_skipped_checks_are_listed_not_scored_as_clean(cfg):
    checks = {
        "forward_collision": "ran",
        "obstacle_in_lane": "absent",
        "tailgating": "skipped_no_ego_speed",
        "harsh_braking": "skipped_no_ego_speed",
    }
    r = score_trip(cfg, [], checks, 600, None)
    assert {n["type"] for n in r.not_checked} == {"obstacle_in_lane", "tailgating", "harsh_braking"}
    assert not r.breakdown["tailgating"]["checked"]
    positives = [f["type"] for f in r.feedback if f["kind"] == "positive"]
    assert positives == ["forward_collision"]  # never "no tailgating detected" when it wasn't checked
    assert "speed" in next(n["reason"] for n in r.not_checked if n["type"] == "tailgating")


def test_nothing_checked_and_nothing_found_has_no_score(cfg):
    r = score_trip(cfg, [], {t: "absent" for t in ALL_RAN}, 600, None)
    assert r.score is None and r.risk_rate is None


def test_score_is_never_negative(cfg):
    events = [ev(i, sev="critical") for i in range(500)]
    r = score_trip(cfg, events, ALL_RAN, 600, None)
    assert 0 <= r.score < 1


def test_feedback_lines_link_to_their_events_and_shares_add_up(cfg):
    events = [
        ev(1, "forward_collision", "critical", 30, 0.9),
        ev(2, "tailgating", peak=40),
        ev(3, "tailgating", peak=50),
    ]
    r = score_trip(cfg, events, ALL_RAN, 600, None)
    issues = [f for f in r.feedback if f["kind"] == "issue"]
    assert [f["type"] for f in issues] == ["forward_collision", "tailgating"]  # biggest share first
    assert issues[1]["event_ids"] == [2, 3]
    assert "2 times" in issues[1]["text"]
    assert sum(b["share"] for b in r.breakdown.values()) == pytest.approx(1.0, abs=1e-3)
    worst = next(f for f in r.feedback if f["kind"] == "worst_moments")
    assert worst["event_ids"][0] == 1  # the critical forward collision


def test_time_cluster_line(cfg):
    events = [ev(i, peak=500 + i) for i in range(1, 5)] + [ev(9, peak=10)]
    r = score_trip(cfg, events, ALL_RAN, duration_s=600, distance_km=None)
    pattern = next(f for f in r.feedback if f["kind"] == "pattern")
    assert "last third" in pattern["text"] and set(pattern["event_ids"]) == {1, 2, 3, 4}


def test_no_cluster_line_when_spread_out(cfg):
    events = [ev(1, peak=50), ev(2, peak=250), ev(3, peak=450)]
    r = score_trip(cfg, events, ALL_RAN, duration_s=600, distance_km=None)
    assert not any(f["kind"] == "pattern" for f in r.feedback)


def test_config_must_cover_every_event_type(tmp_path: Path):
    raw = yaml.safe_load((REPO_ROOT / "configs" / "risk.yaml").read_text())
    del raw["type_weights"]["tailgating"]
    bad = tmp_path / "risk.yaml"
    bad.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="type_weights"):
        load_risk_config(bad)
