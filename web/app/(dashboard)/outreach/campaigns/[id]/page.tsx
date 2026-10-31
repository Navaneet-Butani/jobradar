import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";
import type { OutreachCampaign } from "@/lib/types";
import { getCampaign } from "@/lib/session";
import { formatAbsolute, formatRelativeDate } from "@/lib/format";
import { CampaignActions } from "@/components/outreach/CampaignActions";
import { RecipientTable } from "@/components/outreach/RecipientTable";

const STATUS_STYLE: Record<OutreachCampaign["status"], string> = {
  draft: "bg-bg-sunken text-ink-faint",
  running: "bg-score-strong-bg text-score-strong",
  paused: "bg-bg-sunken text-ink-soft",
  completed: "bg-bg-sunken text-ink-soft",
};

/** One number in the strip across the top. Muted at zero so the eye lands on
 *  what actually happened rather than on a row of noughts. */
function Metric({
  label,
  value,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: number;
  tone?: "neutral" | "good" | "bad";
  hint?: string;
}) {
  const toneClass =
    value === 0
      ? "text-ink-faint"
      : tone === "good"
        ? "text-score-strong"
        : tone === "bad"
          ? "text-danger"
          : "text-ink";

  return (
    <div title={hint}>
      <div className={`font-mono text-xl font-semibold tabular-nums ${toneClass}`}>{value}</div>
      <div className="text-xs text-ink-faint">{label}</div>
    </div>
  );
}

function Template({ label, subject, body }: { label: string; subject: string | null; body: string | null }) {
  if (!subject && !body) return null;
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">{label}</h3>
      {subject && <p className="mt-1.5 text-sm font-medium text-ink">{subject}</p>}
      {body && <p className="mt-1 whitespace-pre-wrap text-sm text-ink-soft">{body}</p>}
    </div>
  );
}

export default async function CampaignDetailPage(props: PageProps<"/outreach/campaigns/[id]">) {
  const { id } = await props.params;
  const campaignId = Number(id);
  const campaign = Number.isFinite(campaignId) ? await getCampaign(campaignId) : null;
  if (!campaign) notFound();

  const { counts } = campaign;
  const done = counts.sent + counts.failed;
  const pct = counts.total ? Math.round((done / counts.total) * 100) : 0;
  const replyRate = counts.sent ? Math.round((counts.replied / counts.sent) * 100) : null;

  return (
    <div className="flex flex-col gap-5">
      <Link
        href="/outreach"
        className="inline-flex w-fit items-center gap-1.5 text-sm text-ink-soft hover:text-accent"
      >
        <ArrowLeft size={14} />
        Back to campaigns
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-display text-xl font-semibold tracking-tight text-ink">{campaign.name}</h1>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[campaign.status]}`}>
              {campaign.status}
            </span>
          </div>
          <p className="mt-1 text-sm text-ink-faint">
            Created {formatRelativeDate(campaign.created_at)}
            {campaign.started_at && <> · started {formatRelativeDate(campaign.started_at)}</>}
            {campaign.completed_at && <> · finished {formatRelativeDate(campaign.completed_at)}</>}
            <span className="ml-1.5" title={formatAbsolute(campaign.created_at)} />
          </p>
        </div>

        <CampaignActions campaign={campaign} afterDelete="/outreach" size="md" />
      </header>

      <section className="rounded-xl border border-border bg-bg-elevated p-4">
        <div className="grid grid-cols-3 gap-4 sm:grid-cols-6">
          <Metric label="recipients" value={counts.total} />
          <Metric label="sent" value={counts.sent} />
          <Metric label="replied" value={counts.replied} tone="good" />
          <Metric label="awaiting" value={counts.awaiting} hint="Sent, no reply and no bounce yet" />
          <Metric label="bounced" value={counts.bounced} tone="bad" />
          <Metric label="failed" value={counts.failed} tone="bad" hint="Never left your mailbox" />
        </div>

        <div className="mt-4">
          <div className="flex items-center justify-between text-xs text-ink-faint">
            <span>
              {done} of {counts.total} processed
              {counts.queued > 0 && <> · {counts.queued} still queued</>}
            </span>
            {/* Reply rate is the only number that says whether the campaign
                worked. Below ~10 sent it is noise, so it stays hidden. */}
            {replyRate != null && counts.sent >= 10 && <span>{replyRate}% reply rate</span>}
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-bg-sunken">
            <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${pct}%` }} />
          </div>
        </div>

        <p className="mt-3 text-xs text-ink-faint">
          {campaign.followup_enabled
            ? `Follow-up goes out ${campaign.followup_after_days} days after the first email to anyone who hasn't replied${
                counts.followups > 0 ? ` (${counts.followups} queued or sent)` : ""
              }.`
            : "No follow-up configured."}
          {campaign.attach_resume && " Resume attached to every email."}
          {campaign.personalize_with_llm && " Each email personalised by the LLM before sending."}
        </p>
      </section>

      <section className="rounded-xl border border-border bg-bg-elevated p-4">
        <h2 className="font-display text-sm font-semibold text-ink">Templates</h2>
        <div className="mt-3 flex flex-col gap-4">
          <Template label="First email" subject={campaign.subject_template} body={campaign.body_template} />
          {campaign.followup_enabled && (
            <Template
              label="Follow-up"
              subject={campaign.followup_subject_template}
              body={campaign.followup_body_template}
            />
          )}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="font-display text-sm font-semibold text-ink">Recipients</h2>
        <RecipientTable messages={campaign.messages} />
      </section>
    </div>
  );
}
