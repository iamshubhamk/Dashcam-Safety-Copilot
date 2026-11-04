import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Card, ErrorBox } from "../components/ui";

/** Matches the backend's upload cap. */
export const MAX_VIDEO_BYTES = 2 * 1024 ** 3;
const VIDEO_TYPES = ".mp4,.mov,.avi,.mkv,video/*";
const GPS_TYPES = ".gpx,.csv";

export function validateVideo(file: File | null): string | null {
  if (!file) return "Choose a video file.";
  if (file.size > MAX_VIDEO_BYTES) return "That video is over 2 GB. Trim it or upload a shorter clip.";
  return null;
}

export function UploadPage() {
  const [video, setVideo] = useState<File | null>(null);
  const [gps, setGps] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [progress, setProgress] = useState(0);
  const [formError, setFormError] = useState<string | null>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const upload = useMutation({
    mutationFn: () => api.uploadTrip({ video: video!, gps, label }, setProgress),
    onSuccess: async (trip) => {
      await queryClient.invalidateQueries({ queryKey: ["trips"] });
      navigate(`/trips/${trip.id}`);
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const problem = validateVideo(video);
    setFormError(problem);
    if (problem) return;
    setProgress(0);
    upload.mutate();
  };

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-xl font-semibold">Upload a dashcam video</h1>
      <p className="text-sm text-slate-600">
        We detect vehicles, people, animals and road hazards, flag risky moments, and give you a driving report with
        a score out of 100. Processing runs after the upload finishes and can take a few minutes.
      </p>

      <Card>
        <form onSubmit={onSubmit} className="space-y-5">
          <div>
            <label htmlFor="video" className="block text-sm font-medium">
              Video <span className="text-red-600">*</span>
            </label>
            <p className="mb-2 text-xs text-slate-500">Forward-facing dashcam or phone video, up to 2 GB.</p>
            <input
              id="video"
              type="file"
              accept={VIDEO_TYPES}
              onChange={(e) => setVideo(e.target.files?.[0] ?? null)}
              className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-brand-50 file:px-3 file:py-2 file:text-brand-700"
            />
          </div>

          <div>
            <label htmlFor="gps" className="block text-sm font-medium">
              GPS file <span className="font-normal text-slate-500">(optional)</span>
            </label>
            <p className="mb-2 text-xs text-slate-500">
              A .gpx or .csv track recorded during the drive. Without it, the report still works but hazards from this
              trip won't appear on the map.
            </p>
            <input
              id="gps"
              type="file"
              accept={GPS_TYPES}
              onChange={(e) => setGps(e.target.files?.[0] ?? null)}
              className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-slate-700"
            />
          </div>

          <div>
            <label htmlFor="label" className="block text-sm font-medium">
              Name this trip <span className="font-normal text-slate-500">(optional)</span>
            </label>
            <input
              id="label"
              type="text"
              maxLength={120}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Office commute, Monday"
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-600 focus:outline-none"
            />
          </div>

          {formError && <ErrorBox error={formError} />}
          {upload.error && <ErrorBox error={upload.error} />}

          {upload.isPending && (
            <div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full bg-brand-600 transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
              </div>
              <p className="mt-1 text-xs text-slate-500">Uploading… {Math.round(progress * 100)}%</p>
            </div>
          )}

          <button
            type="submit"
            disabled={upload.isPending}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {upload.isPending ? "Uploading…" : "Upload and analyse"}
          </button>
        </form>
      </Card>
    </div>
  );
}
