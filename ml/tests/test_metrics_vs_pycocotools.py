"""Our AP must equal the official COCO evaluator's on the same boxes."""

from __future__ import annotations

import numpy as np
import pytest

from dashcam_ml.metrics import ImageEval, evaluate

pytest.importorskip("pycocotools")
from pycocotools.coco import COCO  # noqa: E402
from pycocotools.cocoeval import COCOeval  # noqa: E402


def random_images(rng: np.random.Generator, n_images: int, n_classes: int) -> list[ImageEval]:
    out = []
    for _ in range(n_images):
        g = rng.integers(0, 6)
        xy = rng.uniform(0, 800, (g, 2))
        gt = np.hstack([xy, xy + rng.uniform(20, 200, (g, 2))])
        gc = rng.integers(0, n_classes, g)
        # predictions: jittered copies of GT (some), plus random false positives
        keep = rng.random(g) < 0.8
        jit = gt[keep] + rng.normal(0, 12, (keep.sum(), 4))
        fp_n = rng.integers(0, 4)
        fxy = rng.uniform(0, 800, (fp_n, 2))
        fp = np.hstack([fxy, fxy + rng.uniform(20, 200, (fp_n, 2))])
        pb = np.vstack([jit, fp]).reshape(-1, 4)
        pb[:, 2:] = np.maximum(pb[:, 2:], pb[:, :2] + 1)
        pc = np.concatenate([gc[keep], rng.integers(0, n_classes, fp_n)])
        ps = rng.uniform(0.01, 1.0, len(pb))
        out.append(ImageEval(gt, gc, pb, pc, ps))
    return out


def coco_reference(images: list[ImageEval], n_classes: int) -> dict[int, tuple[float, float]]:
    anns, dets = [], []
    for i, im in enumerate(images):
        for b, c in zip(im.gt_boxes, im.gt_classes, strict=True):
            w, h = b[2] - b[0], b[3] - b[1]
            anns.append({"id": len(anns) + 1, "image_id": i, "category_id": int(c), "bbox": [*b[:2], w, h],
                         "area": w * h, "iscrowd": 0})
        for b, c, s in zip(im.pred_boxes, im.pred_classes, im.pred_scores, strict=True):
            dets.append({"image_id": i, "category_id": int(c), "bbox": [*b[:2], b[2] - b[0], b[3] - b[1]],
                         "score": float(s)})
    gt = COCO()
    gt.dataset = {"images": [{"id": i} for i in range(len(images))], "annotations": anns,
                  "categories": [{"id": c} for c in range(n_classes)]}
    gt.createIndex()
    ev = COCOeval(gt, gt.loadRes(dets), "bbox")
    ev.params.maxDets = [1, 10, 300]
    ev.params.areaRng, ev.params.areaRngLbl = [ev.params.areaRng[0]], ["all"]
    ev.evaluate()
    ev.accumulate()
    p = ev.eval["precision"][:, :, :, 0, -1]
    ref = {}
    for k in range(n_classes):
        per_t = [p[t, :, k][p[t, :, k] > -1].mean() if (p[t, :, k] > -1).any() else np.nan for t in range(10)]
        ref[k] = (per_t[0], float(np.mean(per_t)))
    return ref


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_matches_pycocotools(seed: int) -> None:
    rng = np.random.default_rng(seed)
    images = random_images(rng, 40, 3)
    ours = evaluate(images, 3)
    ref = coco_reference(images, 3)
    for k in range(3):
        if ours[k]["n_gt"] == 0:
            continue
        assert ours[k]["ap50"] == pytest.approx(ref[k][0], abs=1e-9)
        assert ours[k]["ap50_95"] == pytest.approx(ref[k][1], abs=1e-9)
