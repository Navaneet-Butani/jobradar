"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Pause, Play, Trash } from "@phosphor-icons/react";
import type { OutreachCampaign } from "@/lib/types";

/*
  Start / pause / delete for one campaign. Lives on both the list row and the
  detail page, so the redirect target is a prop: deleting from the detail page
  has to leave the page, deleting from the list only refreshes it.
*/
export function CampaignActions({
  campaign,
  afterDelete,
  size = "sm",
}: {
  campaign: OutreachCampaign;
  afterDelete?: string;
  size?: "sm" | "md";
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canStart =
    (campaign.status === "paused" || campaign.status === "draft") && campaign.counts.queued > 0;

  async function act(action: "start" | "pause") {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/outreach/campaigns/${campaign.id}/${action}`, { method: "POST" });
    const body = await res.json().catch(() => null);
    setBusy(false);
    if (!res.ok || !body?.status) {
      setError(body?.error_message ?? `Couldn't ${action} that campaign`);
      return;
    }
    router.refresh();
  }

  async function remove() {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/outreach/campaigns/${campaign.id}`, { method: "DELETE" });
    setBusy(false);
    if (!res.ok) {
      setError("Couldn't delete that campaign");
      return;
    }
    if (afterDelete) router.push(afterDelete);
    router.refresh();
  }

  const buttonClass =
    size === "md"
      ? "inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium"
      : "text-xs font-medium";

  return (
    <div className="flex items-center gap-3">
      {error && (
        <span role="alert" className="text-xs text-danger">
          {error}
        </span>
      )}

      {canStart && (
        <button
          type="button"
          disabled={busy}
          onClick={() => act("start")}
          className={`${buttonClass} text-accent hover:underline disabled:opacity-50`}
        >
          {size === "md" && <Play size={14} weight="fill" />}
          {campaign.status === "draft" ? "Start" : "Resume"}
        </button>
      )}

      {campaign.status === "running" && (
        <button
          type="button"
          disabled={busy}
          onClick={() => act("pause")}
          className={`${buttonClass} text-accent hover:underline disabled:opacity-50`}
        >
          {size === "md" && <Pause size={14} weight="fill" />}
          Pause
        </button>
      )}

      <button
        type="button"
        disabled={busy}
        onClick={remove}
        aria-label={`Delete ${campaign.name}`}
        className="rounded p-1 text-ink-faint transition-colors hover:text-danger disabled:opacity-50"
      >
        <Trash size={size === "md" ? 16 : 14} />
      </button>
    </div>
  );
}
