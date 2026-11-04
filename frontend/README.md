# Dashboard (Phase 4)

React + Vite + TypeScript web app for the driving report: upload a dashcam video, see your
trips, open a trip report (score, feedback, risky moments with clips, what was and wasn't
checked) and a hazard map.

## Run it

Needs Node 22+.

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173, demo data, no backend needed
npm test           # unit + component tests
npm run build      # typecheck + production build into dist/
```

### Demo data vs the real backend

`VITE_API_MODE` picks the data source (copy `.env.example` to `.env`):

- `mock` (default): an in-browser fake backend (`src/api/mock.ts`) with hand-written trips
  in `src/mocks/fixtures.ts`. A yellow banner says so on every page. None of these numbers
  came from a real video.
- `http`: calls the FastAPI backend (API v1 under `/api/v1`); the dev server proxies `/api`
  to `VITE_PROXY_TARGET` (default `http://localhost:8000`).

## How it is organised

```
src/
  api/types.ts            events.json v1 types + backend API v1 types
  api/openapi.v1.json     copy of the backend's OpenAPI spec
  api/events.v1.schema.json  copy of perception/schema/events.v1.json
  api/client.ts           ApiClient interface; picks mock or http
  api/http.ts             real backend calls (paging, errors, upload progress)
  api/mock.ts             fake backend for demos and development
  lib/display.ts          display rules (tested): "not checked", approximate distance, formats
  components/             Card, ScoreBadge, StatusPill, ChecksPanel
  pages/                  Trips, Upload, TripReport, HazardMap
```

## Rules the UI follows

- **Skipped checks are never shown as a pass.** Every check in the report's `not_checked`
  list shows as "Not checked" with the backend's reason (e.g. tailgating needs the
  vehicle's speed, which a plain video doesn't have).
- **Provisional scores are labelled.** When the backend marks a score `provisional`, the
  report says to treat it as rough; a `null` score says not enough was checked.
- **Distances are approximate.** A single camera can't measure distance exactly; when
  `distance_confidence` is `"low"` (uncalibrated camera, 20-40% error) the distance is
  rounded and shown as "≈ 9 m".
- **The score comes from the backend** (`configs/risk.yaml`). The UI only colours it:
  80+ green, 50-79 amber, below 50 red.
- **The hazard map only shows trips uploaded with a GPS file.**
- Clips must be H.264 MP4 so every browser can play them.

## Keeping the contracts honest

Two tests stop the demo data drifting from the real system:

- `src/mocks/fixtures.test.ts` validates the demo events.json documents against
  `events.v1.schema.json` (the perception contract).
- `src/api/openapi.contract.test.ts` validates every demo API response against
  `openapi.v1.json` (the backend contract).

When perception or the backend changes its contract, re-copy the file; the failing test
shows what to update.

## Known gaps

- Map tiles come from the public OpenStreetMap servers, which are fine for a demo but have a
  usage policy; switch the `TileLayer` URL for heavier use.
- No marker clustering yet; add it if a map ever shows hundreds of hazards.
- The report doesn't show "objects seen" or time spent under the TTC thresholds yet,
  because API v1 doesn't return them.
