import type { ReactNode } from "react";
import type { TripStatus } from "../api/types";
import { scoreBand } from "../lib/display";

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm ${className}`}>
      {title && <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>}
      {children}
    </section>
  );
}

const BAND_STYLES = {
  good: "bg-green-50 text-good ring-green-200",
  fair: "bg-amber-50 text-fair ring-amber-200",
  poor: "bg-red-50 text-poor ring-red-200",
} as const;

export function ScoreBadge({ score, size = "sm" }: { score: number | null; size?: "sm" | "lg" }) {
  const sizing = size === "lg" ? "h-24 w-24 text-4xl" : "h-10 w-10 text-sm";
  if (score === null) {
    return (
      <span className={`inline-flex shrink-0 items-center justify-center rounded-full bg-slate-50 text-slate-400 ring-1 ring-slate-200 ${sizing}`} aria-label="No score">
        —
      </span>
    );
  }
  const band = scoreBand(score);
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ring-1 ${sizing} ${BAND_STYLES[band]}`}
      aria-label={`Score ${score} out of 100`}
    >
      {score}
    </span>
  );
}

const STATUS_STYLES: Record<TripStatus, string> = {
  queued: "bg-slate-100 text-slate-700",
  processing: "bg-blue-50 text-blue-700",
  done: "bg-green-50 text-green-700",
  failed: "bg-red-50 text-red-700",
};

const STATUS_LABELS: Record<TripStatus, string> = {
  queued: "Queued",
  processing: "Processing",
  done: "Ready",
  failed: "Failed",
};

export function StatusPill({ status, progress }: { status: TripStatus; progress?: number | null }) {
  const pct = status === "processing" && progress != null ? ` ${Math.round(progress * 100)}%` : "";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}>
      {STATUS_LABELS[status]}
      {pct}
    </span>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      {message}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="text-sm text-slate-500">Loading {what}…</p>;
}
