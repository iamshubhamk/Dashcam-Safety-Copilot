import type { MapHazard, Trip, TripReport, UploadInput } from "./types";
import { httpClient } from "./http";
import { mockClient } from "./mock";

/** Everything the dashboard needs from the backend. Pages only talk to this interface. */
export interface ApiClient {
  listTrips(): Promise<Trip[]>;
  getTrip(id: string): Promise<Trip>;
  getReport(id: string): Promise<TripReport>;
  uploadTrip(input: UploadInput, onProgress?: (fraction: number) => void): Promise<Trip>;
  listHazards(): Promise<MapHazard[]>;
}

export const API_MODE: "mock" | "http" =
  import.meta.env.VITE_API_MODE === "http" ? "http" : "mock";

export const api: ApiClient = API_MODE === "http" ? httpClient : mockClient;
