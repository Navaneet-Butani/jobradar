import { getCurrentUser } from "@/lib/session";
import { PageHeader } from "@/components/shell/PageHeader";
import { SubNav } from "@/components/shell/SubNav";

export default async function SettingsLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();

  // Team is admin-only. Hiding the tab is convenience, not the control — the
  // page and the API both check again.
  const items = [
    { href: "/settings/scraping", label: "Scraping" },
    ...(user.is_admin ? [{ href: "/settings/team", label: "People" }] : []),
  ];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Settings"
        description="Deployment-wide configuration. These apply to everyone, not just you."
      />

      <SubNav items={items} />

      {children}
    </div>
  );
}
