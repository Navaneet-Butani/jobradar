"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Kanban, ListBullets } from "@phosphor-icons/react";
import type { Application, ApplicationStatus } from "@/lib/types";

const STATUSES: { status: ApplicationStatus; label: string }[] = [
  { status: "applied", label: "Applied" },
  { status: "screening", label: "Screening" },
  { status: "interview", label: "Interview" },
  { status: "offer", label: "Offer" },
  { status: "rejected", label: "Rejected" },
  { status: "ghosted", label: "Ghosted" },
];

/**
 * View switch, plus a status filter that only appears in list view.
 *
 * The board already *is* the status view — every column is a status — so
 * filtering it to one status leaves five empty columns and one thin one. The
 * list is where a filter earns its place, and it is also the view that works
 * on a phone, where a six-column horizontal scroll does not.
 */
export function TrackerControls({ applications }: { applications: Application[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const view = searchParams.get("view") === "list" ? "list" : "board";
  const status = searchParams.get("status");

  function push(mutate: (params: URLSearchParams) => void) {
    const params = new URLSearchParams(searchParams.toString());
    mutate(params);
    router.push(params.size ? `${pathname}?${params.toString()}` : pathname);
  }

  const counts = STATUSES.map((s) => ({
    ...s,
    count: applications.filter((a) => a.status === s.status).length,
  }));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-1 self-start rounded-lg border border-border p-0.5">
        {([
          { value: "board", label: "Board", icon: Kanban },
          { value: "list", label: "List", icon: ListBullets },
        ] as const).map(({ value, label, icon: Icon }) => {
          const active = view === value;
          return (
            <button
              key={value}
              type="button"
              aria-pressed={active}
              onClick={() =>
                push((params) => {
                  if (value === "board") {
                    params.delete("view");
                    params.delete("status"); // meaningless on the board
                  } else {
                    params.set("view", value);
                  }
                })
              }
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                active ? "bg-accent-soft text-accent-soft-ink" : "text-ink-soft hover:text-ink"
              }`}
            >
              <Icon size={14} weight={active ? "fill" : "regular"} />
              {label}
            </button>
          );
        })}
      </div>

      {view === "list" && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            aria-pressed={!status}
            onClick={() => push((params) => params.delete("status"))}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
              !status
                ? "border-accent bg-accent-soft text-accent-soft-ink"
                : "border-border-strong text-ink-soft hover:border-accent hover:text-accent"
            }`}
          >
            All
            <span className="ml-1.5 font-mono tabular-nums text-ink-faint">{applications.length}</span>
          </button>

          {counts.map((s) => {
            const active = status === s.status;
            return (
              <button
                key={s.status}
                type="button"
                aria-pressed={active}
                disabled={s.count === 0 && !active}
                onClick={() => push((params) => params.set("status", s.status))}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-40 ${
                  active
                    ? "border-accent bg-accent-soft text-accent-soft-ink"
                    : "border-border-strong text-ink-soft hover:border-accent hover:text-accent"
                }`}
              >
                {s.label}
                <span className="ml-1.5 font-mono tabular-nums text-ink-faint">{s.count}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
