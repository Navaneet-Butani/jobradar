import { notFound } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowSquareOut,
  Briefcase,
  CalendarBlank,
  Envelope,
  Globe,
  MapPin,
  Users,
} from "@phosphor-icons/react/dist/ssr";
import type { CompanyJob } from "@/lib/types";
import { getCompany } from "@/lib/session";
import { formatAbsolute, formatExperience, formatRelativeDate, sourceMeta } from "@/lib/format";
import { renderJobHtml } from "@/lib/richtext";
import { CompanyLogo } from "@/components/CompanyLogo";
import { RatingChip } from "@/components/RatingChip";
import { EmptyState } from "@/components/EmptyState";

function jobSalary(job: CompanyJob): string | null {
  if (!job.salary_disclosed || (!job.salary_min && !job.salary_max)) return null;
  const fmt = (n: number) =>
    job.salary_currency === "INR"
      ? `₹${(n / 100000).toFixed(1)}L`
      : `${job.salary_currency} ${n.toLocaleString()}`;
  if (job.salary_min && job.salary_max && job.salary_min !== job.salary_max) {
    return `${fmt(job.salary_min)}-${fmt(job.salary_max)}`;
  }
  return fmt(job.salary_max ?? job.salary_min ?? 0);
}

/** One label/value pair in the facts strip under the company name. */
function Fact({ icon: Icon, children }: { icon: typeof MapPin; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-ink-soft">
      <Icon size={14} className="shrink-0 text-ink-faint" />
      {children}
    </span>
  );
}

export default async function CompanyPage(props: PageProps<"/companies/[id]">) {
  const { id } = await props.params;
  const companyId = Number(id);
  const company = Number.isFinite(companyId) ? await getCompany(companyId) : null;
  if (!company) notFound();

  const headcount = company.employee_range ?? company.employee_count?.toLocaleString("en-IN");

  return (
    <div className="flex flex-col gap-5">
      <Link
        href="/search"
        className="inline-flex w-fit items-center gap-1.5 text-sm text-ink-soft hover:text-accent"
      >
        <ArrowLeft size={14} />
        Back to search
      </Link>

      <header className="flex flex-wrap items-start gap-4 border-b border-border pb-5">
        <CompanyLogo name={company.name} src={company.logo_url} size="lg" />

        <div className="min-w-0 flex-1">
          <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">{company.name}</h1>
          {company.tagline && <p className="mt-1 text-sm text-ink-soft">{company.tagline}</p>}

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            {company.industry && <Fact icon={Briefcase}>{company.industry}</Fact>}
            {company.headquarters && <Fact icon={MapPin}>{company.headquarters}</Fact>}
            {headcount && <Fact icon={Users}>{headcount} employees</Fact>}
            {company.founded_year && <Fact icon={CalendarBlank}>Founded {company.founded_year}</Fact>}
            <RatingChip
              rating={company.rating}
              count={company.rating_count}
              source={company.rating_source}
              href={company.rating_url}
            />
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
            {company.website && (
              <a
                href={company.website}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 font-medium text-accent hover:underline"
              >
                <Globe size={14} />
                {company.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}
              </a>
            )}
            {company.career_page_url && (
              <a
                href={company.career_page_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 font-medium text-accent hover:underline"
              >
                <ArrowSquareOut size={14} />
                Careers page
              </a>
            )}
            {company.contact_email && (
              <a
                href={`mailto:${company.contact_email}`}
                className="inline-flex items-center gap-1.5 font-medium text-accent hover:underline"
              >
                <Envelope size={14} />
                {company.contact_email}
              </a>
            )}
          </div>

          {/* The website is inferred from the posting recruiter's email domain,
              which is the employer for a direct post and the agency for an
              agency post. Say so rather than presenting a guess as a fact. */}
          {company.website && (
            <p className="mt-2 text-xs text-ink-faint">
              Website inferred from the address that posted these jobs, so on agency postings it may be the
              agency&apos;s.
            </p>
          )}
        </div>
      </header>

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-base font-semibold text-ink">
              {company.active_jobs.toLocaleString("en-IN")} open{" "}
              {company.active_jobs === 1 ? "role" : "roles"}
            </h2>
            {company.jobs.length < company.active_jobs && (
              <span className="text-xs text-ink-faint">showing the {company.jobs.length} most recent</span>
            )}
          </div>

          {company.jobs.length === 0 ? (
            <div className="mt-3">
              <EmptyState
                icon={Briefcase}
                title="Nothing open right now"
                description="Every posting we had from this company has expired or been filled."
              />
            </div>
          ) : (
            <ul className="mt-3 flex flex-col gap-2">
              {company.jobs.map((job) => {
                const salary = jobSalary(job);
                const experience = formatExperience(job.min_exp_years, job.max_exp_years);
                const source = sourceMeta(job.source_name);
                const location = job.city ?? (job.is_remote ? "Remote" : "Location unspecified");

                return (
                  <li
                    key={job.id}
                    className="rounded-lg border border-border bg-bg-elevated p-3 transition-colors hover:border-border-strong"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <Link
                          href={`/jobs/${job.id}`}
                          className="text-sm font-semibold text-ink hover:text-accent hover:underline"
                        >
                          {job.title}
                        </Link>
                        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-faint">
                          <span>{location}</span>
                          {experience && <span>{experience}</span>}
                          {salary && <span className="font-mono tabular-nums">{salary}</span>}
                          {job.source_applicant_count != null && job.source_applicant_count > 0 && (
                            <span title="Applicants the source board reports">
                              <span className="font-mono tabular-nums">
                                {job.source_applicant_count.toLocaleString("en-IN")}
                              </span>{" "}
                              applied
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1 text-xs text-ink-faint">
                        <span className="capitalize">{source.label}</span>
                        {job.posted_date && (
                          <span title={formatAbsolute(job.posted_date)}>
                            {formatRelativeDate(job.posted_date)}
                          </span>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <aside className="w-full shrink-0 lg:w-72">
          {company.description && (
            <section className="rounded-xl border border-border bg-bg-elevated p-4">
              <h2 className="font-display text-sm font-semibold text-ink">About</h2>
              <div
                className="job-html mt-2 text-sm"
                dangerouslySetInnerHTML={{ __html: renderJobHtml(company.description) }}
              />
            </section>
          )}

          <section className="mt-4 rounded-xl border border-border bg-bg-elevated p-4">
            <h2 className="font-display text-sm font-semibold text-ink">Where these came from</h2>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {company.sources.map((name) => (
                <li key={name} className="rounded-md bg-bg-sunken px-2 py-1 text-xs capitalize text-ink-soft">
                  {sourceMeta(name).label}
                </li>
              ))}
            </ul>
            {company.ats_type && (
              <p className="mt-3 text-xs text-ink-faint">
                Runs hiring on <span className="capitalize text-ink-soft">{company.ats_type}</span>, so applying
                through its own careers page reaches the hiring team directly.
              </p>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
