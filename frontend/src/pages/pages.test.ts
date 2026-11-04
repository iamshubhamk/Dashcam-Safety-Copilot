import { pollWhileBusy } from "./TripsPage";
import { MAX_VIDEO_BYTES, validateVideo } from "./UploadPage";
import { boundsFor } from "./HazardMapPage";
import { seedHazards, seedTrips } from "../mocks/fixtures";

describe("trip list polling", () => {
  it("polls only while a trip is queued or processing", () => {
    expect(pollWhileBusy(seedTrips)).toBe(false);
    expect(pollWhileBusy([{ ...seedTrips[0]!, status: "processing" }])).toBe(3000);
    expect(pollWhileBusy(undefined)).toBe(false);
  });
});

describe("upload validation", () => {
  const fileOfSize = (size: number) => {
    const f = new File(["x"], "trip.mp4", { type: "video/mp4" });
    Object.defineProperty(f, "size", { value: size });
    return f;
  };
  it("requires a video and enforces the 2 GB cap", () => {
    expect(validateVideo(null)).toMatch(/Choose/);
    expect(validateVideo(fileOfSize(MAX_VIDEO_BYTES + 1))).toMatch(/2 GB/);
    expect(validateVideo(fileOfSize(1024))).toBeNull();
  });
});

describe("hazard map bounds", () => {
  it("fits all hazards", () => {
    const [[s, w], [n, e]] = boundsFor(seedHazards) as [[number, number], [number, number]];
    for (const h of seedHazards) {
      expect(h.lat).toBeGreaterThanOrEqual(s);
      expect(h.lat).toBeLessThanOrEqual(n);
      expect(h.lon).toBeGreaterThanOrEqual(w);
      expect(h.lon).toBeLessThanOrEqual(e);
    }
  });
});
