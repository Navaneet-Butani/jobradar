import Link from "next/link";
import { CaretRight, PaperPlaneTilt } from "@phosphor-icons/react/dist/ssr";
import type { OutreachCampaign } from "@/lib/types";
import { formatRelativeDate } from "@/lib/format";
import { EmptyState } from "@/components/EmptyState";
import { CampaignActions } from "@/components/outreach/CampaignActions";

function Count({
  value,
  label,
  tone = "muted",
}: {
  value: number;
  label: string;
  tone?: "strong" | "danger" | "muted";
}) {
  const toneClass =
    tone === "strong" && value > 0
      ? "text-score-strong"
      : tone === "danger" && value > 0
        ? "text-danger"
        : "text-ink";
  return (
    <span className="text-ink-faint">
      <span className={`font-mono font-semibold tabular-nums ${toneClass}`}>{value}</span> {label}
    </span>
  );
}

const STATUS_STYLE: Record<OutreachCampaign["status"], string> = {
  draft: "bg-bg-sunken text-ink-faint",
  running: "bg-score-strong-bg text-score-strong",
  paused: "bg-bg-sunken text-ink-soft",
  completed: "bg-bg-sunken text-ink-soft",
};

export function CampaignList({ campaigns }: { campaigns: OutreachCampaign[] }) {
  if (campaigns.length === 0) {
    return (
      <EmptyState
        icon={PaperPlaneTilt}
        title="No campaigns yet"
        description="A campaign sends one email per selected contact, paced against your daily cap, and follows up with anyone who doesn't reply."
      />
    );
  }

  return (
    <section className="flex flex-col gap-3">
      {campaigns.map((campaign) => {
        const { counts } = campaign;
        const done = counts.sent + counts.failed;
        const pct = counts.total ? Math.round((done / counts.total) * 100) : 0;

        return (
          <article
            key={campaign.id}
            className="rounded-lg border border-border p-3 transition-colors hover:border-border-strong"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                {/* The whole row used to be inert, with an expander that only
                    showed a table. The name is now the way in. */}
                <Link
                  href={`/outreach/campaigns/${campaign.id}`}
                  className="inline-flex items-center gap-1 text-sm font-semibold text-ink hover:text-accent hover:underline"
                >
                  {campaign.name}
                  <CaretRight size={12} className="text-ink-faint" />
                </Link>
                <div className="mt-1 flex flex-wrap items-center gap-x-3.5 gap-y-1 text-xs">
                  <Count value={counts.replied} label="replied" tone="strong" />
                  <Count value={counts.awaiting} label="awaiting" />
                  <Count value={counts.bounced} label="bounced" tone={counts.bounced ? "danger" : "muted"} />
                  {counts.queued > 0 && <Count value={counts.queued} label="queued" />}
                  {counts.failed > 0 && <Count value={counts.failed} label="failed" tone="danger" />}
                  <span className="text-ink-faint">
                    {counts.sent} of {counts.total} sent
                  </span>
                  <span className="text-ink-faint">created {formatRelativeDate(campaign.created_at)}</span>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[campaign.status]}`}>
                  {campaign.status}
                </span>
                <CampaignActions campaign={campaign} />
              </div>
            </div>

            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-bg-sunken">
              <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${pct}%` }} />
            </div>
          </article>
        );
      })}
    </section>
  );
}
