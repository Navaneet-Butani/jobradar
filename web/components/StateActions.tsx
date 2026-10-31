"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Check } from "@phosphor-icons/react";
import type { MatchState } from "@/lib/types";

const ACTIONS: { state: MatchState; label: string }[] = [
  { state: "interested", label: "Interested" },
  { state: "applied", label: "Applied" },
  { state: "dismissed", label: "Dismiss" },
];

export function StateActions({
  jobId,
  profileId,
  currentState,
}: {
  jobId: number;
  profileId: number;
  currentState: MatchState;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [optimisticState, setOptimisticState] = useState(currentState);
  const [error, setError] = useState<string | null>(null);

  async function setState(state: MatchState) {
    setError(null);
    const previous = optimisticState;
    setOptimisticState(state);

    const res = await fetch(`/api/matches/${jobId}/state`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_id: profileId, state }),
    });

    if (!res.ok) {
      setOptimisticState(previous);
      setError("Couldn't save, try again");
      return;
    }

    startTransition(() => router.refresh());
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {ACTIONS.map((a) => {
        const active = optimisticState === a.state;
        return (
          <button
            key={a.state}
            type="button"
            disabled={pending}
            aria-pressed={active}
            onClick={() => setState(active ? "seen" : a.state)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
              active
                ? "border-accent bg-accent text-accent-ink"
                : "border-border-strong text-ink-soft hover:border-accent hover:text-accent"
            }`}
          >
            {/* An icon, not a "✓" in the label. The literal character renders
                differently per font and lands inside the accessible name, so a
                screen reader announced "check mark Interested". aria-pressed
                already carries the state. */}
            {active && <Check size={12} weight="bold" aria-hidden />}
            {a.label}
          </button>
        );
      })}
      {error && (
        <span role="alert" className="text-xs text-danger">
          {error}
        </span>
      )}
    </div>
  );
}
