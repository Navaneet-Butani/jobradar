"use client";

import { useMemo, useState } from "react";
import { CaretDown, CaretRight } from "@phosphor-icons/react";
import type { OutreachMessage } from "@/lib/types";
import { formatAbsolute, formatRelativeDate } from "@/lib/format";

/*
  Every recipient in a campaign, with what actually happened to their email.

  The list page only ever showed a progress bar, which answers "how far along"
  but never "did anyone reply" — the one thing worth knowing. Outcome is derived
  in one place here because it is not a single column: a message can be sent and
  replied, sent and bounced, or just sent and waiting.
*/

type Outcome = "replied" | "bounced" | "failed" | "awaiting" | "queued" | "other";

const OUTCOME_STYLE: Record<Outcome, string> = {
  replied: "text-score-strong",
  bounced: "text-danger",
  failed: "text-danger",
  awaiting: "text-ink-soft",
  queued: "text-ink-faint",
  other: "text-ink-faint",
};

const OUTCOME_LABEL: Record<Outcome, string> = {
  replied: "replied",
  bounced: "bounced",
  failed: "failed",
  awaiting: "awaiting reply",
  queued: "queued",
  other: "other",
};

function outcomeOf(message: OutreachMessage): Outcome {
  if (message.replied_at) return "replied";
  if (message.bounced_at) return "bounced";
  if (message.status === "failed") return "failed";
  if (message.status === "sent") return "awaiting";
  if (message.status === "queued") return "queued";
  return "other";
}

const FILTERS: { key: Outcome | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "replied", label: "Replied" },
  { key: "awaiting", label: "Awaiting" },
  { key: "bounced", label: "Bounced" },
  { key: "failed", label: "Failed" },
  { key: "queued", label: "Queued" },
];

export function RecipientTable({ messages }: { messages: OutreachMessage[] }) {
  const [filter, setFilter] = useState<Outcome | "all">("all");
  const [openId, setOpenId] = useState<number | null>(null);

  const counts = useMemo(() => {
    const tally: Record<string, number> = { all: messages.length };
    for (const message of messages) {
      const outcome = outcomeOf(message);
      tally[outcome] = (tally[outcome] ?? 0) + 1;
    }
    return tally;
  }, [messages]);

  const visible = useMemo(
    () => (filter === "all" ? messages : messages.filter((m) => outcomeOf(m) === filter)),
    [messages, filter],
  );

  if (messages.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border-strong px-4 py-6 text-sm text-ink-faint">
        No recipients on this campaign yet.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter recipients by outcome">
        {FILTERS.filter((f) => f.key === "all" || counts[f.key]).map((f) => {
          const active = filter === f.key;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              aria-pressed={active}
              className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                active
                  ? "bg-accent text-accent-ink"
                  : "bg-bg-sunken text-ink-soft hover:text-ink"
              }`}
            >
              {f.label}
              <span className="ml-1.5 font-mono tabular-nums opacity-70">{counts[f.key] ?? 0}</span>
            </button>
          );
        })}
      </div>

      {/* Reply snippets and bounce diagnostics are long and arbitrary, so the
          table scrolls inside its own box rather than pushing the page sideways. */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full table-fixed text-left text-sm">
          <thead className="bg-bg-sunken text-xs uppercase tracking-wide text-ink-faint">
            <tr>
              <th scope="col" className="w-1/4 px-3 py-2 font-medium">
                Recipient
              </th>
              <th scope="col" className="w-20 px-3 py-2 font-medium">
                Step
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Outcome
              </th>
              <th scope="col" className="w-24 px-3 py-2 font-medium">
                When
              </th>
              <th scope="col" className="w-24 px-3 py-2 font-medium">
                <span className="sr-only">Show email</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((message) => {
              const outcome = outcomeOf(message);
              const open = openId === message.id;
              const when = message.replied_at ?? message.bounced_at ?? message.sent_at;

              return (
                <tr key={message.id} className="border-t border-border align-top">
                  <td className="px-3 py-2">
                    <div className="truncate font-medium text-ink">{message.to_name ?? message.to_email}</div>
                    {message.to_name && <div className="truncate font-mono text-xs text-ink-faint">{message.to_email}</div>}
                    {message.company_name && (
                      <div className="text-xs text-ink-faint">{message.company_name}</div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-ink-faint">
                    {message.step === 2 ? "follow-up" : "initial"}
                  </td>
                  <td className={`px-3 py-2 whitespace-nowrap text-xs ${OUTCOME_STYLE[outcome]}`}>
                    {OUTCOME_LABEL[outcome]}
                    {/* Snippets and SMTP diagnostics run long. Two lines here,
                        the rest on hover, so rows stay scannable. */}
                    {(message.reply_snippet || message.bounce_reason || message.error) && (
                      <div
                        title={message.reply_snippet ?? message.bounce_reason ?? message.error ?? undefined}
                        className="mt-1 line-clamp-2 whitespace-normal text-xs text-ink-faint"
                      >
                        {message.reply_from && <span className="text-ink-soft">{message.reply_from}: </span>}
                        {message.reply_snippet ?? message.bounce_reason ?? message.error}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-xs text-ink-faint" title={formatAbsolute(when)}>
                    {when ? formatRelativeDate(when) : "-"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => setOpenId(open ? null : message.id)}
                      aria-expanded={open}
                      className="inline-flex items-center gap-1 text-xs font-medium text-ink-faint hover:text-accent"
                    >
                      {open ? <CaretDown size={12} /> : <CaretRight size={12} />}
                      {open ? "Hide" : "Email"}
                    </button>
                    {open && (
                      <div className="mt-2 max-w-prose rounded-lg bg-bg-sunken p-3 text-left">
                        <p className="text-xs font-semibold text-ink">{message.subject}</p>
                        <p className="mt-2 whitespace-pre-wrap text-xs text-ink-soft">{message.body}</p>
                        {message.attached_resume && (
                          <p className="mt-2 text-xs text-ink-faint">Resume attached</p>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
