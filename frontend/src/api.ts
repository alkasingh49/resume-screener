import type { Assessment, Candidate, Job, JobBrief, UploadSummary } from "./types";

/** Vite proxies /api to the FastAPI backend - see vite.config.ts. */
const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init);

  if (!response.ok) {
    // FastAPI puts the useful message in `detail`; fall back to the status.
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) message = String(body.detail);
    } catch {
      /* response had no JSON body */
    }
    throw new Error(message);
  }

  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  health: () => request<{ api_key_set: boolean; model: string }>("/health"),

  // --- Job descriptions ---
  listJobs: () => request<JobBrief[]>("/jds"),
  getJob: (id: number) => request<Job>(`/jds/${id}`),
  uploadJob: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Job>("/jds", { method: "POST", body: form });
  },
  reparseJob: (id: number) => request<Job>(`/jds/${id}/reparse`, { method: "POST" }),
  deleteJob: (id: number) => request<void>(`/jds/${id}`, { method: "DELETE" }),

  // --- Resumes ---
  listCandidates: (jobId: number) => request<Candidate[]>(`/resumes?jd_id=${jobId}`),
  uploadResumes: (jobId: number, files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return request<UploadSummary>(`/resumes?jd_id=${jobId}`, { method: "POST", body: form });
  },
  rescreen: (id: number) => request<Candidate>(`/resumes/${id}/rescreen`, { method: "POST" }),
  deleteResume: (id: number) => request<void>(`/resumes/${id}`, { method: "DELETE" }),

  // --- Assessments ---
  listAssessments: (resumeId: number) =>
    request<Assessment[]>(`/assessments?resume_id=${resumeId}`),
  generateAssessment: (resumeId: number, count: number) =>
    request<Assessment>(`/assessments?resume_id=${resumeId}&num_questions=${count}`, {
      method: "POST",
    }),
};
