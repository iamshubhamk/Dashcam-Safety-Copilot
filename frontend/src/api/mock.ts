import type { ApiClient } from "./client";
import type { Trip, TripReport } from "./types";
import { seedHazards, seedReports, seedTrips } from "../mocks/fixtures";

/**
 * In-browser fake backend so the dashboard can be built and demoed before the API exists.
 * Uploaded files are never read; a fake job moves the new trip through
 * queued -> processing -> done over ~12 s and then reuses a demo report.
 */
const QUEUED_MS = 2_000;
const PROCESSING_MS = 10_000;

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

interface UploadedTrip {
  trip: Trip;
  uploadedAt: number;
}

const uploaded: UploadedTrip[] = [];
let nextId = 1;

function liveState(u: UploadedTrip, now: number): Trip {
  const elapsed = now - u.uploadedAt;
  if (elapsed < QUEUED_MS) return { ...u.trip, status: "queued", progress: null };
  if (elapsed < QUEUED_MS + PROCESSING_MS) {
    return { ...u.trip, status: "processing", progress: (elapsed - QUEUED_MS) / PROCESSING_MS };
  }
  const demo = seedReports["demo-2"]!;
  return {
    ...u.trip,
    status: "done",
    progress: null,
    duration_s: demo.events_doc.video.duration_s,
    score: demo.score,
    event_count: demo.events_doc.events.length,
  };
}

function allTrips(): Trip[] {
  const now = Date.now();
  const live = uploaded.map((u) => liveState(u, now));
  return [...live, ...seedTrips].sort((a, b) => b.created_at.localeCompare(a.created_at));
}

function findTrip(id: string): Trip {
  const trip = allTrips().find((t) => t.id === id);
  if (!trip) throw new Error(`Trip ${id} not found`);
  return trip;
}

export const mockClient: ApiClient = {
  async listTrips() {
    await delay(150);
    return allTrips();
  },

  async getTrip(id) {
    await delay(100);
    return findTrip(id);
  },

  async getReport(id): Promise<TripReport> {
    await delay(200);
    const trip = findTrip(id);
    if (trip.status !== "done") throw new Error("Report is not ready yet");
    const seeded = seedReports[id] ?? seedReports["demo-2"]!;
    return { ...seeded, trip };
  },

  async uploadTrip(input, onProgress) {
    // Pretend to upload in 10 steps so the progress bar can be seen.
    for (let i = 1; i <= 10; i++) {
      await delay(120);
      onProgress?.(i / 10);
    }
    const trip: Trip = {
      id: `upload-${nextId++}`,
      label: input.label?.trim() || null,
      original_filename: input.video.name,
      status: "queued",
      progress: null,
      error: null,
      created_at: new Date().toISOString(),
      duration_s: null,
      score: null,
      has_gps: Boolean(input.gps),
      event_count: null,
    };
    uploaded.push({ trip, uploadedAt: Date.now() });
    return trip;
  },

  async listHazards() {
    await delay(150);
    return seedHazards;
  },
};
