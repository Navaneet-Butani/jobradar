"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export type SubNavItem = {
  href: string;
  label: string;
  /** Small count shown after the label. Omit rather than passing 0. */
  count?: number;
};

/**
 * Section-level navigation, used when one area of the app has several screens
 * that share context (Outreach: contacts, campaigns, sending account).
 * A tab row rather than more rail items, because these only make sense inside
 * their section.
 */
export function SubNav({ items }: { items: SubNavItem[] }) {
  const pathname = usePathname();

  return (
    <nav className="-mb-px flex gap-1 overflow-x-auto border-b border-border" aria-label="Section">
      {items.map(({ href, label, count }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`whitespace-nowrap border-b-2 px-3 py-2.5 text-sm transition-colors ${
              active
                ? "border-accent font-semibold text-ink"
                : "border-transparent font-medium text-ink-soft hover:border-border-strong hover:text-ink"
            }`}
          >
            {label}
            {count != null && count > 0 && (
              <span
                className={`ml-1.5 rounded-full px-1.5 py-0.5 font-mono text-[11px] tabular-nums ${
                  active ? "bg-accent-soft text-accent-soft-ink" : "bg-bg-sunken text-ink-faint"
                }`}
              >
                {count}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
