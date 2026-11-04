/**
 * Types for the data the dashboard shows.
 *
 * Part 1 mirrors events.json schema 1.0 (perception/schema/events.v1.json, vendored here as
 * events.v1.schema.json). The perception pydantic models are the source of truth; a test
 * validates every mock document against the vendored JSON Schema so drift shows up fast.
 *
 * Part 2 is the API wrapper (trips, reports, score). The backend thread owns the real
 * OpenAPI; these shapes are the dashboard's proposal until that lands.
 */

// ---------- Part 1: events.json v1 ----------

export const EVENT_TYPES = [
  "forward_collision",
  "obstacle_in_lane",
  "tailgating",
  "harsh_braking",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

export type Severity = "warning" | "critical";

export type CheckStatus = "ran" | "skipped_no_ego_speed" | "skipped_no_gps" | "absent";

export const CHECK_KEYS = [
  "forward_collision",
  "obstacle_in_lane",
  "tailgating",
  "harsh_braking",
  "gps",
] as const;
export type CheckKey = (typeof CHECK_KEYS)[number];
export type Checks = Record<CheckKey, CheckStatus>;

export interface GPS {
  lat: number;
  lon: number;
}

export interface SafetyEvent {
  event_id: number;
  type: EventType;
  severity: Severity;
  track_id: number;
  class_name: string;
  start_frame: number;
  start_time_s: number;
  end_time_s: number;
  peak_time_s: number;
  min_ttc_s: number | null;
  min_distance_m: number | null;
  /** "low" while the camera is uncalibrated: distances can be off by 20-40% */
  distance_confidence: "low" | "ok";
  max_confidence: number;
  peak_box_xyxy: [number, number, number, number];
  gps: GPS | null;
  /** Clip path relative to the pipeline output folder, if clips were written */
  clip: string | null;
}

export type HazardClass = "pothole" | "barricade" | "speed_breaker" | "debris";

export interface Hazard {
  class: HazardClass;
  track_id: number;
  first_seen_s: number;
  last_seen_s: number;
  gps: GPS | null;
}

export interface TripSummary {
  ttc_below_warning_s: number;
  ttc_below_critical_s: number;
  min_ttc_s: number | null;
  /** Always lists all 4 event types, zero-filled */
  event_counts: Record<EventType, Partial<Record<Severity, number>>>;
  checks: Checks;
}

export interface EventsDocument {
  schema_version?: "1.0";
  classes_version: number;
  video: {
    path: string;
    duration_s: number;
    fps: number;
    frames_processed: number;
    width: number;
    height: number;
  };
  thresholds: { ttc_warning_s: number; ttc_critical_s: number };
  events: SafetyEvent[];
  hazards: Hazard[];
  trip_summary: TripSummary;
  /** Unique tracked objects per class (classes.yaml names), not per-frame detections */
  objects_seen: Record<string, number>;
}

// ---------- Part 2: backend API v1 (mirrors openapi.v1.json; the backend owns it) ----------
// src/api/openapi.contract.test.ts validates the demo responses against the vendored spec.

export type TripStatus = "queued" | "processing" | "done" | "failed";

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface Trip {
  id: string;
  label: string | null;
  status: TripStatus;
  /** "upload" or "import" (results bundle from Kaggle) */
  source: string;
  original_filename: string | null;
  duration_s: number | null;
  distance_km: number | null;
  has_gps: boolean;
  has_original_video: boolean;
  has_annotated_video: boolean;
  /** 0-100, computed by the backend from configs/risk.yaml; null until done */
  score: number | null;
  event_count: number;
  error: string | null;
  created_at: string;
  processed_at: string | null;
}

/** One risky moment, flattened from events.json by the backend. */
export interface TripEvent {
  id: number;
  trip_id: string;
  type: EventType;
  severity: Severity;
  class_name: string;
  track_id: number;
  start_s: number;
  end_s: number;
  peak_s: number;
  min_ttc_s: number | null;
  min_distance_m: number | null;
  distance_confidence: "low" | "ok";
  max_confidence: number;
  lat: number | null;
  lon: number | null;
  has_clip: boolean;
  metrics: Record<string, unknown>;
}

/** Known kinds; anything else is shown as a neutral note. */
export type FeedbackKind = "issue" | "positive" | "pattern" | "worst_moments" | (string & {});

export interface FeedbackLine {
  kind: FeedbackKind;
  text: string;
  /** Events this line is about; the UI links them to the clip player */
  event_ids: number[];
  type?: string | null;
}

/** A check that did not run for this trip. Anything listed here must read "Not checked". */
export interface NotChecked {
  type: string;
  label: string;
  /** e.g. skipped_no_ego_speed, skipped_no_gps, absent */
  status: string;
  reason: string;
}

export interface Report {
  trip_id: string;
  score: number | null;
  risk_rate: number | null;
  exposure_unit: string;
  exposure_value: number;
  /** True when too little was checked (or the trip is too short) for the score to mean much */
  provisional: boolean;
  scoring_version: number;
  breakdown: Record<string, unknown>;
  feedback: FeedbackLine[];
  not_checked: NotChecked[];
}

export interface MapHazard {
  id: number;
  hazard_class: HazardClass;
  lat: number;
  lon: number;
  seen_count: number;
  trip_count: number;
  first_seen_at: string;
  last_seen_at: string;
}

export interface HazardList {
  items: MapHazard[];
  /** True when the box held more hazards than the server returns; zoom in to see the rest */
  truncated: boolean;
}

/** [west, south, east, north] in degrees */
export type BBox = [number, number, number, number];

export interface UploadInput {
  video: File;
  gps?: File | null;
  label?: string | null;
}

/** Backend error body */
export interface ApiErrorBody {
  code: string;
  message: string;
}
