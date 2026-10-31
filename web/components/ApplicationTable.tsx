"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { Application, ApplicationStatus } from "@/lib/types";
import { formatAbsolute, formatRelativeDate, formatDueDate } from "@/lib/format";

const STATUSES: ApplicationStatus[] = [
  "applied",
  "screening",
  "interview",
  "offer",
  "rejected",
  "ghosted",
];

const TONE: Record<ApplicationStatus, string> = {
  applied: "text-ink-soft",
  screening: "text-ink-soft",
  interview: "text-accent",
  offer: "text-score-strong",
  rejected: "text-ink-faint",
  ghosted: "text-ink-faint",
};

/**
 * The board in one column, sortable by nothing and scannable at a glance.
 *
 * Moving a card here is a select, not a drag: dragging does not work on a
 * phone, and it is the slower gesture on a desktop too once there are more
 * rows than fit on screen.
 */
export function ApplicationTable({ applications }: { applications: Application[] }) {
  const router = useRouter();
  const [items, setItems] = useState(applications);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [, startTransition] = useTransition();

  // The parent re-renders with a filtered list on every URL change; without
  // this the optimistic copy would keep showing the previous filter's rows.
  const [seen, setSeen] = useState(applications);
  if (seen !== applications) {
    setSeen(applications);
    setItems(applications);
  }

  async function move(id: number, status: ApplicationStatus) {
    const previous = items;
    setItems((cur) => cur.map((a) => (a.id === id ? { ...a, status } : a)));
    setPendingId(id);
    setError(null);

    const res = await fetch(`/api/applications/${id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });

    setPendingId(null);
    if (!res.ok) {
      setItems(previous);
      setError("Couldn't update, try again");
      return;
    }
    startTransition(() => router.refresh());
  }

  if (items.length === 0) {
    return <p className="rounded-xl border border-border bg-bg-elevated p-6 text-sm text-ink-faint">Nothing in this status.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <div className="overflow-x-auto rounded-xl border border-border bg-bg-elevated">
        <table className="w-full min-w-[42rem] text-sm">
          <caption className="sr-only">Tracked applications</caption>
          <thead>
            <tr className="border-b border-border text-left text-xs font-semibold uppercase tracking-wide text-ink-faint">
              <th scope="col" className="px-4 py-2.5">Role</th>
              <th scope="col" className="px-4 py-2.5">Applied</th>
              <th scope="col" className="px-4 py-2.5">Next step</th>
              <th scope="col" className="px-4 py-2.5">Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((app) => (
              <tr key={app.id} className="border-b border-border last:border-0 hover:bg-bg-sunken/60">
                <td className="px-4 py-3">
                  <Link
                    href={`/jobs/${app.job_id}`}
                    className="font-medium text-ink hover:text-accent hover:underline"
                  >
                    {app.job_title}
                  </Link>
                  <p className="text-xs text-ink-soft">{app.company_name}</p>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-ink-soft" title={formatAbsolute(app.applied_date)}>
                  {formatRelativeDate(app.applied_date)}
                </td>
                <td className="px-4 py-3 text-xs text-ink-soft">
                  {app.next_step ? (
                    <>
                      {app.next_step}
                      {app.next_step_date && (
                        <span className="block text-ink-faint">{formatDueDate(app.next_step_date)}</span>
                      )}
                    </>
                  ) : (
                    <span className="text-ink-faint">None</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <select
                    value={app.status}
                    disabled={pendingId === app.id}
                    aria-label={`Status for ${app.job_title}`}
                    onChange={(e) => move(app.id, e.target.value as ApplicationStatus)}
                    className={`rounded-md border border-border-strong bg-bg-elevated px-2 py-1 text-xs font-medium capitalize outline-none focus:border-accent disabled:opacity-50 ${TONE[app.status]}`}
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s} className="capitalize">
                        {s}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
