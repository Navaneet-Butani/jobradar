"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { Resume } from "@/lib/types";

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function ResumeUpload({ resume }: { resume: Resume | null }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(file: File) {
    setBusy(true);
    setError(null);

    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/resume", { method: "POST", body: form });
    const body = await res.json().catch(() => null);

    setBusy(false);
    if (inputRef.current) inputRef.current.value = "";

    if (!res.ok || !body?.status) {
      setError(body?.message ?? body?.error_message ?? "Upload failed, try again");
      return;
    }
    router.refresh();
  }

  async function remove() {
    setBusy(true);
    setError(null);
    const res = await fetch("/api/resume", { method: "DELETE" });
    setBusy(false);
    if (!res.ok) {
      setError("Couldn't delete, try again");
      return;
    }
    router.refresh();
  }

  return (
    <section className="rounded-xl border border-border bg-bg-elevated p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-lg font-semibold text-ink">Master resume</h2>
          <p className="mt-1 text-sm text-ink-soft">
            Used to tailor bullets in application packets. The text is extracted and stored; the file itself isn&apos;t kept.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {error && (
            <span role="alert" className="text-sm text-danger">
              {error}
            </span>
          )}
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
            }}
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Working…" : resume ? "Replace" : "Upload resume"}
          </button>
          {resume && (
            <button
              type="button"
              disabled={busy}
              onClick={remove}
              className="text-sm font-medium text-ink-faint hover:text-danger disabled:opacity-50"
            >
              Remove
            </button>
          )}
        </div>
      </div>

      {resume ? (
        <div className="mt-4 rounded-lg bg-bg-sunken p-3">
          <p className="text-sm font-medium text-ink">{resume.filename}</p>
          <p className="mt-0.5 text-xs text-ink-faint">
            {resume.char_count.toLocaleString("en-IN")} characters · uploaded {formatDate(resume.updated_at)}
          </p>
          <details className="mt-2">
            <summary className="cursor-pointer text-xs font-medium text-accent">Show extracted text</summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs text-ink-soft">
              {resume.content_text}
            </pre>
          </details>
        </div>
      ) : (
        <p className="mt-4 rounded-lg bg-bg-sunken p-3 text-sm text-ink-faint">
          No resume yet. PDF, DOCX, TXT or MD. Scanned or image-only PDFs won&apos;t work, since there&apos;s no OCR.
        </p>
      )}
    </section>
  );
}
