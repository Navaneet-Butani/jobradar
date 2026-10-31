import Link from "next/link";
import { MagnifyingGlass } from "@phosphor-icons/react/dist/ssr";
import { searchJobs, getJobFacets, getMatchStates, getProfiles } from "@/lib/session";
import { JobResultCard } from "@/components/JobResultCard";
import { FacetSidebar } from "@/components/FacetSidebar";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader, Stat } from "@/components/shell/PageHeader";

export default async function SearchPage(props: PageProps<"/search">) {
  const sp = await props.searchParams;
  const q = typeof sp.q === "string" ? sp.q : "";
  const page = typeof sp.page === "string" ? Number(sp.page) : 1;

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (typeof sp.location === "string") params.set("location", sp.location);
  if (typeof sp.company === "string") params.set("company", sp.company);
  if (typeof sp.remote === "string") params.set("remote", sp.remote);
  if (typeof sp.posted_within === "string") params.set("posted_within", sp.posted_within);
  params.set("page", String(page));
  params.set("limit", "20");

  const facetParams = new URLSearchParams();
  if (q) facetParams.set("q", q);

  const [{ jobs, metadata }, facets, profiles] = await Promise.all([
    searchJobs(`?${params.toString()}`),
    getJobFacets(`?${facetParams.toString()}`),
    getProfiles(),
  ]);

  // Second round trip on purpose: it needs the ids the search just returned.
  const activeProfile = profiles.find((p) => String(p.id) === sp.profile_id) ?? profiles[0];
  const states = activeProfile
    ? await getMatchStates(activeProfile.id, jobs.map((j) => j.id))
    : {};

  const currentParams = new URLSearchParams();
  for (const [key, value] of Object.entries(sp)) {
    if (typeof value === "string") currentParams.set(key, value);
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Search"
        description="Every ingested job, unscored. Use the feed for what actually fits you."
        meta={<Stat label={`job${metadata.total === 1 ? "" : "s"} indexed`} value={metadata.total.toLocaleString("en-IN")} />}
      />

      <div className="flex flex-col gap-6 sm:flex-row">
        <FacetSidebar facets={facets} searchParams={currentParams} query={q} />

        <div className="min-w-0 flex-1">
          {jobs.length === 0 ? (
            <EmptyState
              icon={MagnifyingGlass}
              title="No jobs match this search"
              description={q ? `Nothing found for “${q}”. Try a broader term or clear a filter.` : "Try a broader term or clear a filter."}
              action={
                <Link href="/search" className="text-sm font-semibold text-accent hover:underline">
                  Clear search
                </Link>
              }
            />
          ) : (
            <div className="flex flex-col gap-3">
              {jobs.map((job) => (
                <JobResultCard
                  key={job.id}
                  job={job}
                  profileId={activeProfile?.id}
                  matchState={states[job.id]}
                />
              ))}
            </div>
          )}

          {metadata.pages > 1 && (
            <nav className="mt-5 flex items-center justify-between border-t border-border pt-4 text-sm" aria-label="Pagination">
              <PageLink page={page - 1} disabled={page <= 1} label="Previous" searchParams={sp} />
              <span className="text-ink-faint">
                Page <span className="font-mono font-semibold tabular-nums text-ink">{page}</span> of{" "}
                <span className="font-mono tabular-nums">{metadata.pages}</span>
              </span>
              <PageLink page={page + 1} disabled={page >= metadata.pages} label="Next" searchParams={sp} />
            </nav>
          )}
        </div>
      </div>
    </div>
  );
}

function PageLink({
  page,
  disabled,
  label,
  searchParams,
}: {
  page: number;
  disabled: boolean;
  label: string;
  searchParams: Record<string, string | string[] | undefined>;
}) {
  if (disabled) return <span className="text-ink-faint">{label}</span>;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (typeof value === "string") params.set(key, value);
  }
  params.set("page", String(page));
  return (
    <Link href={`?${params.toString()}`} className="font-medium text-accent hover:underline">
      {label}
    </Link>
  );
}
