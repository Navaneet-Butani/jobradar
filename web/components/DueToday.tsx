import Link from "next/link";
import { BellRinging } from "@phosphor-icons/react/dist/ssr";
import type { Application } from "@/lib/types";
import { formatDueDate } from "@/lib/format";

export function DueToday({ applications }: { applications: Application[] }) {
  if (applications.length === 0) return null;

  return (
    <section className="rounded-xl border border-accent/40 bg-accent-soft p-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-accent-soft-ink">
        <BellRinging size={16} weight="fill" />
        {applications.length} follow-up{applications.length === 1 ? "" : "s"} due today
      </h2>
      <ul className="mt-3 flex flex-col gap-2">
        {applications.map((app) => (
          <li key={app.id} className="flex items-center justify-between gap-3 rounded-lg bg-bg-elevated px-3 py-2 text-sm">
            <div className="min-w-0">
              <Link href={`/jobs/${app.job_id}`} className="font-medium text-ink hover:text-accent hover:underline">
                {app.job_title}
              </Link>
              <span className="text-ink-soft"> · {app.company_name}</span>
            </div>
            <div className="flex shrink-0 items-center gap-3 text-xs text-ink-faint">
              <span>{app.next_step ?? "Follow up"}</span>
              {app.next_step_date && <span className="font-mono tabular-nums">{formatDueDate(app.next_step_date)}</span>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
