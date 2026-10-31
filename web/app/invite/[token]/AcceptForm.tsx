"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle, WarningCircle } from "@phosphor-icons/react";

/** Mirrors RegistrationService.validate_password so the rules are visible while
 *  typing instead of arriving as a server error after submit. */
const RULES: { label: string; test: (v: string) => boolean }[] = [
  { label: "8 characters or more", test: (v) => v.length >= 8 },
  { label: "an uppercase letter", test: (v) => /[A-Z]/.test(v) },
  { label: "a lowercase letter", test: (v) => /[a-z]/.test(v) },
  { label: "a number", test: (v) => /\d/.test(v) },
  { label: "a symbol", test: (v) => /[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(v) },
];

export function AcceptForm({
  token,
  email,
  firstName,
  lastName,
}: {
  token: string;
  email: string;
  firstName: string;
  lastName: string;
}) {
  const router = useRouter();
  const [first, setFirst] = useState(firstName);
  const [last, setLast] = useState(lastName);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const unmet = RULES.filter((r) => !r.test(password));
  const mismatch = confirm.length > 0 && confirm !== password;
  const ready = unmet.length === 0 && password === confirm && password.length > 0;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ready) return;
    setSubmitting(true);
    setError(null);

    const res = await fetch(`/api/invite/${encodeURIComponent(token)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        password,
        first_name: first.trim() || null,
        last_name: last.trim() || null,
      }),
    });
    const body = await res.json().catch(() => null);

    if (!res.ok || !body?.status) {
      setError(body?.error_message ?? "Could not set up the account. The link may have expired.");
      setSubmitting(false);
      return;
    }

    // The route handler has already set the session cookies, so this lands
    // signed in. Profile first: a feed with no matching rules is an empty page.
    router.push("/profile?welcome=1");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
        Email
        <input
          type="email"
          value={email}
          readOnly
          aria-describedby="email-fixed"
          className="rounded-lg border border-border bg-bg-sunken px-3 py-2 text-sm text-ink-soft outline-none"
        />
        <span id="email-fixed" className="text-xs font-normal text-ink-faint">
          Fixed by the invite. This is also your sign-in.
        </span>
      </label>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
          First name
          <input
            type="text"
            autoComplete="given-name"
            value={first}
            onChange={(e) => setFirst(e.target.value)}
            className="rounded-lg border border-border-strong bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
          Last name
          <input
            type="text"
            autoComplete="family-name"
            value={last}
            onChange={(e) => setLast(e.target.value)}
            className="rounded-lg border border-border-strong bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
        </label>
      </div>

      <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
        Password
        <input
          type="password"
          required
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded-lg border border-border-strong bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-accent"
        />
      </label>

      {password.length > 0 && unmet.length > 0 && (
        <p className="text-xs text-ink-faint">Still needs {unmet.map((r) => r.label).join(", ")}.</p>
      )}
      {password.length > 0 && unmet.length === 0 && (
        <p className="inline-flex items-center gap-1.5 text-xs font-medium text-score-strong">
          <CheckCircle size={14} weight="fill" />
          Strong enough
        </p>
      )}

      <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
        Confirm password
        <input
          type="password"
          required
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          aria-invalid={mismatch}
          aria-describedby={mismatch ? "confirm-mismatch" : undefined}
          className={`rounded-lg border bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-accent ${
            mismatch ? "border-danger" : "border-border-strong"
          }`}
        />
        {mismatch && (
          <span id="confirm-mismatch" className="text-xs font-normal text-danger">
            The two passwords don&rsquo;t match.
          </span>
        )}
      </label>

      {error && (
        <p role="alert" className="flex items-start gap-1.5 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          <WarningCircle size={15} className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={submitting || !ready}
        className="mt-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {submitting ? "Setting up…" : "Create account"}
      </button>

      <p className="text-xs text-ink-faint">
        Next you&rsquo;ll fill in what you&rsquo;re looking for: titles, skills, cities, salary
        floor. That&rsquo;s what turns twenty thousand listings into a list worth reading.
      </p>
    </form>
  );
}
