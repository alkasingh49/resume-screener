import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { CandidateDrawer } from "./components/CandidateDrawer";
import { JobPanel } from "./components/JobPanel";
import { ResultsTable } from "./components/ResultsTable";
import { Sidebar } from "./components/Sidebar";
import { UploadZone } from "./components/UploadZone";
import { Banner, EmptyState } from "./components/ui";
import type { Candidate, Job, JobBrief } from "./types";

const POLL_MS = 2500;

export default function App() {
  const [jobs, setJobs] = useState<JobBrief[]>([]);
  const [jobId, setJobId] = useState<number | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Candidate | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [keyMissing, setKeyMissing] = useState(false);
  const [busyJob, setBusyJob] = useState(false);
  const [rescreening, setRescreening] = useState<number | null>(null);

  const report = (e: unknown) => setError(e instanceof Error ? e.message : String(e));

  // --- initial load ------------------------------------------------------
  const refreshJobs = useCallback(async () => {
    const list = await api.listJobs();
    setJobs(list);
    return list;
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const [list, health] = await Promise.all([refreshJobs(), api.health()]);
        setKeyMissing(!health.api_key_set);
        if (list.length > 0) setJobId(list[0].id);
      } catch (e) {
        report(e);
      }
    })();
  }, [refreshJobs]);

  // --- selected job + its candidates -------------------------------------
  const refreshCandidates = useCallback(async (id: number) => {
    const rows = await api.listCandidates(id);
    setCandidates(rows);
    return rows;
  }, []);

  useEffect(() => {
    if (jobId === null) {
      setJob(null);
      setCandidates([]);
      return;
    }
    void (async () => {
      try {
        const [detail] = await Promise.all([api.getJob(jobId), refreshCandidates(jobId)]);
        setJob(detail);
      } catch (e) {
        report(e);
      }
    })();
  }, [jobId, refreshCandidates]);

  // --- poll while anything is still screening ----------------------------
  const workingCount = candidates.filter(
    (c) => c.status === "PENDING" || c.status === "PROCESSING",
  ).length;

  const jobIdRef = useRef(jobId);
  jobIdRef.current = jobId;

  useEffect(() => {
    if (workingCount === 0 || jobId === null) return;

    const timer = setInterval(() => {
      const current = jobIdRef.current;
      if (current === null) return;
      void refreshCandidates(current)
        .then(() => refreshJobs())
        .catch(report);
    }, POLL_MS);

    return () => clearInterval(timer);
  }, [workingCount, jobId, refreshCandidates, refreshJobs]);

  // Keep the open drawer in sync with polled data.
  useEffect(() => {
    if (!selected) return;
    const fresh = candidates.find((c) => c.id === selected.id);
    if (fresh && fresh !== selected) setSelected(fresh);
  }, [candidates, selected]);

  // --- actions -----------------------------------------------------------
  async function addJob(file: File) {
    setError(null);
    try {
      const created = await api.uploadJob(file);
      await refreshJobs();
      setJobId(created.id);
    } catch (e) {
      report(e);
    }
  }

  async function addResumes(files: File[]) {
    if (jobId === null) return;
    setError(null);
    try {
      const summary = await api.uploadResumes(jobId, files);
      setCandidates(summary.resumes);
      await refreshCandidates(jobId);
      await refreshJobs();
    } catch (e) {
      report(e);
    }
  }

  async function reparse() {
    if (jobId === null) return;
    setBusyJob(true);
    setError(null);
    try {
      setJob(await api.reparseJob(jobId));
      await refreshJobs();
    } catch (e) {
      report(e);
    } finally {
      setBusyJob(false);
    }
  }

  async function removeJob() {
    if (jobId === null) return;
    if (!confirm("Delete this job description and every resume screened against it?")) return;
    setBusyJob(true);
    try {
      await api.deleteJob(jobId);
      const list = await refreshJobs();
      setJobId(list[0]?.id ?? null);
    } catch (e) {
      report(e);
    } finally {
      setBusyJob(false);
    }
  }

  async function rescreen(candidate: Candidate) {
    setRescreening(candidate.id);
    try {
      await api.rescreen(candidate.id);
      if (jobId !== null) await refreshCandidates(jobId);
    } catch (e) {
      report(e);
    } finally {
      setRescreening(null);
    }
  }

  // --- render ------------------------------------------------------------
  const done = candidates.filter((c) => c.status === "DONE");
  const stats = [
    { label: "Candidates", value: candidates.length, tone: "text-slate-900" },
    { label: "Best fit", value: done.filter((c) => c.fit === "BEST").length, tone: "text-emerald-600" },
    { label: "Medium", value: done.filter((c) => c.fit === "MEDIUM").length, tone: "text-amber-600" },
    { label: "Not a fit", value: done.filter((c) => c.fit === "NO").length, tone: "text-slate-500" },
  ];

  return (
    <div className="flex h-screen flex-col bg-slate-50 text-slate-900">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
            R
          </div>
          <span className="font-semibold tracking-tight">Resume Screener</span>
        </div>
        {workingCount > 0 && (
          <span className="text-sm text-indigo-600">
            Screening {workingCount} resume{workingCount === 1 ? "" : "s"}…
          </span>
        )}
      </header>

      <div className="flex min-h-0 flex-1">
        <Sidebar jobs={jobs} selectedId={jobId} onSelect={setJobId} onUpload={addJob} />

        <main className="min-w-0 flex-1 overflow-y-auto">
          {(keyMissing || error) && (
            <div className="space-y-2 px-8 pt-6">
              {keyMissing && (
                <Banner tone="error">
                  No AI API key is configured. Add <code className="font-mono">GOOGLE_API_KEY</code>{" "}
                  to your <code className="font-mono">.env</code> file and restart the backend —
                  until then every upload will fail.
                </Banner>
              )}
              {error && <Banner tone="error">{error}</Banner>}
            </div>
          )}

          {!job ? (
            <EmptyState
              title="No job description selected"
              hint="Add a job description on the left to start screening candidates against it."
              icon={
                <svg className="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.2}>
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M20.25 14.15v4.07a2.25 2.25 0 0 1-2.25 2.25h-12a2.25 2.25 0 0
                       1-2.25-2.25v-4.07m16.5 0a2.25 2.25 0 0 0-.659-1.591L16.5
                       7.5m3.75 6.65V9.75a2.25 2.25 0 0 0-2.25-2.25H16.5m-12
                       6.65a2.25 2.25 0 0 1 .659-1.591L7.5 7.5m-3.75
                       6.65V9.75a2.25 2.25 0 0 1 2.25-2.25H7.5m9 0v-3a1.5
                       1.5 0 0 0-1.5-1.5h-6a1.5 1.5 0 0 0-1.5 1.5v3m9 0h-9"
                  />
                </svg>
              }
            />
          ) : (
            <>
              <JobPanel job={job} onReparse={reparse} onDelete={removeJob} busy={busyJob} />

              <div className="space-y-6 px-8 py-6">
                <UploadZone onUpload={addResumes} disabled={job.status !== "DONE"} />

                {candidates.length > 0 && (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {stats.map((stat) => (
                      <div
                        key={stat.label}
                        className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
                      >
                        <div className={`text-2xl font-semibold tabular-nums ${stat.tone}`}>
                          {stat.value}
                        </div>
                        <div className="mt-0.5 text-xs font-medium text-slate-500">{stat.label}</div>
                      </div>
                    ))}
                  </div>
                )}

                <ResultsTable
                  candidates={candidates}
                  onSelect={setSelected}
                  onRescreen={rescreen}
                  rescreening={rescreening}
                />
              </div>
            </>
          )}
        </main>
      </div>

      {selected && job && (
        <CandidateDrawer candidate={selected} job={job} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
