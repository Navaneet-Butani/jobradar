import { notFound } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowSquareOut,
  Briefcase,
  BuildingOffice,
  CalendarBlank,
  Clock,
  Money,
  Envelope,
  Globe,
  MapPin,
  Star,
  UserCircle,
  Users,
} from "@phosphor-icons/react/dist/ssr";
import { getJobDetail, getMatchForJob } from "@/lib/session";
import { formatAbsolute, formatRelativeDate, remoteScopeLabel, sourceMeta } from "@/lib/format";
import { renderJobHtml } from "@/lib/richtext";
import { CompanyLogo } from "@/components/CompanyLogo";
import { RatingChip } from "@/components/RatingChip";
import { ScoreBreakdown } from "@/components/ScoreBreakdown";
import { StateActions } from "@/components/StateActions";
import { ApplicationPacket } from "@/components/ApplicationPacket";

function formatDetailSalary(job: {
  salary: { min: number | null; max: number | null; currency: string; disclosed: boolean };
}) {
  const { min, max, currency, disclosed } = job.salary;
  if (!disclosed || (!min && !max)) return null;
  const fmt = (n: number) =>
    currency === "INR" ? `₹${(n / 100000).toFixed(1)}L` : `${currency} ${n.toLocaleString()}`;
  if (min && max && min !== max) return `${fmt(min)}-${fmt(max)}`;
  return fmt(max ?? min ?? 0);
}

function experienceRange(min: number | null, max: number | null, level: string | null) {
  if (min != null && max != null) return `${min}-${max} yrs`;
  if (min != null) return `${min}+ yrs`;
  if (max != null) return `up to ${max} yrs`;
  return level;
}

/** One label/value row in the provenance panel. */
function DetailRow({
  icon: Icon,
  label,
  value,
  title,
}: {
  icon: typeof MapPin;
  label: string;
  value: React.ReactNode;
  title?: string;
}) {
  return (
    <div className="flex items-start gap-2.5 py-2">
      <Icon size={15} className="mt-0.5 shrink-0 text-ink-faint" />
      <div className="min-w-0 flex-1">
        <dt className="text-xs text-ink-faint">{label}</dt>
        <dd className="truncate text-sm text-ink" title={title}>
          {value}
        </dd>
      </div>
    </div>
  );
}

export default async function JobDetailPage(props: PageProps<"/jobs/[id]">) {
  const { id } = await props.params;
  const sp = await props.searchParams;
  const jobId = Number(id);

  const job = Number.isFinite(jobId) ? await getJobDetail(jobId) : null;
  if (!job) notFound();

  const profileId = typeof sp.profileId === "string" ? Number(sp.profileId) : null;
  const match = profileId ? await getMatchForJob(jobId, profileId) : null;

  const salary = formatDetailSalary(job);
  const source = sourceMeta(job.source_name);
  const experience = experienceRange(job.min_exp_years, job.max_exp_years, job.experience_level);
  const location =
    job.location.city ?? job.location.raw ?? (job.location.is_remote ? "Remote" : job.location.country);
  const remoteScope = job.location.is_remote ? remoteScopeLabel(job.remote_scope) : null;

  return (
    <div className="flex flex-col gap-5">
      <Link
        href={profileId ? `/?profile_id=${profileId}` : "/search"}
        className="inline-flex w-fit items-center gap-1.5 text-sm text-ink-soft hover:text-accent"
      >
        <ArrowLeft size={14} />
        Back to {profileId ? "feed" : "search"}
      </Link>

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <div className="min-w-0 flex-1">
          <header className="border-b border-border pb-5">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="rounded-full bg-bg-sunken px-2 py-0.5 text-[11px] font-medium capitalize text-ink-soft"
                title={
                  source.direct
                    ? "Employer's own ATS, so this link reaches the hiring team directly"
                    : `Ingested from ${source.label}`
                }
              >
                {source.label}
              </span>
              {source.direct && <span className="text-[11px] font-medium text-score-strong">direct apply</span>}
              {job.employment_type && (
                <span className="rounded-full bg-bg-sunken px-2 py-0.5 text-[11px] font-medium text-ink-soft">
                  {job.employment_type}
                </span>
              )}
            </div>

            <div className="mt-2.5 flex items-start gap-3">
              <CompanyLogo name={job.company.name} src={job.company.logo_url} size="lg" />
              <div className="min-w-0">
                <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">{job.title}</h1>
                <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-soft">
                  {job.company.id ? (
                    <Link href={`/companies/${job.company.id}`} className="hover:text-accent hover:underline">
                      {job.company.name}
                    </Link>
                  ) : (
                    <span>{job.company.name}</span>
                  )}
                  {job.department && <span className="text-ink-faint">· {job.department}</span>}
                  <RatingChip
                    rating={job.company.rating}
                    count={job.company.rating_count}
                    source={job.company.rating_source}
                    href={job.company.rating_url}
                  />
                </p>
                {(job.poster_name || job.source_applicant_count != null) && (
                  <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-faint">
                    {job.poster_name && (
                      <span className="inline-flex items-center gap-1.5">
                        <UserCircle size={13} />
                        Posted by <span className="text-ink-soft">{job.poster_name}</span>
                        {job.poster_title && <span>({job.poster_title})</span>}
                      </span>
                    )}
                    {/* The board's own counters. Useful as a crowding signal and
                        nowhere else visible once you leave the source site. */}
                    {job.source_applicant_count != null && (
                      <span className="inline-flex items-center gap-1.5" title="Applicants reported by the source board">
                        <Users size={13} />
                        <span className="font-mono tabular-nums text-ink-soft">
                          {job.source_applicant_count.toLocaleString("en-IN")}
                        </span>
                        applied
                        {job.source_view_count != null && (
                          <>
                            {" · "}
                            <span className="font-mono tabular-nums text-ink-soft">
                              {job.source_view_count.toLocaleString("en-IN")}
                            </span>
                            views
                          </>
                        )}
                      </span>
                    )}
                  </p>
                )}
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              {match && <StateActions jobId={job.id} profileId={profileId as number} currentState={match.state} />}
              <a
                href={job.apply_url}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition-opacity hover:opacity-90"
              >
                Apply
                <ArrowSquareOut size={15} />
              </a>
            </div>
          </header>

          {match && (match.state === "interested" || match.state === "applied") && (
            <div className="mt-5">
              <ApplicationPacket jobId={job.id} profileId={profileId as number} />
            </div>
          )}

          {job.skills_required.length > 0 && (
            <section className="mt-6">
              <h2 className="font-display text-sm font-semibold text-ink">Skills asked for</h2>
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {job.skills_required.map((skill) => (
                  <li
                    key={skill}
                    className="rounded-md bg-bg-sunken px-2 py-1 text-xs text-ink-soft"
                  >
                    {skill}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {job.description ? (
            <section className="mt-6">
              <h2 className="font-display text-base font-semibold text-ink">Description</h2>
              <div className="job-html mt-2" dangerouslySetInnerHTML={{ __html: renderJobHtml(job.description) }} />
            </section>
          ) : (
            <section className="mt-6 rounded-lg border border-dashed border-border-strong px-4 py-5">
              <h2 className="font-display text-sm font-semibold text-ink">No description from this source</h2>
              <p className="mt-1.5 text-sm text-ink-faint">
                {job.source_name === "instahyre"
                  ? "Instahyre's feed carries the title, skills and employer only. The full text is on the posting itself."
                  : "This source's feed didn't include the description. The posting itself has it."}
              </p>
              {/* Whatever the source did give us beats an empty panel: the
                  company blurb is the only prose Instahyre ships. */}
              {job.company.description && (
                <p className="mt-3 max-w-[65ch] text-sm text-ink-soft">
                  <span className="font-medium text-ink">About {job.company.name}: </span>
                  {job.company.tagline ? `${job.company.tagline}. ` : ""}
                  {job.company.description}
                </p>
              )}
              <a
                href={job.source_url ?? job.apply_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-accent hover:underline"
              >
                Read it on {source.label}
                <ArrowSquareOut size={14} />
              </a>
            </section>
          )}

          {job.requirements && (
            <section className="mt-6">
              <h2 className="font-display text-base font-semibold text-ink">Requirements</h2>
              <div className="job-html mt-2" dangerouslySetInnerHTML={{ __html: renderJobHtml(job.requirements) }} />
            </section>
          )}

          {job.responsibilities && (
            <section className="mt-6">
              <h2 className="font-display text-base font-semibold text-ink">Responsibilities</h2>
              <div
                className="job-html mt-2"
                dangerouslySetInnerHTML={{ __html: renderJobHtml(job.responsibilities) }}
              />
            </section>
          )}

          {job.benefits.length > 0 && (
            <section className="mt-6">
              <h2 className="font-display text-base font-semibold text-ink">Benefits</h2>
              <ul className="job-html mt-2 list-disc pl-5">
                {job.benefits.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </section>
          )}

          {job.how_to_apply && (
            <section className="mt-6">
              <h2 className="font-display text-base font-semibold text-ink">How to apply</h2>
              <div className="job-html mt-2" dangerouslySetInnerHTML={{ __html: renderJobHtml(job.how_to_apply) }} />
            </section>
          )}
        </div>

        <aside className="w-full shrink-0 lg:w-72">
          {match && <ScoreBreakdown score={match.score} reasons={match.reasons} />}

          <section className="mt-4 rounded-xl border border-border bg-bg-elevated p-4">
            <h2 className="font-display text-sm font-semibold text-ink">Job details</h2>
            <dl className="mt-1 divide-y divide-border">
              <DetailRow icon={MapPin} label="Location" value={location} />
              {remoteScope && <DetailRow icon={Globe} label="Remote scope" value={remoteScope} />}
              {job.work_arrangement && (
                <DetailRow icon={Users} label="Arrangement" value={job.work_arrangement} />
              )}
              {experience && <DetailRow icon={Briefcase} label="Experience" value={experience} />}
              {salary && (
                <DetailRow
                  icon={Money}
                  label="Salary"
                  value={<span className="font-mono tabular-nums">{salary}</span>}
                />
              )}
              {job.posted_date && (
                <DetailRow
                  icon={CalendarBlank}
                  label="Posted"
                  title={formatAbsolute(job.posted_date)}
                  value={
                    <>
                      {formatRelativeDate(job.posted_date)}
                      <span className="ml-1.5 text-xs text-ink-faint">{formatAbsolute(job.posted_date)}</span>
                    </>
                  }
                />
              )}
              {job.first_seen_at && (
                <DetailRow
                  icon={Clock}
                  label="First seen by JobRadar"
                  title={formatAbsolute(job.first_seen_at)}
                  value={formatRelativeDate(job.first_seen_at)}
                />
              )}
              {job.application_deadline && (
                <DetailRow
                  icon={CalendarBlank}
                  label="Deadline"
                  value={formatAbsolute(job.application_deadline)}
                />
              )}
              {job.apply_email && (
                <DetailRow
                  icon={Envelope}
                  label="Application email"
                  value={
                    <a href={`mailto:${job.apply_email}`} className="text-accent hover:underline">
                      {job.apply_email}
                    </a>
                  }
                />
              )}
            </dl>
          </section>

          <section className="mt-4 rounded-xl border border-border bg-bg-elevated p-4">
            <h2 className="font-display text-sm font-semibold text-ink">Company</h2>
            <dl className="mt-1 divide-y divide-border">
              <DetailRow
                icon={BuildingOffice}
                label="Name"
                value={
                  job.company.id ? (
                    <Link href={`/companies/${job.company.id}`} className="text-accent hover:underline">
                      {job.company.name}
                    </Link>
                  ) : (
                    job.company.name
                  )
                }
              />
              {job.company.industry && (
                <DetailRow icon={Briefcase} label="Industry" value={job.company.industry} />
              )}
              {job.company.headquarters && (
                <DetailRow icon={MapPin} label="Headquarters" value={job.company.headquarters} />
              )}
              {(job.company.employee_range || job.company.employee_count) && (
                <DetailRow
                  icon={Users}
                  label="Headcount"
                  value={job.company.employee_range ?? job.company.employee_count?.toLocaleString("en-IN")}
                />
              )}
              {job.company.founded_year && (
                <DetailRow icon={CalendarBlank} label="Founded" value={job.company.founded_year} />
              )}
              {job.company.rating != null && (
                <DetailRow
                  icon={Star}
                  label={`Rating (${job.company.rating_source ?? "source"})`}
                  value={
                    <RatingChip
                      rating={job.company.rating}
                      count={job.company.rating_count}
                      source={job.company.rating_source}
                      href={job.company.rating_url}
                    />
                  }
                />
              )}
              {job.company.website && (
                <DetailRow
                  icon={Globe}
                  label="Website"
                  value={
                    <a
                      href={job.company.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent hover:underline"
                    >
                      {job.company.website.replace(/^https?:\/\//, "")}
                    </a>
                  }
                />
              )}
              {job.source_url && (
                <DetailRow
                  icon={ArrowSquareOut}
                  label="Original posting"
                  value={
                    <a
                      href={job.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent hover:underline"
                    >
                      View on {source.label}
                    </a>
                  }
                />
              )}
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
}
