"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CaretUpDown, SignOut } from "@phosphor-icons/react";

export function UserMenu({ email }: { email: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  const initial = email.trim().charAt(0).toUpperCase() || "?";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors hover:bg-bg-sunken"
      >
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent-soft font-semibold text-xs text-accent-soft-ink">
          {initial}
        </span>
        <span className="min-w-0 flex-1 truncate text-sm text-ink-soft">{email}</span>
        <CaretUpDown size={14} className="shrink-0 text-ink-faint" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 mb-1 w-full overflow-hidden rounded-lg border border-border bg-bg-elevated shadow-[var(--shadow-card)]"
        >
          <button
            type="button"
            role="menuitem"
            onClick={logout}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-ink-soft transition-colors hover:bg-bg-sunken hover:text-danger"
          >
            <SignOut size={15} />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
