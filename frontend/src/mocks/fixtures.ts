/**
 * DEMO DATA. Hand-written to exercise every UI state; none of it came from a real video.
 * The UI shows a "Demo data" banner whenever these are in use.
 *
 * The EventsDocuments are validated against events.v1.schema.json (fixtures.test.ts), and the
 * API responses built from them against openapi.v1.json (api/openapi.contract.test.ts), so a
 * change on either side makes a test fail.
 */
import type { EventsDocument, MapHazard, Report, Trip, TripEvent } from "../api/types";

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

export const DEMO_TRIP_1 = "0b6f3c1e-5d4a-4c1f-9a51-2f0c7d1e8a01";
export const DEMO_TRIP_2 = "0b6f3c1e-5d4a-4c1f-9a51-2f0c7d1e8a02";
export const DEMO_TRIP_3 = "0b6f3c1e-5d4a-4c1f-9a51-2f0c7d1e8a03";

/** Flatten events.json events the way the backend does (GET /trips/{id}/events). */
export function toTripEvents(tripId: string, doc: EventsDocument, idOffset: number): TripEvent[] {
  return doc.events.map((e) => ({
    id: idOffset + e.event_id,
    trip_id: tripId,
    type: e.type,
    severity: e.severity,
    class_name: e.class_name,
    track_id: e.track_id,
    start_s: e.start_time_s,
    end_s: e.end_time_s,
    peak_s: e.peak_time_s,
    min_ttc_s: e.min_ttc_s,
    min_distance_m: e.min_distance_m,
    distance_confidence: e.distance_confidence,
    max_confidence: e.max_confidence,
    lat: e.gps?.lat ?? null,
    lon: e.gps?.lon ?? null,
    has_clip: e.clip !== null,
    metrics: {},
  }));
}

const baseTrip = {
  source: "upload",
  has_original_video: true,
  has_annotated_video: false,
  error: null,
} as const;

export const seedTrips: Trip[] = [
  {
    ...baseTrip,
    id: DEMO_TRIP_1,
    label: "Outer Ring Road, evening",
    original_filename: "demo_outer_ring_road.mp4",
    status: "done",
    duration_s: 312.4,
    distance_km: 3.9,
    score: 68,
    has_gps: true,
    event_count: 3,
    created_at: "2026-11-03T13:20:00Z",
    processed_at: "2026-11-03T13:27:41Z",
  },
  {
    ...baseTrip,
    id: DEMO_TRIP_2,
    label: null,
    original_filename: "demo_highway_morning.mp4",
    status: "done",
    duration_s: 184.0,
    distance_km: null,
    score: 94,
    has_gps: false,
    event_count: 0,
    created_at: "2026-11-02T03:05:00Z",
    processed_at: "2026-11-02T03:09:12Z",
  },
  {
    ...baseTrip,
    id: DEMO_TRIP_3,
    label: "Corrupted test file",
    original_filename: "broken.mp4",
    status: "failed",
    duration_s: null,
    distance_km: null,
    score: null,
    has_gps: false,
    event_count: 0,
    error: "Could not read video: no decodable frames",
    created_at: "2026-11-01T10:40:00Z",
    processed_at: "2026-11-01T10:40:09Z",
  },
];

export const seedEvents: Record<string, TripEvent[]> = {
  [DEMO_TRIP_1]: toTripEvents(DEMO_TRIP_1, docWithGps, 100),
  [DEMO_TRIP_2]: toTripEvents(DEMO_TRIP_2, docNoGps, 200),
};

const NOT_CHECKED_NO_SPEED = [
  {
    type: "obstacle_in_lane",
    label: "Obstacles in your lane",
    status: "absent",
    reason: "The current detection model can't see road obstacles yet.",
  },
  {
    type: "tailgating",
    label: "Tailgating",
    status: "skipped_no_ego_speed",
    reason: "Needs your vehicle's speed, which this video doesn't have.",
  },
  {
    type: "harsh_braking",
    label: "Harsh braking ahead",
    status: "skipped_no_ego_speed",
    reason: "Needs your vehicle's speed, which this video doesn't have.",
  },
];

const reportBase = {
  exposure_unit: "per_hour",
  scoring_version: 1,
} as const;

/** report.breakdown.trip as the backend builds it from events.json trip_summary. */
function breakdownFrom(doc: EventsDocument, videoCodec: string) {
  return {
    trip: {
      ttc_below_warning_s: doc.trip_summary.ttc_below_warning_s,
      ttc_below_critical_s: doc.trip_summary.ttc_below_critical_s,
      min_ttc_s: doc.trip_summary.min_ttc_s,
      objects_seen: doc.objects_seen,
      gps: doc.trip_summary.checks.gps,
      thresholds: doc.thresholds,
      classes_version: doc.classes_version,
      video_codec: videoCodec,
    },
  };
}

export const seedReports: Record<string, Report> = {
  [DEMO_TRIP_1]: {
    ...reportBase,
    trip_id: DEMO_TRIP_1,
    breakdown: breakdownFrom(docWithGps, "h264"),
    score: 68,
    risk_rate: 41.5,
    exposure_value: 0.087,
    provisional: true,
    feedback: [
      {
        kind: "issue",
        text: "1 critical close approach to a two-wheeler. Leave more room in dense two-wheeler traffic.",
        event_ids: [102],
        type: "forward_collision",
      },
      {
        kind: "pattern",
        text: "About 10 s of the trip had a road user ahead closing in under 2.7 s.",
        event_ids: [],
        type: null,
      },
      { kind: "worst_moments", text: "Your closest calls on this trip.", event_ids: [102, 101], type: null },
      { kind: "positive", text: "No warnings in the last minute of the trip.", event_ids: [], type: null },
    ],
    not_checked: NOT_CHECKED_NO_SPEED,
  },
  [DEMO_TRIP_2]: {
    ...reportBase,
    trip_id: DEMO_TRIP_2,
    breakdown: breakdownFrom(docNoGps, "mp4v"),
    score: 94,
    risk_rate: 0,
    exposure_value: 0.051,
    provisional: true,
    feedback: [{ kind: "positive", text: "No close approaches detected on this trip.", event_ids: [], type: null }],
    not_checked: [
      ...NOT_CHECKED_NO_SPEED,
      {
        type: "gps",
        label: "Map positions",
        status: "skipped_no_gps",
        reason: "No GPS file was uploaded, so hazards from this trip are not on the map.",
      },
    ],
  },
};

export const seedHazards: MapHazard[] = [
  { id: 1, hazard_class: "pothole", lat: 12.9318, lon: 77.6259, seen_count: 3, trip_count: 2, first_seen_at: "2026-10-28T09:10:00Z", last_seen_at: "2026-11-03T13:21:28Z" },
  { id: 2, hazard_class: "speed_breaker", lat: 12.9231, lon: 77.629, seen_count: 1, trip_count: 1, first_seen_at: "2026-11-03T13:23:21Z", last_seen_at: "2026-11-03T13:23:21Z" },
  { id: 3, hazard_class: "barricade", lat: 12.9411, lon: 77.6198, seen_count: 2, trip_count: 1, first_seen_at: "2026-11-03T13:20:05Z", last_seen_at: "2026-11-03T13:20:10Z" },
  { id: 4, hazard_class: "debris", lat: 12.9142, lon: 77.6335, seen_count: 1, trip_count: 1, first_seen_at: "2026-11-03T13:24:40Z", last_seen_at: "2026-11-03T13:24:40Z" },
];
