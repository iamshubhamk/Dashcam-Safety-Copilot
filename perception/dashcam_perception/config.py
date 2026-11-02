"""Typed pipeline config loaded from YAML (perception/configs/default.yaml).

Validation happens here, once, so a typo in a threshold fails at startup with a clear
message instead of silently disabling an alert halfway through a video.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path("perception/configs/default.yaml")


class ConfigError(ValueError):
    """The YAML config is missing a key, has a bad value, or enables an unsupported alert."""


@dataclass(frozen=True)
class DetectorConfig:
    weights: str
    coco_map: str
    classes_file: str
    conf: float
    iou: float
    imgsz: int
    device: str | None
    suppress_riders: bool
    rider_overlap: float


@dataclass(frozen=True)
class CameraConfig:
    horizontal_fov_deg: float
    mount_height_m: float
    horizon_y_frac: float


@dataclass(frozen=True)
class EgoLaneConfig:
    polygon: tuple[tuple[float, float], ...]
    min_overlap: float


@dataclass(frozen=True)
class TTCConfig:
    window_s: float
    min_samples: int
    max_gap_s: float
    min_significance: float
    min_size_px: float


@dataclass(frozen=True)
class ForwardCollisionConfig:
    enabled: bool
    classes: frozenset[str]
    ttc_warning_s: float
    ttc_critical_s: float
    critical_distance_m: float
    vulnerable_classes: frozenset[str]
    vulnerable_distance_m: float


@dataclass(frozen=True)
class ObstacleConfig:
    enabled: bool
    classes: frozenset[str]
    warning_distance_m: float
    critical_distance_m: float


@dataclass(frozen=True)
class AlertsConfig:
    confirm_hits: int
    confirm_window: int
    episode_gap_s: float
    forward_collision: ForwardCollisionConfig
    obstacle_in_lane: ObstacleConfig


@dataclass(frozen=True)
class OutputConfig:
    annotated_video: bool
    clips: bool
    clip_pre_s: float
    clip_post_s: float


@dataclass(frozen=True)
class PipelineConfig:
    detector: DetectorConfig
    tracker_config: str
    camera: CameraConfig
    ego_lane: EgoLaneConfig
    ttc: TTCConfig
    alerts: AlertsConfig
    output: OutputConfig
    raw: dict[str, Any] = field(repr=False, compare=False, default_factory=dict)


def _req(d: dict[str, Any], key: str, where: str) -> Any:
    if not isinstance(d, dict) or key not in d:
        raise ConfigError(f"missing key '{where}.{key}'")
    return d[key]


def _positive(value: Any, where: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError) as e:
        raise ConfigError(f"'{where}' must be a number, got {value!r}") from e
    if v <= 0:
        raise ConfigError(f"'{where}' must be > 0, got {v}")
    return v


def _fraction(value: Any, where: str) -> float:
    v = float(value)
    if not 0.0 <= v <= 1.0:
        raise ConfigError(f"'{where}' must be between 0 and 1, got {v}")
    return v


def parse_config(data: dict[str, Any], known_classes: list[str] | None = None) -> PipelineConfig:
    """Build a PipelineConfig from a parsed YAML dict. `known_classes` (from classes.yaml)
    lets us reject alert class names that don't exist, e.g. "two-wheeler" vs "two_wheeler"."""
    d = _req(data, "detector", "")
    detector = DetectorConfig(
        weights=str(_req(d, "weights", "detector")),
        coco_map=str(_req(d, "coco_map", "detector")),
        classes_file=str(_req(d, "classes_file", "detector")),
        conf=_fraction(_req(d, "conf", "detector"), "detector.conf"),
        iou=_fraction(_req(d, "iou", "detector"), "detector.iou"),
        imgsz=int(_positive(_req(d, "imgsz", "detector"), "detector.imgsz")),
        device=None if d.get("device") is None else str(d["device"]),
        suppress_riders=bool(d.get("suppress_riders", True)),
        rider_overlap=_fraction(d.get("rider_overlap", 0.5), "detector.rider_overlap"),
    )

    t = _req(data, "tracker", "")
    tracker_config = str(_req(t, "config", "tracker"))

    c = _req(data, "camera", "")
    fov = _positive(_req(c, "horizontal_fov_deg", "camera"), "camera.horizontal_fov_deg")
    if fov >= 180:
        raise ConfigError("'camera.horizontal_fov_deg' must be < 180")
    camera = CameraConfig(
        horizontal_fov_deg=fov,
        mount_height_m=_positive(_req(c, "mount_height_m", "camera"), "camera.mount_height_m"),
        horizon_y_frac=_fraction(_req(c, "horizon_y_frac", "camera"), "camera.horizon_y_frac"),
    )

    e = _req(data, "ego_lane", "")
    poly_raw = _req(e, "polygon", "ego_lane")
    if not isinstance(poly_raw, list) or len(poly_raw) < 3:
        raise ConfigError("'ego_lane.polygon' needs at least 3 [x, y] points")
    polygon = tuple((_fraction(p[0], "ego_lane.polygon x"), _fraction(p[1], "ego_lane.polygon y")) for p in poly_raw)
    ego_lane = EgoLaneConfig(
        polygon=polygon, min_overlap=_fraction(_req(e, "min_overlap", "ego_lane"), "ego_lane.min_overlap")
    )

    tt = _req(data, "ttc", "")
    ttc = TTCConfig(
        window_s=_positive(_req(tt, "window_s", "ttc"), "ttc.window_s"),
        min_samples=int(_positive(_req(tt, "min_samples", "ttc"), "ttc.min_samples")),
        max_gap_s=_positive(_req(tt, "max_gap_s", "ttc"), "ttc.max_gap_s"),
        min_significance=float(tt.get("min_significance", 0.0)),
        min_size_px=float(tt.get("min_size_px", 0.0)),
    )
    if ttc.min_significance < 0:
        raise ConfigError("'ttc.min_significance' must be >= 0")
    if ttc.min_samples < 2:
        raise ConfigError("'ttc.min_samples' must be >= 2 (a slope needs two points)")

    a = _req(data, "alerts", "")
    for unsupported in ("tailgating", "lead_vehicle_braking"):
        if (a.get(unsupported) or {}).get("enabled"):
            raise ConfigError(
                f"'alerts.{unsupported}' needs the vehicle's own speed (GPS/OBD), which the pipeline "
                "doesn't have yet. Keep it disabled."
            )

    def classes(value: Any, where: str) -> frozenset[str]:
        names = frozenset(str(x) for x in (value or []))
        if known_classes is not None:
            bad = sorted(names - set(known_classes))
            if bad:
                raise ConfigError(f"'{where}' has unknown classes {bad}. Valid: {known_classes}")
        return names

    f = _req(a, "forward_collision", "alerts")
    fc = ForwardCollisionConfig(
        enabled=bool(_req(f, "enabled", "alerts.forward_collision")),
        classes=classes(_req(f, "classes", "alerts.forward_collision"), "alerts.forward_collision.classes"),
        ttc_warning_s=_positive(_req(f, "ttc_warning_s", "alerts.forward_collision"), "ttc_warning_s"),
        ttc_critical_s=_positive(_req(f, "ttc_critical_s", "alerts.forward_collision"), "ttc_critical_s"),
        critical_distance_m=_positive(f.get("critical_distance_m", 5.0), "critical_distance_m"),
        vulnerable_classes=classes(f.get("vulnerable_classes"), "alerts.forward_collision.vulnerable_classes"),
        vulnerable_distance_m=_positive(f.get("vulnerable_distance_m", 15.0), "vulnerable_distance_m"),
    )
    if fc.ttc_critical_s > fc.ttc_warning_s:
        raise ConfigError("'ttc_critical_s' must be <= 'ttc_warning_s' (critical is the more urgent level)")

    o = _req(a, "obstacle_in_lane", "alerts")
    ob = ObstacleConfig(
        enabled=bool(_req(o, "enabled", "alerts.obstacle_in_lane")),
        classes=classes(_req(o, "classes", "alerts.obstacle_in_lane"), "alerts.obstacle_in_lane.classes"),
        warning_distance_m=_positive(_req(o, "warning_distance_m", "alerts.obstacle_in_lane"), "warning_distance_m"),
        critical_distance_m=_positive(_req(o, "critical_distance_m", "alerts.obstacle_in_lane"), "critical_distance_m"),
    )
    if ob.critical_distance_m > ob.warning_distance_m:
        raise ConfigError("obstacle 'critical_distance_m' must be <= 'warning_distance_m'")

    confirm_hits = int(_positive(_req(a, "confirm_hits", "alerts"), "alerts.confirm_hits"))
    confirm_window = int(_positive(_req(a, "confirm_window", "alerts"), "alerts.confirm_window"))
    if confirm_hits > confirm_window:
        raise ConfigError("'alerts.confirm_hits' can't be larger than 'alerts.confirm_window'")
    alerts = AlertsConfig(
        confirm_hits=confirm_hits,
        confirm_window=confirm_window,
        episode_gap_s=_positive(_req(a, "episode_gap_s", "alerts"), "alerts.episode_gap_s"),
        forward_collision=fc,
        obstacle_in_lane=ob,
    )

    out = data.get("output") or {}
    output = OutputConfig(
        annotated_video=bool(out.get("annotated_video", True)),
        clips=bool(out.get("clips", True)),
        clip_pre_s=float(out.get("clip_pre_s", 5.0)),
        clip_post_s=float(out.get("clip_post_s", 5.0)),
    )

    return PipelineConfig(
        detector=detector,
        tracker_config=tracker_config,
        camera=camera,
        ego_lane=ego_lane,
        ttc=ttc,
        alerts=alerts,
        output=output,
        raw=data,
    )


def load_classes(path: Path) -> list[str]:
    """Class names ordered by id from the shared configs/classes.yaml contract."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    raw = data["classes"]
    ids = sorted(int(k) for k in raw)
    if ids != list(range(len(ids))):
        raise ConfigError(f"{path}: class ids must be 0..N-1 without gaps, got {ids}")
    return [str(raw[i] if i in raw else raw[str(i)]) for i in ids]


def load_config(path: Path = DEFAULT_CONFIG) -> PipelineConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    classes_file = Path((data.get("detector") or {}).get("classes_file", "configs/classes.yaml"))
    known = load_classes(classes_file) if classes_file.exists() else None
    return parse_config(data, known)
