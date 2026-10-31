"use client";

import { useState } from "react";
import { Warning } from "@phosphor-icons/react";
import type { ApplicationPacket as Packet } from "@/lib/types";

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      type="button"
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="text-xs font-medium text-accent hover:underline"
    >
      {copied ? "Copied" : label}
    </button>
  );
}

function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="border-t border-border pt-3">
      <div className="flex items-baseline justify-between gap-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">{title}</h4>
        {action}
      </div>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

export function ApplicationPacket({ jobId, profileId }: { jobId: number; profileId: number }) {
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [packet, setPacket] = useState<Packet | null>(null);

  async function generate() {
    setState("loading");
    const res = await fetch("/api/packet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId, profile_id: profileId }),
    });
    const body = await res.json().catch(() => null);

    if (!res.ok || !body?.status || !body.data) {
      setState("error");
      return;
    }
    setPacket(body.data as Packet);
    setState("idle");
  }

  if (!packet) {
    return (
      <button
        type="button"
        onClick={generate}
        disabled={state === "loading"}
        className="rounded-lg border border-border-strong px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
      >
        {state === "loading"
          ? "Building packet…"
          : state === "error"
            ? "Couldn't build packet, try again"
            : "Generate application packet"}
      </button>
    );
  }

  const { apply, bullets, cover_note, contact, answers, warnings, resume_filename } = packet;
  const answerLines = [
    `Total experience: ${answers.total_experience}`,
    answers.notice_period && `Notice period: ${answers.notice_period}`,
    answers.current_ctc && `Current CTC: ${answers.current_ctc}`,
    answers.expected_ctc && `Expected CTC: ${answers.expected_ctc}`,
    `Willing to relocate: ${answers.willing_to_relocate}`,
  ].filter(Boolean) as string[];

  return (
    <div className="rounded-xl border border-border bg-bg-elevated p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-display text-base font-semibold text-ink">Application packet</h3>
        <button
          type="button"
          onClick={generate}
          disabled={state === "loading"}
          className="text-xs font-medium text-ink-faint hover:text-accent disabled:opacity-50"
        >
          {state === "loading" ? "Regenerating…" : "Regenerate"}
        </button>
      </div>

      {warnings.length > 0 && (
        <ul className="mt-2 space-y-1">
          {warnings.map((w) => (
            <li key={w} className="flex gap-1.5 text-xs text-ink-faint">
              <Warning size={13} className="mt-0.5 shrink-0" />
              {w}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 flex flex-col gap-3">
        <Section
          title="1. Apply here"
          action={
            apply.is_direct_ats ? (
              <span className="rounded-full bg-score-strong-bg px-2 py-0.5 text-xs font-medium text-score-strong">
                {apply.ats_label}. direct
              </span>
            ) : (
              <span className="text-xs text-ink-faint">Aggregator link</span>
            )
          }
        >
          <a
            href={apply.url}
            target="_blank"
            rel="noopener noreferrer"
            className="break-all text-sm text-accent hover:underline"
          >
            {apply.url}
          </a>
          <p className="mt-1 text-xs text-ink-faint">{apply.note}</p>
        </Section>

        {bullets.length > 0 && (
          <Section
            title="2. Tailored resume bullets"
            action={<CopyButton text={bullets.map((b) => `• ${b}`).join("\n")} label="Copy all" />}
          >
            <ul className="list-disc space-y-1 pl-5 text-sm text-ink-soft">
              {bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
            {resume_filename && (
              <p className="mt-1.5 text-xs text-ink-faint">Rewritten from {resume_filename}. Verify every claim before you send it.</p>
            )}
          </Section>
        )}

        {cover_note && (
          <Section title="3. Cover note" action={<CopyButton text={cover_note} />}>
            <p className="whitespace-pre-wrap text-sm text-ink-soft">{cover_note}</p>
          </Section>
        )}

        <Section
          title="4. Contact"
          action={contact.email ? <CopyButton text={contact.email} label="Copy email" /> : undefined}
        >
          <p className="text-sm text-ink">
            {contact.email ?? contact.label}
            {contact.email && <span className="ml-2 text-xs text-ink-faint">{contact.label}</span>}
          </p>
          <p className="mt-1 text-xs text-ink-faint">{contact.note}</p>
        </Section>

        <Section title="5. Standard answers" action={<CopyButton text={answerLines.join("\n")} label="Copy all" />}>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
            {answerLines.map((line) => {
              const [key, value] = line.split(": ");
              return (
                <div key={line} className="flex justify-between gap-3">
                  <dt className="text-ink-faint">{key}</dt>
                  <dd className="font-medium text-ink">{value}</dd>
                </div>
              );
            })}
          </dl>
        </Section>
      </div>

      <p className="mt-4 border-t border-border pt-3 text-xs text-ink-faint">
        Nothing here is sent for you. Apply through the link above first, because outreach is a follow-up and never a bypass.
      </p>
    </div>
  );
}
