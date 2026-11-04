import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { FeedbackLine, Report, Trip, TripEvent } from "../api/types";
import { ChecksPanel } from "../components/ChecksPanel";
import { Card, ErrorBox, Loading, ScoreBadge, StatusPill } from "../components/ui";
import {
  EVENT_LABELS,
  SEVERITY_LABELS,
  checkRows,
  classLabel,
  formatDistance,
  formatTimestamp,
  formatTtc,
} from "../lib/display";
import { mayNotPlay, readTripBreakdown } from "../lib/breakdown";

export function TripReportPage() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const trip = useQuery({
    queryKey: ["trip", id],
    queryFn: () => api.getTrip(id),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "queued" || s === "processing" ? 3_000 : false;
    },
  });
  const done = trip.data?.status === "done";
  const report = useQuery({ queryKey: ["report", id], queryFn: () => api.getReport(id), enabled: done });
  const events = useQuery({ queryKey: ["events", id], queryFn: () => api.listEvents(id), enabled: done });

  const retry = useMutation({
    mutationFn: () => api.retryTrip(id),
    onSuccess: (t) => {
      queryClient.setQueryData(["trip", id], t);
      void queryClient.invalidateQueries({ queryKey: ["trips"] });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteTrip(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["trips"] });
      navigate("/trips");
    },
  });

  if (trip.isLoading) return <Loading what="trip" />;
  if (trip.error) return <ErrorBox error={trip.error} />;
  const t = trip.data!;
  const title = t.label ?? t.original_filename ?? "Imported trip";

  return (
    <div className="space-y-4">
      <Link to="/trips" className="text-sm text-brand-600 hover:underline">
        ← All trips
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{title}</h1>
        <StatusPill status={t.status} />
        <button
          type="button"
          onClick={() => {
            if (window.confirm("Delete this trip, its videos and its report? This can't be undone.")) remove.mutate();
          }}
          disabled={remove.isPending}
          className="ml-auto text-sm text-slate-500 hover:text-red-700"
        >
          Delete trip
        </button>
      </div>
      {remove.error && <ErrorBox error={remove.error} />}

      {(t.status === "queued" || t.status === "processing") && (
        <Card>
          <p className="text-sm text-slate-600">
            {t.status === "queued"
              ? "Waiting for the analyser to pick up this video."
              : "Analysing the video: detecting objects, tracking them and checking for risky moments. This can take a few minutes."}{" "}
            This page updates by itself.
          </p>
        </Card>
      )}

      {t.status === "failed" && (
        <div className="space-y-2">
          <ErrorBox error={t.error ?? "Processing failed."} />
          <button
            type="button"
            onClick={() => retry.mutate()}
            disabled={retry.isPending}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
          >
            {retry.isPending ? "Retrying…" : "Try again"}
          </button>
          {retry.error && <ErrorBox error={retry.error} />}
        </div>
      )}

      {done && (report.isLoading || events.isLoading) && <Loading what="report" />}
      {report.error && <ErrorBox error={report.error} />}
      {events.error && <ErrorBox error={events.error} />}
      {report.data && events.data && <ReportBody trip={t} report={report.data} events={events.data} />}
    </div>
  );
}

function ReportBody({ trip, report, events }: { trip: Trip; report: Report; events: TripEvent[] }) {
  const bd = readTripBreakdown(report.breakdown);
  const [selectedId, setSelectedId] = useState<number | null>(events[0]?.id ?? null);
  const selected = events.find((e) => e.id === selectedId) ?? null;
  const eventsById = new Map(events.map((e) => [e.id, e]));
  const select = (id: number) => {
    setSelectedId(id);
    document.getElementById("video-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const scoreCard = (className: string) => (
    <ScoreCard report={report} eventsById={eventsById} onSelectEvent={select} className={className} />
  );

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        {/* On phones the score comes first, above the video. */}
        {scoreCard("lg:hidden")}
        <Card title="Video">
          <div id="video-panel">
            <VideoPanel trip={trip} selected={selected} codecWarning={mayNotPlay(bd.video_codec)} />
          </div>
        </Card>
        <Card title={`Risky moments (${events.length})`}>
          {events.length === 0 ? (
            <p className="text-sm text-slate-600">
              No risky moments were flagged by the checks that ran. See "What we checked" for what wasn't covered.
            </p>
          ) : (
            <ul className="space-y-2">
              {events.map((ev) => (
                <li key={ev.id}>
                  <EventRow event={ev} active={selected?.id === ev.id} onSelect={() => select(ev.id)} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="space-y-4">
        {/* On wide screens the score sits at the top of the sidebar. */}
        {scoreCard("hidden lg:block")}

        <Card title="What we checked">
          <ChecksPanel rows={checkRows(report.not_checked, trip.has_gps)} />
        </Card>

        <Card title="Trip">
          <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
            <dt className="text-slate-500">Length</dt>
            <dd>{trip.duration_s != null ? formatTimestamp(trip.duration_s) : "—"}</dd>
            <dt className="text-slate-500">Distance</dt>
            <dd>{trip.distance_km != null ? `${trip.distance_km.toFixed(1)} km` : "— (no GPS)"}</dd>
            <dt className="text-slate-500">Risky moments</dt>
            <dd>{events.length}</dd>
            <dt className="text-slate-500">Critical</dt>
            <dd>{events.filter((e) => e.severity === "critical").length}</dd>
            <dt className="text-slate-500">Closest time-to-collision</dt>
            <dd>{formatTtc(bd.min_ttc_s ?? minOrNull(events.map((e) => e.min_ttc_s)))}</dd>
            {bd.thresholds && bd.ttc_below_warning_s !== null && (
              <>
                <dt className="text-slate-500">Time under {bd.thresholds.ttc_warning_s} s TTC</dt>
                <dd>{bd.ttc_below_warning_s.toFixed(1)} s</dd>
              </>
            )}
            {bd.thresholds && bd.ttc_below_critical_s !== null && (
              <>
                <dt className="text-slate-500">Time under {bd.thresholds.ttc_critical_s} s TTC</dt>
                <dd>{bd.ttc_below_critical_s.toFixed(1)} s</dd>
              </>
            )}
          </dl>
        </Card>

        {Object.keys(bd.objects_seen).length > 0 && (
          <Card title="Seen on the road">
            <ObjectsSeen counts={bd.objects_seen} />
          </Card>
        )}
      </div>
    </div>
  );
}

const minOrNull = (xs: (number | null)[]): number | null => {
  const nums = xs.filter((x): x is number => x !== null);
  return nums.length ? Math.min(...nums) : null;
};

function ScoreCard({
  report,
  eventsById,
  onSelectEvent,
  className,
}: {
  report: Report;
  eventsById: Map<number, TripEvent>;
  onSelectEvent: (id: number) => void;
  className: string;
}) {
  return (
    <Card title="Driving score" className={className}>
      <div className="flex items-center gap-4">
        <ScoreBadge score={report.score === null ? null : Math.round(report.score)} size="lg" />
        <div className="text-sm text-slate-600">
          {report.score === null ? (
            <p>Not enough was checked on this trip to give a score.</p>
          ) : (
            <p>Out of 100, based only on the checks that ran. Higher is safer.</p>
          )}
          {report.provisional && report.score !== null && (
            <p className="mt-1 text-xs text-amber-800">
              Score not calibrated yet: the scoring weights haven't been tuned on real trips, so treat it as a rough guide.
            </p>
          )}
        </div>
      </div>
      <FeedbackList items={report.feedback} eventsById={eventsById} onSelectEvent={onSelectEvent} />
    </Card>
  );
}

function VideoPanel({ trip, selected, codecWarning }: { trip: Trip; selected: TripEvent | null; codecWarning: boolean }) {
  const ref = useRef<HTMLVideoElement>(null);
  const clipUrl = selected ? api.clipUrl(selected) : null;
  const fullUrl = api.videoUrl(trip);
  const src = clipUrl ?? fullUrl;

  // With no clip for this moment, jump the full annotated video to a little before it.
  useEffect(() => {
    if (!clipUrl && selected && ref.current && fullUrl) {
      ref.current.currentTime = Math.max(0, selected.start_s - 3);
    }
  }, [clipUrl, selected, fullUrl]);

  if (!src) {
    return (
      <div className="flex aspect-video items-center justify-center rounded-lg bg-slate-900 p-6 text-center text-sm text-slate-300">
        {selected
          ? `No video saved for this moment (${formatTimestamp(selected.start_s)}).`
          : "No annotated video was saved for this trip."}
      </div>
    );
  }
  return (
    <div>
      {codecWarning && (
        <p className="mb-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">
          This video was saved in a format (mp4v) most browsers can't play. If it stays black, download it and open it
          in a desktop player such as VLC.
        </p>
      )}
      <video key={src} ref={ref} src={src} controls playsInline preload="metadata" className="aspect-video w-full rounded-lg bg-black">
        Your browser can't play this video.
      </video>
      {selected && (
        <p className="mt-2 text-xs text-slate-500">
          {clipUrl ? "Clip" : "Full trip video"} · {EVENT_LABELS[selected.type]} at {formatTimestamp(selected.start_s)}
        </p>
      )}
    </div>
  );
}

function EventRow({ event, active, onSelect }: { event: TripEvent; active: boolean; onSelect: () => void }) {
  const critical = event.severity === "critical";
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={`flex w-full items-start gap-3 rounded-lg border p-3 text-left ${
        active ? "border-brand-600 bg-brand-50" : "border-slate-200 hover:bg-slate-50"
      }`}
    >
      <span className="w-12 shrink-0 font-mono text-sm text-slate-600">{formatTimestamp(event.start_s)}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          {EVENT_LABELS[event.type] ?? event.type}: {classLabel(event.class_name).toLowerCase()}
        </p>
        <p className="text-xs text-slate-500">
          Closest TTC {formatTtc(event.min_ttc_s)} · distance{" "}
          <span title={event.distance_confidence === "low" ? "Estimated from one camera; can be off by 20-40%." : undefined}>
            {formatDistance(event)}
          </span>
        </p>
      </div>
      <span
        className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
          critical ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-800"
        }`}
      >
        {SEVERITY_LABELS[event.severity] ?? event.severity}
      </span>
    </button>
  );
}

const FEEDBACK_STYLE: Record<string, { icon: string; style: string }> = {
  issue: { icon: "!", style: "bg-amber-50 text-amber-800" },
  worst_moments: { icon: "!", style: "bg-red-50 text-red-700" },
  pattern: { icon: "~", style: "bg-slate-100 text-slate-600" },
  positive: { icon: "✓", style: "bg-green-50 text-green-700" },
};
const NEUTRAL = { icon: "i", style: "bg-slate-100 text-slate-600" };

function FeedbackList({
  items,
  eventsById,
  onSelectEvent,
}: {
  items: FeedbackLine[];
  eventsById: Map<number, TripEvent>;
  onSelectEvent: (id: number) => void;
}) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-4 space-y-2">
      {items.map((item, i) => {
        const look = FEEDBACK_STYLE[item.kind] ?? NEUTRAL;
        const linked = item.event_ids.map((id) => eventsById.get(id)).filter((e): e is TripEvent => Boolean(e));
        return (
          <li key={i} className="flex gap-2 text-sm">
            <span
              aria-hidden
              className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold ${look.style}`}
            >
              {look.icon}
            </span>
            <div>
              <span>{item.text}</span>
              {linked.length > 0 && (
                <span className="mt-1 flex flex-wrap gap-1">
                  {linked.map((e) => (
                    <button
                      key={e.id}
                      type="button"
                      onClick={() => onSelectEvent(e.id)}
                      className="rounded border border-slate-200 px-1.5 py-0.5 font-mono text-xs text-brand-700 hover:bg-brand-50"
                    >
                      ▶ {formatTimestamp(e.start_s)}
                    </button>
                  ))}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function ObjectsSeen({ counts }: { counts: Record<string, number> }) {
  const rows = Object.entries(counts)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  if (rows.length === 0) return <p className="text-sm text-slate-600">Nothing was tracked.</p>;
  const max = rows[0]![1];
  return (
    <>
      <ul className="space-y-1.5">
        {rows.map(([name, n]) => (
          <li key={name} className="grid grid-cols-[7rem_1fr_2.5rem] items-center gap-2 text-sm">
            <span className="truncate">{classLabel(name)}</span>
            <span className="h-2 rounded-full bg-slate-100">
              <span className="block h-2 rounded-full bg-brand-600/70" style={{ width: `${(n / max) * 100}%` }} />
            </span>
            <span className="text-right tabular-nums text-slate-600">{n}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-slate-500">Unique objects tracked, not frames.</p>
    </>
  );
}
