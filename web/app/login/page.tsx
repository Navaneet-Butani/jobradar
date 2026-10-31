import { Suspense } from "react";
import { RadarMark } from "@/components/RadarMark";
import { LoginForm } from "./LoginForm";

export default function LoginPage() {
  return (
    // min-h-[100dvh], not h-screen: iOS Safari's collapsing address bar makes
    // vh taller than the visible area and pushes the card under the chrome.
    <div className="flex min-h-[100dvh] items-center justify-center bg-bg-sunken px-6 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2.5 text-accent">
          <RadarMark className="h-7 w-7" />
          <span className="font-display text-xl font-semibold tracking-tight text-ink">JobRadar</span>
        </div>

        <div className="rounded-2xl border border-border bg-bg-elevated p-7">
          <h1 className="font-display text-lg font-semibold text-ink">Sign in</h1>
          <p className="mt-1 text-sm text-ink-soft">
            Invite-only. Ask your admin for an invite link.
          </p>

          <div className="mt-6">
            <Suspense>
              <LoginForm />
            </Suspense>
          </div>
        </div>

        <p className="mt-5 text-center text-xs text-ink-faint">
          Ranks jobs from nine sources against your profile.
        </p>
      </div>
    </div>
  );
}
