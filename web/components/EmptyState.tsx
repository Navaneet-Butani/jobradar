import type { Icon } from "@phosphor-icons/react";
import type { ReactNode } from "react";

/**
 * Empty states say what to do next, not just that something is missing.
 * Used everywhere a list can legitimately be empty.
 */
export function EmptyState({
  icon: IconGlyph,
  title,
  description,
  action,
}: {
  icon: Icon;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border-strong px-6 py-14 text-center">
      <span className="mb-3 grid h-11 w-11 place-items-center rounded-full bg-bg-sunken text-ink-faint">
        <IconGlyph size={20} />
      </span>
      <p className="font-display text-base font-semibold text-ink">{title}</p>
      <p className="mt-1 max-w-[46ch] text-sm text-ink-soft">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
