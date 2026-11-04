import type { ApiClient } from "./client";
import type { MapHazard, Trip, TripReport } from "./types";

/**
 * Real backend client. Paths are the dashboard's proposal; the backend thread owns the
 * OpenAPI, so adjust here (and only here) once it is published.
 */
const BASE = "/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // body was not JSON; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const httpClient: ApiClient = {
  listTrips: () => getJson<Trip[]>("/trips"),
  getTrip: (id) => getJson<Trip>(`/trips/${encodeURIComponent(id)}`),
  getReport: (id) => getJson<TripReport>(`/trips/${encodeURIComponent(id)}/report`),
  listHazards: () => getJson<MapHazard[]>("/hazards"),

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
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText) as Trip);
        } else {
          reject(new ApiError(xhr.status, xhr.responseText || xhr.statusText));
        }
      };
      xhr.onerror = () => reject(new ApiError(0, "Network error while uploading"));
      xhr.send(form);
    }),
};
