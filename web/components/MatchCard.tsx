import Link from "next/link";
import {
  ArrowSquareOut,
  Briefcase,
  CalendarBlank,
  Money,
  MapPin,
  Sparkle,
  UserCircle,
  Users,
} from "@phosphor-icons/react/dist/ssr";
import type { Match } from "@/lib/types";
import { CompanyLogo } from "@/components/CompanyLogo";
import { RatingChip } from "@/components/RatingChip";
import { ScoreMeter } from "@/components/ScoreMeter";
import { StateActions } from "@/components/StateActions";
import {
  formatAbsolute,
  formatExperience,
  formatRelativeDate,
  formatSalary,
  locationLabel,
  sourceMeta,
} from "@/lib/format";

function Fact({ icon: Icon, children, title }: { icon: typeof MapPin; children: React.ReactNode; title?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-ink-soft" title={title}>
      <Icon size={14} className="shrink-0 text-ink-faint" />
      {children}
    </span>
  );
}

export function MatchCard({ match, profileId }: { match: Match; profileId: number }) {
  const salary = formatSalary(match);
  const experience = formatExperience(match.min_exp_years, match.max_exp_years);
  const source = sourceMeta(match.source_name);
  const company = match.company_name ?? "Company undisclosed";

  return (
    <article className="group rounded-xl border border-border bg-bg-elevated p-4 transition-colors hover:border-border-strong sm:p-5">
      <div className="flex items-start gap-4">
        <CompanyLogo name={company} src={match.company_logo_url} />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {match.state === "new" && (
              <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent-soft-ink">
                New
              </span>
            )}
            <span
              className="rounded-full bg-bg-sunken px-2 py-0.5 text-[11px] font-medium capitalize text-ink-soft"
              title={source.direct ? "Employer's own ATS, so applying here reaches the hiring team" : `Ingested from ${source.label}`}
            >
              {source.label}
            </span>
            {source.direct && (
              <span className="text-[11px] font-medium text-score-strong">direct</span>
            )}
            <RatingChip rating={match.company_rating} count={match.company_rating_count} source="AmbitionBox" />
            {/* Instahyre publishes no job description at all, so say so before
                the click rather than after it. */}
            {!match.has_description && (
              <span
                className="text-[11px] text-ink-faint"
                title="This board's feed carries no description. The posting itself still has one."
              >
                no description
              </span>
            )}
          </div>

          <h3 className="mt-2 text-base font-semibold leading-snug text-ink">
            <Link
              href={`/jobs/${match.job_id}?profileId=${profileId}`}
              className="hover:text-accent hover:underline"
            >
              {match.title}
            </Link>
          </h3>

          <p className="mt-1 text-sm">
            {match.company_id ? (
              <Link href={`/companies/${match.company_id}`} className="text-ink-soft hover:text-accent hover:underline">
                {company}
              </Link>
            ) : (
              <span className="text-ink-soft">{company}</span>
            )}
          </p>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
            <Fact icon={MapPin}>{locationLabel(match)}</Fact>
            {experience && <Fact icon={Briefcase}>{experience}</Fact>}
            {salary && (
              <Fact icon={Money}>
                <span className="font-mono tabular-nums">{salary}</span>
              </Fact>
            )}
            {match.posted_date && (
              <Fact icon={CalendarBlank} title={`Posted ${formatAbsolute(match.posted_date)}`}>
                Posted {formatRelativeDate(match.posted_date)}
              </Fact>
            )}
            {match.poster_name && (
              <Fact icon={UserCircle} title={match.poster_title ? `${match.poster_name}, ${match.poster_title}` : undefined}>
                {match.poster_name}
              </Fact>
            )}
            {/* Competition, straight from the board. 800 applicants is a
                different decision from 4, and it is the one number a job seeker
                can never get anywhere else. */}
            {match.source_applicant_count != null && match.source_applicant_count > 0 && (
              <Fact icon={Users} title="Applicants the source board reports">
                <span className="font-mono tabular-nums">
                  {match.source_applicant_count.toLocaleString("en-IN")}
                </span>{" "}
                applied
              </Fact>
            )}
          </div>

          {match.explanation && (
            <p className="mt-3 flex gap-2 rounded-lg bg-bg-sunken px-3 py-2 text-sm text-ink-soft">
              <Sparkle size={14} className="mt-0.5 shrink-0 text-accent" weight="fill" />
              <span>{match.explanation}</span>
            </p>
          )}
        </div>

        <ScoreMeter score={match.score} />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3.5">
        <StateActions jobId={match.job_id} profileId={profileId} currentState={match.state} />
        <a
          href={match.apply_url}
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
