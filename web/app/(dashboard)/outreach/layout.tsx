import { getCampaigns, getOutreachContacts } from "@/lib/session";
import { PageHeader } from "@/components/shell/PageHeader";
import { SubNav } from "@/components/shell/SubNav";

export default async function OutreachLayout({ children }: { children: React.ReactNode }) {
  // Counts are decoration on the tabs; a failure here must not take the
  // section down, so both fall back to undefined and the badge disappears.
  const [contacts, campaigns] = await Promise.all([
    getOutreachContacts()
      .then((c) => c.total_count)
      .catch(() => undefined),
    getCampaigns()
      .then((c) => c.total_count)
      .catch(() => undefined),
  ]);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Outreach"
        description="Email hiring contacts from your own mailbox. Nothing sends without you pressing send."
      />

      <SubNav
        items={[
          { href: "/outreach", label: "Campaigns", count: campaigns },
          { href: "/outreach/contacts", label: "Contacts", count: contacts },
          { href: "/outreach/account", label: "Sending account" },
        ]}
      />

      {children}
    </div>
  );
}
