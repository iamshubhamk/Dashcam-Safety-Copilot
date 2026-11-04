/**
 * Display rules for report data. Kept as plain functions so they are unit-tested
 * (src/lib/display.test.ts) instead of buried in JSX.
 */
import { EVENT_TYPES, type CheckKey, type EventType, type HazardClass, type NotChecked, type Severity, type TripEvent } from "../api/types";

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

export interface CheckRow {
  type: string;
  label: string;
  checked: boolean;
  /** Why it wasn't checked (from the backend); null when checked */
  reason: string | null;
}

/**
 * Rows for "What we checked". The backend lists every check that did not run in
 * `not_checked`; those always read "Not checked" with its reason, never as a clean pass.
 * The 4 event checks are always shown; GPS is shown as checked when the trip has GPS.
 */
export function checkRows(notChecked: NotChecked[], hasGps: boolean): CheckRow[] {
  const skipped = new Map(notChecked.map((n) => [n.type, n]));
  const rows: CheckRow[] = EVENT_TYPES.map((type) => {
    const n = skipped.get(type);
    return { type, label: n?.label ?? CHECK_LABELS[type], checked: !n, reason: n?.reason ?? null };
  });
  for (const n of notChecked) {
    if (!(EVENT_TYPES as readonly string[]).includes(n.type)) {
      rows.push({ type: n.type, label: n.label, checked: false, reason: n.reason });
    }
  }
  if (hasGps && !skipped.has("gps")) {
    rows.push({ type: "gps", label: CHECK_LABELS.gps, checked: true, reason: null });
  }
  return rows;
}

/**
 * Monocular distance is an estimate. With distance_confidence "low" (uncalibrated camera,
 * 20-40% error) show it rounded with "≈" so nobody reads 9.4 m as precise.
 */
export function formatDistance(event: Pick<TripEvent, "min_distance_m" | "distance_confidence">): string {
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
