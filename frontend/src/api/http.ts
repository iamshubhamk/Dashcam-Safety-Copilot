import type { ApiClient } from "./client";
import type { ApiErrorBody, HazardList, Page, Report, Trip, TripEvent } from "./types";

/** Real backend client for API v1 (backend/openapi.v1.json). */
export const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

/** Turn any error body into a readable message: {code, message}, or FastAPI's 422 {detail}. */
export function parseError(status: number, text: string): ApiError {
  try {
    const body = JSON.parse(text) as Partial<ApiErrorBody> & { detail?: unknown };
    if (typeof body.message === "string") return new ApiError(status, body.code ?? "error", body.message);
    if (Array.isArray(body.detail)) {
      const msgs = body.detail.map((d: { msg?: string }) => d.msg).filter(Boolean);
      return new ApiError(status, "validation_error", msgs.join("; ") || "Invalid request");
    }
  } catch {
    // not JSON
  }
  return new ApiError(status, "http_error", text || `Request failed (${status})`);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) throw parseError(res.status, await res.text());
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

export const httpClient: ApiClient = {
  listTrips: (cursor) => request<Page<Trip>>(`/trips?limit=50${cursor ? `&cursor=${enc(cursor)}` : ""}`),
  getTrip: (id) => request<Trip>(`/trips/${enc(id)}`),
  getReport: (id) => request<Report>(`/trips/${enc(id)}/report`),

  async listEvents(tripId) {
    const all: TripEvent[] = [];
    let cursor: string | null = null;
    // A trip has at most a few hundred events; stop after 20 pages as a safety net.
    for (let i = 0; i < 20; i++) {
      const page: Page<TripEvent> = await request<Page<TripEvent>>(
        `/trips/${enc(tripId)}/events?limit=100${cursor ? `&cursor=${enc(cursor)}` : ""}`,
      );
      all.push(...page.items);
      cursor = page.next_cursor;
      if (!cursor) break;
    }
    return all;
  },

  retryTrip: (id) => request<Trip>(`/trips/${enc(id)}/retry`, { method: "POST" }),
  deleteTrip: (id) => request<void>(`/trips/${enc(id)}`, { method: "DELETE" }),
  listHazards: (bbox) => request<HazardList>(`/hazards?bbox=${bbox.map((n) => n.toFixed(5)).join(",")}`),

  clipUrl: (event) => (event.has_clip ? `${BASE}/events/${event.id}/clip` : null),
  videoUrl: (trip) => (trip.has_annotated_video ? `${BASE}/trips/${enc(trip.id)}/video?annotated=true` : null),

  // XMLHttpRequest instead of fetch because fetch has no upload progress events,
  // and dashcam videos can be up to 2 GB.
  uploadTrip: (input, onProgress) =>
    new Promise<Trip>((resolve, reject) => {
      const form = new FormData();
      form.append("video", input.video);
      if (input.gps) form.append("gps", input.gps);
      if (input.label) form.append("label", input.label);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${BASE}/trips`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress?.(e.loaded / e.total);
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText) as Trip);
        else reject(parseError(xhr.status, xhr.responseText));
      };
      xhr.onerror = () => reject(new ApiError(0, "network_error", "Network error while uploading"));
      xhr.send(form);
    }),
};
