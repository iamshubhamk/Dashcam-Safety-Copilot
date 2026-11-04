import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import "leaflet/dist/leaflet.css";
import { api } from "../api/client";
import type { HazardClass, MapHazard } from "../api/types";
import { Card, ErrorBox, Loading } from "../components/ui";
import { HAZARD_LABELS } from "../lib/display";

const HAZARD_COLORS: Record<HazardClass, string> = {
  pothole: "#b91c1c",
  barricade: "#c2410c",
  speed_breaker: "#a16207",
  debris: "#6d28d9",
};

const ALL_CLASSES = Object.keys(HAZARD_LABELS) as HazardClass[];

// Fallback view when there are no hazards yet: India.
const INDIA_BOUNDS: LatLngBoundsExpression = [
  [8, 68],
  [35, 97],
];

export function HazardMapPage() {
  const { data, error, isLoading } = useQuery({ queryKey: ["hazards"], queryFn: api.listHazards });
  const [shown, setShown] = useState<Set<HazardClass>>(new Set(ALL_CLASSES));

  const visible = useMemo(() => (data ?? []).filter((h) => shown.has(h.class)), [data, shown]);
  const bounds = useMemo<LatLngBoundsExpression>(() => boundsFor(data ?? []), [data]);

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

      <div className="flex flex-wrap gap-2">
        {ALL_CLASSES.map((c) => (
          <label key={c} className="flex cursor-pointer items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-sm">
            <input type="checkbox" checked={shown.has(c)} onChange={() => toggle(c)} className="accent-slate-700" />
            <span className="inline-block h-3 w-3 rounded-full" style={{ background: HAZARD_COLORS[c] }} />
            {HAZARD_LABELS[c]}
          </label>
        ))}
      </div>

      {isLoading && <Loading what="hazards" />}
      {error && <ErrorBox error={error} />}
      {data && data.length === 0 && (
        <Card>
          <p className="text-sm text-slate-600">
            No hazards with a location yet. Upload a trip with a GPS file to start filling the map.
          </p>
        </Card>
      )}

      {data && (
        <div className="h-[60vh] min-h-80 overflow-hidden rounded-xl border border-slate-200">
          <MapContainer bounds={bounds} boundsOptions={{ padding: [40, 40] }} className="h-full w-full" scrollWheelZoom>
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {visible.map((h) => (
              <CircleMarker
                key={h.id}
                center={[h.lat, h.lon]}
                radius={6 + Math.min(h.sightings, 5) * 1.5}
                pathOptions={{ color: HAZARD_COLORS[h.class], fillColor: HAZARD_COLORS[h.class], fillOpacity: 0.6, weight: 2 }}
              >
                <Popup>
                  <p className="font-medium">{HAZARD_LABELS[h.class]}</p>
                  <p>
                    Seen {h.sightings} {h.sightings === 1 ? "time" : "times"}, last on{" "}
                    {new Date(h.last_seen_at).toLocaleDateString()}
                  </p>
                  <p>
                    {h.trip_ids.map((id, i) => (
                      <span key={id}>
                        {i > 0 && ", "}
                        <Link to={`/trips/${id}`}>Open trip</Link>
                      </span>
                    ))}
                  </p>
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>
      )}
    </div>
  );
}

export function boundsFor(hazards: MapHazard[]): LatLngBoundsExpression {
  if (hazards.length === 0) return INDIA_BOUNDS;
  const lats = hazards.map((h) => h.lat);
  const lons = hazards.map((h) => h.lon);
  return [
    [Math.min(...lats), Math.min(...lons)],
    [Math.max(...lats), Math.max(...lons)],
  ];
}
