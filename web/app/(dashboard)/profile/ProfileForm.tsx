"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle, FloppyDisk, MagicWand } from "@phosphor-icons/react";
import type { JobProfile } from "@/lib/types";
import { TagInput } from "@/components/TagInput";
import { Field } from "@/components/Field";

/**
 * Grouped into the questions the matcher actually asks, with a hint on every
 * control saying what it does to the feed. This form is the single biggest
 * lever on match quality, and an unlabelled grid of inputs gives no clue which
 * knob to turn when the feed is wrong.
 */
function Fieldset({
  legend,
  description,
  children,
}: {
  legend: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="border-t border-border pt-5">
      <legend className="sr-only">{legend}</legend>
      <div className="mb-4">
        <h3 className="font-display text-sm font-semibold text-ink">{legend}</h3>
        <p className="mt-0.5 max-w-[60ch] text-xs text-ink-faint">{description}</p>
      </div>
      {children}
    </fieldset>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5"
      />
      <span>
        <span className="block text-sm text-ink">{label}</span>
        <span className="block text-xs text-ink-faint">{hint}</span>
      </span>
    </label>
  );
}

type Suggestion = {
  years_exp: number | null;
  must_have_skills: string[];
  nice_to_have_skills: string[];
  target_titles: string[];
  cities: string[];
};

export function ProfileForm({ profile, hasResume = false }: { profile: JobProfile; hasResume?: boolean }) {
  const router = useRouter();
  const [form, setForm] = useState(profile);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filling, setFilling] = useState(false);
  const [filledNote, setFilledNote] = useState<string | null>(null);

  const dirty = JSON.stringify(form) !== JSON.stringify(profile);

  function set<K extends keyof JobProfile>(key: K, value: JobProfile[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setSavedAt(null);
  }

  /** Fill the form from the resume; the user reviews, then saves as usual. */
  async function fillFromResume() {
    setFilling(true);
    setError(null);
    setFilledNote(null);
    try {
      const res = await fetch("/api/profiles/suggest", { method: "POST" });
      const body = await res.json();
      if (!res.ok || !body.status) throw new Error(body.error_message ?? "Couldn't read your resume");
      const { source, suggestion } = body.data as { source: string; suggestion: Suggestion };
      setForm((f) => ({
        ...f,
        years_exp: suggestion.years_exp ?? f.years_exp,
        must_have_skills: suggestion.must_have_skills.length ? suggestion.must_have_skills : f.must_have_skills,
        nice_to_have_skills: suggestion.nice_to_have_skills.length ? suggestion.nice_to_have_skills : f.nice_to_have_skills,
        target_titles: suggestion.target_titles.length ? suggestion.target_titles : f.target_titles,
        cities: f.cities.length ? f.cities : suggestion.cities,
      }));
      setSavedAt(null);
      setFilledNote(
        source === "llm" ? "Filled from your resume with AI. Review, then save." : "Filled from your resume. Review, then save."
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't read your resume");
    } finally {
      setFilling(false);
    }
  }

  async function save() {
    setSaving(true);
    setError(null);
    const { id, uuid, is_active, ...editable } = form;
    void id;
    void uuid;
    void is_active;

    const res = await fetch(`/api/profiles/${form.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(editable),
    });

    setSaving(false);
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      const detail = body?.details?.validation_errors?.[0]?.msg ?? body?.error_message;
      setError(detail ? String(detail).replace(/^Value error, /, "") : "Couldn't save, try again");
      return;
    }
    setSavedAt(Date.now());
    router.refresh();
  }

  return (
    <section className="rounded-xl border border-border bg-bg-elevated">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-5">
        <div>
          <h2 className="font-display text-base font-semibold text-ink">{form.name}</h2>
          <p className="mt-0.5 text-xs text-ink-faint">
            {form.must_have_skills.length} must-have skills, {form.target_titles.length} target titles,{" "}
            {form.cities.length} onsite cities
          </p>
        </div>

        <div className="flex items-center gap-3">
          {error && (
            <span role="alert" className="text-sm text-danger">
              {error}
            </span>
          )}
          {!error && !savedAt && filledNote && <span className="text-sm text-ink-soft">{filledNote}</span>}
          {hasResume && (
            <button
              type="button"
              onClick={fillFromResume}
              disabled={filling}
              title="Suggest skills, titles, experience and cities from your uploaded resume"
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium text-ink transition-colors hover:bg-bg-sunken disabled:opacity-40"
            >
              <MagicWand size={15} />
              {filling ? "Reading resume…" : "Fill from resume"}
            </button>
          )}
          {!error && savedAt && (
            <span className="inline-flex items-center gap-1.5 text-sm text-score-strong">
              <CheckCircle size={15} weight="fill" />
              Saved
            </span>
          )}
          <button
            type="button"
            onClick={save}
            disabled={saving || !dirty}
            title={!dirty ? "No changes to save" : undefined}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            <FloppyDisk size={15} />
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-6 p-5">
        <Fieldset
          legend="Experience and seniority"
          description="Postings asking far more or far less than this are dropped before scoring."
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field
              label="Years of experience"
              type="number"
              step={0.5}
              min={0}
              value={form.years_exp}
              onChange={(v) => set("years_exp", Number(v))}
              hint="Indian JDs overstate, so up to 1.5 years above this still passes."
            />
            <Field
              label="Minimum salary (₹/yr)"
              type="number"
              step={100000}
              min={0}
              value={form.min_salary_inr ?? ""}
              onChange={(v) => set("min_salary_inr", v ? Number(v) : null)}
              hint="Only 7% of postings disclose salary, so this rarely filters much."
            />
          </div>
        </Fieldset>

        <Fieldset
          legend="Location and remote"
          description="Onsite cities score full weight. Metro cities only surface when the posting reads hybrid or remote-friendly."
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="remote-scope" className="text-sm font-medium text-ink">
                Remote scope
              </label>
              <select
                id="remote-scope"
                value={form.remote_scope}
                onChange={(e) => set("remote_scope", e.target.value)}
                className="rounded-lg border border-border-strong bg-bg px-3 py-2 text-sm text-ink outline-none transition-colors focus:border-accent"
              >
                <option value="india_only">India only</option>
                <option value="global">Global</option>
              </select>
              <p className="text-xs text-ink-faint">
                India only drops US-only and EU-only remote roles, which are the largest noise source.
              </p>
            </div>

            <div className="flex flex-col justify-start gap-3 pt-1">
              <Toggle
                label="Accepts remote roles"
                hint="Off means onsite and hybrid only."
                checked={form.accepts_remote}
                onChange={(v) => set("accepts_remote", v)}
              />
              <Toggle
                label="Remote only"
                hint="Drops every onsite posting, including your own cities."
                checked={form.remote_only}
                onChange={(v) => set("remote_only", v)}
              />
              <Toggle
                label="Willing to relocate"
                hint="Appears in application packets as a standard answer."
                checked={form.willing_to_relocate}
                onChange={(v) => set("willing_to_relocate", v)}
              />
            </div>
          </div>
        </Fieldset>

        <Fieldset
          legend="Skills and titles"
          description="A posting must match at least one must-have skill to survive filtering. Nice-to-haves and titles then move the score."
        >
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <TagInput
              label="Must-have skills"
              values={form.must_have_skills}
              onChange={(v) => set("must_have_skills", v)}
            />
            <TagInput
              label="Nice-to-have skills"
              values={form.nice_to_have_skills}
              onChange={(v) => set("nice_to_have_skills", v)}
            />
            <TagInput label="Target titles" values={form.target_titles} onChange={(v) => set("target_titles", v)} />
            <TagInput label="Onsite cities" values={form.cities} onChange={(v) => set("cities", v)} />
            <TagInput
              label="Metro cities (hybrid only)"
              values={form.metro_cities}
              onChange={(v) => set("metro_cities", v)}
            />
          </div>
        </Fieldset>

        <Fieldset
          legend="Standard application answers"
          description="Pre-filled into every application packet, so you are not retyping them per form."
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field
              label="Notice period (days)"
              type="number"
              step={15}
              min={0}
              max={365}
              value={form.notice_period_days ?? ""}
              onChange={(v) => set("notice_period_days", v ? Number(v) : null)}
            />
            <Field
              label="Current CTC (₹/yr)"
              type="number"
              step={100000}
              min={0}
              value={form.current_ctc_inr ?? ""}
              onChange={(v) => set("current_ctc_inr", v ? Number(v) : null)}
            />
            <Field
              label="Expected CTC (₹/yr)"
              type="number"
              step={100000}
              min={0}
              value={form.expected_ctc_inr ?? ""}
              onChange={(v) => set("expected_ctc_inr", v ? Number(v) : null)}
            />
          </div>
        </Fieldset>

        <Fieldset
          legend="Alerts"
          description="Get new matches scoring 60+ pushed to your phone after every ingest. Each job is sent once."
        >
          <Field
            label="Webhook URL (Telegram, Discord, Slack or ntfy)"
            value={form.notify_webhook_url ?? ""}
            onChange={(v) => set("notify_webhook_url", v.trim() ? v : null)}
            placeholder="https://ntfy.sh/your-private-topic"
            hint="Telegram: https://api.telegram.org/bot<token>/sendMessage?chat_id=<id> · Discord: channel webhook URL · ntfy: install the app and pick a hard-to-guess topic."
          />
        </Fieldset>

        <Fieldset
          legend="Noise filters"
          description="The single biggest quality lever. Excluded terms drop a posting outright; staffing signals only penalise the score."
        >
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <TagInput
              label="Excluded keywords"
              values={form.exclude_keywords}
              onChange={(v) => set("exclude_keywords", v)}
            />
            <TagInput
              label="Excluded companies"
              values={form.exclude_companies}
              onChange={(v) => set("exclude_companies", v)}
            />
            <TagInput
              label="Preferred domains"
              values={form.domain_keywords}
              onChange={(v) => set("domain_keywords", v)}
            />
          </div>
          <div className="mt-4">
            <Toggle
              label="Include staffing and consultancy postings"
              hint="Off applies a score penalty to c2h, third-party payroll and deputation listings rather than hiding them."
              checked={form.include_staffing}
              onChange={(v) => set("include_staffing", v)}
            />
          </div>
          <div className="mt-4">
            <Toggle
              label="I don't have a CS degree"
              hint="Applies a small penalty to postings that make a computer-science degree mandatory. Preferred domains (e.g. fintech) earn a small bonus."
              checked={form.no_cs_degree}
              onChange={(v) => set("no_cs_degree", v)}
            />
          </div>
        </Fieldset>
      </div>
    </section>
  );
}
