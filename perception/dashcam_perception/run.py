"""CLI: python -m dashcam_perception.run --video x.mp4 --out out/

Run from the repo root (config paths are relative to it). Writes:
  out/events.json      alert events + trip summary (schema v1, see schema.py)
  out/annotated.mp4    video with lane, boxes, distance/TTC and alert banners
  out/clips/           ~5 s before/after each event
  out/run_summary.json frames, processing FPS, event counts (script-produced numbers)
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

from dashcam_perception.alerts import AlertEngine, AlertType
from dashcam_perception.config import DEFAULT_CONFIG, ConfigError, load_classes, load_classes_version, load_config
from dashcam_perception.events import build_document, write_document
from dashcam_perception.scene import SceneEstimator, suppress_riders
from dashcam_perception.schema import SCHEMA_VERSION, Video
from dashcam_perception.summary import TripAccumulator
from dashcam_perception.types import FrameInfo


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect, track and raise collision alerts on a dashcam video.")
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--weights", help="override detector.weights (e.g. weights/best.pt from ml/)")
    p.add_argument("--device", help="override detector.device ('cpu', '0', ...)")
    p.add_argument("--no-video", action="store_true", help="skip the annotated video (faster)")
    p.add_argument("--no-clips", action="store_true", help="skip per-event clips")
    p.add_argument("--max-frames", type=int, help="stop after N frames (quick tests)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        cfg = load_config(args.config)
    except (ConfigError, FileNotFoundError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    if args.weights or args.device:
        cfg = replace(
            cfg,
            detector=replace(
                cfg.detector, weights=args.weights or cfg.detector.weights, device=args.device or cfg.detector.device
            ),
        )
    if not args.video.is_file():
        print(f"video not found: {args.video}", file=sys.stderr)
        return 2

    import cv2  # after arg parsing so --help is instant

    from dashcam_perception.annotate import draw
    from dashcam_perception.clips import write_clips
    from dashcam_perception.detector import Tracker

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        print(f"OpenCV could not open {args.video}", file=sys.stderr)
        return 2
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if fps <= 0 or fps > 240:
        print(f"warning: video reports fps={fps}; assuming 30", file=sys.stderr)
        fps = 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    args.out.mkdir(parents=True, exist_ok=True)
    tracker = Tracker(cfg.detector, cfg.tracker_config)
    scene = SceneEstimator(cfg)
    engine = AlertEngine(cfg.alerts)
    trip = TripAccumulator(cfg.alerts.forward_collision, frame_dt_s=1.0 / fps)
    writer = None
    if cfg.output.annotated_video and not args.no_video:
        writer = cv2.VideoWriter(str(args.out / "annotated.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

    idx = 0
    t0 = time.perf_counter()
    try:
        while args.max_frames is None or idx < args.max_frames:
            ok, img = cap.read()
            if not ok:
                break
            frame = FrameInfo(index=idx, time_s=idx / fps, width=width, height=height)
            objects = tracker(img)
            if cfg.detector.suppress_riders:
                objects = suppress_riders(objects, cfg.detector.rider_overlap)
            states = scene.step(frame, objects)
            active = engine.step(frame, states)
            trip.step(frame, states, {e.track_id for e in active if e.type == AlertType.FORWARD_COLLISION})
            if writer is not None:
                writer.write(draw(img, frame, states, active, cfg.ego_lane.polygon))
            idx += 1
            if idx % 300 == 0:
                print(f"  {idx} frames, {idx / (time.perf_counter() - t0):.1f} fps", file=sys.stderr)
    finally:
        cap.release()
        if writer is not None:
            writer.release()
    elapsed = time.perf_counter() - t0
    events = engine.finish()

    clips: dict[int, str] = {}
    if cfg.output.clips and not args.no_clips:
        clips = write_clips(
            args.video, events, args.out / "clips", fps, idx, cfg.output.clip_pre_s, cfg.output.clip_post_s
        )

    classes_file = Path(cfg.detector.classes_file)
    doc = build_document(
        cfg,
        classes_version=load_classes_version(classes_file),
        class_names=load_classes(classes_file),
        detector_classes=set(tracker.label_map.values()),
        video=Video(
            path=str(args.video),
            duration_s=round(idx / fps, 3),
            fps=fps,
            frames_processed=idx,
            width=width,
            height=height,
        ),
        events=events,
        trip=trip,
        clips=clips,
    )
    write_document(args.out / "events.json", doc)

    run_meta = {
        "weights": cfg.detector.weights,
        "coco_mapped": tracker.uses_coco,
        "config": str(args.config),
        "device": cfg.detector.device or "auto",
    }
    summary = {
        "schema_version": SCHEMA_VERSION,
        "frames": idx,
        "seconds": round(elapsed, 2),
        # End-to-end processing speed (decode + detect + track + rules + drawing/encoding).
        # Not a clean model benchmark; that's the M8 benchmark script's job.
        "pipeline_fps": round(idx / elapsed, 2) if elapsed > 0 else None,
        "events_by_type": dict(Counter(str(e.type) for e in events)),
        "events_by_severity": dict(Counter(str(e.severity) for e in events)),
        "machine": {"platform": platform.platform(), "python": platform.python_version()},
        **run_meta,
    }
    (args.out / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
