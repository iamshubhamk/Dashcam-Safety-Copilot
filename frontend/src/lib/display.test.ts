import { checkView, eventCount, formatDistance, formatTimestamp, formatTtc, scoreBand } from "./display";
import { docNoGps, docWithGps } from "../mocks/fixtures";

describe("checkView", () => {
  it("treats only 'ran' as checked", () => {
    expect(checkView("ran")).toMatchObject({ checked: true, label: "Checked" });
    for (const s of ["skipped_no_ego_speed", "skipped_no_gps", "absent"] as const) {
      const v = checkView(s);
      expect(v.checked).toBe(false);
      expect(v.label).toBe("Not checked");
      expect(v.reason).toBeTruthy();
    }
  });
});

describe("eventCount", () => {
  it("sums warning and critical for checks that ran", () => {
    expect(eventCount(docWithGps.trip_summary, "forward_collision")).toBe(3);
    expect(eventCount(docNoGps.trip_summary, "forward_collision")).toBe(0);
  });

  it("returns null (not 0) when the check did not run", () => {
    expect(eventCount(docWithGps.trip_summary, "tailgating")).toBeNull();
    expect(eventCount(docWithGps.trip_summary, "obstacle_in_lane")).toBeNull();
  });
});

describe("formatDistance", () => {
  it("rounds and marks low-confidence distances as approximate", () => {
    expect(formatDistance({ min_distance_m: 9.4, distance_confidence: "low" })).toBe("≈ 9 m");
  });
  it("shows one decimal when confidence is ok", () => {
    expect(formatDistance({ min_distance_m: 9.44, distance_confidence: "ok" })).toBe("9.4 m");
  });
  it("shows a dash when there is no estimate", () => {
    expect(formatDistance({ min_distance_m: null, distance_confidence: "low" })).toBe("—");
  });
});

describe("formatters", () => {
  it("formats TTC", () => {
    expect(formatTtc(null)).toBe("—");
    expect(formatTtc(1.234)).toBe("1.2 s");
  });
  it("formats video timestamps", () => {
    expect(formatTimestamp(0)).toBe("0:00");
    expect(formatTimestamp(83.9)).toBe("1:23");
    expect(formatTimestamp(3725)).toBe("1:02:05");
  });
  it("bands scores for colour only", () => {
    expect(scoreBand(80)).toBe("good");
    expect(scoreBand(79)).toBe("fair");
    expect(scoreBand(50)).toBe("fair");
    expect(scoreBand(49)).toBe("poor");
  });
});
