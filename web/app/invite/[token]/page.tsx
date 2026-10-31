import Link from "next/link";
import { backendFetch } from "@/lib/backend";
import { RadarMark } from "@/components/RadarMark";
import type { InvitePreview } from "@/lib/types";
import { AcceptForm } from "./AcceptForm";

/** Unauthenticated on purpose — the token in the URL is the only credential
 *  the invitee has, and an account does not exist for them yet. */
async function loadInvite(token: string): Promise<{ invite: InvitePreview | null; message: string }> {
  const res = await backendFetch(`/invites/accept/${encodeURIComponent(token)}`);
  const body = await res.json().catch(() => null);
  if (!res.ok || !body?.status || !body.data) {
    return { invite: null, message: body?.error_message ?? "This invite link is not valid." };
  }
  return { invite: body.data as InvitePreview, message: "" };
}

export default async function InvitePage(props: PageProps<"/invite/[token]">) {
  const { token } = await props.params;
  const { invite, message } = await loadInvite(token);

  return (
    <main className="mx-auto flex min-h-[100dvh] w-full max-w-md flex-col justify-center gap-6 px-5 py-10">
      <div className="flex items-center gap-2 text-accent">
        <RadarMark className="h-7 w-7" />
        <span className="font-display text-lg font-semibold tracking-tight text-ink">JobRadar</span>
      </div>

      {invite ? (
        <>
          <div>
            <h1 className="font-display text-xl font-semibold text-ink">Set up your account</h1>
            <p className="mt-1 text-sm text-ink-soft">
              {invite.invited_by ? `${invite.invited_by} invited ` : "You've been invited to "}
              <span className="font-medium text-ink">{invite.email}</span>. Choose a password and
              you&rsquo;re in.
            </p>
          </div>

          <AcceptForm
            token={token}
            email={invite.email}
            firstName={invite.first_name ?? ""}
            lastName={invite.last_name ?? ""}
          />
        </>
      ) : (
        <div className="rounded-xl border border-border bg-bg-elevated p-5">
          <h1 className="font-display text-base font-semibold text-ink">This link doesn&rsquo;t work</h1>
          <p className="mt-1 text-sm text-ink-soft">{message}</p>
          <p className="mt-3 text-sm text-ink-faint">
            Invite links expire after 7 days and work once. Ask whoever sent it for a new one.
          </p>
          <Link href="/login" className="mt-4 inline-block text-sm font-semibold text-accent hover:underline">
            Go to sign in
          </Link>
        </div>
      )}
    </main>
  );
}
