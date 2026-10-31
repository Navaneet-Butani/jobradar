"use client";

import { useState } from "react";

export function DraftFollowup({ applicationId }: { applicationId: number }) {
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [draft, setDraft] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function generate() {
    setState("loading");
    setDraft(null);
    const res = await fetch(`/api/applications/${applicationId}/draft-followup`, { method: "POST" });
    const body = await res.json();
    if (!res.ok || !body.status) {
      setState("error");
      return;
    }
    setDraft(body.data.draft);
    setState("idle");
  }

  async function copy() {
    if (!draft) return;
    await navigator.clipboard.writeText(draft);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (draft) {
    return (
      <div className="mt-1.5 rounded-md bg-bg-sunken p-2" onMouseDown={(e) => e.stopPropagation()}>
        <p className="whitespace-pre-wrap text-xs text-ink-soft">{draft}</p>
        <button
          type="button"
          onClick={copy}
          className="mt-1.5 text-xs font-medium text-accent hover:underline"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      draggable={false}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={generate}
      disabled={state === "loading"}
      className="mt-1.5 text-left text-xs font-medium text-ink-faint hover:text-accent disabled:opacity-50"
    >
      {state === "loading" ? "Drafting…" : state === "error" ? "Draft unavailable, try again" : "Draft follow-up"}
    </button>
  );
}
