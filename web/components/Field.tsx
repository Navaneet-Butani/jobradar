"use client";

import { useId } from "react";

/**
 * The one form field in the app.
 *
 * Label above the input, hint below it, error below that. Placeholders are for
 * format examples only, never as a substitute for the label: a placeholder
 * disappears the moment someone types, which leaves a filled form with no way
 * to tell what each box holds.
 */
export function Field({
  label,
  value,
  onChange,
  type = "text",
  hint,
  error,
  required,
  placeholder,
  disabled,
  inputMode,
  min,
  max,
  step,
  autoComplete,
}: {
  label: string;
  value: string | number;
  onChange: (value: string) => void;
  type?: string;
  hint?: string;
  error?: string | null;
  required?: boolean;
  placeholder?: string;
  disabled?: boolean;
  inputMode?: "numeric" | "text" | "email";
  min?: number;
  max?: number;
  step?: number;
  autoComplete?: string;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
        {required && (
          <span className="ml-1 text-danger" aria-hidden>
            *
          </span>
        )}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        placeholder={placeholder}
        disabled={disabled}
        inputMode={inputMode}
        min={min}
        max={max}
        step={step}
        autoComplete={autoComplete}
        aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
        aria-invalid={error ? true : undefined}
        className={`rounded-lg border bg-bg px-3 py-2 text-sm text-ink outline-none transition-colors disabled:opacity-50 ${
          error ? "border-danger" : "border-border-strong focus:border-accent"
        }`}
      />
      {hint && !error && (
        <p id={hintId} className="text-xs text-ink-faint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
