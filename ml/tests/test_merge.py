from __future__ import annotations

import json
from pathlib import Path

import yaml

from conftest import make_image
from dashcam_ml import merge
from dashcam_ml.stats import compute_stats


def make_pool(root: Path, name: str, items: list[tuple[str, str, str, tuple[int, int, int]]]) -> None:
    """items: (image name, group, label text, colour). Same colour => identical bytes."""
    manifest = []
    for img, group, label, color in items:
        make_image(root / name / "images" / f"{img}.png", color=color)
        (root / name / "labels").mkdir(parents=True, exist_ok=True)
        (root / name / "labels" / f"{img}.txt").write_text(label)
        manifest.append({"name": img, "group": group, "source_split": "train"})
    (root / name / "manifest.json").write_text(json.dumps({"report": {"license": "CC BY 4.0"}, "images": manifest}))


def test_assign_split_is_deterministic_and_roughly_proportional() -> None:
    groups = [f"g{i}" for i in range(2000)]
    a = [merge.assign_split(g, 0.15, 0) for g in groups]
    assert a == [merge.assign_split(g, 0.15, 0) for g in groups]
    assert 0.12 < a.count("val") / len(a) < 0.18
    assert a != [merge.assign_split(g, 0.15, 1) for g in groups]


def test_merge_keeps_groups_together_and_dedupes(tmp_path: Path, class_names: list[str]) -> None:
    obs = tmp_path / "obstacles"
    pid = class_names.index("pothole")
    items = []
    for g in range(30):  # 30 photos x 3 augmented copies, each copy distinct bytes
        for k in range(3):
            items.append((f"a__train__p{g}_{k}", f"a/p{g}", f"{pid} 0.5 0.5 0.1 0.1\n", (g, k, 1)))
    make_pool(obs, "a", items)
    make_pool(obs, "b", [("b__train__dup", "b/dup", f"{pid} 0.5 0.5 0.1 0.1\n", (0, 0, 1))])  # same bytes as p0_0

    out = tmp_path / "merged"
    summary = merge.merge(None, obs, out, class_names, val_frac=0.3, seed=0, mode="copy")
    assert summary["duplicates_removed"] == 1
    split_of = {}
    for split in ("train", "val"):
        for f in (out / "labels" / split).glob("*.txt"):
            split_of.setdefault(f.stem.rsplit("_", 1)[0], set()).add(split)
    assert all(len(s) == 1 for s in split_of.values()), "augmented copies straddle train/val"
    assert {s for v in split_of.values() for s in v} == {"train", "val"}

    data = yaml.safe_load((out / "data.yaml").read_text())
    assert data["names"][4] == "auto_rickshaw" and "path" not in data

    stats = compute_stats(out, class_names)
    total = sum(stats["splits"][s]["boxes_per_class"]["pothole"] for s in ("train", "val"))
    assert total == 90
    per_src = [stats["splits"][s]["per_source"]["a"]["images"] for s in ("train", "val")]
    assert sum(per_src) == 90


def test_merge_keeps_idd_split(tmp_path: Path, class_names: list[str]) -> None:
    idd = tmp_path / "idd"
    for split in ("train", "val"):
        make_image(idd / "images" / split / f"idd__{split}1.jpg")
        (idd / "labels" / split).mkdir(parents=True)
        (idd / "labels" / split / f"idd__{split}1.txt").write_text("0 0.5 0.5 0.2 0.2\n")
    out = tmp_path / "merged"
    merge.merge(idd, None, out, class_names, mode="copy")
    assert (out / "images/val/idd__val1.jpg").exists() and (out / "labels/train/idd__train1.txt").exists()
