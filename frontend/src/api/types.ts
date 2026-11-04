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

// ---------- Part 2: API wrapper (proposal, backend owns the final OpenAPI) ----------

export type TripStatus = "queued" | "processing" | "done" | "failed";

export interface Trip {
  id: string;
  /** Optional free-text label the user typed at upload */
  label: string | null;
  original_filename: string;
  status: TripStatus;
  /** 0-1 while processing, null when unknown */
  progress: number | null;
  error: string | null;
  created_at: string;
  duration_s: number | null;
  /** 0-100, computed by the backend from configs/risk.yaml; null until done */
  score: number | null;
  has_gps: boolean;
  event_count: number | null;
}

export interface FeedbackItem {
  kind: "good" | "improve" | "info";
  text: string;
}

export interface TripReport {
  trip: Trip;
  score: number;
  feedback: FeedbackItem[];
  /** URL of the full annotated video, or null if not rendered */
  annotated_video_url: string | null;
  /** event_id -> playable clip URL (H.264 MP4) */
  clip_urls: Record<number, string>;
  events_doc: EventsDocument;
}

/** One hazard on the map, aggregated across trips (nearby sightings merged by the backend). */
export interface MapHazard {
  id: string;
  class: HazardClass;
  lat: number;
  lon: number;
  sightings: number;
  trip_ids: string[];
  last_seen_at: string;
}

export interface UploadInput {
  video: File;
  gps?: File | null;
  label?: string | null;
}
