import { CHECK_KEYS, type Checks } from "../api/types";
import { CHECK_LABELS, checkView } from "../lib/display";

/**
 * Lists what the pipeline checked. Anything not "ran" is shown as "Not checked" with a reason,
 * so a trip with no tailgating events is never mistaken for "no tailgating".
 */
export function ChecksPanel({ checks }: { checks: Checks }) {
  return (
    <ul className="divide-y divide-slate-100">
      {CHECK_KEYS.map((key) => {
        const view = checkView(checks[key]);
        return (
          <li key={key} className="flex items-start justify-between gap-3 py-2" data-testid={`check-${key}`}>
            <div>
              <p className="text-sm font-medium">{CHECK_LABELS[key]}</p>
              {view.reason && <p className="text-xs text-slate-500">{view.reason}</p>}
            </div>
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                view.checked ? "bg-green-50 text-green-700" : "bg-slate-100 text-slate-600"
              }`}
            >
              {view.label}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
