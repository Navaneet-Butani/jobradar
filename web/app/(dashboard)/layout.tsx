import { getCurrentUser, getDueToday, getMatchStats, getProfiles } from "@/lib/session";
import { AppShell } from "@/components/shell/AppShell";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [user, profiles] = await Promise.all([getCurrentUser(), getProfiles()]);

  // Rail badges. Neither is worth failing the whole shell over, so a badge
  // that can't be resolved simply doesn't render.
  const [newToday, dueToday] = await Promise.all([
    profiles[0]
      ? getMatchStats(profiles[0].id)
          .then((s) => s.new_today)
          .catch(() => undefined)
      : Promise.resolve(undefined),
    getDueToday()
      .then((d) => d.total_count)
      .catch(() => undefined),
  ]);

  return (
    <AppShell
      email={user.email}
      profiles={profiles}
      counts={{ feed: newToday, due: dueToday }}
      isAdmin={user.is_admin}
    >
      {children}
    </AppShell>
  );
}
