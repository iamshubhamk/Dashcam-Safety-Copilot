import math

import pytest

from dashcam_perception.ttc import SizeSample, TrackSizeHistory, fit_log_scale_rate, ttc_from_rate


def approaching(distance0: float, speed: float, fps: float, n: int, k: float = 1000.0) -> list[SizeSample]:
    """Image size = k / distance for an object approaching at constant speed."""
    return [SizeSample(i / fps, k / (distance0 - speed * i / fps)) for i in range(n)]


def test_constant_approach_gives_true_ttc():
    # 20 m away closing at 10 m/s: true TTC at the last sample = remaining distance / speed
    samples = approaching(20.0, 10.0, fps=30, n=18)
    rate = fit_log_scale_rate(samples)
    true_ttc_last = (20.0 - 10.0 * 17 / 30) / 10.0
    # Raw 1/slope is the TTC at the window's middle, i.e. too optimistic now ...
    assert 1.0 / rate > true_ttc_last + 0.2
    # ... the lag correction brings it to the newest frame
    lag = 17 / 30 - sum(s.time_s for s in samples) / len(samples)
    assert ttc_from_rate(rate, lag) == pytest.approx(true_ttc_last, rel=0.05)


def test_history_reports_ttc_at_newest_frame():
    h = TrackSizeHistory(window_s=0.6, min_samples=4, max_gap_s=0.5)
    ttc = None
    for s in approaching(20.0, 10.0, fps=30, n=18):
        ttc, _ = h.update(1, s.time_s, s.size_px, s.size_px)
    assert ttc == pytest.approx((20.0 - 10.0 * 17 / 30) / 10.0, rel=0.05)


def test_receding_or_static_has_no_ttc():
    static = [SizeSample(i / 30, 50.0) for i in range(10)]
    receding = approaching(20.0, -5.0, fps=30, n=10)
    assert ttc_from_rate(fit_log_scale_rate(static)) is None
    assert ttc_from_rate(fit_log_scale_rate(receding)) is None


def test_fit_needs_two_distinct_times():
    assert fit_log_scale_rate([SizeSample(0.0, 10.0)]) is None
    assert fit_log_scale_rate([SizeSample(0.0, 10.0), SizeSample(0.0, 12.0)]) is None


def test_history_waits_for_min_samples_and_resets_after_gap():
    h = TrackSizeHistory(window_s=0.6, min_samples=4, max_gap_s=0.5)
    for i in range(3):
        assert h.update(1, i / 30, 10 + i, 10 + i) == (None, None)
    ttc, rate = h.update(1, 3 / 30, 13, 13)
    assert ttc is not None and rate > 0
    # Track lost for 1 s: history resets, so no TTC from stale sizes
    assert h.update(1, 1.2, 40, 40) == (None, None)


def test_history_window_drops_old_samples():
    h = TrackSizeHistory(window_s=0.2, min_samples=2, max_gap_s=1.0)
    for i in range(30):
        h.update(7, i / 30, 20, 20)
    assert len(h._hist[7]) <= 7  # 0.2 s at 30 fps, inclusive


def test_prune_forgets_stale_tracks():
    h = TrackSizeHistory(window_s=0.6, min_samples=2, max_gap_s=0.5)
    h.update(1, 0.0, 10, 10)
    h.update(2, 1.0, 10, 10)
    h.prune(1.0)
    assert set(h._hist) == {2}


def test_log_rate_is_scale_invariant():
    a = approaching(30.0, 8.0, fps=25, n=12, k=100.0)
    b = approaching(30.0, 8.0, fps=25, n=12, k=5000.0)
    assert math.isclose(fit_log_scale_rate(a), fit_log_scale_rate(b), rel_tol=1e-9)


def test_settling_small_box_gives_no_ttc():
    """Replay of a real false alarm (Udacity highway clip, frames 178-185): a weak ~15 px
    detection of a distant car grew ~30% in 4 frames as the detector settled -> TTC 1.3 s."""
    widths = [13.2, 13.9, 14.9, 16.4, 16.9, 16.7, 16.7, 15.9, 15.6]
    heights = [9.6, 10.1, 10.9, 12.2, 12.8, 12.9, 13.1, 12.7, 12.7]
    ungated = TrackSizeHistory(window_s=0.6, min_samples=4, max_gap_s=0.5)
    gated = TrackSizeHistory(window_s=0.6, min_samples=4, max_gap_s=0.5, min_significance=3.0, min_size_px=22)
    raw = [ungated.update(1, i / 25, w, h)[0] for i, (w, h) in enumerate(zip(widths, heights, strict=True))]
    out = [gated.update(1, i / 25, w, h)[0] for i, (w, h) in enumerate(zip(widths, heights, strict=True))]
    assert min(t for t in raw if t is not None) < 2.0  # the false alarm, reproduced
    assert all(t is None for t in out)


def test_min_size_does_not_block_nearby_approach():
    # Same approach as below but with large boxes (k=3000 -> 150+ px)
    h = TrackSizeHistory(window_s=0.6, min_samples=4, max_gap_s=0.5, min_significance=3.0, min_size_px=22)
    ttc = None
    for s in approaching(20.0, 10.0, fps=30, n=18, k=3000.0):
        ttc, _ = h.update(1, s.time_s, s.size_px, s.size_px)
    assert ttc is not None


def test_gate_keeps_real_approach():
    h = TrackSizeHistory(window_s=0.6, min_samples=4, max_gap_s=0.5, min_significance=3.0)
    ttc = None
    for s in approaching(20.0, 10.0, fps=30, n=18):
        ttc, _ = h.update(1, s.time_s, s.size_px, s.size_px)
    assert ttc == pytest.approx((20.0 - 10.0 * 17 / 30) / 10.0, rel=0.05)
