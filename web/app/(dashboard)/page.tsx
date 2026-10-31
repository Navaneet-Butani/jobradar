import Link from "next/link";
import { CaretLeft, CaretRight, SlidersHorizontal, Target } from "@phosphor-icons/react/dist/ssr";
import { getMatches, getMatchStats, getProfiles } from "@/lib/session";
import { FeedFilters } from "@/components/FeedFilters";
import { BulkSelect, SelectableRow } from "@/components/BulkSelect";
import { MatchCard } from "@/components/MatchCard";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader, Stat } from "@/components/shell/PageHeader";

const STATE_LABELS: Record<string, string> = {
  new: "new",
  seen: "seen",
  interested: "interested",
  applied: "applied",
  dismissed: "dismissed",
};

export default async function FeedPage(props: PageProps<"/">) {
  const sp = await props.searchParams;
  const profiles = await getProfiles();
  const activeProfile = profiles.find((p) => String(p.id) === sp.profile_id) ?? profiles[0];

  if (!activeProfile) {
    return (
      <EmptyState
        icon={SlidersHorizontal}
        title="No job profile yet"
        description="A profile is what turns thousands of listings into a short, relevant list. Set one up to start seeing matches."
        action={
          <Link
            href="/profile"
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90"
          >
            Set up a profile
          </Link>
        }
      />
    );
  }

  const state = typeof sp.state === "string" ? sp.state : undefined;

  const params = new URLSearchParams();
  params.set("profile_id", String(activeProfile.id));
  if (state) params.set("state", state);
  if (typeof sp.min_score === "string") params.set("min_score", sp.min_score);
  if (typeof sp.remote_only === "string") params.set("remote_only", sp.remote_only);
  if (typeof sp.my_cities_only === "string") params.set("my_cities_only", sp.my_cities_only);
  if (typeof sp.sort === "string") params.set("sort", sp.sort);
  const page = typeof sp.page === "string" ? Number(sp.page) : 1;
  params.set("page", String(page));
  params.set("limit", "20");

  const [feed, stats] = await Promise.all([
    getMatches(`?${params.toString()}`),
    getMatchStats(activeProfile.id),
  ]);

  const totalPages = Math.max(1, Math.ceil(feed.total_count / feed.limit));

  // What the feed would show with no filters at all. Dismissed matches are
  // excluded server-side, so comparing against stats.total would report
  // "filtered" for everyone who has ever pressed Dismiss.
  const unfilteredTotal = stats.total - (stats.by_state.dismissed ?? 0);
  const filtered = Boolean(state) || feed.total_count !== unfilteredTotal;
  const jobIds = feed.matches.map((m) => m.job_id);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Match feed"
        description={`Scored against ${activeProfile.name}, highest first.`}
        meta={
          <>
            <Stat label="new today" value={stats.new_today} tone="accent" />
            <Stat label="interested" value={stats.by_state.interested ?? 0} tone="strong" />
            <Stat label="matches total" value={stats.total} />
          </>
        }
      />

      <FeedFilters stats={stats} />

      {feed.matches.length === 0 ? (
        <EmptyState
          icon={Target}
          title={
            state
              ? `Nothing marked ${STATE_LABELS[state] ?? state}`
              : filtered
                ? "Nothing matches these filters"
                : "No matches yet"
          }
          description={
            filtered
              ? "Loosen a filter above to widen the net."
              : "The next ingest run will score new jobs into this feed. If it stays empty, the profile may be too narrow."
          }
          action={
            filtered ? (
              <Link href="/" className="text-sm font-semibold text-accent hover:underline">
                Clear filters
              </Link>
            ) : (
              <Link href="/profile" className="text-sm font-semibold text-accent hover:underline">
                Review matching rules
              </Link>
            )
          }
        />
      ) : (
        <BulkSelect profileId={activeProfile.id} jobIds={jobIds}>
          <div className="flex flex-col gap-3">
            {feed.matches.map((match) => (
              <SelectableRow key={match.job_id} jobId={match.job_id} label={match.title}>
                <MatchCard match={match} profileId={activeProfile.id} />
              </SelectableRow>
            ))}
          </div>
        </BulkSelect>
      )}

      {totalPages > 1 && (
        <nav className="flex items-center justify-between border-t border-border pt-4 text-sm" aria-label="Pagination">
          <PageLink page={page - 1} disabled={page <= 1} direction="prev" searchParams={sp} />
          <span className="text-ink-faint">
            Page <span className="font-mono font-semibold tabular-nums text-ink">{page}</span> of{" "}
            <span className="font-mono tabular-nums">{totalPages}</span>
          </span>
          <PageLink page={page + 1} disabled={page >= totalPages} direction="next" searchParams={sp} />
        </nav>
      )}
    </div>
  );
}

function PageLink({
  page,
  disabled,
  direction,
  searchParams,
}: {
  page: number;
  disabled: boolean;
  direction: "prev" | "next";
  searchParams: Record<string, string | string[] | undefined>;
}) {
  const label = direction === "prev" ? "Previous" : "Next";
  const content =
    direction === "prev" ? (
      <>
        <CaretLeft size={14} /> {label}
      </>
    ) : (
      <>
        {label} <CaretRight size={14} />
      </>
    );

  if (disabled) {
    return <span className="inline-flex items-center gap-1.5 text-ink-faint">{content}</span>;
  }

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (typeof value === "string") params.set(key, value);
  }
  params.set("page", String(page));

  return (
    <Link
      href={`?${params.toString()}`}
      className="inline-flex items-center gap-1.5 font-medium text-accent hover:underline"
    >
      {content}
    </Link>
  );
}
