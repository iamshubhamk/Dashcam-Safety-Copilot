"""Time-to-collision from how fast a tracked box grows. No camera calibration needed.

Why this works: an object's image size s is proportional to 1/Z (Z = distance). If it
approaches at constant speed v, then d(ln s)/dt = -dZ/dt / Z = v / Z = 1 / TTC.
So we fit a straight line to ln(size) over the last ~0.6 s and 1 / slope is the TTC at
the MIDDLE of that window. We subtract the time from the window's middle to the newest
frame to get TTC *now*; skipping that step would report a TTC ~0.3 s too optimistic.

Size is sqrt(width * height): it averages out jitter in either dimension.

Limitations:
- Assumes constant closing speed over the window (braking makes it optimistic).
- Box jitter from the detector becomes TTC noise, so we fit over several frames.
- A box cut off by the frame edge stops growing even as the object gets closer; callers
  should treat edge-touching boxes as "very close" separately.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

# Slopes below this (1/s) mean "not meaningfully closing": TTC > 100 s.
_MIN_SLOPE = 0.01


@dataclass(frozen=True)
class SizeSample:
    time_s: float
    size_px: float


def fit_log_scale_rate(samples: list[SizeSample]) -> float | None:
    """Least-squares slope of ln(size) vs time, in 1/s. None if it can't be computed.
    The slope is the instantaneous rate at the samples' mean time."""
    pts = [(s.time_s, math.log(s.size_px)) for s in samples if s.size_px > 0]
    if len(pts) < 2:
        return None
    n = len(pts)
    mt = sum(t for t, _ in pts) / n
    ml = sum(v for _, v in pts) / n
    var_t = sum((t - mt) ** 2 for t, _ in pts)
    if var_t == 0:
        return None
    return sum((t - mt) * (v - ml) for t, v in pts) / var_t


# Floor for TTC after the lag correction: "already at or past contact" in the model.
_MIN_TTC_S = 0.05


def ttc_from_rate(rate: float | None, lag_s: float = 0.0) -> float | None:
    """TTC in seconds from d(ln size)/dt measured `lag_s` ago; None when not closing.
    With constant closing speed, TTC falls one second per second, so TTC_now = 1/rate - lag."""
    if rate is None or rate < _MIN_SLOPE:
        return None
    return max(_MIN_TTC_S, 1.0 / rate - lag_s)


class TrackSizeHistory:
    """Rolling per-track size history. One instance for the whole video."""

    def __init__(self, window_s: float, min_samples: int, max_gap_s: float) -> None:
        self.window_s = window_s
        self.min_samples = min_samples
        self.max_gap_s = max_gap_s
        self._hist: dict[int, deque[SizeSample]] = {}

    def update(self, track_id: int, time_s: float, width: float, height: float) -> tuple[float | None, float | None]:
        """Add a sample and return (ttc_s, rate). Both None until enough history exists."""
        h = self._hist.setdefault(track_id, deque())
        if h and time_s - h[-1].time_s > self.max_gap_s:
            h.clear()  # track was lost for a while; old sizes no longer comparable
        h.append(SizeSample(time_s, math.sqrt(max(width, 0.0) * max(height, 0.0))))
        while h and time_s - h[0].time_s > self.window_s:
            h.popleft()
        if len(h) < self.min_samples:
            return None, None
        rate = fit_log_scale_rate(list(h))
        mean_t = sum(x.time_s for x in h) / len(h)
        return ttc_from_rate(rate, lag_s=time_s - mean_t), rate

    def prune(self, now_s: float) -> None:
        """Forget tracks not seen for longer than max_gap_s (keeps memory flat on long videos)."""
        stale = [tid for tid, h in self._hist.items() if not h or now_s - h[-1].time_s > self.max_gap_s]
        for tid in stale:
            del self._hist[tid]
