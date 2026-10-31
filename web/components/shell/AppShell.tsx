"use client";

import { useState } from "react";
import Link from "next/link";
import { List, X } from "@phosphor-icons/react";
import type { JobProfile } from "@/lib/types";
import { RadarMark } from "@/components/RadarMark";
import { ProfileSwitcher } from "@/components/ProfileSwitcher";
import { SidebarNav } from "@/components/shell/SidebarNav";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { UserMenu } from "@/components/shell/UserMenu";

/**
 * Persistent left rail + content column.
 *
 * Navigation lives in the rail because this is a tool people move between
 * sections in constantly, not a site they read top to bottom. The rail is
 * fixed on desktop and becomes a drawer under `lg`; the content column is
 * the only thing that scrolls.
 */
export function AppShell({
  email,
  profiles,
  counts,
  isAdmin,
  children,
}: {
  email: string;
  profiles: JobProfile[];
  counts?: { feed?: number; due?: number };
  isAdmin?: boolean;
  children: React.ReactNode;
}) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  const rail = (
    <div className="flex h-full flex-col gap-6 p-4">
      <Link href="/" className="flex items-center gap-2 px-2 pt-1 text-accent">
        <RadarMark className="h-6 w-6" />
        <span className="font-display text-base font-semibold tracking-tight text-ink">JobRadar</span>
      </Link>

      <div className="px-1">
        <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
          Profile
        </p>
        <ProfileSwitcher profiles={profiles} />
      </div>

      <div onClick={() => setDrawerOpen(false)}>
        <SidebarNav counts={counts} isAdmin={isAdmin} />
      </div>

      <div className="mt-auto flex flex-col gap-2">
        <ThemeToggle />
        <UserMenu email={email} />
      </div>
    </div>
  );

  return (
    <div className="flex min-h-[100dvh]">
      {/* Desktop rail */}
      <aside className="hidden w-60 shrink-0 border-r border-border bg-bg-elevated lg:block">
        <div className="sticky top-0 h-[100dvh]">{rail}</div>
      </aside>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-black/40"
          />
          <aside className="relative h-full w-64 border-r border-border bg-bg-elevated">
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              className="absolute right-3 top-3 rounded-md p-1.5 text-ink-faint hover:text-ink"
              aria-label="Close navigation"
            >
              <X size={18} />
            </button>
            {rail}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-bg/85 px-4 backdrop-blur lg:hidden">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="rounded-md p-1.5 text-ink-soft hover:bg-bg-sunken hover:text-ink"
            aria-label="Open navigation"
          >
            <List size={20} />
          </button>
          <Link href="/" className="flex items-center gap-2 text-accent">
            <RadarMark className="h-5 w-5" />
            <span className="font-display text-sm font-semibold text-ink">JobRadar</span>
          </Link>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </div>
  );
}
