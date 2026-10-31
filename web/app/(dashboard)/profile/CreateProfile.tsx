"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "@phosphor-icons/react";
import { Field } from "@/components/Field";

/**
 * The one gap the invite flow exposed: a brand new account has no job profile,
 * and the profile page rendered a list of zero forms with nothing to press.
 *
 * Only name and years of experience are asked for, because those are the only
 * two the API requires. Everything else is better filled in against the real
 * form once it exists, with its hints explaining what each field does.
 */
export function CreateProfile() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [years, setYears] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    const parsed = Number(years);
    if (!name.trim()) return setError("Give the profile a name.");
    if (!Number.isFinite(parsed) || parsed < 0 || parsed > 50) {
      return setError("Years of experience must be a number between 0 and 50.");
    }

    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/profiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), years_exp: parsed }),
      });
      const body = await res.json();
      if (!res.ok || !body.status) throw new Error(body.error_message ?? "Could not create the profile");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the profile");
      setSaving(false);
    }
  }

  return (
    <section className="rounded-xl border border-border bg-bg-elevated p-5">
      <h2 className="font-display text-base font-semibold text-ink">Create your matching profile</h2>
      <p className="mt-1 max-w-[60ch] text-sm text-ink-soft">
        Nothing gets scored until this exists. Start with a name and your experience. The rest of
        the settings appear once it&rsquo;s created, and every ingest run re-scores against them.
      </p>

      <div className="mt-4 grid max-w-lg gap-4 sm:grid-cols-2">
        <Field
          label="Profile name"
          value={name}
          onChange={setName}
          required
          placeholder="Backend engineer"
          hint="Just a label for you."
          disabled={saving}
        />
        <Field
          label="Years of experience"
          value={years}
          onChange={setYears}
          type="number"
          inputMode="numeric"
          required
          min={0}
          max={50}
          placeholder="2"
          hint="Filters out roles well outside your band."
          disabled={saving}
        />
      </div>

      {error && (
        <p role="alert" className="mt-3 text-xs font-medium text-danger">
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={create}
        disabled={saving}
        className="mt-4 inline-flex items-center gap-2 rounded-lg bg-accent px-3.5 py-2 text-sm font-semibold text-accent-ink transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        <Plus size={16} weight="bold" />
        {saving ? "Creating…" : "Create profile"}
      </button>
    </section>
  );
}
