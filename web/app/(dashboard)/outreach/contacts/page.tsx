import { getOutreachContacts } from "@/lib/session";
import { ContactsPanel } from "@/components/outreach/ContactsPanel";

export default async function OutreachContactsPage() {
  const { contacts } = await getOutreachContacts();
  return <ContactsPanel contacts={contacts} />;
}
