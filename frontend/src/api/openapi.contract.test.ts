import Ajv2020 from "ajv/dist/2020";
import spec from "./openapi.v1.json";
import { parseError } from "./http";
import { seedEvents, seedHazards, seedReports, seedTrips } from "../mocks/fixtures";

// The demo backend must return exactly what the real one does. openapi.v1.json is a copy of
// the backend's spec (/mnt/project-files/backend/openapi.v1.json, later backend/openapi.v1.json);
// re-copy it when the backend changes and this test shows what the dashboard must adapt to.
const ajv = new Ajv2020({ strict: false, validateFormats: false, allErrors: true });
ajv.addSchema(spec, "openapi");
const validator = (name: string) => ajv.compile({ $ref: `openapi#/components/schemas/${name}` });

function expectValid(name: string, data: unknown) {
  const validate = validator(name);
  validate(data);
  expect(validate.errors ?? []).toEqual([]);
}

describe("demo data matches the backend OpenAPI", () => {
  it("trips page", () => expectValid("Page_TripOut_", { items: seedTrips, next_cursor: null }));
  it("events pages", () => {
    for (const items of Object.values(seedEvents)) expectValid("Page_EventOut_", { items, next_cursor: null });
  });
  it("reports", () => {
    for (const r of Object.values(seedReports)) expectValid("ReportOut", r);
  });
  it("hazards", () => expectValid("HazardList", { items: seedHazards, truncated: false }));

  it("catches a mismatch", () => {
    const validate = validator("TripOut");
    const { score: _drop, ...noScore } = seedTrips[0]!;
    expect(validate(noScore)).toBe(false);
  });
});

describe("parseError", () => {
  it("reads the backend's {code, message}", () => {
    const e = parseError(404, JSON.stringify({ code: "trip_not_found", message: "Trip not found" }));
    expect(e.message).toBe("Trip not found");
    expect(e.code).toBe("trip_not_found");
  });
  it("reads FastAPI validation errors", () => {
    const e = parseError(422, JSON.stringify({ detail: [{ loc: ["query", "bbox"], msg: "Field required", type: "missing" }] }));
    expect(e.message).toBe("Field required");
  });
  it("falls back to plain text", () => {
    expect(parseError(502, "Bad gateway").message).toBe("Bad gateway");
  });
});
