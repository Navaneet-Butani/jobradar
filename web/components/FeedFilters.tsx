"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowsDownUp, Check } from "@phosphor-icons/react";
import type { MatchStats } from "@/lib/types";

type Chip = { key: string; value: string; label: string };

const CHIPS: Chip[] = [
  { key: "min_score", value: "70", label: "Score > 70" },
  { key: "remote_only", value: "true", label: "Remote only" },
  { key: "my_cities_only", value: "true", label: "My cities only" },
];

/**
 * `null` is not a state. It means "no state filter", which the API reads as
 * everything except dismissed. Dismissed gets its own filter rather than
 * sitting inside All: the point of dismissing something is that it leaves.
 */
const TABS: { state: string | null; label: string }[] = [
  { state: null, label: "All" },
  { state: "new", label: "New" },
  { state: "interested", label: "Interested" },
  { state: "applied", label: "Applied" },
  { state: "dismissed", label: "Dismissed" },
];

const SORTS = [
  { value: "score", label: "Best match" },
  { value: "newest", label: "Newest posted" },
];

export function FeedFilters({ stats }: { stats: MatchStats }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const currentState = searchParams.get("state");
  const currentSort = searchParams.get("sort") ?? "score";

  /** Every navigation drops `page` — filtering into page 7 of a 2-page list
   *  shows an empty screen that looks like "no results". */
  function push(mutate: (params: URLSearchParams) => void) {
    const params = new URLSearchParams(searchParams.toString());
    mutate(params);
    params.delete("page");
    router.push(`${pathname}?${params.toString()}`);
  }

  function countFor(state: string | null): number {
    if (state) return stats.by_state[state as keyof typeof stats.by_state] ?? 0;
    return stats.total - (stats.by_state.dismissed ?? 0);
  }

  const activeChips = CHIPS.filter((chip) => searchParams.get(chip.key) === chip.value);

  return (
    <div className="flex flex-col gap-3">
      {/* role="group", not "tablist". These buttons re-run a query and reload
          the list; they do not switch between rendered tab panels. Announcing
          them as tabs promises arrow-key traversal into a panel that does not
          exist, so a screen-reader user is told the wrong thing about how the
          control works. */}
      <div
        role="group"
        aria-label="Filter by status"
        className="flex gap-1 overflow-x-auto border-b border-border"
      >
        {TABS.map((tab) => {
          const active = currentState === tab.state;
          const count = countFor(tab.state);
          return (
            <button
              key={tab.label}
              type="button"
              aria-current={active ? "true" : undefined}
              onClick={() =>
                push((params) => (tab.state ? params.set("state", tab.state) : params.delete("state")))
              }
              className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2.5 text-sm transition-colors ${
                active
                  ? "border-accent font-semibold text-ink"
                  : "border-transparent font-medium text-ink-soft hover:border-border-strong hover:text-ink"
              }`}
            >
              {tab.label}
              <span
                className={`ml-1.5 rounded-full px-1.5 py-0.5 font-mono text-[11px] tabular-nums ${
                  active ? "bg-accent-soft text-accent-soft-ink" : "bg-bg-sunken text-ink-faint"
                }`}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {CHIPS.map((chip) => {
          const active = searchParams.get(chip.key) === chip.value;
          return (
            <button
              key={chip.key}
              type="button"
              onClick={() =>
                push((params) =>
                  active ? params.delete(chip.key) : params.set(chip.key, chip.value)
                )
              }
              aria-pressed={active}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                active
                  ? "border-accent bg-accent-soft text-accent-soft-ink"
                  : "border-border-strong text-ink-soft hover:border-accent hover:text-accent"
              }`}
            >
              {active && <Check size={12} weight="bold" />}
              {chip.label}
            </button>
          );
        })}

        {activeChips.length > 0 && (
          <button
            type="button"
            onClick={() => push((params) => CHIPS.forEach((chip) => params.delete(chip.key)))}
            className="text-xs font-medium text-ink-faint underline underline-offset-2 hover:text-ink"
          >
            Clear {activeChips.length}
          </button>
        )}

        <label className="ml-auto inline-flex items-center gap-1.5 text-xs text-ink-faint">
          <ArrowsDownUp size={14} />
          <span className="sr-only sm:not-sr-only">Sort</span>
          <select
            value={currentSort}
            onChange={(e) =>
              push((params) =>
                e.target.value === "score" ? params.delete("sort") : params.set("sort", e.target.value)
              )
            }
            className="rounded-md border border-border-strong bg-bg-elevated px-2 py-1 text-xs font-medium text-ink-soft outline-none focus:border-accent"
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}
