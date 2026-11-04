import { useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Trip } from "../api/types";
import { Card, ErrorBox, Loading, ScoreBadge, StatusPill } from "../components/ui";
import { formatTimestamp } from "../lib/display";

const POLL_MS = 3_000;

/** Poll only while something is still being processed. */
export const pollWhileBusy = (trips: Trip[] | undefined): number | false =>
  trips?.some((t) => t.status === "queued" || t.status === "processing") ? POLL_MS : false;

export function TripsPage() {
  const { data, error, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ["trips"],
    queryFn: ({ pageParam }) => api.listTrips(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    refetchInterval: (q) => pollWhileBusy(q.state.data?.pages.flatMap((p) => p.items)),
  });
  const trips = data?.pages.flatMap((p) => p.items);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Your trips</h1>
        <Link to="/upload" className="rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700">
          Upload a video
        </Link>
      </div>

      {isLoading && <Loading what="trips" />}
      {error && <ErrorBox error={error} />}
      {trips && trips.length === 0 && (
        <Card>
          <p className="text-sm text-slate-600">
            No trips yet. <Link className="text-brand-600 underline" to="/upload">Upload a dashcam video</Link> to get a
            driving report.
          </p>
        </Card>
      )}

      {trips && trips.length > 0 && (
        <ul className="space-y-2">
          {trips.map((trip) => (
            <li key={trip.id}>
              <TripRow trip={trip} />
            </li>
          ))}
        </ul>
      )}
      {hasNextPage && (
        <button
          type="button"
          onClick={() => fetchNextPage()}
          disabled={isFetchingNextPage}
          className="w-full rounded-md border border-slate-200 bg-white py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {isFetchingNextPage ? "Loading…" : "Show older trips"}
        </button>
      )}
    </div>
  );
}

function TripRow({ trip }: { trip: Trip }) {
  const title = trip.label ?? trip.original_filename ?? "Imported trip";
  const created = new Date(trip.created_at).toLocaleString();
  return (
    <Link
      to={`/trips/${trip.id}`}
      className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-3 shadow-sm hover:border-brand-100 hover:bg-brand-50/40"
    >
      <ScoreBadge score={trip.score} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{title}</p>
        <p className="truncate text-xs text-slate-500">
          {created}
          {trip.duration_s != null && ` · ${formatTimestamp(trip.duration_s)} long`}
          {trip.label && ` · ${trip.original_filename}`}
        </p>
        {trip.status === "failed" && trip.error && <p className="mt-1 text-xs text-red-700">{trip.error}</p>}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <StatusPill status={trip.status} />
        {trip.status === "done" && (
          <span className="text-xs text-slate-500">
            {trip.event_count === 1 ? "1 risky moment" : `${trip.event_count} risky moments`}
          </span>
        )}
        {trip.status === "done" && !trip.has_gps && <span className="text-xs text-slate-400">no GPS</span>}
      </div>
    </Link>
  );
}
