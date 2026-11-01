from __future__ import annotations

import numpy as np
import pytest

from dashcam_ml.metrics import ImageEval, average_precision, box_iou, evaluate, mean_ap


def im(gt, gt_cls, pred, pred_cls, scores) -> ImageEval:
    return ImageEval(np.array(gt, float).reshape(-1, 4), np.array(gt_cls, int),
                     np.array(pred, float).reshape(-1, 4), np.array(pred_cls, int), np.array(scores, float))


def test_iou_basic() -> None:
    a = np.array([[0, 0, 2, 2]], float)
    b = np.array([[1, 1, 3, 3], [0, 0, 2, 2], [5, 5, 6, 6]], float)
    assert box_iou(a, b) == pytest.approx(np.array([[1 / 7, 1.0, 0.0]]))


def test_perfect_predictions_score_one() -> None:
    r = evaluate([im([[0, 0, 1, 1]], [0], [[0, 0, 1, 1]], [0], [0.9])], 2)
    assert r[0]["ap50"] == pytest.approx(1.0) and r[0]["ap50_95"] == pytest.approx(1.0)
    assert r[1]["ap50"] is None  # no ground truth for class 1 -> undefined, not 0


def test_missed_and_wrong_class() -> None:
    r = evaluate([im([[0, 0, 1, 1]], [0], [[0, 0, 1, 1]], [1], [0.9])], 2)
    assert r[0]["ap50"] == 0.0


def test_iou_060_counts_at_050_but_not_at_075() -> None:
    # pred [0,0,1,0.6] vs gt [0,0,1,1]: IoU 0.6 -> TP for t in {0.5, 0.55, 0.6}, FP above
    r = evaluate([im([[0, 0, 1, 1]], [0], [[0, 0, 1, 0.6]], [0], [0.9])], 1)
    assert r[0]["ap50"] == pytest.approx(1.0)
    assert r[0]["ap50_95"] == pytest.approx(0.3)


def test_duplicate_detection_is_false_positive() -> None:
    # Two boxes on one object: the higher score matches, the other is FP. One GT, so
    # precision at recall 1.0 is 1.0 (the TP comes first) and AP stays 1.0.
    r = evaluate([im([[0, 0, 1, 1]], [0], [[0, 0, 1, 1], [0, 0, 1, 1]], [0, 0], [0.9, 0.8])], 1)
    assert r[0]["ap50"] == pytest.approx(1.0)
    # If the duplicate scores higher than... same box, so order doesn't matter; now make the
    # high-score one a miss: FP first, then TP -> precision at recall 1 is 0.5.
    r = evaluate([im([[0, 0, 1, 1]], [0], [[5, 5, 6, 6], [0, 0, 1, 1]], [0, 0], [0.9, 0.8])], 1)
    assert r[0]["ap50"] == pytest.approx(0.5)


def test_hand_computed_two_images() -> None:
    # 2 GTs; predictions by score: TP, FP, TP -> precision envelope 1.0 up to recall 0.5,
    # then 2/3 up to recall 1.0. 101-point AP = (51*1.0 + 50*(2/3)) / 101.
    images = [
        im([[0, 0, 1, 1]], [0], [[0, 0, 1, 1], [3, 3, 4, 4]], [0, 0], [0.9, 0.8]),
        im([[0, 0, 1, 1]], [0], [[0, 0, 1, 1]], [0], [0.7]),
    ]
    r = evaluate(images, 1)
    assert r[0]["ap50"] == pytest.approx((51 * 1.0 + 50 * (2 / 3)) / 101)


def test_average_precision_edge_cases() -> None:
    assert np.isnan(average_precision(np.zeros(0, bool), np.zeros(0), 0))
    assert average_precision(np.zeros(0, bool), np.zeros(0), 3) == 0.0


def test_mean_ap_skips_undefined() -> None:
    per = {0: {"ap50": 0.5}, 1: {"ap50": None}, 2: {"ap50": 1.0}}
    assert mean_ap(per, [0, 1, 2], "ap50") == pytest.approx(0.75)
    assert mean_ap(per, [1], "ap50") is None
