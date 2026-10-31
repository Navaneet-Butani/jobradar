"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, PaperPlaneTilt, Warning } from "@phosphor-icons/react";
import type { CampaignPreview, EmailAccount, OutreachContact, TemplateDefaults } from "@/lib/types";
import { formatDate } from "@/lib/format";

const FIELD =
  "rounded-lg border border-border-strong bg-bg px-3 py-2 text-sm outline-none transition-colors focus:border-accent";

export function CampaignComposer({
  contacts,
  defaults,
  account,
}: {
  contacts: OutreachContact[];
  defaults: TemplateDefaults;
  account: EmailAccount | null;
}) {
  const router = useRouter();

  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState<null | "preview" | "launch">(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<CampaignPreview | null>(null);

  const [name, setName] = useState("");
  const [subject, setSubject] = useState(defaults.subject_template);
  const [body, setBody] = useState(defaults.body_template);
  const [attachResume, setAttachResume] = useState(true);
  const [personalize, setPersonalize] = useState(false);
  const [followup, setFollowup] = useState(true);
  const [followupDays, setFollowupDays] = useState(4);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return contacts;
    return contacts.filter((c) =>
      [c.email, c.company_name, c.contact_name].some((v) => v?.toLowerCase().includes(q)),
    );
  }, [contacts, filter]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setPreview(null);
  }

  async function runPreview() {
    setBusy("preview");
    setError(null);
    const res = await fetch("/api/outreach/campaigns/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        subject_template: subject,
        body_template: body,
        contact_ids: [...selected],
        attach_resume: attachResume,
        limit: 5,
      }),
    });
    const payload = await res.json().catch(() => null);
    setBusy(null);
    if (!res.ok || !payload?.status) {
      setError(payload?.error_message ?? "Couldn't build the preview");
      return;
    }
    setPreview(payload.data as CampaignPreview);
  }

  async function launch() {
    setBusy("launch");
    setError(null);

    const created = await fetch("/api/outreach/campaigns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name || `Campaign ${new Date().toLocaleDateString("en-IN")}`,
        subject_template: subject,
        body_template: body,
        attach_resume: attachResume,
        personalize_with_llm: personalize,
        followup_enabled: followup,
        followup_after_days: followupDays,
        contact_ids: [...selected],
      }),
    });
    const payload = await created.json().catch(() => null);

    if (!created.ok || !payload?.status) {
      setBusy(null);
      setError(payload?.error_message ?? "Couldn't create the campaign");
      return;
    }

    const started = await fetch(`/api/outreach/campaigns/${payload.data.id}/start`, { method: "POST" });
    const startPayload = await started.json().catch(() => null);
    setBusy(null);

    if (!started.ok || !startPayload?.status) {
      setError(startPayload?.error_message ?? "Created, but couldn't start. Start it from the list below.");
      router.refresh();
      return;
    }

    setSelected(new Set());
    setPreview(null);
    setName("");
    setOpen(false);
    router.refresh();
  }

  if (!account) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-bg-elevated px-4 py-3.5">
        <Warning size={18} className="text-ink-faint" />
        <p className="flex-1 text-sm text-ink-soft">
          Set up a sending account before composing, because a campaign needs to know who the email is from.
        </p>
        <Link
          href="/outreach/account"
          className="rounded-lg bg-accent px-3.5 py-2 text-sm font-semibold text-accent-ink hover:opacity-90"
        >
          Set up sending
        </Link>
      </div>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={contacts.length === 0}
        className="inline-flex w-fit items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition-opacity hover:opacity-90 disabled:opacity-50"
        title={contacts.length === 0 ? "Add contacts first" : undefined}
      >
        <PaperPlaneTilt size={15} />
        New campaign
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-bg-elevated p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display text-base font-semibold text-ink">New campaign</h2>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-sm text-ink-faint hover:text-ink"
        >
          Cancel
        </button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
        Campaign name
        <input
          className={FIELD}
          placeholder="Ahmedabad backend roles, August"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>

      {/* Recipients */}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-medium text-ink">
            Recipients
            <span className="ml-2 font-mono text-xs tabular-nums text-ink-faint">{selected.size} selected</span>
          </span>
          <button
            type="button"
            onClick={() => {
              setSelected(selected.size === visible.length ? new Set() : new Set(visible.map((c) => c.id)));
              setPreview(null);
            }}
            className="text-sm font-medium text-accent hover:underline"
          >
            {selected.size === visible.length && visible.length > 0 ? "Clear all" : "Select all shown"}
          </button>
        </div>

        <input
          className={FIELD}
          type="search"
          aria-label="Filter contacts"
          placeholder="Filter contacts…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />

        <ul className="max-h-56 divide-y divide-border overflow-y-auto rounded-lg border border-border">
          {visible.map((c) => (
            <li key={c.id}>
              <label className="flex cursor-pointer items-center gap-3 px-3 py-2 text-sm transition-colors hover:bg-bg-sunken">
                <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)} />
                <span className="min-w-0 flex-1 truncate text-ink">
                  {c.company_name ?? c.email}
                  {c.contact_name && <span className="ml-1.5 text-ink-soft">{c.contact_name}</span>}
                </span>
                {c.last_emailed_at && (
                  <span className="shrink-0 text-xs text-ink-faint">
                    emailed {formatDate(c.last_emailed_at)}
                  </span>
                )}
              </label>
            </li>
          ))}
        </ul>
      </div>

      {/* Message */}
      <div className="flex flex-col gap-3">
        <p className="text-xs text-ink-faint">
          Merge fields:{" "}
          {defaults.merge_fields.map((f) => (
            <code key={f} className="mr-1 rounded bg-bg-sunken px-1 py-0.5 font-mono">{`{{${f}}}`}</code>
          ))}
        </p>

        <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
          Subject
          <input className={FIELD} value={subject} onChange={(e) => setSubject(e.target.value)} />
        </label>

        <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
          Body
          <textarea
            className={`${FIELD} min-h-[200px] resize-y font-mono text-xs leading-relaxed`}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
        </label>
      </div>

      <div className="flex flex-col gap-2.5 rounded-lg bg-bg-sunken p-3">
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={attachResume} onChange={(e) => setAttachResume(e.target.checked)} />
          Attach my resume
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={personalize} onChange={(e) => setPersonalize(e.target.checked)} />
          Rewrite each email for its company (LLM)
        </label>
        <label className="flex flex-wrap items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={followup} onChange={(e) => setFollowup(e.target.checked)} />
          Send one follow-up after
          <input
            type="number"
            min={1}
            max={60}
            disabled={!followup}
            value={followupDays}
            onChange={(e) => setFollowupDays(Number(e.target.value))}
            className="w-16 rounded-md border border-border-strong bg-bg px-2 py-1 text-sm outline-none focus:border-accent disabled:opacity-50"
          />
          days
        </label>
        <p className="text-xs text-ink-faint">
          Follow-ups go only to people who neither replied nor bounced, checked against your mailbox first.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={runPreview}
          disabled={busy !== null || selected.size === 0}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border-strong px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
        >
          <Eye size={15} />
          {busy === "preview" ? "Rendering…" : "Preview"}
        </button>
        <button
          type="button"
          onClick={launch}
          disabled={busy !== null || preview === null}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          <PaperPlaneTilt size={15} />
          {busy === "launch" ? "Starting…" : `Send to ${selected.size}`}
        </button>
        {preview === null && selected.size > 0 && (
          <span className="text-xs text-ink-faint">Preview before sending.</span>
        )}
      </div>

      {preview && (
        <div className="flex flex-col gap-3 border-t border-border pt-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="font-display text-sm font-semibold text-ink">
              Preview, {preview.items.length} of {preview.total_selected}
            </h3>
            <span className="text-xs text-ink-faint">{preview.pacing_note}</span>
          </div>

          {preview.warnings.map((w) => (
            <p key={w} className="flex gap-2 text-xs text-ink-faint">
              <Warning size={14} className="mt-0.5 shrink-0" />
              {w}
            </p>
          ))}

          {preview.items.map((item) => (
            <article key={item.contact_id} className="rounded-lg bg-bg-sunken p-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-mono text-xs text-ink-soft">{item.to_email}</p>
                {item.previously_emailed_at && (
                  <span className="text-xs text-ink-faint">
                    already emailed {formatDate(item.previously_emailed_at)}
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm font-semibold text-ink">{item.subject}</p>
              <p className="mt-2 whitespace-pre-wrap text-sm text-ink-soft">{item.body}</p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
