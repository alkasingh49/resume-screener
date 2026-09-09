import { useRef, useState } from "react";
import { Spinner } from "./ui";

interface Props {
  onUpload: (files: File[]) => Promise<void>;
  disabled: boolean;
}

export function UploadZone({ onUpload, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);

  async function send(files: FileList | null) {
    if (!files?.length || disabled) return;
    setUploading(true);
    try {
      await onUpload(Array.from(files));
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        void send(e.dataTransfer.files);
      }}
      onClick={() => !disabled && inputRef.current?.click()}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-xl
        border-2 border-dashed px-6 py-8 text-center transition ${
          disabled
            ? "cursor-not-allowed border-slate-200 bg-slate-50 opacity-60"
            : dragging
              ? "border-indigo-400 bg-indigo-50"
              : "border-slate-300 bg-white hover:border-indigo-300 hover:bg-slate-50"
        }`}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.docx,.txt,.rtf,.md"
        className="hidden"
        disabled={disabled}
        onChange={(e) => void send(e.target.files)}
      />

      {uploading ? (
        <div className="flex items-center gap-2 text-sm font-medium text-indigo-700">
          <Spinner /> Uploading…
        </div>
      ) : (
        <>
          <svg
            className="mb-2 h-7 w-7 text-slate-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
            aria-hidden
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 16.5V9.75m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 0 1-1.41-8.775
                 5.25 5.25 0 0 1 10.233-2.33 3 3 0 0 1 3.758 3.848A3.752 3.752 0 0 1 18 19.5H6.75Z"
            />
          </svg>
          <p className="text-sm font-medium text-slate-900">
            {disabled ? "Analyse the job description first" : "Drop resumes here, or click to browse"}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Upload as many as you like at once · PDF, DOCX, TXT, RTF
          </p>
        </>
      )}
    </div>
  );
}
