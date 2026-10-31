"use client";

import { createContext, useContext, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { X } from "@phosphor-icons/react";
import type { MatchState } from "@/lib/types";

/**
 * Checkbox + batch actions around a list of server-rendered cards.
 *
 * The provider owns the selection and the action bar; `SelectableRow` only
 * renders a checkbox beside `children`. Splitting it that way keeps MatchCard
 * a server component — wrapping the cards themselves in a client component
 * would drag the whole card tree, icons included, into the client bundle for
 * the sake of one checkbox.
 */

type Ctx = {
  selected: Set<number>;
  toggle: (id: number) => void;
  busy: boolean;
};

const SelectionContext = createContext<Ctx | null>(null);

const ACTIONS: { state: MatchState; label: string }[] = [
  { state: "dismissed", label: "Dismiss" },
  { state: "interested", label: "Interested" },
  { state: "seen", label: "Mark seen" },
];

export function BulkSelect({
  profileId,
  jobIds,
  children,
}: {
  profileId: number;
  /** Everything on this page, for "select all". */
  jobIds: number[];
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  // Which action is running, not just "something is" -- with a single
  // boolean all three buttons relabelled themselves to "Saving…" at once,
  // so you could not tell what you had actually pressed.
  const [running, setRunning] = useState<MatchState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function apply(state: MatchState) {
    setRunning(state);
    setError(null);
    const ids = [...selected];

    // Sequential on purpose. Render's free instance runs one worker with a
    // small connection pool; firing 20 PATCHes at once queues them there
    // anyway and turns one slow request into twenty timeouts.
    let failed = 0;
    for (const jobId of ids) {
      const res = await fetch(`/api/matches/${jobId}/state`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: profileId, state }),
      });
      if (!res.ok) failed += 1;
    }

    setRunning(null);
    if (failed > 0) {
      setError(`${failed} of ${ids.length} didn't save. Try those again.`);
      return;
    }
    setSelected(new Set());
    startTransition(() => router.refresh());
  }

  const busy = running !== null;
  const count = selected.size;

  return (
    <SelectionContext.Provider value={{ selected, toggle, busy }}>
      {children}

      {count > 0 && (
        <div
          role="region"
          aria-label="Bulk actions"
          className="sticky bottom-4 z-20 mx-auto flex w-fit max-w-full flex-wrap items-center gap-2 rounded-full border border-border-strong bg-bg-elevated px-3 py-2 shadow-[var(--shadow-card)]"
        >
          <span className="px-1 font-mono text-xs font-semibold tabular-nums text-ink">
            {count} selected
          </span>

          {count < jobIds.length && (
            <button
              type="button"
              onClick={() => setSelected(new Set(jobIds))}
              disabled={busy}
              className="text-xs font-medium text-accent hover:underline disabled:opacity-50"
            >
              Select all {jobIds.length}
            </button>
          )}

          <span className="h-4 w-px bg-border" aria-hidden />

          {ACTIONS.map((a) => (
            <button
              key={a.state}
              type="button"
              onClick={() => apply(a.state)}
              disabled={busy}
              className="rounded-full border border-border-strong px-3 py-1 text-xs font-medium text-ink-soft transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
            >
              {running === a.state ? "Saving…" : a.label}
            </button>
          ))}

          <button
            type="button"
            onClick={() => setSelected(new Set())}
            disabled={busy}
            aria-label="Clear selection"
            className="grid size-11 place-items-center rounded-full text-ink-faint hover:bg-bg-sunken hover:text-ink disabled:opacity-50"
          >
            <X size={14} weight="bold" />
          </button>

          {error && (
            <span role="alert" className="px-1 text-xs text-danger">
              {error}
            </span>
          )}
        </div>
      )}
    </SelectionContext.Provider>
  );
}

export function SelectableRow({
  jobId,
  label,
  children,
}: {
  jobId: number;
  /** The job title. `Select job 8974` is what a screen reader read before. */
  label: string;
  children: React.ReactNode;
}) {
  const ctx = useContext(SelectionContext);
  if (!ctx) return <>{children}</>;

  const checked = ctx.selected.has(jobId);

  return (
    <div className="flex items-start gap-2">
      {/* The box stays 16px; the label around it is the 44px touch target. */}
      <label className="mt-3 grid size-11 shrink-0 cursor-pointer place-items-center">
        <input
          type="checkbox"
          checked={checked}
          disabled={ctx.busy}
          onChange={() => ctx.toggle(jobId)}
          aria-label={`Select ${label}`}
          className="size-4 accent-[var(--accent)]"
        />
      </label>
      <div className={`min-w-0 flex-1 rounded-xl ${checked ? "ring-2 ring-accent" : ""}`}>{children}</div>
    </div>
  );
}
