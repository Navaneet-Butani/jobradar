import Link from "next/link";
import {
  ArrowSquareOut,
  Briefcase,
  CalendarBlank,
  Money,
  MapPin,
} from "@phosphor-icons/react/dist/ssr";
import type { JobSearchResult, MatchState } from "@/lib/types";
import { CompanyLogo } from "@/components/CompanyLogo";
import { RatingChip } from "@/components/RatingChip";
import { StateActions } from "@/components/StateActions";
import { formatAbsolute, formatRelativeDate } from "@/lib/format";

function formatResultSalary(job: JobSearchResult): string | null {
  const { min, max, currency, disclosed } = job.salary;
  if (!disclosed || (!min && !max)) return null;
  const fmt = (n: number) =>
    currency === "INR" ? `₹${(n / 100000).toFixed(1)}L` : `${currency} ${n.toLocaleString()}`;
  if (min && max && min !== max) return `${fmt(min)}-${fmt(max)}`;
  return fmt(max ?? min ?? 0);
}

function Fact({ icon: Icon, children, title }: { icon: typeof MapPin; children: React.ReactNode; title?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-ink-soft" title={title}>
      <Icon size={14} className="shrink-0 text-ink-faint" />
      {children}
    </span>
  );
}

/** Feed states worth calling out on a search hit. "new" and "seen" are not:
 *  every scored job is one of those, so a badge for them would mark almost
 *  everything and mean nothing. */
const STATE_BADGES: Partial<Record<MatchState, { label: string; className: string }>> = {
  interested: { label: "Interested", className: "bg-accent-soft text-accent-soft-ink" },
  applied: { label: "Applied", className: "bg-score-strong-bg text-score-strong" },
  dismissed: { label: "Dismissed", className: "bg-bg-sunken text-ink-faint" },
};

export function JobResultCard({
  job,
  profileId,
  matchState,
}: {
  job: JobSearchResult;
  /** Absent only when the user has no job profile yet. */
  profileId?: number;
  matchState?: MatchState;
}) {
  const badge = matchState ? STATE_BADGES[matchState] : undefined;
  const salary = formatResultSalary(job);
  const location =
    job.location.city ?? job.location.raw ?? (job.location.is_remote ? "Remote" : job.location.country);

  return (
    <article className="rounded-xl border border-border bg-bg-elevated p-4 transition-colors hover:border-border-strong sm:p-5">
      <div className="flex items-start gap-4">
        <CompanyLogo name={job.company.name} src={job.company.logo_url} />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {badge && (
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${badge.className}`}>
                {badge.label}
              </span>
            )}
            {job.location.is_remote && (
              <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent-soft-ink">
                Remote
              </span>
            )}
            {job.employment_type && (
              <span className="rounded-full bg-bg-sunken px-2 py-0.5 text-[11px] font-medium text-ink-soft">
                {job.employment_type}
              </span>
            )}
            <RatingChip
              rating={job.company.rating}
              count={job.company.rating_count}
              source={job.company.rating_source}
              href={job.company.rating_url}
            />
          </div>

          <h3 className="mt-2 text-base font-semibold leading-snug text-ink">
            <Link href={`/jobs/${job.id}`} className="hover:text-accent hover:underline">
              {job.title}
            </Link>
          </h3>

          <p className="mt-1 text-sm">
            {job.company.id ? (
              <Link href={`/companies/${job.company.id}`} className="text-ink-soft hover:text-accent hover:underline">
                {job.company.name}
              </Link>
            ) : (
              <span className="text-ink-soft">{job.company.name}</span>
            )}
          </p>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
            <Fact icon={MapPin}>{location}</Fact>
            {job.experience_level && <Fact icon={Briefcase}>{job.experience_level}</Fact>}
            {salary && (
              <Fact icon={Money}>
                <span className="font-mono tabular-nums">{salary}</span>
              </Fact>
            )}
            {job.posted_date && (
              <Fact icon={CalendarBlank} title={`Posted ${formatAbsolute(job.posted_date)}`}>
                Posted {formatRelativeDate(job.posted_date)}
              </Fact>
            )}
          </div>

          {job.skills_required.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {job.skills_required.slice(0, 6).map((skill) => (
                <li key={skill} className="rounded-md bg-bg-sunken px-2 py-0.5 text-xs text-ink-soft">
                  {skill}
                </li>
              ))}
              {job.skills_required.length > 6 && (
                <li className="px-1 py-0.5 text-xs text-ink-faint">+{job.skills_required.length - 6} more</li>
              )}
            </ul>
          )}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3.5">
        {profileId ? (
          <StateActions jobId={job.id} profileId={profileId} currentState={matchState ?? "new"} />
        ) : (
          <Link href={`/jobs/${job.id}`} className="text-sm font-medium text-ink-soft hover:text-accent">
            View details
          </Link>
        )}
        <a
          href={job.apply_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent hover:underline"
        >
          Apply
          <ArrowSquareOut size={14} />
        </a>
      </div>
    </article>
  );
}
