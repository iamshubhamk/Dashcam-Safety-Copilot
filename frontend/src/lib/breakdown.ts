import type { TripBreakdown } from "../api/types";

const num = (x: unknown): number | null => (typeof x === "number" && Number.isFinite(x) ? x : null);
const obj = (x: unknown): Record<string, unknown> | null =>
  x !== null && typeof x === "object" && !Array.isArray(x) ? (x as Record<string, unknown>) : null;

/** Pull report.breakdown.trip out of an untyped dict; missing or odd values become null/empty. */
export function readTripBreakdown(breakdown: Record<string, unknown>): TripBreakdown {
  const trip = obj(breakdown.trip) ?? {};
  const objects: Record<string, number> = {};
  for (const [k, v] of Object.entries(obj(trip.objects_seen) ?? {})) {
    const n = num(v);
    if (n !== null) objects[k] = n;
  }
  const th = obj(trip.thresholds);
  const warn = num(th?.ttc_warning_s);
  const crit = num(th?.ttc_critical_s);
  return {
    ttc_below_warning_s: num(trip.ttc_below_warning_s),
    ttc_below_critical_s: num(trip.ttc_below_critical_s),
    min_ttc_s: num(trip.min_ttc_s),
    objects_seen: objects,
    thresholds: warn !== null && crit !== null ? { ttc_warning_s: warn, ttc_critical_s: crit } : null,
    video_codec: typeof trip.video_codec === "string" ? trip.video_codec : null,
  };
}

/** Browsers can't decode MPEG-4 Part 2 ("mp4v"); warn instead of showing a silent black box. */
export const mayNotPlay = (codec: string | null): boolean => codec === "mp4v";
