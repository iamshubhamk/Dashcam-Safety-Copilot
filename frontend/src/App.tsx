import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { API_MODE } from "./api/client";
import { TripsPage } from "./pages/TripsPage";
import { UploadPage } from "./pages/UploadPage";
import { TripReportPage } from "./pages/TripReportPage";
import { HazardMapPage } from "./pages/HazardMapPage";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-2 text-sm font-medium ${
    isActive ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
  }`;

export function App() {
  return (
    <div className="min-h-screen">
      {API_MODE === "mock" && (
        <div className="bg-amber-100 px-4 py-1.5 text-center text-xs text-amber-900">
          Demo mode: trips, scores and hazards below are made-up sample data, not results from a real video.
        </div>
      )}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <NavLink to="/trips" className="text-base font-semibold tracking-tight">
            Dashcam Safety Copilot
          </NavLink>
          <nav className="flex flex-wrap gap-1">
            <NavLink to="/trips" className={navClass}>
              Trips
            </NavLink>
            <NavLink to="/upload" className={navClass}>
              Upload
            </NavLink>
            <NavLink to="/map" className={navClass}>
              Hazard map
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Navigate to="/trips" replace />} />
          <Route path="/trips" element={<TripsPage />} />
          <Route path="/trips/:id" element={<TripReportPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/map" element={<HazardMapPage />} />
          <Route path="*" element={<p className="text-slate-600">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
