import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet";
import type { LatLngBounds, LatLngBoundsExpression } from "leaflet";
import "leaflet/dist/leaflet.css";
import { api } from "../api/client";
import type { BBox, HazardClass, MapHazard } from "../api/types";
import { ErrorBox } from "../components/ui";
import { HAZARD_LABELS } from "../lib/display";

const HAZARD_COLORS: Record<HazardClass, string> = {
  pothole: "#b91c1c",
  barricade: "#c2410c",
  speed_breaker: "#a16207",
  debris: "#6d28d9",
};

const ALL_CLASSES = Object.keys(HAZARD_LABELS) as HazardClass[];

/** Starting view: all of India. */
export const INDIA_BBOX: BBox = [68, 6, 98, 36];
const toLeaflet = ([w, s, e, n]: BBox): LatLngBoundsExpression => [
  [s, w],
  [n, e],
];

/** Leaflet bounds -> API bbox, rounded so tiny pans don't refetch. */
export function toBBox(b: Pick<LatLngBounds, "getWest" | "getSouth" | "getEast" | "getNorth">): BBox {
  const r = (x: number) => Math.round(x * 1000) / 1000;
  return [r(b.getWest()), r(b.getSouth()), r(b.getEast()), r(b.getNorth())];
}

export function boundsFor(hazards: Pick<MapHazard, "lat" | "lon">[]): LatLngBoundsExpression | null {
  if (hazards.length === 0) return null;
  const lats = hazards.map((h) => h.lat);
  const lons = hazards.map((h) => h.lon);
  return [
    [Math.min(...lats), Math.min(...lons)],
    [Math.max(...lats), Math.max(...lons)],
  ];
}

export function HazardMapPage() {
  const [bbox, setBbox] = useState<BBox>(INDIA_BBOX);
  const [shown, setShown] = useState<Set<HazardClass>>(new Set(ALL_CLASSES));

  const { data, error, isFetching } = useQuery({
    queryKey: ["hazards", bbox],
    queryFn: () => api.listHazards(bbox),
    placeholderData: keepPreviousData,
  });

  const visible = useMemo(() => (data?.items ?? []).filter((h) => shown.has(h.hazard_class)), [data, shown]);

  const toggle = (c: HazardClass) =>
    setShown((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Hazard map</h1>
        <p className="text-sm text-slate-600">
          Road hazards spotted across your trips. Only trips uploaded with a GPS file appear here; sightings close
          together are merged into one marker.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {ALL_CLASSES.map((c) => (
          <label key={c} className="flex cursor-pointer items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-sm">
            <input type="checkbox" checked={shown.has(c)} onChange={() => toggle(c)} className="accent-slate-700" />
            <span className="inline-block h-3 w-3 rounded-full" style={{ background: HAZARD_COLORS[c] }} />
            {HAZARD_LABELS[c]}
          </label>
        ))}
        <span className="text-xs text-slate-500">
          {isFetching ? "Loading…" : data ? `${visible.length} shown in this area` : ""}
        </span>
      </div>

      {error && <ErrorBox error={error} />}
      {data?.truncated && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          There are more hazards in this area than can be shown at once. Zoom in to see them all.
        </p>
      )}

      <div className="relative h-[60vh] min-h-80 overflow-hidden rounded-xl border border-slate-200">
        <MapContainer bounds={toLeaflet(INDIA_BBOX)} className="h-full w-full" scrollWheelZoom>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <TrackBounds onChange={setBbox} />
          <FitOnce hazards={data?.items} />
          {visible.map((h) => (
            <CircleMarker
              key={h.id}
              center={[h.lat, h.lon]}
              radius={6 + Math.min(h.seen_count, 5) * 1.5}
              pathOptions={{ color: HAZARD_COLORS[h.hazard_class], fillColor: HAZARD_COLORS[h.hazard_class], fillOpacity: 0.6, weight: 2 }}
            >
              <Popup>
                <p className="font-medium">{HAZARD_LABELS[h.hazard_class]}</p>
                <p>
                  Seen {h.seen_count} {h.seen_count === 1 ? "time" : "times"} on {h.trip_count}{" "}
                  {h.trip_count === 1 ? "trip" : "trips"}
                </p>
                <p>Last seen {new Date(h.last_seen_at).toLocaleDateString()}</p>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
        {data && data.items.length === 0 && (
          <div className="pointer-events-none absolute inset-x-0 top-3 z-[400] mx-auto w-fit rounded-md bg-white/95 px-3 py-2 text-sm text-slate-600 shadow">
            No hazards with a location in this area. Upload a trip with a GPS file to fill the map.
          </div>
        )}
      </div>
    </div>
  );
}

/** Reports the visible area after every pan/zoom so hazards are fetched for it. */
function TrackBounds({ onChange }: { onChange: (b: BBox) => void }) {
  const map = useMapEvents({ moveend: () => onChange(toBBox(map.getBounds())) });
  useEffect(() => onChange(toBBox(map.getBounds())), [map, onChange]);
  return null;
}

/** On first load, zoom to where the hazards are instead of showing all of India. */
function FitOnce({ hazards }: { hazards: MapHazard[] | undefined }) {
  const map = useMap();
  const done = useRef(false);
  useEffect(() => {
    if (done.current || !hazards) return;
    done.current = true;
    const b = boundsFor(hazards);
    if (b) map.fitBounds(b, { padding: [40, 40], maxZoom: 15 });
  }, [hazards, map]);
  return null;
}
