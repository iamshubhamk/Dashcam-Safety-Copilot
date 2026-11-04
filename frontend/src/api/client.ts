import type { BBox, HazardList, Page, Report, Trip, TripEvent, UploadInput } from "./types";
import { httpClient } from "./http";
import { mockClient } from "./mock";

/** Everything the dashboard needs from the backend. Pages only talk to this interface. */
export interface ApiClient {
  listTrips(cursor?: string | null): Promise<Page<Trip>>;
  getTrip(id: string): Promise<Trip>;
  getReport(id: string): Promise<Report>;
  /** All events of a trip (follows pagination) */
  listEvents(tripId: string): Promise<TripEvent[]>;
  uploadTrip(input: UploadInput, onProgress?: (fraction: number) => void): Promise<Trip>;
  retryTrip(id: string): Promise<Trip>;
  deleteTrip(id: string): Promise<void>;
  listHazards(bbox: BBox): Promise<HazardList>;
  /** Playable URLs (null when the file doesn't exist) */
  clipUrl(event: TripEvent): string | null;
  videoUrl(trip: Trip): string | null;
}

export const API_MODE: "mock" | "http" =
  import.meta.env.VITE_API_MODE === "http" ? "http" : "mock";

export const api: ApiClient = API_MODE === "http" ? httpClient : mockClient;
