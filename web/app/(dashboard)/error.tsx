"use client";

import { useEffect } from "react";
import { ArrowClockwise, WarningCircle } from "@phosphor-icons/react";

/**
 * The API spins down on the free tier and cold-starts in ~50s, so a failed
 * fetch here is usually "not awake yet" rather than "broken". Say that, and
 * make retrying one click, instead of showing a stack trace.
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Dashboard render failed:", error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border-strong px-6 py-16 text-center">
      <span className="mb-3 grid h-11 w-11 place-items-center rounded-full bg-danger-soft text-danger">
        <WarningCircle size={20} />
      </span>
      <p className="font-display text-base font-semibold text-ink">This screen didn&apos;t load</p>
      <p className="mt-1 max-w-[48ch] text-sm text-ink-soft">
        The API may still be waking up, which takes about a minute on the free tier. Retry before assuming
        something is wrong.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition-opacity hover:opacity-90"
      >
        <ArrowClockwise size={15} />
        Try again
      </button>
      {error.digest && (
        <p className="mt-3 font-mono text-xs text-ink-faint">Reference: {error.digest}</p>
      )}
    </div>
  );
}
