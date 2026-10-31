"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { EmailAccount } from "@/lib/types";

const FIELD =
  "rounded-lg border border-border-strong bg-bg px-3 py-2 text-sm outline-none focus:border-accent";

export function EmailAccountForm({ account }: { account: EmailAccount | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(account === null);
  const [busy, setBusy] = useState<"idle" | "saving" | "verifying" | "syncing">("idle");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [form, setForm] = useState({
    from_name: account?.from_name ?? "",
    from_email: account?.from_email ?? "",
    smtp_username: account?.smtp_username ?? "",
    smtp_password: "",
    smtp_host: account?.smtp_host ?? "smtp.gmail.com",
    smtp_port: account?.smtp_port ?? 587,
    daily_send_cap: account?.daily_send_cap ?? 25,
    send_interval_seconds: account?.send_interval_seconds ?? 45,
    signature: account?.signature ?? "",
  });

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function save() {
    setBusy("saving");
    setError(null);
    setNotice(null);

    const res = await fetch("/api/outreach/email-account", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...form,
        smtp_username: form.smtp_username || form.from_email,
        signature: form.signature || null,
      }),
    });
    const body = await res.json().catch(() => null);
    setBusy("idle");

    if (!res.ok || !body?.status) {
      setError(body?.error_message ?? "Couldn't save, check the fields and try again");
      return;
    }
    set("smtp_password", "");
    setOpen(false);
    setNotice("Saved. Hit Test connection to confirm the App Password works.");
    router.refresh();
  }

  async function verify() {
    setBusy("verifying");
    setError(null);
    setNotice(null);

    const res = await fetch("/api/outreach/email-account/verify", { method: "POST" });
    const body = await res.json().catch(() => null);
    setBusy("idle");

    if (!res.ok || !body?.status) {
      setError(body?.error_message ?? "Connection test failed");
      return;
    }
    setNotice("Connected. Gmail accepted the login, so you're ready to send.");
    router.refresh();
  }

  async function sync() {
    setBusy("syncing");
    setError(null);
    setNotice(null);

    const res = await fetch("/api/outreach/sync", { method: "POST" });
    const body = await res.json().catch(() => null);
    setBusy("idle");

    if (!res.ok || !body?.status) {
      setError(body?.error_message ?? "Couldn't reach the mailbox");
      return;
    }

    const r = body.data as {
      scanned: number;
      replies: number;
      bounces: number;
      followups_queued: number;
      skipped_replied: number;
      error: string | null;
    };

    if (r.error) {
      setError(r.error);
      return;
    }

    const parts = [`${r.replies} new repl${r.replies === 1 ? "y" : "ies"}`, `${r.bounces} bounced`];
    if (r.followups_queued) parts.push(`${r.followups_queued} follow-up(s) queued`);
    if (r.skipped_replied) parts.push(`${r.skipped_replied} skipped. already replied`);
    setNotice(parts.join(" · "));
    router.refresh();
  }

  return (
    <section className="rounded-xl border border-border bg-bg-elevated p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-lg font-semibold text-ink">Sending account</h2>
          <p className="mt-1 text-sm text-ink-soft">
            Outreach goes out from your own mailbox, never a shared address, so replies come back to you.
          </p>
        </div>

        {account && (
          <div className="text-right">
            <p className="text-sm text-ink">
              {account.from_email}{" "}
              {account.is_verified ? (
                <span className="ml-1 rounded-full bg-score-strong-bg px-2 py-0.5 text-xs font-medium text-score-strong">
                  verified
                </span>
              ) : (
                <span className="ml-1 rounded-full bg-bg-sunken px-2 py-0.5 text-xs text-ink-faint">untested</span>
              )}
            </p>
            <p className="mt-1 text-xs text-ink-faint">
              {account.sent_today} sent today · {account.remaining_today} left of {account.daily_send_cap}
            </p>
            <p className="mt-0.5 text-xs text-ink-faint">
              {account.last_synced_at
                ? `Inbox synced ${new Date(account.last_synced_at).toLocaleString("en-IN")}`
                : "Inbox never synced"}
            </p>
          </div>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}
      {notice && <p className="mt-3 text-sm text-score-strong">{notice}</p>}

      {!open && account && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={sync}
            disabled={busy !== "idle"}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50"
          >
            {busy === "syncing" ? "Checking inbox…" : "Sync inbox"}
          </button>
          <button
            type="button"
            onClick={verify}
            disabled={busy !== "idle"}
            className="rounded-lg border border-border-strong px-4 py-2 text-sm font-medium text-ink-soft hover:border-accent hover:text-accent disabled:opacity-50"
          >
            {busy === "verifying" ? "Testing…" : "Test connection"}
          </button>
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="rounded-lg border border-border-strong px-4 py-2 text-sm font-medium text-ink-soft hover:border-accent hover:text-accent"
          >
            Edit
          </button>
        </div>
      )}

      {open && (
        <>
          <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
              Your name (appears as the sender)
              <input className={FIELD} value={form.from_name} onChange={(e) => set("from_name", e.target.value)} />
            </label>

            <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
              Your email address
              <input
                className={FIELD}
                type="email"
                value={form.from_email}
                onChange={(e) => {
                  set("from_email", e.target.value);
                  if (!form.smtp_username) set("smtp_username", e.target.value);
                }}
              />
            </label>

            <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
              App Password
              <input
                className={FIELD}
                type="password"
                autoComplete="off"
                placeholder={account ? "••••••••  (leave to re-enter)" : "16 characters from Google"}
                value={form.smtp_password}
                onChange={(e) => set("smtp_password", e.target.value)}
              />
              <span className="text-xs font-normal text-ink-faint">
                Google Account → Security → 2-Step Verification → App passwords. Your normal Gmail password will not
                work here.
              </span>
            </label>

            <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
              Signature (appended to every outreach email)
              <textarea
                className={`${FIELD} min-h-[76px] resize-y`}
                value={form.signature}
                onChange={(e) => set("signature", e.target.value)}
              />
            </label>

            <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
              Daily send cap
              <input
                className={FIELD}
                type="number"
                min={1}
                max={200}
                value={form.daily_send_cap}
                onChange={(e) => set("daily_send_cap", Number(e.target.value))}
              />
              <span className="text-xs font-normal text-ink-faint">
                Counted per day in IST across campaigns and one-off sends alike.
              </span>
            </label>

            <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
              Seconds between sends
              <input
                className={FIELD}
                type="number"
                min={5}
                max={3600}
                value={form.send_interval_seconds}
                onChange={(e) => set("send_interval_seconds", Number(e.target.value))}
              />
              <span className="text-xs font-normal text-ink-faint">
                Pacing is what keeps a batch out of the spam folder. 45s is a sane floor.
              </span>
            </label>

            <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
              SMTP host
              <input className={FIELD} value={form.smtp_host} onChange={(e) => set("smtp_host", e.target.value)} />
            </label>

            <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
              SMTP port
              <input
                className={FIELD}
                type="number"
                value={form.smtp_port}
                onChange={(e) => set("smtp_port", Number(e.target.value))}
              />
            </label>
          </div>

          <div className="mt-5 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={save}
              disabled={busy !== "idle" || !form.from_name || !form.from_email || !form.smtp_password}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50"
            >
              {busy === "saving" ? "Saving…" : "Save account"}
            </button>
            {account && (
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg border border-border-strong px-4 py-2 text-sm font-medium text-ink-soft hover:border-accent hover:text-accent"
              >
                Cancel
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
