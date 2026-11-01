"""COCO-style average precision, implemented once and used for BOTH models.

Why our own implementation instead of Ultralytics' `model.val()`: the COCO baseline
predicts COCO classes (80 of them), not ours, so its outputs must be remapped before
scoring. Scoring both models with the same code on the same images is the only way the
"fine-tuned vs baseline" comparison is fair. `evaluate.py --crosscheck` also runs
Ultralytics' own validator on the fine-tuned model so the two implementations can be
compared.

Definitions (standard COCO):
- A prediction is a true positive at IoU threshold t if it overlaps a not-yet-matched
  ground-truth box of the same class with IoU >= t (higher-confidence predictions match first).
- AP = area under the precision-recall curve, sampled at 101 recall points.
- AP50 uses t = 0.5; AP50-95 averages t = 0.50, 0.55, ..., 0.95.
- Classes with no ground-truth boxes have undefined AP and are left out of the mean.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

IOU_THRESHOLDS = np.linspace(0.5, 0.95, 10)
RECALL_POINTS = np.linspace(0.0, 1.0, 101)


@dataclass
class ImageEval:
    """Boxes in xyxy (any consistent units; IoU doesn't depend on scale)."""

    gt_boxes: np.ndarray  # (G, 4)
    gt_classes: np.ndarray  # (G,)
    pred_boxes: np.ndarray  # (P, 4)
    pred_classes: np.ndarray  # (P,)
    pred_scores: np.ndarray  # (P,)


def box_iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU matrix (len(a), len(b)) for xyxy boxes."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    tl = np.maximum(a[:, None, :2], b[None, :, :2])
    br = np.minimum(a[:, None, 2:], b[None, :, 2:])
    inter = np.prod(np.clip(br - tl, 0, None), axis=2)
    area_a = np.prod(a[:, 2:] - a[:, :2], axis=1)
    area_b = np.prod(b[:, 2:] - b[:, :2], axis=1)
    return inter / np.maximum(area_a[:, None] + area_b[None, :] - inter, 1e-12)


def match_image(pred_boxes: np.ndarray, pred_scores: np.ndarray, gt_boxes: np.ndarray) -> np.ndarray:
    """For one image and one class: (P, T) bool, whether each prediction is a TP at each threshold."""
    tp = np.zeros((len(pred_boxes), len(IOU_THRESHOLDS)), dtype=bool)
    if len(pred_boxes) == 0 or len(gt_boxes) == 0:
        return tp
    order = np.argsort(-pred_scores, kind="stable")
    ious = box_iou(pred_boxes[order], gt_boxes)
    for t_idx, t in enumerate(IOU_THRESHOLDS):
        taken = np.zeros(len(gt_boxes), dtype=bool)
        for p_idx in np.flatnonzero(ious.max(axis=1) >= t):  # others can't match at this t
            cand = np.where(taken, -1.0, ious[p_idx])
            g = int(cand.argmax())
            if cand[g] >= t:
                taken[g] = True
                tp[order[p_idx], t_idx] = True
    return tp


def average_precision(tp: np.ndarray, scores: np.ndarray, n_gt: int) -> float:
    """101-point interpolated AP for one class at one IoU threshold."""
    if n_gt == 0:
        return float("nan")
    if len(tp) == 0:
        return 0.0
    order = np.argsort(-scores, kind="stable")
    tp_sorted = tp[order].astype(float)
    ctp = np.cumsum(tp_sorted)
    cfp = np.cumsum(1.0 - tp_sorted)
    recall = ctp / n_gt
    precision = ctp / np.maximum(ctp + cfp, 1e-12)
    precision = np.maximum.accumulate(precision[::-1])[::-1]  # make it non-increasing
    idx = np.searchsorted(recall, RECALL_POINTS, side="left")
    sampled = np.where(idx < len(precision), precision[np.minimum(idx, len(precision) - 1)], 0.0)
    return float(sampled.mean())


def evaluate(images: list[ImageEval], num_classes: int) -> dict[int, dict]:
    """Per-class {'n_gt', 'n_pred', 'ap50', 'ap50_95'}; ap* are None when n_gt == 0."""
    per_class_tp: dict[int, list[np.ndarray]] = {c: [] for c in range(num_classes)}
    per_class_scores: dict[int, list[np.ndarray]] = {c: [] for c in range(num_classes)}
    n_gt = np.zeros(num_classes, dtype=int)
    for im in images:
        for c in range(num_classes):
            g = im.gt_boxes[im.gt_classes == c]
            pm = im.pred_classes == c
            n_gt[c] += len(g)
            if pm.any():
                per_class_tp[c].append(match_image(im.pred_boxes[pm], im.pred_scores[pm], g))
                per_class_scores[c].append(im.pred_scores[pm])
    out: dict[int, dict] = {}
    for c in range(num_classes):
        tp = np.concatenate(per_class_tp[c]) if per_class_tp[c] else np.zeros((0, len(IOU_THRESHOLDS)), bool)
        sc = np.concatenate(per_class_scores[c]) if per_class_scores[c] else np.zeros(0)
        if n_gt[c] == 0:
            out[c] = {"n_gt": 0, "n_pred": int(len(sc)), "ap50": None, "ap50_95": None}
            continue
        aps = [average_precision(tp[:, t], sc, int(n_gt[c])) for t in range(len(IOU_THRESHOLDS))]
        out[c] = {"n_gt": int(n_gt[c]), "n_pred": int(len(sc)), "ap50": aps[0], "ap50_95": float(np.mean(aps))}
    return out


def mean_ap(per_class: dict[int, dict], classes: list[int], key: str) -> float | None:
    vals = [per_class[c][key] for c in classes if per_class[c][key] is not None]
    return float(np.mean(vals)) if vals else None
