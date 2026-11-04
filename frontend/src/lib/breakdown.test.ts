import { mayNotPlay, readTripBreakdown } from "./breakdown";

describe("readTripBreakdown", () => {
  it("reads the documented trip block", () => {
    const b = readTripBreakdown({
      trip: {
        ttc_below_warning_s: 9.6,
        ttc_below_critical_s: 0.9,
        min_ttc_s: 1.2,
        objects_seen: { car: 64, bus: 9 },
        thresholds: { ttc_warning_s: 2.7, ttc_critical_s: 1.5 },
        video_codec: "mp4v",
        gps: "ran",
      },
    });
    expect(b).toEqual({
      ttc_below_warning_s: 9.6,
      ttc_below_critical_s: 0.9,
      min_ttc_s: 1.2,
      objects_seen: { car: 64, bus: 9 },
      thresholds: { ttc_warning_s: 2.7, ttc_critical_s: 1.5 },
      video_codec: "mp4v",
    });
  });

  it("survives a missing or malformed breakdown", () => {
    expect(readTripBreakdown({})).toEqual({
      ttc_below_warning_s: null,
      ttc_below_critical_s: null,
      min_ttc_s: null,
      objects_seen: {},
      thresholds: null,
      video_codec: null,
    });
    expect(readTripBreakdown({ trip: { objects_seen: { car: "lots" }, thresholds: { ttc_warning_s: 2 } } }).objects_seen).toEqual({});
  });

  it("flags mp4v video as possibly unplayable", () => {
    expect(mayNotPlay("mp4v")).toBe(true);
    expect(mayNotPlay("h264")).toBe(false);
    expect(mayNotPlay(null)).toBe(false);
  });
});
