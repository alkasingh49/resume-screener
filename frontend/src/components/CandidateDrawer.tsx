import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Assessment, Candidate, Job, Question } from "../types";
import { Banner, Button, Chip, FitBadge, Spinner, years } from "./ui";

interface Props {
  candidate: Candidate;
  job: Job;
  onClose: () => void;
}

const DIFFICULTY_STYLES: Record<string, string> = {
  EASY: "bg-emerald-50 text-emerald-700",
  MEDIUM: "bg-amber-50 text-amber-700",
  HARD: "bg-rose-50 text-rose-700",
};

export function CandidateDrawer({ candidate, job, onClose }: Props) {
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [count, setCount] = useState(6);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const loadExisting = useCallback(async () => {
    setLoading(true);
    try {
      const existing = await api.listAssessments(candidate.id);
      setAssessment(existing[0] ?? null);
    } catch {
      setAssessment(null);
    } finally {
      setLoading(false);
    }
  }, [candidate.id]);

  useEffect(() => {
    void loadExisting();
  }, [loadExisting]);

  async function generate() {
    setGenerating(true);
    setError(null);
    try {
      setAssessment(await api.generateAssessment(candidate.id, count));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not generate questions");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 animate-fade-in bg-slate-900/25" onClick={onClose} />

      <div className="animate-slide-in relative flex h-full w-full max-w-2xl flex-col bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <h2 className="truncate text-xl font-semibold text-slate-900">
                {candidate.name || "Unnamed candidate"}
              </h2>
              <FitBadge fit={candidate.fit} />
            </div>
            <p className="mt-1 truncate text-sm text-slate-500">
              {candidate.current_title || "Role unknown"}
              {candidate.current_company && ` · ${candidate.current_company}`}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 space-y-7 overflow-y-auto px-6 py-6">
          <Facts candidate={candidate} />

          {candidate.reason && (
            <Section title="Why this rating">
              <p className="text-sm leading-relaxed text-slate-700">{candidate.reason}</p>
            </Section>
          )}

          {job.must_have_skills.length > 0 && (
            <Section title="Skill match">
              <div className="space-y-2.5">
                {job.must_have_skills.map((skill) => {
                  const score = candidate.skill_scores[skill] ?? 0;
                  return (
                    <div key={skill} className="flex items-center gap-3">
                      <span className="w-40 shrink-0 truncate text-sm text-slate-700">{skill}</span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className={`h-full rounded-full ${
                            score >= 7 ? "bg-emerald-500" : score >= 4 ? "bg-amber-500" : "bg-slate-300"
                          }`}
                          style={{ width: `${score * 10}%` }}
                        />
                      </div>
                      <span className="w-10 shrink-0 text-right text-sm font-medium tabular-nums text-slate-600">
                        {score}/10
                      </span>
                    </div>
                  );
                })}
              </div>
            </Section>
          )}

          {candidate.skills.length > 0 && (
            <Section title="Skills on the resume">
              <div className="flex flex-wrap gap-1.5">
                {candidate.skills.map((skill) => (
                  <Chip key={skill}>{skill}</Chip>
                ))}
              </div>
            </Section>
          )}

          {/* Assessment */}
          <Section title="Technical round">
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Spinner /> Loading…
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-3">
                  <label className="text-sm text-slate-600">
                    Questions
                    <select
                      value={count}
                      onChange={(e) => setCount(Number(e.target.value))}
                      className="ml-2 rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm
                        focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                    >
                      {[3, 6, 9, 12].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Button variant="primary" size="sm" onClick={generate} busy={generating}>
                    {assessment ? "Regenerate" : "Generate questions"}
                  </Button>
                  {assessment && (
                    <ExportButtons candidate={candidate} job={job} questions={assessment.questions} />
                  )}
                </div>

                {error && (
                  <div className="mt-3">
                    <Banner tone="error">{error}</Banner>
                  </div>
                )}

                {assessment ? (
                  <ol className="mt-4 space-y-3">
                    {assessment.questions.map((question, index) => (
                      <li
                        key={index}
                        className="rounded-lg border border-slate-200 bg-slate-50/60 p-4"
                      >
                        <div className="mb-2 flex flex-wrap items-center gap-2">
                          <span className="text-xs font-semibold text-slate-400">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <span
                            className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${
                              DIFFICULTY_STYLES[question.difficulty] ?? "bg-slate-100 text-slate-600"
                            }`}
                          >
                            {question.difficulty}
                          </span>
                          <Chip>{question.skill}</Chip>
                        </div>
                        <p className="text-sm leading-relaxed text-slate-900">{question.question}</p>
                        {question.expected_answer && (
                          <details className="group mt-2">
                            <summary
                              className="cursor-pointer text-xs font-medium text-indigo-600
                                select-none hover:text-indigo-800"
                            >
                              Expected answer (interviewer only)
                            </summary>
                            <p className="mt-1.5 border-l-2 border-slate-200 pl-3 text-sm whitespace-pre-line text-slate-600">
                              {question.expected_answer}
                            </p>
                          </details>
                        )}
                      </li>
                    ))}
                  </ol>
                ) : (
                  !generating && (
                    <p className="mt-3 text-sm text-slate-500">
                      Generate a technical round tailored to this candidate's background and the
                      role's must-have skills.
                    </p>
                  )
                )}
              </>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-3 text-xs font-semibold tracking-wide text-slate-500 uppercase">{title}</h3>
      {children}
    </section>
  );
}

function Facts({ candidate }: { candidate: Candidate }) {
  const facts: [string, string][] = [
    ["Email", candidate.email || "—"],
    ["Phone", candidate.phone || "—"],
    ["Location", candidate.location || "—"],
    ["Rating", candidate.score !== null ? `${candidate.score}/100` : "—"],
    ["Total experience", years(candidate.total_experience_years)],
    ["Relevant experience", years(candidate.relevant_experience_years)],
  ];

  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 rounded-xl bg-slate-50 p-5">
      {facts.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="text-xs font-medium text-slate-500">{label}</dt>
          <dd className="mt-0.5 truncate text-sm font-medium text-slate-900" title={value}>
            {value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Two exports: one for the candidate (questions only) and one for the
 *  interviewer (with the expected answers). */
function ExportButtons({
  candidate,
  job,
  questions,
}: {
  candidate: Candidate;
  job: Job;
  questions: Question[];
}) {
  function download(withAnswers: boolean) {
    const lines = [
      `# Technical assessment — ${job.title || "Role"}`,
      `Candidate: ${candidate.name || candidate.filename}`,
      "",
    ];
    questions.forEach((question, index) => {
      lines.push(`## ${index + 1}. ${question.question}`);
      lines.push(`*${question.skill} · ${question.difficulty}*`);
      if (withAnswers && question.expected_answer) {
        lines.push("", `**Expected answer:** ${question.expected_answer}`);
      }
      lines.push("");
    });

    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const who = (candidate.name || "candidate").replace(/\s+/g, "-").toLowerCase();
    link.href = url;
    link.download = `assessment-${who}${withAnswers ? "-interviewer" : ""}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <Button size="sm" onClick={() => download(false)} title="Questions only, safe to send out">
        For candidate
      </Button>
      <Button size="sm" onClick={() => download(true)} title="Includes expected answers">
        For interviewer
      </Button>
    </>
  );
}
