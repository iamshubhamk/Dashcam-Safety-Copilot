"""Load the shared class list (configs/classes.yaml) and label-mapping files."""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_CLASSES = Path("configs/classes.yaml")


class MappingError(ValueError):
    """A mapping file references a class that doesn't exist, or misses a source label."""


def load_classes(path: Path = DEFAULT_CLASSES) -> list[str]:
    """Return class names ordered by id. Ids must be 0..N-1 with no gaps."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    raw = data["classes"]
    ids = sorted(int(k) for k in raw)
    if ids != list(range(len(ids))):
        raise MappingError(f"{path}: class ids must be 0..N-1 without gaps, got {ids}")
    names = [str(raw[i] if i in raw else raw[str(i)]) for i in ids]
    if len(set(names)) != len(names):
        raise MappingError(f"{path}: duplicate class names")
    return names


def load_class_groups(path: Path = DEFAULT_CLASSES) -> dict[str, list[str]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return {k: list(v) for k, v in (data.get("groups") or {}).items()}


def resolve_mapping(raw: dict[str, str | None], class_names: list[str], where: str) -> dict[str, int | None]:
    """Turn {source_label: target_name | None} into {source_label: target_id | None}.

    Raises MappingError if a target name is not one of our classes, which catches typos
    like "two-wheeler" vs "two_wheeler" before any data is written.
    """
    index = {name: i for i, name in enumerate(class_names)}
    out: dict[str, int | None] = {}
    bad: list[str] = []
    for src, dst in raw.items():
        if dst is None:
            out[str(src)] = None
        elif dst in index:
            out[str(src)] = index[dst]
        else:
            bad.append(f"{src!r} -> {dst!r}")
    if bad:
        raise MappingError(f"{where}: unknown target classes: {', '.join(bad)}. Valid: {class_names}")
    return out


def load_flat_mapping(path: Path, class_names: list[str]) -> dict[str, int | None]:
    """Load a flat {label: target} YAML (idd_mapping.yaml, coco_map.yaml)."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return resolve_mapping(raw, class_names, str(path))
