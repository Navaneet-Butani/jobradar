import { Prohibit } from "@phosphor-icons/react/dist/ssr";
import { getCurrentUser, getMembers } from "@/lib/session";
import { EmptyState } from "@/components/EmptyState";
import { TeamManager } from "./TeamManager";

export default async function TeamSettingsPage() {
  const user = await getCurrentUser();

  // The tab is hidden for non-admins, but the URL is guessable, so check here
  // too rather than letting getMembers() throw a raw 403 into the error page.
  if (!user.is_admin) {
    return (
      <EmptyState
        icon={Prohibit}
        title="Admin only"
        description="Inviting and deactivating accounts changes who can reach the whole deployment, so it is limited to the admin account."
      />
    );
  }

  const { members } = await getMembers();

  return (
    <section className="rounded-xl border border-border bg-bg-raised p-5">
      <div className="mb-4 max-w-[70ch]">
        <h2 className="font-display text-sm font-semibold text-ink">People</h2>
        <p className="mt-1 text-xs text-ink-faint">
          JobRadar is invite-only, with no public signup. Inviting someone creates a
          dormant account and a one-time link; nothing exists for them to log into until they
          open it and choose a password.
        </p>
      </div>

      <TeamManager members={members} />
    </section>
  );
}
