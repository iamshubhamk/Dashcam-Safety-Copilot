"""Fine-tune a COCO-pretrained YOLO model on the merged dataset.

    python -m dashcam_ml.train --config ml/configs/train/yolo26s_idd.yaml
    python -m dashcam_ml.train --config ... --set train.epochs=5 train.batch=8   # overrides
    python -m dashcam_ml.train --resume runs/train/yolo26s_idd/weights/last.pt     # after a disconnect

A thin wrapper so the exact settings live in a versioned YAML file instead of a
notebook cell. Ultralytics saves `last.pt` every epoch and `best.pt` (highest val mAP)
under <project>/<name>/weights/. On Kaggle, point `project` at /kaggle/working so the
weights survive in the notebook's output.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from dashcam_ml.classes import DEFAULT_CLASSES, load_classes


def apply_overrides(cfg: dict[str, Any], overrides: list[str]) -> dict[str, Any]:
    """'train.epochs=5' -> cfg['train']['epochs'] = 5 (value parsed as YAML)."""
    for item in overrides:
        key, sep, value = item.partition("=")
        if not sep:
            raise ValueError(f"override {item!r} must look like key=value")
        node = cfg
        *parents, leaf = key.split(".")
        for k in parents:
            node = node.setdefault(k, {})
        node[leaf] = yaml.safe_load(value)
    return cfg


def check_dataset(data_yaml: Path, class_names: list[str]) -> None:
    data = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    names = data["names"]
    got = [names[i] for i in sorted(names)] if isinstance(names, dict) else list(names)
    if got != class_names:
        raise SystemExit(f"{data_yaml} classes {got} != configs/classes.yaml {class_names}. Re-run merge.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, help="training YAML")
    p.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE", help="override config values")
    p.add_argument("--resume", type=Path, help="continue an interrupted run from its last.pt")
    p.add_argument("--classes", type=Path, default=DEFAULT_CLASSES)
    p.add_argument("--export-best", type=Path, default=Path("weights/best.pt"),
                   help="copy the best checkpoint here when training finishes")
    a = p.parse_args(argv)

    from ultralytics import YOLO  # heavy import, only when training

    if a.resume:
        YOLO(str(a.resume)).train(resume=True)
        return 0
    if not a.config:
        p.error("--config is required unless --resume is given")

    cfg = apply_overrides(yaml.safe_load(a.config.read_text(encoding="utf-8")), a.set)
    data_yaml = Path(cfg["data"]).resolve()  # Ultralytics resolves relative dataset paths oddly; be explicit
    check_dataset(data_yaml, load_classes(a.classes))
    print(json.dumps(cfg, indent=2))

    model = YOLO(cfg["model"])
    model.train(data=str(data_yaml), **cfg.get("train", {}))
    best = Path(model.trainer.best)
    if best.exists():
        a.export_best.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(best, a.export_best)
        print(f"best checkpoint copied to {a.export_best}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
