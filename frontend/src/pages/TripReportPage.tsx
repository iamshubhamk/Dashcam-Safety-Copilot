import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { EVENT_TYPES, type FeedbackItem, type SafetyEvent, type TripReport } from "../api/types";
import { ChecksPanel } from "../components/ChecksPanel";
import { Card, ErrorBox, Loading, ScoreBadge, StatusPill } from "../components/ui";
import {
  EVENT_LABELS,
  SEVERITY_LABELS,
  classLabel,
  eventCount,
  formatDistance,
  formatTimestamp,
  formatTtc,
} from "../lib/display";

export function TripReportPage() {
  const { id = "" } = useParams();

  const trip = useQuery({
    queryKey: ["trip", id],
    queryFn: () => api.getTrip(id),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "queued" || s === "processing" ? 3_000 : false;
    },
  });

  const report = useQuery({
    queryKey: ["report", id],
    queryFn: () => api.getReport(id),
    enabled: trip.data?.status === "done",
  });

  if (trip.isLoading) return <Loading what="trip" />;
  if (trip.error) return <ErrorBox error={trip.error} />;
  const t = trip.data!;
  const title = t.label ?? t.original_filename;

  return (
    <div className="space-y-4">
      <Link to="/trips" className="text-sm text-brand-600 hover:underline">
        ← All trips
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{title}</h1>
        <StatusPill status={t.status} progress={t.progress} />
      </div>

      {(t.status === "queued" || t.status === "processing") && (
        <Card>
          <p className="text-sm text-slate-600">
            {t.status === "queued"
              ? "Waiting for the analyser to pick up this video."
              : "Analysing the video: detecting objects, tracking them and checking for risky moments."}{" "}
            This page updates by itself.
          </p>
          {t.status === "processing" && t.progress != null && (
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full bg-brand-600 transition-all" style={{ width: `${Math.round(t.progress * 100)}%` }} />
            </div>
          )}
        </Card>
      )}

      {t.status === "failed" && <ErrorBox error={t.error ?? "Processing failed."} />}

      {t.status === "done" && report.isLoading && <Loading what="report" />}
      {report.error && <ErrorBox error={report.error} />}
      {report.data && <ReportBody report={report.data} />}
    </div>
  );
}

function ReportBody({ report }: { report: TripReport }) {
  const doc = report.events_doc;
  const [selected, setSelected] = useState<SafetyEvent | null>(doc.events[0] ?? null);

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        {/* On phones the score comes first, above the video. */}
        <ScoreCard report={report} className="lg:hidden" />
        <Card title="Video">
          <VideoPanel report={report} selected={selected} />
        </Card>
        <Card title={`Risky moments (${doc.events.length})`}>
          {doc.events.length === 0 ? (
            <p className="text-sm text-slate-600">
              No risky moments were flagged by the checks that ran. See "What we checked" for what wasn't covered.
            </p>
          ) : (
            <ul className="space-y-2">
              {doc.events.map((ev) => (
                <li key={ev.event_id}>
                  <EventRow event={ev} active={selected?.event_id === ev.event_id} onSelect={() => setSelected(ev)} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="space-y-4">
        {/* On wide screens the score sits at the top of the sidebar. */}
        <ScoreCard report={report} className="hidden lg:block" />

        <Card title="What we checked">
          <ChecksPanel checks={doc.trip_summary.checks} />
        </Card>

        <Card title="Trip numbers">
          <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
            <dt className="text-slate-500">Length</dt>
            <dd>{formatTimestamp(doc.video.duration_s)}</dd>
            <dt className="text-slate-500">Closest time-to-collision</dt>
            <dd>{formatTtc(doc.trip_summary.min_ttc_s)}</dd>
            <dt className="text-slate-500">Time under {doc.thresholds.ttc_warning_s} s TTC</dt>
            <dd>{doc.trip_summary.ttc_below_warning_s.toFixed(1)} s</dd>
            <dt className="text-slate-500">Time under {doc.thresholds.ttc_critical_s} s TTC</dt>
            <dd>{doc.trip_summary.ttc_below_critical_s.toFixed(1)} s</dd>
            {EVENT_TYPES.map((type) => {
              const n = eventCount(doc.trip_summary, type);
              return (
                <div key={type} className="contents">
                  <dt className="text-slate-500">{EVENT_LABELS[type]}</dt>
                  <dd className={n === null ? "text-slate-400" : ""}>{n === null ? "not checked" : n}</dd>
                </div>
              );
            })}
          </dl>
        </Card>

        <Card title="Seen on the road">
          <ObjectsSeen counts={doc.objects_seen} />
        </Card>
      </div>
    </div>
  );
}

function ScoreCard({ report, className }: { report: TripReport; className: string }) {
  return (
    <Card title="Driving score" className={className}>
      <div className="flex items-center gap-4">
        <ScoreBadge score={report.score} size="lg" />
        <p className="text-sm text-slate-600">Out of 100, based only on the checks that ran. Higher is safer.</p>
      </div>
      <FeedbackList items={report.feedback} />
    </Card>
  );
}

function VideoPanel({ report, selected }: { report: TripReport; selected: SafetyEvent | null }) {
  const ref = useRef<HTMLVideoElement>(null);
  const clipUrl = selected ? report.clip_urls[selected.event_id] : undefined;
  const src = clipUrl ?? report.annotated_video_url;

  // With no per-event clip, jump the full annotated video to a little before the event.
  useEffect(() => {
    if (!clipUrl && selected && ref.current && report.annotated_video_url) {
      ref.current.currentTime = Math.max(0, selected.start_time_s - 3);
    }
  }, [clipUrl, selected, report.annotated_video_url]);

  if (!src) {
    return (
      <div className="flex aspect-video items-center justify-center rounded-lg bg-slate-900 p-6 text-center text-sm text-slate-300">
        {selected
          ? `No video saved for this moment (${formatTimestamp(selected.start_time_s)}).`
          : "No annotated video was saved for this trip."}
      </div>
    );
  }
  return (
    <video key={src} ref={ref} src={src} controls playsInline preload="metadata" className="aspect-video w-full rounded-lg bg-black">
      Your browser can't play this video.
    </video>
  );
}

function EventRow({ event, active, onSelect }: { event: SafetyEvent; active: boolean; onSelect: () => void }) {
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
      <span className="w-12 shrink-0 font-mono text-sm text-slate-600">{formatTimestamp(event.start_time_s)}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          {EVENT_LABELS[event.type]}: {classLabel(event.class_name).toLowerCase()}
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
        {SEVERITY_LABELS[event.severity]}
      </span>
    </button>
  );
}

const FEEDBACK_ICON: Record<FeedbackItem["kind"], string> = { good: "✓", improve: "!", info: "i" };
const FEEDBACK_STYLE: Record<FeedbackItem["kind"], string> = {
  good: "bg-green-50 text-green-700",
  improve: "bg-amber-50 text-amber-800",
  info: "bg-slate-100 text-slate-600",
};

function FeedbackList({ items }: { items: FeedbackItem[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-4 space-y-2">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-sm">
          <span
            aria-hidden
            className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold ${FEEDBACK_STYLE[item.kind]}`}
          >
            {FEEDBACK_ICON[item.kind]}
          </span>
          <span>{item.text}</span>
        </li>
      ))}
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
  );
}
