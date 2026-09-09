import type { Job } from "../types";
import { Banner, Button, Chip } from "./ui";

interface Props {
  job: Job;
  onReparse: () => void;
  onDelete: () => void;
  busy: boolean;
}

export function JobPanel({ job, onReparse, onDelete, busy }: Props) {
  const experience =
    job.min_years && job.max_years
      ? `${job.min_years}–${job.max_years} years`
      : job.min_years
        ? `${job.min_years}+ years`
        : "Not specified";

  return (
    <section className="border-b border-slate-200 bg-white px-8 py-6">
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight text-slate-900">
            {job.title || job.filename}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {[job.location, experience].filter(Boolean).join(" · ")}
            <span className="mx-2 text-slate-300">|</span>
            <span className="text-slate-400">{job.filename}</span>
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button size="sm" onClick={onReparse} busy={busy} title="Run the AI over this JD again">
            Re-analyse
          </Button>
          <Button size="sm" variant="danger" onClick={onDelete} disabled={busy}>
            Delete
          </Button>
        </div>
      </div>

      {job.status === "FAILED" && (
        <div className="mt-4">
          <Banner tone="error">{job.error || "This job description could not be analysed."}</Banner>
        </div>
      )}

      {job.status === "DONE" && (
        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <div>
            <h2 className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
              Must have
            </h2>
            <div className="flex flex-wrap gap-1.5">
              {job.must_have_skills.length ? (
                job.must_have_skills.map((skill) => (
                  <span
                    key={skill}
                    className="inline-flex rounded-md bg-indigo-50 px-2 py-1 text-xs
                      font-medium text-indigo-700 ring-1 ring-inset ring-indigo-600/20"
                  >
                    {skill}
                  </span>
                ))
              ) : (
                <span className="text-sm text-slate-400">None found</span>
              )}
            </div>
          </div>

          <div>
            <h2 className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
              Good to have
            </h2>
            <div className="flex flex-wrap gap-1.5">
              {job.good_to_have_skills.length ? (
                job.good_to_have_skills.map((skill) => <Chip key={skill}>{skill}</Chip>)
              ) : (
                <span className="text-sm text-slate-400">None found</span>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
