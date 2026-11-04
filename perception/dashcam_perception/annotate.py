"""Draw lane, boxes, distance/TTC and active alerts on a frame (OpenCV)."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from dashcam_perception.alerts import AlertEvent, Severity
from dashcam_perception.types import FrameInfo, ObjectState

# BGR
_GREY = (180, 180, 180)
_GREEN = (80, 200, 80)
_AMBER = (0, 170, 255)
_RED = (40, 40, 230)


def draw(
    img: Any,
    frame: FrameInfo,
    states: list[ObjectState],
    active: list[AlertEvent],
    lane: tuple[tuple[float, float], ...],
) -> Any:
    pts = np.array([[x * frame.width, y * frame.height] for x, y in lane], dtype=np.int32)
    overlay = img.copy()
    cv2.fillPoly(overlay, [pts], (90, 160, 90))
    img = cv2.addWeighted(overlay, 0.18, img, 0.82, 0)
    cv2.polylines(img, [pts], True, _GREEN, 2)

    sev_by_track: dict[int, Severity] = {}
    for ev in active:
        prev = sev_by_track.get(ev.track_id)
        if prev is None or ev.severity == Severity.CRITICAL:
            sev_by_track[ev.track_id] = ev.severity

    for s in states:
        b = s.obj.box
        sev = sev_by_track.get(s.obj.track_id)
        color = (
            _RED
            if sev == Severity.CRITICAL
            else _AMBER
            if sev == Severity.WARNING
            else (_GREEN if s.in_ego_lane else _GREY)
        )
        cv2.rectangle(img, (int(b.x1), int(b.y1)), (int(b.x2), int(b.y2)), color, 2)
        parts = [f"#{s.obj.track_id} {s.obj.class_name}"]
        if s.distance_m is not None:
            parts.append(f"~{s.distance_m:.0f}m")
        if s.ttc_s is not None:
            parts.append(f"TTC {s.ttc_s:.1f}s")
        label = " ".join(parts)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        y = max(int(b.y1) - 4, th + 4)
        cv2.rectangle(img, (int(b.x1), y - th - 4), (int(b.x1) + tw + 4, y + 2), color, -1)
        cv2.putText(img, label, (int(b.x1) + 2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

    if active:
        worst = Severity.CRITICAL if any(e.severity == Severity.CRITICAL for e in active) else Severity.WARNING
        text = f"{worst.upper()}: " + ", ".join(sorted({str(e.type).replace("_", " ") for e in active}))
        cv2.rectangle(img, (0, 0), (frame.width, 36), _RED if worst == Severity.CRITICAL else _AMBER, -1)
        cv2.putText(img, text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(
        img, f"t={frame.time_s:6.2f}s", (10, frame.height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1
    )
    return img
