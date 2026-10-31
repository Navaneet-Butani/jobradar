"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Warning } from "@phosphor-icons/react";
import type { ApplicationEmailDraft } from "@/lib/types";

const FIELD =
  "w-full rounded-md border border-border-strong bg-bg px-2 py-1.5 text-xs outline-none focus:border-accent";

export function ApplicationEmail({
  applicationId,
  contactEmail,
  contactName,
}: {
  applicationId: number;
  contactEmail: string | null;
  contactName: string | null;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<null | "draft" | "save" | "send">(null);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const [email, setEmail] = useState(contactEmail ?? "");
  const [name, setName] = useState(contactName ?? "");
  const [draft, setDraft] = useState<ApplicationEmailDraft | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [attach, setAttach] = useState(true);

  async function saveContact() {
    setBusy("save");
    setError(null);
    const res = await fetch(`/api/applications/${applicationId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contact_email: email || null, contact_name: name || null }),
    });
    setBusy(null);
    if (!res.ok) {
      setError("Couldn't save the contact");
      return;
    }
    router.refresh();
  }

  async function loadDraft() {
    setBusy("draft");
    setError(null);
    const res = await fetch(`/api/outreach/application/${applicationId}/draft`);
    const payload = await res.json().catch(() => null);
    setBusy(null);

    if (!res.ok || !payload?.status) {
      setError(payload?.error_message ?? "Couldn't prepare a draft");
      return;
    }
    const d = payload.data as ApplicationEmailDraft;
    setDraft(d);
    setSubject(d.subject);
    setBody(d.body);
    if (d.to_email && !email) setEmail(d.to_email);
    if (d.to_name && !name) setName(d.to_name);
  }

  async function send() {
    setBusy("send");
    setError(null);
    const res = await fetch("/api/outreach/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        application_id: applicationId,
        to_email: email,
        to_name: name || null,
        subject,
        body,
        attach_resume: attach,
        save_contact: true,
      }),
    });
    const payload = await res.json().catch(() => null);
    setBusy(null);

    if (!res.ok || !payload?.status) {
      setError(payload?.error_message ?? "Send failed");
      return;
    }
    setSent(true);
    setDraft(null);
    router.refresh();
  }

  if (!open) {
    return (
      <button
        type="button"
        draggable={false}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={() => setOpen(true)}
        className="mt-1.5 text-left text-xs font-medium text-ink-faint hover:text-accent"
      >
        {contactEmail ? `Email ${contactEmail}` : "Add contact / email"}
      </button>
    );
  }

  return (
    <div className="mt-1.5 rounded-md bg-bg-sunken p-2" onMouseDown={(e) => e.stopPropagation()}>
      {sent && <p className="mb-1.5 text-xs text-score-strong">Sent. Logged against this application.</p>}
      {error && (
        <p role="alert" className="mb-1.5 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-1.5">
        <label className="flex flex-col gap-1 text-xs font-medium text-ink">
          Contact email
          <input
            className={FIELD}
            type="email"
            placeholder="hr@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-ink">
          Contact name
          <input className={FIELD} value={name} onChange={(e) => setName(e.target.value)} />
        </label>

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={saveContact}
            disabled={busy !== null}
            className="text-xs font-medium text-accent hover:underline disabled:opacity-50"
          >
            {busy === "save" ? "Saving…" : "Save contact"}
          </button>
          <button
            type="button"
            onClick={loadDraft}
            disabled={busy !== null}
            className="text-xs font-medium text-accent hover:underline disabled:opacity-50"
          >
            {busy === "draft" ? "Drafting…" : "Draft email"}
          </button>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="ml-auto text-xs text-ink-faint hover:text-ink"
          >
            Close
          </button>
        </div>
      </div>

      {draft && (
        <div className="mt-2 flex flex-col gap-1.5 border-t border-border pt-2">
          {draft.warnings.map((w) => (
            <p key={w} className="flex gap-1.5 text-xs text-ink-faint">
              <Warning size={13} className="mt-0.5 shrink-0" />
              {w}
            </p>
          ))}
          {draft.previously_emailed_at && (
            <p className="flex gap-1.5 text-xs text-ink-faint">
              <Warning size={13} className="mt-0.5 shrink-0" />
              You already emailed this address on{" "}
              {new Date(draft.previously_emailed_at).toLocaleDateString("en-IN")}.
            </p>
          )}

          <label className="flex flex-col gap-1 text-xs font-medium text-ink">
            Subject
            <input className={FIELD} value={subject} onChange={(e) => setSubject(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-ink">
            Message
            <textarea
              className={`${FIELD} min-h-[150px] resize-y`}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </label>

          <label className="flex items-center gap-2 text-xs text-ink-soft">
            <input type="checkbox" checked={attach} onChange={(e) => setAttach(e.target.checked)} />
            Attach resume
          </label>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={send}
              disabled={busy !== null || !email || !subject || !body}
              className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50"
            >
              {busy === "send" ? "Sending…" : "Send now"}
            </button>
            <span className="text-xs text-ink-faint">{draft.remaining_today} left in today&apos;s cap</span>
          </div>
        </div>
      )}
    </div>
  );
}
