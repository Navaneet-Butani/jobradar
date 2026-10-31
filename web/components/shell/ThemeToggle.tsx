"use client";

import { useCallback, useSyncExternalStore } from "react";
import { Desktop, Moon, Sun } from "@phosphor-icons/react";

type Mode = "light" | "dark" | "system";

const MODES: { value: Mode; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Desktop },
];

export const THEME_STORAGE_KEY = "jr-theme";
const CHANGE_EVENT = "jr-theme-change";

function applyToDocument(mode: Mode) {
  const root = document.documentElement;
  if (mode === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", mode);
}

/*
  Read through useSyncExternalStore rather than an effect.

  The obvious version (useState + useEffect reading localStorage) either warns
  about setState-in-effect or hydration-mismatches, because the server cannot
  know the stored preference. useSyncExternalStore is built for exactly this:
  it takes a separate server snapshot, so React renders "system" on the server
  and the real value on the client without complaining about either.
*/
function subscribe(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

function getSnapshot(): Mode {
  return (localStorage.getItem(THEME_STORAGE_KEY) as Mode | null) ?? "system";
}

function getServerSnapshot(): Mode {
  return "system";
}

export function ThemeToggle() {
  const mode = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const choose = useCallback((next: Mode) => {
    localStorage.setItem(THEME_STORAGE_KEY, next);
    applyToDocument(next);
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  return (
    <div
      className="flex items-center gap-0.5 rounded-lg border border-border bg-bg-sunken p-0.5"
      role="group"
      aria-label="Colour theme"
    >
      {MODES.map(({ value, label, icon: Icon }) => {
        const active = mode === value;
        return (
          <button
            key={value}
            type="button"
            onClick={() => choose(value)}
            aria-pressed={active}
            title={label}
            className={`rounded-md p-1.5 transition-colors ${
              active ? "bg-bg-elevated text-ink shadow-[var(--shadow-card)]" : "text-ink-faint hover:text-ink-soft"
            }`}
          >
            <Icon size={15} weight={active ? "fill" : "regular"} />
            <span className="sr-only">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
