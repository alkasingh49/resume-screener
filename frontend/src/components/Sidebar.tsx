import { useRef, useState } from "react";
import type { JobBrief } from "../types";
import { Button, Spinner } from "./ui";

interface Props {
  jobs: JobBrief[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onUpload: (file: File) => Promise<void>;
}

export function Sidebar({ jobs, selectedId, onSelect, onUpload }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    try {
      await onUpload(file);
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="border-b border-slate-200 p-4">
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.txt,.rtf,.md"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <Button variant="primary" onClick={() => inputRef.current?.click()} busy={uploading}>
          {uploading ? "Analysing…" : "+ Add job description"}
        </Button>
        <p className="mt-2 text-xs text-slate-500">PDF, DOCX, TXT or RTF</p>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {jobs.length === 0 ? (
          <p className="px-2 py-6 text-center text-sm text-slate-400">No job descriptions yet</p>
        ) : (
          <ul className="space-y-1">
            {jobs.map((job) => {
              const selected = job.id === selectedId;
              return (
                <li key={job.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(job.id)}
                    className={`w-full rounded-lg px-3 py-2.5 text-left transition ${
                      selected ? "bg-indigo-50 ring-1 ring-indigo-200" : "hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span
                        className={`truncate text-sm font-medium ${
                          selected ? "text-indigo-900" : "text-slate-900"
                        }`}
                      >
                        {job.title || job.filename}
                      </span>
                      {job.status === "PROCESSING" && (
                        <Spinner className="mt-0.5 h-3 w-3 shrink-0 text-indigo-500" />
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                      {job.status === "FAILED" ? (
                        <span className="text-rose-600">Could not read this file</span>
                      ) : (
                        <span>
                          {job.resume_count} resume{job.resume_count === 1 ? "" : "s"}
                        </span>
                      )}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
