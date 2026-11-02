"""Ultralytics YOLO + ByteTrack wrapper: frame in, TrackedObjects (our class names) out.

This is the only module that imports torch/ultralytics, so everything downstream stays
testable without a GPU or model weights.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dashcam_perception.config import ConfigError, DetectorConfig, load_classes
from dashcam_perception.types import Box, TrackedObject


def build_label_map(
    model_names: dict[int, str], our_classes: list[str], coco_map: dict[str, str | None]
) -> dict[int, str]:
    """Map the model's class ids to our class names.

    - Fine-tuned model (trained in ml/ on configs/classes.yaml): names match ours 1:1.
    - Stock COCO model: map through ml/configs/coco_map.yaml; unmapped COCO classes
      (chairs, laptops, traffic lights...) are ignored.
    """
    ours = set(our_classes)
    if set(model_names.values()) <= ours:
        return dict(model_names)
    mapping: dict[int, str] = {}
    for idx, name in model_names.items():
        target = coco_map.get(name)
        if target is None:
            continue
        if target not in ours:
            raise ConfigError(f"coco_map maps {name!r} to unknown class {target!r}")
        mapping[idx] = target
    if not mapping:
        raise ConfigError(
            f"model classes {sorted(model_names.values())[:10]}... match neither configs/classes.yaml "
            "nor the COCO map, so nothing would be detected"
        )
    return mapping


class Tracker:
    """Runs detection + ByteTrack on consecutive frames of ONE video."""

    def __init__(self, cfg: DetectorConfig, tracker_config: str) -> None:
        from ultralytics import YOLO  # heavy import kept local

        self.cfg = cfg
        self.tracker_config = str(Path(tracker_config))
        self.model = YOLO(cfg.weights)
        coco_map = yaml.safe_load(Path(cfg.coco_map).read_text(encoding="utf-8")) or {}
        self.label_map = build_label_map(dict(self.model.names), load_classes(Path(cfg.classes_file)), coco_map)
        self.uses_coco = set(self.model.names.values()) != set(self.label_map.values())

    def __call__(self, frame: Any) -> list[TrackedObject]:
        results = self.model.track(
            frame,
            persist=True,  # keep tracker state between calls (same video)
            tracker=self.tracker_config,
            conf=self.cfg.conf,
            iou=self.cfg.iou,
            imgsz=self.cfg.imgsz,
            device=self.cfg.device,
            classes=sorted(self.label_map),
            verbose=False,
        )
        boxes = results[0].boxes
        if boxes is None or boxes.id is None:
            return []  # no confirmed tracks this frame
        out: list[TrackedObject] = []
        for xyxy, cls, conf, tid in zip(
            boxes.xyxy.tolist(), boxes.cls.tolist(), boxes.conf.tolist(), boxes.id.tolist(), strict=True
        ):
            name = self.label_map.get(int(cls))
            if name is None:
                continue
            out.append(TrackedObject(track_id=int(tid), class_name=name, confidence=float(conf), box=Box(*xyxy)))
        return out
