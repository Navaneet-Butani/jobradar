"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Copy,
  Check,
  EnvelopeSimple,
  Prohibit,
  Trash,
  UserPlus,
} from "@phosphor-icons/react";
import type { InviteResult, Member } from "@/lib/types";
import { Field } from "@/components/Field";
import { formatAbsolute, formatRelativeDate } from "@/lib/format";

function CopyLink({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be refused outright; the readonly input beside
      // this is the fallback, so there is nothing to report.
    }
  }

  return (
    <div className="flex items-center gap-2">
      <input
        readOnly
        value={url}
        onFocus={(e) => e.currentTarget.select()}
        aria-label="Invite link"
        className="min-w-0 flex-1 rounded-md border border-border bg-bg-sunken px-2 py-1 font-mono text-xs text-ink-soft outline-none focus:border-accent"
      />
      <button
        type="button"
        onClick={copy}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border-strong px-2.5 py-1 text-xs font-medium text-ink-soft transition-colors hover:border-accent hover:text-accent"
      >
        {copied ? <Check size={13} weight="bold" /> : <Copy size={13} />}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function Badge({ children, tone = "muted" }: { children: React.ReactNode; tone?: "muted" | "accent" | "warn" }) {
  const tones = {
    muted: "bg-bg-sunken text-ink-faint",
    accent: "bg-accent-soft text-accent-soft-ink",
    warn: "bg-danger-soft text-danger",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${tones[tone]}`}>{children}</span>
  );
}

export function TeamManager({ members }: { members: Member[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InviteResult | null>(null);

  async function send() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/invites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          first_name: firstName.trim() || null,
          last_name: lastName.trim() || null,
        }),
      });
      const body = await res.json();
      if (!res.ok || !body.status) throw new Error(body.error_message ?? "Could not create the invite");
      setResult(body.data as InviteResult);
      setEmail("");
      setFirstName("");
      setLastName("");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the invite");
    } finally {
      setBusy(false);
    }
  }

  async function mutate(member: Member, action: "revoke" | "activate" | "deactivate") {
    const label =
      action === "revoke"
        ? `Withdraw the invite for ${member.email}?`
        : action === "deactivate"
          ? `Sign ${member.email} out and block future logins? Their data is kept.`
          : null;
    // Both are recoverable — revoke only removes an account nobody has used,
    // and deactivate is a flag — but they are surprising enough to confirm.
    if (label && !window.confirm(label)) return;

    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/invites/${member.id}`, {
        method: action === "revoke" ? "DELETE" : "PATCH",
        headers: { "Content-Type": "application/json" },
        ...(action === "revoke"
          ? {}
          : { body: JSON.stringify({ is_active: action === "activate" }) }),
      });
      const body = await res.json();
      if (!res.ok || !body.status) throw new Error(body.error_message ?? "That didn't work");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't work");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <ul className="flex flex-col gap-2">
        {members.map((m) => {
          const name = [m.first_name, m.last_name].filter(Boolean).join(" ");
          return (
            <li
              key={m.id}
              className="flex flex-col gap-3 rounded-lg border border-border bg-bg-elevated p-3.5"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-ink">{name || m.email}</span>
                    {m.is_self && <Badge tone="accent">You</Badge>}
                    {m.is_admin && <Badge>Admin</Badge>}
                    {m.pending && <Badge tone="accent">Invite pending</Badge>}
                    {m.invite_expired && <Badge tone="warn">Link expired</Badge>}
                    {!m.is_active && !m.pending && <Badge tone="warn">Deactivated</Badge>}
                  </div>
                  {name && <p className="mt-0.5 text-xs text-ink-soft">{m.email}</p>}
                  <p className="mt-1 text-xs text-ink-faint">
                    {m.pending
                      ? m.invite_expires_at
                        ? `Link expires ${formatAbsolute(m.invite_expires_at)}`
                        : "Waiting to be accepted"
                      : m.last_login_at
                        ? `Last signed in ${formatRelativeDate(m.last_login_at)}`
                        : "Never signed in"}
                  </p>
                </div>

                {!m.is_self && (
                  <div className="flex shrink-0 items-center gap-2">
                    {m.pending ? (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => mutate(m, "revoke")}
                        className="inline-flex items-center gap-1.5 rounded-md border border-border-strong px-2.5 py-1 text-xs font-medium text-ink-soft transition-colors hover:border-danger hover:text-danger disabled:opacity-50"
                      >
                        <Trash size={13} />
                        Revoke
                      </button>
                    ) : (
                      !m.is_admin && (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => mutate(m, m.is_active ? "deactivate" : "activate")}
                          className="inline-flex items-center gap-1.5 rounded-md border border-border-strong px-2.5 py-1 text-xs font-medium text-ink-soft transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
                        >
                          <Prohibit size={13} />
                          {m.is_active ? "Deactivate" : "Reactivate"}
                        </button>
                      )
                    )}
                  </div>
                )}
              </div>

              {m.pending && m.invite_url && <CopyLink url={m.invite_url} />}
            </li>
          );
        })}
      </ul>

      {error && (
        <p role="alert" className="text-xs font-medium text-danger">
          {error}
        </p>
      )}

      {result && (
        <div className="flex flex-col gap-2 rounded-lg border border-accent bg-accent-soft/40 p-3.5">
          <p className="text-sm font-semibold text-ink">Invite ready for {result.member.email}</p>
          <p className="text-xs text-ink-soft">
            {result.emailed
              ? "The invite email has been sent. Share the link too if it doesn't arrive."
              : `The email didn't send${result.email_error ? ` (${result.email_error})` : ""}. Send this link yourself.`}
          </p>
          {result.member.invite_url && <CopyLink url={result.member.invite_url} />}
        </div>
      )}

      {open ? (
        <div className="flex flex-col gap-4 rounded-lg border border-border bg-bg-elevated p-4">
          <Field
            label="Email"
            type="email"
            value={email}
            onChange={setEmail}
            required
            placeholder="name@example.com"
            hint="The invite link is tied to this address. It's also the login."
            disabled={busy}
            autoComplete="off"
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="First name" value={firstName} onChange={setFirstName} disabled={busy} />
            <Field label="Last name" value={lastName} onChange={setLastName} disabled={busy} />
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={send}
              disabled={busy || !email.trim()}
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-3.5 py-2 text-sm font-semibold text-accent-ink transition-opacity disabled:opacity-50"
            >
              <EnvelopeSimple size={16} weight="bold" />
              {busy ? "Creating…" : "Create invite"}
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={busy}
              className="text-sm font-medium text-ink-faint hover:text-ink disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex w-fit items-center gap-2 rounded-lg bg-accent px-3.5 py-2 text-sm font-semibold text-accent-ink transition-opacity hover:opacity-90"
        >
          <UserPlus size={16} weight="bold" />
          Invite someone
        </button>
      )}
    </div>
  );
}
