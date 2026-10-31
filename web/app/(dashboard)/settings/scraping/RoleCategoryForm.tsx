"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle, FloppyDisk, Warning } from "@phosphor-icons/react";
import type { RoleCategories } from "@/lib/types";

/**
 * Controls what the scrapers collect, not what the feed shows.
 *
 * Unchecking a category stops new jobs of that kind being stored at all —
 * jobs already in the corpus stay. That asymmetry is worth stating on the page
 * itself, because "uncheck to hide" is the reasonable wrong assumption.
 */
export function RoleCategoryForm({ initial }: { initial: RoleCategories }) {
  const router = useRouter();
  const [enabled, setEnabled] = useState<Set<string>>(
    () => new Set(initial.categories.filter((c) => c.enabled).map((c) => c.key))
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const editable = initial.editable;
  const dirty =
    enabled.size !== initial.categories.filter((c) => c.enabled).length ||
    initial.categories.some((c) => c.enabled !== enabled.has(c.key));

  function toggle(key: string) {
    setSaved(false);
    setError(null);
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function save() {
    if (enabled.size === 0) {
      setError("Select at least one category. An empty list would stop collecting anything.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/scraping/roles", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: [...enabled] }),
      });
      const body = await res.json();
      if (!res.ok || !body.status) {
        throw new Error(body.error_message ?? "Could not save");
      }
      setSaved(true);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      {!editable && (
        <p className="flex items-start gap-2 rounded-lg bg-bg-sunken px-3 py-2 text-xs text-ink-soft">
          <Warning size={16} className="mt-0.5 shrink-0 text-ink-faint" />
          These settings change what the pipeline collects for every account, so
          only the admin account can edit them. You can see the current setup here.
        </p>
      )}

      <div className="grid gap-2 sm:grid-cols-2">
        {initial.categories.map((c) => {
          const on = enabled.has(c.key);
          return (
            <label
              key={c.key}
              className={`flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2.5 transition-colors ${
                on ? "border-accent bg-accent-soft/40" : "border-border hover:bg-bg-sunken"
              } ${editable ? "" : "cursor-not-allowed opacity-70"}`}
            >
              <input
                type="checkbox"
                className="mt-0.5 size-4 shrink-0 accent-[var(--accent)]"
                checked={on}
                disabled={!editable || saving}
                onChange={() => toggle(c.key)}
              />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-ink">{c.label}</span>
                <span className="mt-0.5 block truncate text-xs text-ink-faint">
                  {c.examples.join(", ")}
                </span>
              </span>
            </label>
          );
        })}
      </div>

      {error && (
        <p role="alert" className="text-xs font-medium text-danger">
          {error}
        </p>
      )}

      {editable && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={save}
            disabled={saving || !dirty}
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-3.5 py-2 text-sm font-semibold text-accent-ink transition-opacity disabled:opacity-50"
          >
            <FloppyDisk size={16} weight="bold" />
            {saving ? "Saving…" : "Save"}
          </button>
          {saved && !dirty && (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-soft">
              <CheckCircle size={15} weight="fill" className="text-accent" />
              Saved. Applies from the next ingest run
            </span>
          )}
          <span className="ml-auto font-mono text-xs tabular-nums text-ink-faint">
            {enabled.size}/{initial.categories.length} collected
          </span>
        </div>
      )}
    </div>
  );
}
