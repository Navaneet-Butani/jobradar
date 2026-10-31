import type { ReactNode } from "react";

/**
 * One page header for every screen, so titles, counts and actions sit in the
 * same place everywhere instead of each page inventing its own arrangement.
 */
export function PageHeader({
  title,
  description,
  meta,
  actions,
}: {
  title: string;
  description?: string;
  /** Short factual counts. Rendered inline under the title. */
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 border-b border-border pb-5">
      <div className="min-w-0">
        <h1 className="font-display text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-[65ch] text-sm text-ink-soft">{description}</p>}
        {meta && <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">{meta}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** A labelled number for the header meta row. Numbers are monospaced so columns of them line up. */
export function Stat({ label, value, tone = "default" }: { label: string; value: number | string; tone?: "default" | "accent" | "strong" }) {
  const toneClass =
    tone === "accent" ? "text-accent" : tone === "strong" ? "text-score-strong" : "text-ink";
  return (
    <span className="text-ink-faint">
      <span className={`font-mono font-semibold tabular-nums ${toneClass}`}>{value}</span> {label}
    </span>
  );
}
