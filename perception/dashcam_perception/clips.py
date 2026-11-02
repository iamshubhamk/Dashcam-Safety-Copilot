"""Cut a short clip around each event from the source video (offline, after the main pass)."""

from __future__ import annotations

from pathlib import Path

import cv2

from dashcam_perception.alerts import AlertEvent


def clip_window(start_s: float, end_s: float, pre_s: float, post_s: float, duration_s: float) -> tuple[float, float]:
    """[start - pre, end + post], clamped to the video. Uses the episode END so a long
    episode is fully inside its clip."""
    return max(0.0, start_s - pre_s), min(duration_s, end_s + post_s)


def write_clips(
    video_path: Path, events: list[AlertEvent], out_dir: Path, fps: float, frame_count: int, pre_s: float, post_s: float
) -> dict[int, str]:
    """Write clips/event_<id>.mp4 and return {event_id: relative path}. One sequential read
    of the video for all clips, so cost doesn't grow with the number of events."""
    if not events:
        return {}
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = frame_count / fps if fps > 0 else 0.0
    windows = {
        e.event_id: tuple(round(t * fps) for t in clip_window(e.start_time_s, e.end_time_s, pre_s, post_s, duration))
        for e in events
    }
    cap = cv2.VideoCapture(str(video_path))
    writers: dict[int, cv2.VideoWriter] = {}
    paths: dict[int, str] = {}
    idx = 0
    last = max(end for _, end in windows.values())
    try:
        while idx <= last:
            ok, img = cap.read()
            if not ok:
                break
            for eid, (a, b) in windows.items():
                if a <= idx <= b:
                    if eid not in writers:
                        h, w = img.shape[:2]
                        p = out_dir / f"event_{eid:04d}.mp4"
                        writers[eid] = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
                        paths[eid] = f"{out_dir.name}/{p.name}"
                    writers[eid].write(img)
                elif idx > b and eid in writers:
                    writers.pop(eid).release()
            idx += 1
    finally:
        cap.release()
        for wr in writers.values():
            wr.release()
    return paths
