"use client";

import { useId, useState } from "react";
import { X } from "@phosphor-icons/react";

export function TagInput({
  label,
  values,
  onChange,
  hint,
}: {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  hint?: string;
}) {
  const id = useId();
  const [draft, setDraft] = useState("");

  function commit() {
    const tag = draft.trim().toLowerCase();
    if (tag && !values.includes(tag)) onChange([...values, tag]);
    setDraft("");
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="flex items-baseline justify-between gap-2 text-sm font-medium text-ink">
        {label}
        {values.length > 0 && (
          <span className="font-mono text-xs font-normal text-ink-faint">{values.length}</span>
        )}
      </label>

      {/* The whole box is the click target, so tapping empty space focuses the
          input rather than only the thin strip the input itself occupies. */}
      <div
        onClick={() => document.getElementById(id)?.focus()}
        className="flex min-h-[2.6rem] cursor-text flex-wrap items-center gap-1.5 rounded-lg border border-border-strong bg-bg px-2 py-1.5 transition-colors focus-within:border-accent"
      >
        {values.map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 rounded-full bg-accent-soft py-1 pl-2.5 pr-1 text-xs font-medium text-accent-soft-ink"
          >
            {tag}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onChange(values.filter((v) => v !== tag));
              }}
              aria-label={`Remove ${tag}`}
              className="rounded-full p-0.5 opacity-70 transition-opacity hover:opacity-100"
            >
              <X size={11} weight="bold" />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              commit();
            } else if (e.key === "Backspace" && !draft && values.length) {
              onChange(values.slice(0, -1));
            }
          }}
          onBlur={commit}
          placeholder={values.length ? "Add another…" : "Type and press Enter"}
          className="min-w-[8rem] flex-1 bg-transparent px-1 py-0.5 text-sm text-ink outline-none placeholder:text-ink-faint"
        />
      </div>

      {hint && <p className="text-xs text-ink-faint">{hint}</p>}
    </div>
  );
}
