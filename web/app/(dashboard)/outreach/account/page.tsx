import { getEmailAccount } from "@/lib/session";
import { EmailAccountForm } from "@/components/outreach/EmailAccountForm";

export default async function OutreachAccountPage() {
  const account = await getEmailAccount();
  return <EmailAccountForm account={account} />;
}
