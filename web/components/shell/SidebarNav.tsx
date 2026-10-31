"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Broadcast,
  FunnelSimple,
  Kanban,
  UsersThree,
  MagnifyingGlass,
  SlidersHorizontal,
  Target,
} from "@phosphor-icons/react";

const ITEMS = [
  { href: "/", label: "Feed", icon: Target, hint: "Scored matches" },
  { href: "/search", label: "Search", icon: MagnifyingGlass, hint: "All jobs" },
  { href: "/tracker", label: "Tracker", icon: Kanban, hint: "Applications" },
  { href: "/outreach", label: "Outreach", icon: Broadcast, hint: "Contacts and campaigns" },
  { href: "/profile", label: "Profile", icon: SlidersHorizontal, hint: "Matching rules" },
  { href: "/settings/scraping", label: "Settings", icon: FunnelSimple, hint: "What we collect" },
];

// Shown only to the admin account. Hiding it is convenience, not access
// control -- the page and the API both check is_admin again.
const ADMIN_ITEMS = [
  { href: "/settings/team", label: "People", icon: UsersThree, hint: "Invites and accounts" },
];

export function SidebarNav({
  counts,
  isAdmin,
}: {
  counts?: { feed?: number; due?: number };
  isAdmin?: boolean;
}) {
  const pathname = usePathname();
  const items = isAdmin ? [...ITEMS, ...ADMIN_ITEMS] : ITEMS;

  return (
    <nav className="flex flex-col gap-0.5" aria-label="Main">
      {items.map(({ href, label, icon: Icon, hint }) => {
        // "/" would prefix-match everything, so it needs an exact test.
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        const badge =
          href === "/" ? counts?.feed : href === "/tracker" ? counts?.due : undefined;

        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            title={hint}
            className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
              active
                ? "bg-accent-soft font-semibold text-accent-soft-ink"
                : "font-medium text-ink-soft hover:bg-bg-sunken hover:text-ink"
            }`}
          >
            <Icon
              size={18}
              weight={active ? "fill" : "regular"}
              className={active ? "text-accent" : "text-ink-faint group-hover:text-ink-soft"}
            />
            <span className="flex-1 truncate">{label}</span>
            {badge != null && badge > 0 && (
              <span className="rounded-full bg-accent px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums text-accent-ink">
                {badge > 99 ? "99+" : badge}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
