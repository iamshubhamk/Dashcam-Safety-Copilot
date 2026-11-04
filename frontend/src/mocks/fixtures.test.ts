import Ajv2020 from "ajv/dist/2020";
import schema from "../api/events.v1.schema.json";
import { EVENT_TYPES } from "../api/types";
import { docNoGps, docWithGps, seedReports } from "./fixtures";

// Keeps the demo data honest: it must be a valid events.json v1 document,
// exactly as perception would write it.
const validate = new Ajv2020({ allErrors: true, strict: false }).compile(schema);

describe("mock events documents", () => {
  it.each([
    ["docWithGps", docWithGps],
    ["docNoGps", docNoGps],
  ])("%s matches events.v1.schema.json", (_name, doc) => {
    const ok = validate(doc);
    expect(validate.errors ?? []).toEqual([]);
    expect(ok).toBe(true);
  });

  it("zero-fills all 4 event types", () => {
    for (const doc of [docWithGps, docNoGps]) {
      expect(Object.keys(doc.trip_summary.event_counts).sort()).toEqual([...EVENT_TYPES].sort());
    }
  });

  it("report event totals match the events list", () => {
    for (const report of Object.values(seedReports)) {
      const counts = report.events_doc.trip_summary.event_counts;
      const total = Object.values(counts).reduce((s, c) => s + (c.warning ?? 0) + (c.critical ?? 0), 0);
      expect(total).toBe(report.events_doc.events.length);
    }
  });
});

it("schema check rejects a document with an unknown check status", () => {
  const bad = structuredClone(docWithGps) as unknown as { trip_summary: { checks: Record<string, string> } };
  bad.trip_summary.checks.tailgating = "passed";
  expect(validate(bad)).toBe(false);
});
