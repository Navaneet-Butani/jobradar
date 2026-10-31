import { Confetti } from "@phosphor-icons/react/dist/ssr";
import { getProfiles, getResume } from "@/lib/session";
import { ResumeUpload } from "@/components/ResumeUpload";
import { PageHeader } from "@/components/shell/PageHeader";
import { ProfileForm } from "./ProfileForm";
import { CreateProfile } from "./CreateProfile";

export default async function ProfilePage(props: PageProps<"/profile">) {
  const sp = await props.searchParams;
  const welcome = sp.welcome === "1";
  const [profiles, resume] = await Promise.all([getProfiles(), getResume()]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Profile"
        description="This is what drives matching. The more specific it is, the shorter and more relevant the feed."
      />

      {welcome && (
        <p className="flex items-start gap-2.5 rounded-xl border border-accent bg-accent-soft/40 px-4 py-3 text-sm text-ink">
          <Confetti size={18} weight="fill" className="mt-0.5 shrink-0 text-accent" />
          <span>
            <strong className="font-semibold">Your account is ready.</strong> Fill this in and the
            next ingest run will score every job against it. Until then the feed will be empty. That&rsquo;s
            expected, not broken.
          </span>
        </p>
      )}

      <ResumeUpload resume={resume} />

      {profiles.length === 0 ? (
        <CreateProfile />
      ) : (
        profiles.map((profile) => <ProfileForm key={profile.id} profile={profile} hasResume={Boolean(resume)} />)
      )}
    </div>
  );
}
