# perception/

Phase 2: dashcam video in, alert events out.

```
frame ─► YOLO detect ─► ByteTrack ─► per-object: in our lane? distance? TTC? ─► alert rules ─► events.json
                                                                                     └► annotated.mp4, clips/
```

## Run it

From the repo root (config paths are relative to it):

```bash
pip install -e "perception[run,dev]"          # Ultralytics pulls in PyTorch + OpenCV
python -m dashcam_perception.run --video data/videos/trip1.mp4 --out out/trip1
python -m dashcam_perception.run --video x.mp4 --out out/x --weights weights/best.pt   # fine-tuned model from ml/
pytest perception                              # unit tests, no GPU or weights needed
```

Install [ffmpeg](https://ffmpeg.org/download.html) and put it on PATH (on Windows, e.g. `winget install ffmpeg`)
so the annotated video and clips are converted to H.264, which browsers can play. Without it they stay
MPEG-4 Part 2 and the run prints a warning; `run_summary.json` records `video_codec`.

Exit codes: `0` success; `2` permanent failure (bad config, missing or unreadable video), so don't
retry; anything else (e.g. GPU out of memory) may work on retry. The backend worker relies on this.

Useful flags: `--device cpu`, `--no-video` (skip drawing, faster), `--no-clips`, `--max-frames 300`.

Outputs in `--out`:

| file | what |
|---|---|
| `events.json` | alert events, trip summary, hazards, objects seen (schema v1, see below) |
| `annotated.mp4` | lane area, boxes, `~distance` and TTC labels, alert banner |
| `clips/event_NNNN.mp4` | 5 s before the alert to 5 s after it ends |
| `run_summary.json` | frames, end-to-end FPS, event counts by type and severity |

Before the fine-tuned model exists, the stock COCO model (`yolo26s.pt`) is used and its
labels are mapped with `ml/configs/coco_map.yaml`. COCO has no auto-rickshaw or road
obstacles, so obstacle alerts can't fire until the fine-tuned model is plugged in.

## events.json (schema v1)

The contract with the backend and dashboard, agreed with the architecture thread. The pydantic
models in [`dashcam_perception/schema.py`](dashcam_perception/schema.py) are the source of truth;
[`schema/events.v1.json`](schema/events.v1.json) is the exported JSON Schema for other languages.
After changing a model, run `python -m dashcam_perception.schema` from the repo root (a test
fails if the file is stale).

- `events`: one per alert episode (type, severity, times, closest TTC and distance, clip).
  `distance_confidence` is `"low"` until `camera.calibrated: true` in the config.
- `trip_summary`: seconds spent with a confirmed forward-collision risk at TTC below the
  warning/critical thresholds, the trip's closest call (`min_ttc_s`), event counts (zero-filled),
  and `checks`, which says what ran and what was skipped (no speed, no GPS, or a class the
  model can't see) so the report never implies "all clear" for something it didn't check.
  Only confirmed alerts count, so a one-frame glitch can't set the closest call.
- `hazards`: one per tracked pothole/barricade/speed breaker/debris, for the hazard map.
- `objects_seen`: unique tracks per class. A tracker can split one vehicle into two ids after a
  long occlusion, so treat these as approximate counts.

## How it decides (and why)

All thresholds are in [`configs/default.yaml`](configs/default.yaml). The design bias, agreed
with Shubham: **never miss a real risk; a few false alarms are acceptable.**

**Ego lane.** A trapezoid in front of the vehicle. An object counts as "in our lane" when at
least 20% of its *bottom edge* (where it touches the road) is inside. Using the bottom edge
stops a tall truck in the next lane from triggering alerts just because its roof overlaps
the trapezoid. The top of the trapezoid sits just below the horizon so the lane reaches
~80 m ahead; a shorter lane would miss early warnings at highway speed (there's a test for this).

**Time-to-collision (TTC).** As an object approaches at constant speed, its size in the
image grows so that d(ln size)/dt = 1/TTC. We fit a line to ln(size) over the last 0.6 s
and correct for the fit's built-in lag (the fit measures the window's middle, not now).
This needs **no camera calibration**, which matters because we don't know the camera yet.
Limitations: assumes steady closing speed (sudden braking makes it optimistic for a few
frames), and detector box jitter adds noise.

**Distance (approximate).** Two classic monocular tricks, taking the closer answer because
over-estimating distance is the dangerous mistake:
1. Ground plane: with the camera at a known height, how far below the horizon an object's
   wheels sit tells you how far away it is. Breaks on slopes and speed breakers.
2. Known width: a car is ~1.8 m wide, so its width in pixels gives distance. Breaks for
   unusual vehicles and side-on views.

With the default (uncalibrated) camera values, expect 20 to 40% error, so distances are shown
as `~12m` and stored as `min_distance_m_approx`. Set `camera:` in the YAML once you know your
camera's field of view and mount height.

**Alert rules.**

| alert | warning | critical |
|---|---|---|
| forward collision (vehicle, pedestrian, animal in our lane) | TTC ≤ 4 s, or a pedestrian/animal within ~15 m | TTC ≤ 2 s, or closing in and within ~5 m |
| obstacle in lane (pothole, barricade, speed breaker, debris) | within ~30 m | within ~12 m |
| tailgating, lead-vehicle braking | off: they need our own speed (GPS/OBD), which we don't have yet. The config refuses to enable them. |

**Noise gates on TTC.** A first run on a calm public highway clip raised false alarms from far,
weakly detected cars (~15 px) whose boxes "grew" as the detector settled. Two gates fixed it:
TTC is only computed for boxes at least `ttc.min_size_px` (22 px) in size, and only when the
growth trend is clearly bigger than its own noise (`ttc.min_significance`). The cost is range,
not near-field recall: at 80 km/h the first warning now comes about 3 s before impact instead
of 4 s, and city-speed warnings are unchanged (both cases are covered by tests).

A condition must hold in 2 of the last 3 frames of that object (about 70 ms) before it alerts,
so a single glitchy frame can't trigger it. While the same object keeps triggering, that's
one event with its worst severity; it closes after 1 s without the condition.

COCO detects a motorbike rider as a separate "person". A person box that sits mostly on a
two-wheeler is treated as the rider and dropped, so riders don't raise pedestrian alerts.

## What's not done yet

- No accuracy numbers: measuring missed and false alerts needs our own labelled footage
  (milestone M9). Until then the only evidence is the unit tests (synthetic approaching and
  passing cars) and visual checks of the annotated video.
- GPS is `null` in events; the backend will attach it from a GPX/CSV sidecar.
- `run_summary.json` FPS is end to end (decode + model + drawing), not a clean model
  benchmark; that's the M8 benchmark script.
