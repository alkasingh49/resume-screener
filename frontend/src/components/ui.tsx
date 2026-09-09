import type { ReactNode } from "react";
import type { Fit, Status } from "../types";

/** Small building blocks shared across the app, so spacing, radius and
 *  colour stay consistent without a component library. */

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-20" />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

type ButtonProps = {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  disabled?: boolean;
  busy?: boolean;
  title?: string;
};

const BUTTON_VARIANTS = {
  primary: "bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm",
  secondary: "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shadow-sm",
  ghost: "text-slate-600 hover:bg-slate-100",
  danger: "text-rose-600 hover:bg-rose-50",
};

export function Button({
  children,
  onClick,
  variant = "secondary",
  size = "md",
  disabled,
  busy,
  title,
}: ButtonProps) {
  const sizing = size === "sm" ? "px-2.5 py-1.5 text-xs gap-1.5" : "px-4 py-2 text-sm gap-2";
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled || busy}
      className={`inline-flex items-center justify-center rounded-lg font-medium transition
        focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1
        disabled:opacity-50 disabled:cursor-not-allowed ${sizing} ${BUTTON_VARIANTS[variant]}`}
    >
      {busy && <Spinner className="h-3.5 w-3.5" />}
      {children}
    </button>
  );
}

const FIT_STYLES: Record<Fit, string> = {
  BEST: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  MEDIUM: "bg-amber-50 text-amber-700 ring-amber-600/20",
  NO: "bg-slate-100 text-slate-600 ring-slate-500/20",
};

const FIT_LABELS: Record<Fit, string> = { BEST: "Best fit", MEDIUM: "Medium", NO: "Not a fit" };

export function FitBadge({ fit }: { fit: Fit | null }) {
  if (!fit) return <span className="text-slate-400">—</span>;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold
        ring-1 ring-inset whitespace-nowrap ${FIT_STYLES[fit]}`}
    >
      {FIT_LABELS[fit]}
    </span>
  );
}

const STATUS_STYLES: Record<Status, string> = {
  PENDING: "bg-slate-100 text-slate-600",
  PROCESSING: "bg-indigo-50 text-indigo-700",
  DONE: "bg-emerald-50 text-emerald-700",
  FAILED: "bg-rose-50 text-rose-700",
};

export function StatusPill({ status }: { status: Status }) {
  const busy = status === "PENDING" || status === "PROCESSING";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs
        font-medium whitespace-nowrap ${STATUS_STYLES[status]}`}
    >
      {busy && <Spinner className="h-3 w-3" />}
      {status === "PROCESSING" ? "Screening" : status.charAt(0) + status.slice(1).toLowerCase()}
    </span>
  );
}

/** The 0-100 rating, as a number plus a bar so the table scans quickly. */
export function ScoreBar({ score }: { score: number | null }) {
  if (score === null) return <span className="text-slate-400">—</span>;

  const tone =
    score >= 75 ? "bg-emerald-500" : score >= 45 ? "bg-amber-500" : "bg-slate-400";

  return (
    <div className="flex items-center gap-2.5">
      <span className="w-8 text-sm font-semibold tabular-nums text-slate-900">{score}</span>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-200">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

export function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
      {children}
    </span>
  );
}

export function Banner({ tone, children }: { tone: "error" | "info"; children: ReactNode }) {
  const styles =
    tone === "error"
      ? "bg-rose-50 text-rose-800 ring-rose-600/20"
      : "bg-indigo-50 text-indigo-800 ring-indigo-600/20";
  return (
    <div className={`rounded-lg px-4 py-3 text-sm ring-1 ring-inset ${styles}`}>{children}</div>
  );
}

export function EmptyState({
  title,
  hint,
  icon,
}: {
  title: string;
  hint: string;
  icon: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-3 text-slate-300">{icon}</div>
      <p className="text-sm font-medium text-slate-900">{title}</p>
      <p className="mt-1 max-w-sm text-sm text-slate-500">{hint}</p>
    </div>
  );
}

export function years(value: number | null): string {
  if (value === null || value === undefined) return "—";
  const rounded = Math.round(value * 10) / 10;
  return `${rounded} yr${rounded === 1 ? "" : "s"}`;
}
