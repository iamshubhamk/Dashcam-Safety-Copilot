import type { CheckRow } from "../lib/display";

/**
 * Lists what the pipeline checked. Anything the backend reports in not_checked is shown as
 * "Not checked" with a reason, so a trip with no tailgating events is never mistaken for
 * "no tailgating".
 */
export function ChecksPanel({ rows }: { rows: CheckRow[] }) {
  return (
    <ul className="divide-y divide-slate-100">
      {rows.map((row) => (
        <li key={row.type} className="flex items-start justify-between gap-3 py-2" data-testid={`check-${row.type}`}>
          <div>
            <p className="text-sm font-medium">{row.label}</p>
            {row.reason && <p className="text-xs text-slate-500">{row.reason}</p>}
          </div>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
              row.checked ? "bg-green-50 text-green-700" : "bg-slate-100 text-slate-600"
            }`}
          >
            {row.checked ? "Checked" : "Not checked"}
          </span>
        </li>
      ))}
    </ul>
  );
}
