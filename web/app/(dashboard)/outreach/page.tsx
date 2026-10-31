import { getCampaigns, getEmailAccount, getOutreachContacts, getTemplateDefaults } from "@/lib/session";
import { CampaignComposer } from "@/components/outreach/CampaignComposer";
import { CampaignList } from "@/components/outreach/CampaignList";

export default async function CampaignsPage() {
  const [account, { contacts }, { campaigns }, defaults] = await Promise.all([
    getEmailAccount(),
    getOutreachContacts(),
    getCampaigns(),
    getTemplateDefaults(),
  ]);

  return (
    <div className="flex flex-col gap-5">
      <CampaignComposer contacts={contacts} defaults={defaults} account={account} />
      <CampaignList campaigns={campaigns} />
    </div>
  );
}
