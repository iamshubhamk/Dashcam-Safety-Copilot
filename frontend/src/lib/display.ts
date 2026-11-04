/**
 * Display rules for report data. Kept as plain functions so they are unit-tested
 * (src/lib/display.test.ts) instead of buried in JSX.
 */
import type {
  CheckKey,
  CheckStatus,
  EventType,
  HazardClass,
  SafetyEvent,
  Severity,
  TripSummary,
} from "../api/types";

export const EVENT_LABELS: Record<EventType, string> = {
  forward_collision: "Forward collision risk",
  obstacle_in_lane: "Obstacle in lane",
  tailgating: "Tailgating",
  harsh_braking: "Harsh braking ahead",
};

export const CHECK_LABELS: Record<CheckKey, string> = {
  forward_collision: "Forward collision risk",
  obstacle_in_lane: "Obstacles in your lane",
  tailgating: "Tailgating",
  harsh_braking: "Harsh braking ahead",
  gps: "Location (GPS)",
};

export const HAZARD_LABELS: Record<HazardClass, string> = {
  pothole: "Pothole",
  barricade: "Barricade",
  speed_breaker: "Speed breaker",
  debris: "Debris",
};

export const CLASS_LABELS: Record<string, string> = {
  car: "Car",
  bus: "Bus",
  truck: "Truck",
  two_wheeler: "Two-wheeler",
  auto_rickshaw: "Auto-rickshaw",
  pedestrian: "Pedestrian",
  animal: "Animal",
  pothole: "Pothole",
  barricade: "Barricade",
  speed_breaker: "Speed breaker",
  debris: "Debris",
};

export const classLabel = (name: string): string => CLASS_LABELS[name] ?? name.replaceAll("_", " ");

export interface CheckView {
  checked: boolean;
  label: "Checked" | "Not checked";
  reason: string | null;
}

/**
 * Only "ran" counts as checked. Every other status means the pipeline could not look, so
 * the UI must say "Not checked" and never imply a clean pass.
 */
export function checkView(status: CheckStatus): CheckView {
  switch (status) {
    case "ran":
      return { checked: true, label: "Checked", reason: null };
    case "skipped_no_ego_speed":
      return { checked: false, label: "Not checked", reason: "Needs your vehicle's speed, which this video doesn't have." };
    case "skipped_no_gps":
      return { checked: false, label: "Not checked", reason: "No GPS file was uploaded with this video." };
    case "absent":
      return { checked: false, label: "Not checked", reason: "The current detection model doesn't support this yet." };
  }
}

/** Count for one event type, or null when that check didn't run (show "not checked", not 0). */
export function eventCount(summary: TripSummary, type: EventType): number | null {
  if (summary.checks[type] !== "ran") return null;
  const c = summary.event_counts[type];
  return (c.warning ?? 0) + (c.critical ?? 0);
}

/**
 * Monocular distance is an estimate. With distance_confidence "low" (uncalibrated camera,
 * 20-40% error) show it rounded with "≈" so nobody reads 9.4 m as precise.
 */
export function formatDistance(event: Pick<SafetyEvent, "min_distance_m" | "distance_confidence">): string {
  const m = event.min_distance_m;
  if (m === null) return "—";
  if (event.distance_confidence === "low") return `≈ ${Math.round(m)} m`;
  return `${m.toFixed(1)} m`;
}

export function formatTtc(s: number | null): string {
  return s === null ? "—" : `${s.toFixed(1)} s`;
}

/** 83.4 -> "1:23" */
export function formatTimestamp(totalSeconds: number): string {
  const whole = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const s = whole % 60;
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

export type ScoreBand = "good" | "fair" | "poor";

/** Bands are only for colour; the score itself comes from the backend (configs/risk.yaml). */
export function scoreBand(score: number): ScoreBand {
  if (score >= 80) return "good";
  if (score >= 50) return "fair";
  return "poor";
}

export const SEVERITY_LABELS: Record<Severity, string> = {
  warning: "Warning",
  critical: "Critical",
};
