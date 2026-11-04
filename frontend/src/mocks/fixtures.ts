/**
 * DEMO DATA. Hand-written to exercise every UI state; none of it came from a real video.
 * The UI shows a "Demo data" banner whenever these are in use.
 *
 * Every EventsDocument here is validated against events.v1.schema.json in
 * src/mocks/fixtures.test.ts, so if the perception contract changes, that test fails.
 */
import type { EventsDocument, MapHazard, Trip, TripReport } from "../api/types";

const ZERO_COUNTS = {
  forward_collision: { warning: 0, critical: 0 },
  obstacle_in_lane: { warning: 0, critical: 0 },
  tailgating: { warning: 0, critical: 0 },
  harsh_braking: { warning: 0, critical: 0 },
};

const OBJECTS_ZERO = {
  car: 0,
  bus: 0,
  truck: 0,
  two_wheeler: 0,
  auto_rickshaw: 0,
  pedestrian: 0,
  animal: 0,
  pothole: 0,
  barricade: 0,
  speed_breaker: 0,
  debris: 0,
};

/** Demo trip with GPS and a few forward-collision events. */
export const docWithGps: EventsDocument = {
  schema_version: "1.0",
  classes_version: 1,
  video: {
    path: "demo_outer_ring_road.mp4",
    duration_s: 312.4,
    fps: 30,
    frames_processed: 9372,
    width: 1920,
    height: 1080,
  },
  thresholds: { ttc_warning_s: 2.7, ttc_critical_s: 1.5 },
  events: [
    {
      event_id: 1,
      type: "forward_collision",
      severity: "warning",
      track_id: 14,
      class_name: "auto_rickshaw",
      start_frame: 1290,
      start_time_s: 43.0,
      end_time_s: 46.2,
      peak_time_s: 45.1,
      min_ttc_s: 2.1,
      min_distance_m: 9.4,
      distance_confidence: "low",
      max_confidence: 0.81,
      peak_box_xyxy: [812, 520, 1104, 790],
      gps: { lat: 12.9352, lon: 77.6245 },
      clip: "clips/event_0001.mp4",
    },
    {
      event_id: 2,
      type: "forward_collision",
      severity: "critical",
      track_id: 37,
      class_name: "two_wheeler",
      start_frame: 4410,
      start_time_s: 147.0,
      end_time_s: 149.3,
      peak_time_s: 148.6,
      min_ttc_s: 1.2,
      min_distance_m: 5.8,
      distance_confidence: "low",
      max_confidence: 0.74,
      peak_box_xyxy: [870, 560, 1050, 860],
      gps: { lat: 12.9279, lon: 77.6271 },
      clip: "clips/event_0002.mp4",
    },
    {
      event_id: 3,
      type: "forward_collision",
      severity: "warning",
      track_id: 52,
      class_name: "bus",
      start_frame: 7650,
      start_time_s: 255.0,
      end_time_s: 259.8,
      peak_time_s: 258.0,
      min_ttc_s: 2.4,
      min_distance_m: 14.2,
      distance_confidence: "low",
      max_confidence: 0.9,
      peak_box_xyxy: [700, 380, 1260, 820],
      gps: { lat: 12.9178, lon: 77.6312 },
      clip: null,
    },
  ],
  hazards: [
    { class: "pothole", track_id: 21, first_seen_s: 88.1, last_seen_s: 89.0, gps: { lat: 12.9318, lon: 77.6259 } },
    { class: "speed_breaker", track_id: 44, first_seen_s: 201.5, last_seen_s: 202.6, gps: { lat: 12.9231, lon: 77.629 } },
  ],
  trip_summary: {
    ttc_below_warning_s: 9.6,
    ttc_below_critical_s: 0.9,
    min_ttc_s: 1.2,
    event_counts: {
      ...ZERO_COUNTS,
      forward_collision: { warning: 2, critical: 1 },
    },
    checks: {
      forward_collision: "ran",
      obstacle_in_lane: "absent",
      tailgating: "skipped_no_ego_speed",
      harsh_braking: "skipped_no_ego_speed",
      gps: "ran",
    },
  },
  objects_seen: {
    ...OBJECTS_ZERO,
    car: 64,
    bus: 9,
    truck: 6,
    two_wheeler: 112,
    auto_rickshaw: 27,
    pedestrian: 18,
    animal: 2,
    pothole: 1,
    speed_breaker: 1,
  },
};

/** Demo trip with no GPS file and no events at all. */
export const docNoGps: EventsDocument = {
  schema_version: "1.0",
  classes_version: 1,
  video: {
    path: "demo_highway_morning.mp4",
    duration_s: 184.0,
    fps: 30,
    frames_processed: 5520,
    width: 1280,
    height: 720,
  },
  thresholds: { ttc_warning_s: 2.7, ttc_critical_s: 1.5 },
  events: [],
  hazards: [{ class: "debris", track_id: 8, first_seen_s: 61.2, last_seen_s: 62.0, gps: null }],
  trip_summary: {
    ttc_below_warning_s: 0,
    ttc_below_critical_s: 0,
    min_ttc_s: null,
    event_counts: ZERO_COUNTS,
    checks: {
      forward_collision: "ran",
      obstacle_in_lane: "absent",
      tailgating: "skipped_no_ego_speed",
      harsh_braking: "skipped_no_ego_speed",
      gps: "skipped_no_gps",
    },
  },
  objects_seen: { ...OBJECTS_ZERO, car: 31, truck: 14, two_wheeler: 22, bus: 3, debris: 1 },
};

export const seedTrips: Trip[] = [
  {
    id: "demo-1",
    label: "Outer Ring Road, evening",
    original_filename: "demo_outer_ring_road.mp4",
    status: "done",
    progress: null,
    error: null,
    created_at: "2026-11-03T13:20:00Z",
    duration_s: 312.4,
    score: 68,
    has_gps: true,
    event_count: 3,
  },
  {
    id: "demo-2",
    label: null,
    original_filename: "demo_highway_morning.mp4",
    status: "done",
    progress: null,
    error: null,
    created_at: "2026-11-02T03:05:00Z",
    duration_s: 184.0,
    score: 94,
    has_gps: false,
    event_count: 0,
  },
  {
    id: "demo-3",
    label: "Corrupted test file",
    original_filename: "broken.mp4",
    status: "failed",
    progress: null,
    error: "Could not read video: no decodable frames",
    created_at: "2026-11-01T10:40:00Z",
    duration_s: null,
    score: null,
    has_gps: false,
    event_count: null,
  },
];

export const seedReports: Record<string, Omit<TripReport, "trip">> = {
  "demo-1": {
    score: 68,
    feedback: [
      { kind: "improve", text: "1 critical close approach (two-wheeler at 2:27). Leave more room in dense two-wheeler traffic." },
      { kind: "improve", text: "About 10 s of the trip had a road user ahead closing in under 2.7 s." },
      { kind: "good", text: "No warnings in the last minute of the trip." },
      { kind: "info", text: "Tailgating and harsh braking were not checked: the video has no speed data." },
    ],
    annotated_video_url: null,
    clip_urls: {},
    events_doc: docWithGps,
  },
  "demo-2": {
    score: 94,
    feedback: [
      { kind: "good", text: "No close approaches detected on this trip." },
      { kind: "info", text: "No GPS file was uploaded, so hazards from this trip are not on the map." },
      { kind: "info", text: "Tailgating and harsh braking were not checked: the video has no speed data." },
    ],
    annotated_video_url: null,
    clip_urls: {},
    events_doc: docNoGps,
  },
};

export const seedHazards: MapHazard[] = [
  { id: "hz-1", class: "pothole", lat: 12.9318, lon: 77.6259, sightings: 3, trip_ids: ["demo-1"], last_seen_at: "2026-11-03T13:21:28Z" },
  { id: "hz-2", class: "speed_breaker", lat: 12.9231, lon: 77.629, sightings: 1, trip_ids: ["demo-1"], last_seen_at: "2026-11-03T13:23:21Z" },
  { id: "hz-3", class: "barricade", lat: 12.9411, lon: 77.6198, sightings: 2, trip_ids: ["demo-1"], last_seen_at: "2026-11-03T13:20:10Z" },
  { id: "hz-4", class: "debris", lat: 12.9142, lon: 77.6335, sightings: 1, trip_ids: ["demo-1"], last_seen_at: "2026-11-03T13:24:40Z" },
];
