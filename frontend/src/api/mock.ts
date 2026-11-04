import type { ApiClient } from "./client";
import type { Report, Trip } from "./types";
import { DEMO_TRIP_2, seedEvents, seedHazards, seedReports, seedTrips } from "../mocks/fixtures";

/**
 * In-browser fake backend so the dashboard can be demoed without the API running.
 * Uploaded files are never read: a fake job moves the new trip through
 * queued -> processing -> done over ~12 s and then reuses a demo report.
 */
const QUEUED_MS = 2_000;
const PROCESSING_MS = 10_000;

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

interface UploadedTrip {
  trip: Trip;
  uploadedAt: number;
}

let uploaded: UploadedTrip[] = [];
const deleted = new Set<string>();

function liveState(u: UploadedTrip, now: number): Trip {
  const elapsed = now - u.uploadedAt;
  if (elapsed < QUEUED_MS) return { ...u.trip, status: "queued" };
  if (elapsed < QUEUED_MS + PROCESSING_MS) return { ...u.trip, status: "processing" };
  const demo = seedTrips.find((t) => t.id === DEMO_TRIP_2)!;
  return {
    ...u.trip,
    status: "done",
    duration_s: demo.duration_s,
    score: demo.score,
    event_count: 0,
    processed_at: new Date(u.uploadedAt + QUEUED_MS + PROCESSING_MS).toISOString(),
  };
}

function allTrips(): Trip[] {
  const now = Date.now();
  const live = uploaded.map((u) => liveState(u, now));
  return [...live, ...seedTrips]
    .filter((t) => !deleted.has(t.id))
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}

function findTrip(id: string): Trip {
  const trip = allTrips().find((t) => t.id === id);
  if (!trip) throw new Error("Trip not found");
  return trip;
}

export const mockClient: ApiClient = {
  async listTrips() {
    await delay(150);
    return { items: allTrips(), next_cursor: null };
  },

  async getTrip(id) {
    await delay(100);
    return findTrip(id);
  },

  async getReport(id): Promise<Report> {
    await delay(200);
    const trip = findTrip(id);
    if (trip.status !== "done") throw new Error("Report is not ready yet");
    return { ...(seedReports[id] ?? seedReports[DEMO_TRIP_2]!), trip_id: id };
  },

  async listEvents(tripId) {
    await delay(150);
    return seedEvents[tripId] ?? [];
  },

  async uploadTrip(input, onProgress) {
    // Pretend to upload in 10 steps so the progress bar can be seen.
    for (let i = 1; i <= 10; i++) {
      await delay(120);
      onProgress?.(i / 10);
    }
    const trip: Trip = {
      id: crypto.randomUUID(),
      label: input.label?.trim() || null,
      status: "queued",
      source: "upload",
      original_filename: input.video.name,
      duration_s: null,
      distance_km: null,
      has_gps: Boolean(input.gps),
      has_original_video: true,
      has_annotated_video: false,
      score: null,
      event_count: 0,
      error: null,
      created_at: new Date().toISOString(),
      processed_at: null,
    };
    uploaded.push({ trip, uploadedAt: Date.now() });
    return trip;
  },

  async retryTrip(id) {
    await delay(150);
    const trip = findTrip(id);
    const restarted: Trip = { ...trip, status: "queued", error: null, processed_at: null };
    // Run it again as a fresh fake job under the same id.
    uploaded = uploaded.filter((u) => u.trip.id !== id);
    const seedIdx = seedTrips.findIndex((t) => t.id === id);
    if (seedIdx >= 0) seedTrips.splice(seedIdx, 1);
    uploaded.push({ trip: restarted, uploadedAt: Date.now() });
    return restarted;
  },

  async deleteTrip(id) {
    await delay(150);
    deleted.add(id);
  },

  async listHazards([west, south, east, north]) {
    await delay(150);
    const items = seedHazards.filter((h) => h.lon >= west && h.lon <= east && h.lat >= south && h.lat <= north);
    return { items, truncated: false };
  },

  clipUrl: () => null,
  videoUrl: () => null,
};
