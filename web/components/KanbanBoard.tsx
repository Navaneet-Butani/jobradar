"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { Application, ApplicationStatus } from "@/lib/types";
import { formatAbsolute, formatRelativeDate, formatDueDate } from "@/lib/format";
import { DraftFollowup } from "@/components/DraftFollowup";
import { ApplicationEmail } from "@/components/outreach/ApplicationEmail";

const COLUMNS: { status: ApplicationStatus; label: string }[] = [
  { status: "applied", label: "Applied" },
  { status: "screening", label: "Screening" },
  { status: "interview", label: "Interview" },
  { status: "offer", label: "Offer" },
  { status: "rejected", label: "Rejected" },
  { status: "ghosted", label: "Ghosted" },
];


export function KanbanBoard({ applications }: { applications: Application[] }) {
  const router = useRouter();
  const [, startTransition] = useTransition();
  const [items, setItems] = useState(applications);
  const [dragId, setDragId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function moveTo(id: number, status: ApplicationStatus) {
    const previous = items;
    setItems((cur) => cur.map((a) => (a.id === id ? { ...a, status } : a)));
    setError(null);

    const res = await fetch(`/api/applications/${id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });

    if (!res.ok) {
      setItems(previous);
      setError("Couldn't move, try again");
      return;
    }
    startTransition(() => router.refresh());
  }

  return (
    <div className="flex flex-col gap-3">
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex gap-4 overflow-x-auto pb-2">
        {COLUMNS.map((col) => {
          const cards = items.filter((a) => a.status === col.status);
          return (
            <div
              key={col.status}
              className="flex w-72 shrink-0 flex-col gap-3 rounded-xl border border-border bg-bg-sunken p-3"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (dragId != null) moveTo(dragId, col.status);
                setDragId(null);
              }}
            >
              <div className="flex items-center justify-between px-1">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">{col.label}</h3>
                <span className="font-mono text-xs tabular-nums text-ink-faint">{cards.length}</span>
              </div>

              <div className="flex flex-col gap-2">
                {cards.map((app) => (
                  <article
                    key={app.id}
                    draggable
                    onDragStart={() => setDragId(app.id)}
                    onDragEnd={() => setDragId(null)}
                    className="cursor-grab rounded-lg border border-border bg-bg-elevated p-3 shadow-[var(--shadow-card)] active:cursor-grabbing"
                  >
                    <Link href={`/jobs/${app.job_id}`} className="text-sm font-semibold text-ink hover:text-accent hover:underline">
                      {app.job_title}
                    </Link>
                    <p className="text-xs text-ink-soft">{app.company_name}</p>
                    <p className="mt-2 text-xs text-ink-faint" title={formatAbsolute(app.applied_date)}>
                      Applied {formatRelativeDate(app.applied_date)}
                    </p>
                    {app.next_step && (
                      <p className="mt-1.5 rounded-md bg-bg-sunken px-2 py-1 text-xs text-ink-soft">
                        {app.next_step}
                        {app.next_step_date && ` · ${formatDueDate(app.next_step_date)}`}
                      </p>
                    )}
                    {app.status !== "rejected" && app.status !== "ghosted" && (
                      <div className="flex flex-col items-start">
                        <DraftFollowup applicationId={app.id} />
                        <ApplicationEmail
                          applicationId={app.id}
                          contactEmail={app.contact_email}
                          contactName={app.contact_name}
                        />
                      </div>
                    )}
                  </article>
                ))}
                {cards.length === 0 && <p className="px-1 text-xs text-ink-faint">Empty</p>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
