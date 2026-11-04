"""Driving score and rule-based feedback. Pure functions over plain data, so they are easy to test.

    weight(event) = type_weight[type] * severity_multiplier[severity]
    R             = sum(weights) / exposure          exposure = 100 km of GPS track, else hours of video
    score         = 100 * 0.5 ** (R / r_half)        100 = nothing risky; 50 when R == r_half

Why a rate: a 3-hour highway trip shouldn't score worse than a 10-minute one just for being long.
Why 0.5 ** (R / r_half): it falls smoothly, never goes negative, and r_half has a plain meaning
("the risk rate that halves the score").

Checks the pipeline skipped are listed as "not checked" and add nothing to R; the report says the
score covers only the checks that ran. If no check ran there is no score at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

EVENT_TYPES = ("forward_collision", "obstacle_in_lane", "tailgating", "harsh_braking")
SEVERITIES = ("warning", "critical")

LABELS = {
    "forward_collision": "Forward collision risk",
    "obstacle_in_lane": "Obstacle in lane",
    "tailgating": "Tailgating",
    "harsh_braking": "Lead vehicle braking hard",
}
NOT_CHECKED_REASONS = {
    "skipped_no_ego_speed": "needs the vehicle's own speed, which this trip doesn't have",
    "skipped_no_gps": "needs GPS",
    "absent": "the current detector can't see the objects this check needs",
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RHalf(_Strict):
    per_100_km: float = Field(gt=0)
    per_hour: float = Field(gt=0)


class FeedbackConfig(_Strict):
    max_worst_moments: int = Field(ge=0)
    cluster_share: float = Field(gt=0, le=1)
    cluster_min_events: int = Field(ge=1)


class RiskConfig(_Strict):
    version: int = Field(ge=1)
    type_weights: dict[str, float]
    severity_multipliers: dict[str, float]
    r_half: RHalf
    provisional: bool
    min_distance_km: float = Field(gt=0)
    min_exposure_hours: float = Field(gt=0)
    feedback: FeedbackConfig

    def model_post_init(self, __context: Any) -> None:
        if set(self.type_weights) != set(EVENT_TYPES):
            raise ValueError(f"type_weights must have exactly {EVENT_TYPES}")
        if set(self.severity_multipliers) != set(SEVERITIES):
            raise ValueError(f"severity_multipliers must have exactly {SEVERITIES}")
        if any(v < 0 for v in [*self.type_weights.values(), *self.severity_multipliers.values()]):
            raise ValueError("weights must be >= 0")


def load_risk_config(path: Path) -> RiskConfig:
    with path.open(encoding="utf-8") as f:
        return RiskConfig.model_validate(yaml.safe_load(f))


@dataclass(frozen=True)
class ScoredEvent:
    id: int  # database id, so feedback can link to clips
    type: str
    severity: str
    peak_s: float
    min_ttc_s: float | None = None


@dataclass
class Report:
    score: float | None
    risk_rate: float | None
    exposure_unit: str
    exposure_value: float
    provisional: bool
    scoring_version: int
    breakdown: dict[str, Any]
    feedback: list[dict[str, Any]] = field(default_factory=list)
    not_checked: list[dict[str, Any]] = field(default_factory=list)


def event_weight(cfg: RiskConfig, e: ScoredEvent) -> float:
    return cfg.type_weights[e.type] * cfg.severity_multipliers[e.severity]


def score_trip(
    cfg: RiskConfig,
    events: list[ScoredEvent],
    checks: dict[str, str],
    duration_s: float,
    distance_km: float | None,
) -> Report:
    checked = [t for t in EVENT_TYPES if checks.get(t) == "ran"]
    not_checked = [
        {
            "type": t,
            "label": LABELS[t],
            "status": checks.get(t, "absent"),
            "reason": NOT_CHECKED_REASONS.get(checks.get(t, "absent"), "not run"),
        }
        for t in EVENT_TYPES
        if t not in checked
    ]

    if distance_km is not None and distance_km >= cfg.min_distance_km:
        unit, exposure, r_half = "per_100_km", distance_km / 100.0, cfg.r_half.per_100_km
    else:
        unit, exposure, r_half = "per_hour", max(duration_s / 3600.0, cfg.min_exposure_hours), cfg.r_half.per_hour

    # Events are counted even for a type whose check reported skipped: if it fired, it happened.
    total = sum(event_weight(cfg, e) for e in events)
    breakdown: dict[str, Any] = {}
    for t in EVENT_TYPES:
        mine = [e for e in events if e.type == t]
        w = sum(event_weight(cfg, e) for e in mine)
        breakdown[t] = {
            "label": LABELS[t],
            "checked": t in checked,
            "counts": {s: sum(1 for e in mine if e.severity == s) for s in SEVERITIES},
            "weight": round(w, 3),
            "share": round(w / total, 4) if total > 0 else 0.0,
        }

    if not checked and not events:
        score = rate = None
    else:
        rate = total / exposure
        score = round(100.0 * 0.5 ** (rate / r_half), 1)

    report = Report(
        score=score,
        risk_rate=round(rate, 4) if rate is not None else None,
        exposure_unit=unit,
        exposure_value=round(exposure, 4),
        provisional=cfg.provisional,
        scoring_version=cfg.version,
        breakdown=breakdown,
        not_checked=not_checked,
    )
    report.feedback = build_feedback(cfg, events, checked, breakdown, duration_s)
    return report


def build_feedback(
    cfg: RiskConfig,
    events: list[ScoredEvent],
    checked: list[str],
    breakdown: dict[str, Any],
    duration_s: float,
) -> list[dict[str, Any]]:
    """Plain-language lines. Every line is generated from counts, so each one can be traced back to
    the events behind it (event_ids)."""
    lines: list[dict[str, Any]] = []

    issues = sorted((t for t in EVENT_TYPES if breakdown[t]["weight"] > 0), key=lambda t: -breakdown[t]["weight"])
    for t in issues:
        b = breakdown[t]
        n = b["counts"]["warning"] + b["counts"]["critical"]
        crit = b["counts"]["critical"]
        times = "once" if n == 1 else f"{n} times"
        crit_txt = f", {crit} critical" if crit else ""
        lines.append(
            {
                "kind": "issue",
                "type": t,
                "text": f"{LABELS[t]}: {times}{crit_txt}. {round(b['share'] * 100)}% of this trip's risk.",
                "event_ids": [e.id for e in events if e.type == t],
            }
        )

    for t in checked:
        if breakdown[t]["weight"] == 0 and sum(breakdown[t]["counts"].values()) == 0:
            lines.append({"kind": "positive", "type": t, "text": f"No {LABELS[t].lower()} detected.", "event_ids": []})

    cluster = _time_cluster(cfg, events, duration_s)
    if cluster:
        lines.append(cluster)

    worst = sorted(
        events,
        key=lambda e: (-event_weight(cfg, e), e.min_ttc_s if e.min_ttc_s is not None else float("inf"), e.peak_s),
    )[: cfg.feedback.max_worst_moments]
    if worst:
        lines.append(
            {
                "kind": "worst_moments",
                "text": "Watch these moments first." if len(worst) > 1 else "Watch this moment.",
                "event_ids": [e.id for e in worst],
            }
        )
    return lines


def _time_cluster(cfg: RiskConfig, events: list[ScoredEvent], duration_s: float) -> dict[str, Any] | None:
    if duration_s <= 0 or len(events) < cfg.feedback.cluster_min_events:
        return None
    thirds = [0.0, 0.0, 0.0]
    members: list[list[int]] = [[], [], []]
    for e in events:
        i = min(2, max(0, int(3 * e.peak_s / duration_s)))
        thirds[i] += event_weight(cfg, e)
        members[i].append(e.id)
    total = sum(thirds)
    if total <= 0:
        return None
    i = max(range(3), key=lambda k: thirds[k])
    if thirds[i] / total < cfg.feedback.cluster_share:
        return None
    part = ("first", "middle", "last")[i]
    minutes = duration_s / 180.0
    return {
        "kind": "pattern",
        "text": f"Most risky moments came in the {part} third of the trip (about {minutes:.0f} min).",
        "event_ids": members[i],
    }
