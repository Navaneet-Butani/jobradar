"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CaretDown } from "@phosphor-icons/react";
import type { JobProfile } from "@/lib/types";

export function ProfileSwitcher({ profiles }: { profiles: JobProfile[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeId = Number(searchParams.get("profile_id") ?? profiles[0]?.id);
  const active = profiles.find((p) => p.id === activeId) ?? profiles[0];

  if (!active) {
    return (
      <p className="px-2 text-sm text-ink-faint">No profile yet</p>
    );
  }

  if (profiles.length <= 1) {
    return (
      <p className="truncate rounded-lg px-2 py-1.5 text-sm font-medium text-ink" title={active.name}>
        {active.name}
      </p>
    );
  }

  function onChange(id: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("profile_id", id);
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="relative">
      <select
        value={activeId}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Active job profile"
        className="w-full appearance-none truncate rounded-lg border border-border bg-bg-sunken py-2 pl-2.5 pr-8 text-sm font-medium text-ink outline-none transition-colors hover:border-border-strong focus:border-accent"
      >
        {profiles.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <CaretDown
        size={13}
        className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-faint"
      />
    </div>
  );
}
