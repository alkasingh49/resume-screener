import type { Candidate } from "../types";
import { Button, EmptyState, FitBadge, ScoreBar, StatusPill, years } from "./ui";

interface Props {
  candidates: Candidate[];
  onSelect: (candidate: Candidate) => void;
  onRescreen: (candidate: Candidate) => void;
  rescreening: number | null;
}

const HEADERS = [
  "Candidate",
  "Contact",
  "Total exp",
  "Relevant exp",
  "Fit",
  "Rating",
  "Reason",
  "",
];

export function ResultsTable({ candidates, onSelect, onRescreen, rescreening }: Props) {
  if (candidates.length === 0) {
    return (
      <EmptyState
        title="No resumes yet"
        hint="Upload a batch above and the AI will parse and rank every candidate against this role."
        icon={
          <svg className="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.2}>
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1
                 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25M9 16.5v.75m3-3v3M15
                 12v5.25m-4.5-15H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0
                 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504
                 1.125-1.125V11.25a9 9 0 0 0-9-9Z"
            />
          </svg>
        }
      />
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full min-w-[64rem] border-collapse text-left">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50">
            {HEADERS.map((header) => (
              <th
                key={header}
                className="px-4 py-3 text-xs font-semibold tracking-wide text-slate-500 uppercase whitespace-nowrap"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {candidates.map((candidate) => {
            const done = candidate.status === "DONE";
            return (
              <tr
                key={candidate.id}
                onClick={() => done && onSelect(candidate)}
                className={`transition ${done ? "cursor-pointer hover:bg-indigo-50/40" : "bg-slate-50/40"}`}
              >
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-900">
                    {candidate.name || <span className="text-slate-400">Unnamed</span>}
                  </div>
                  <div className="mt-0.5 max-w-[14rem] truncate text-xs text-slate-500">
                    {candidate.current_title
                      ? `${candidate.current_title}${candidate.current_company ? ` · ${candidate.current_company}` : ""}`
                      : candidate.filename}
                  </div>
                </td>

                <td className="px-4 py-3 text-sm">
                  {done ? (
                    <>
                      <div className="max-w-[13rem] truncate text-slate-700">
                        {candidate.email || <span className="text-slate-400">No email</span>}
                      </div>
                      <div className="mt-0.5 text-xs text-slate-500">
                        {candidate.phone || "No phone"}
                      </div>
                    </>
                  ) : (
                    <StatusPill status={candidate.status} />
                  )}
                </td>

                <td className="px-4 py-3 text-sm whitespace-nowrap text-slate-700">
                  {done ? years(candidate.total_experience_years) : "—"}
                </td>
                <td className="px-4 py-3 text-sm font-medium whitespace-nowrap text-slate-900">
                  {done ? years(candidate.relevant_experience_years) : "—"}
                </td>
                <td className="px-4 py-3">{done ? <FitBadge fit={candidate.fit} /> : null}</td>
                <td className="px-4 py-3">{done ? <ScoreBar score={candidate.score} /> : null}</td>

                <td className="px-4 py-3">
                  <p className="line-clamp-2 max-w-sm text-sm text-slate-600">
                    {candidate.status === "FAILED" ? (
                      <span className="text-rose-600">{candidate.error}</span>
                    ) : (
                      candidate.reason || ""
                    )}
                  </p>
                </td>

                <td className="px-4 py-3 text-right whitespace-nowrap">
                  {candidate.status === "FAILED" ? (
                    <Button
                      size="sm"
                      busy={rescreening === candidate.id}
                      onClick={() => onRescreen(candidate)}
                    >
                      Retry
                    </Button>
                  ) : done ? (
                    <span className="text-xs font-medium text-indigo-600">View →</span>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
