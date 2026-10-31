import Link from "next/link";
import { Kanban } from "@phosphor-icons/react/dist/ssr";
import { getApplications, getDueToday } from "@/lib/session";
import type { ApplicationStatus } from "@/lib/types";
import { DueToday } from "@/components/DueToday";
import { KanbanBoard } from "@/components/KanbanBoard";
import { ApplicationTable } from "@/components/ApplicationTable";
import { TrackerControls } from "@/components/TrackerControls";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader, Stat } from "@/components/shell/PageHeader";

export default async function TrackerPage(props: PageProps<"/tracker">) {
  const sp = await props.searchParams;
  const view = sp.view === "list" ? "list" : "board";
  const status = typeof sp.status === "string" ? (sp.status as ApplicationStatus) : null;

  const [{ applications, total_count }, due] = await Promise.all([
    getApplications("?limit=100"),
    getDueToday(),
  ]);

  const active = applications.filter((a) => !["rejected", "ghosted"].includes(a.status)).length;
  const interviews = applications.filter((a) => a.status === "interview").length;
  const visible = status ? applications.filter((a) => a.status === status) : applications;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Application tracker"
        description="Drag a card to move it, or switch to List and use the dropdown. Applications with no movement for 21 days auto-archive as ghosted."
        meta={
          <>
            <Stat label="live" value={active} tone="accent" />
            <Stat label="interviews" value={interviews} tone="strong" />
            <Stat label="due today" value={due.total_count} />
            <Stat label="tracked" value={total_count} />
          </>
        }
      />

      <DueToday applications={due.applications} />

      {applications.length === 0 ? (
        <EmptyState
          icon={Kanban}
          title="Nothing tracked yet"
          description="Hit Applied on a match and it appears here automatically, with a follow-up due in 7 days."
          action={
            <Link href="/" className="text-sm font-semibold text-accent hover:underline">
              Go to the feed
            </Link>
          }
        />
      ) : (
        <>
          <TrackerControls applications={applications} />
          {view === "list" ? (
            <ApplicationTable applications={visible} />
          ) : (
            <KanbanBoard applications={applications} />
          )}
        </>
      )}
    </div>
  );
}
