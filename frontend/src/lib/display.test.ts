import { checkRows, formatDistance, formatTimestamp, formatTtc, scoreBand } from "./display";

describe("checkRows", () => {
  const notChecked = [
    { type: "tailgating", label: "Tailgating", status: "skipped_no_ego_speed", reason: "No speed" },
    { type: "obstacle_in_lane", label: "Obstacles", status: "absent", reason: "Model can't see them" },
    { type: "gps", label: "Location (GPS)", status: "skipped_no_gps", reason: "No GPS file" },
  ];

  it("marks everything in not_checked as not checked, with the backend's reason", () => {
    const rows = checkRows(notChecked, false);
    for (const t of ["tailgating", "obstacle_in_lane", "gps"]) {
      const row = rows.find((r) => r.type === t)!;
      expect(row.checked).toBe(false);
      expect(row.reason).toBeTruthy();
    }
  });

  it("always lists all four event checks", () => {
    const types = checkRows([], false).map((r) => r.type);
    expect(types).toEqual(["forward_collision", "obstacle_in_lane", "tailgating", "harsh_braking"]);
  });

  it("shows GPS as checked only when the trip has GPS and the backend didn't skip it", () => {
    expect(checkRows([], true).find((r) => r.type === "gps")?.checked).toBe(true);
    expect(checkRows(notChecked, true).find((r) => r.type === "gps")?.checked).toBe(false);
    expect(checkRows([], false).find((r) => r.type === "gps")).toBeUndefined();
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
