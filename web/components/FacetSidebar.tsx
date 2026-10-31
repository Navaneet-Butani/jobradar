import Link from "next/link";
import { MagnifyingGlass } from "@phosphor-icons/react/dist/ssr";
import type { SearchFacets } from "@/lib/types";

type FacetLinkParam = { key: string; value: string };

/** Maps a facet bucket label to the search query param + value it should toggle. */
function paramFor(category: keyof SearchFacets, label: string): FacetLinkParam | null {
  switch (category) {
    case "locations":
      return { key: "location", value: label };
    case "companies":
      return { key: "company", value: label };
    case "remote_work":
      return { key: "remote", value: label === "Remote" ? "true" : "false" };
    case "posted_dates": {
      const days: Record<string, string> = {
        Today: "1",
        "Last 3 days": "3",
        "Last week": "7",
        "Last 2 weeks": "14",
        "Last month": "30",
      };
      return days[label] ? { key: "posted_within", value: days[label] } : null;
    }
    default:
      return null;
  }
}

const SECTION_TITLES: Record<keyof SearchFacets, string> = {
  locations: "Location",
  remote_work: "Work type",
  companies: "Company",
  salary_ranges: "Salary",
  posted_dates: "Posted",
  employment_types: "Employment type",
  experience_levels: "Experience",
};

function buildHref(current: URLSearchParams, param: FacetLinkParam | null, active: boolean): string | null {
  if (!param) return null;
  const next = new URLSearchParams(current.toString());
  if (active) {
    next.delete(param.key);
  } else {
    next.set(param.key, param.value);
  }
  next.delete("page");
  return `/search?${next.toString()}`;
}

const FILTER_KEYS = ["location", "company", "remote", "posted_within"];

/**
 * Search box and facets in one sticky rail.
 *
 * Both belong together: refining a search is a loop of "type, scan, narrow,
 * scan again", and having the query field scroll off the top meant jumping
 * back up for every edit. `self-start` matters — a flex child stretches to the
 * row's height by default, which silently makes `sticky` do nothing.
 */
export function FacetSidebar({
  facets,
  searchParams,
  query,
}: {
  facets: SearchFacets;
  searchParams: URLSearchParams;
  query: string;
}) {
  const sections = (Object.keys(SECTION_TITLES) as (keyof SearchFacets)[]).filter(
    (key) => Object.keys(facets[key] ?? {}).length > 0
  );

  const activeCount = FILTER_KEYS.filter((key) => searchParams.get(key)).length;
  const cleared = new URLSearchParams(searchParams.toString());
  FILTER_KEYS.forEach((key) => cleared.delete(key));
  cleared.delete("page");

  return (
    <aside className="w-full shrink-0 self-start sm:sticky sm:top-4 sm:max-h-[calc(100dvh-2rem)] sm:w-60 sm:overflow-y-auto sm:pr-1 lg:w-64">
      <div className="flex flex-col gap-5">
        <form method="GET" action="/search" className="flex flex-col gap-2">
          <div className="relative">
            <MagnifyingGlass
              size={16}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint"
            />
            <input
              type="search"
              name="q"
              aria-label="Search jobs by title, skill or keyword"
              defaultValue={query}
              placeholder="Title, skill, or keyword…"
              className="w-full rounded-lg border border-border-strong bg-bg-elevated py-2 pl-9 pr-3 text-sm outline-none transition-colors focus:border-accent"
            />
          </div>
          {/* Facet choices live in the URL; without these the form would
              submit a bare ?q= and silently throw the filters away. */}
          {FILTER_KEYS.filter((key) => searchParams.get(key)).map((key) => (
            <input key={key} type="hidden" name={key} value={searchParams.get(key) ?? ""} />
          ))}
          <button
            type="submit"
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition-opacity hover:opacity-90"
          >
            Search
          </button>
        </form>

        {activeCount > 0 && (
          <div className="flex items-center justify-between gap-2 rounded-lg bg-accent-soft px-3 py-2">
            <span className="text-xs font-medium text-accent-soft-ink">
              {activeCount} filter{activeCount === 1 ? "" : "s"} on
            </span>
            <Link
              href={`/search?${cleared.toString()}`}
              className="text-xs font-semibold text-accent-soft-ink underline underline-offset-2"
            >
              Clear
            </Link>
          </div>
        )}

        {sections.map((section) => {
          const entries = Object.entries(facets[section]).sort((a, b) => b[1] - a[1]).slice(0, 8);
          return (
            <div key={section}>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">
                {SECTION_TITLES[section]}
              </h3>
              <ul className="flex flex-col gap-1">
                {entries.map(([label, count]) => {
                  const param = paramFor(section, label);
                  const active = param ? searchParams.get(param.key) === param.value : false;
                  const href = buildHref(searchParams, param, active);
                  const content = (
                    <span className="flex items-center justify-between gap-2 text-sm">
                      <span className="truncate">{label}</span>
                      <span className="font-mono text-xs tabular-nums text-ink-faint">{count}</span>
                    </span>
                  );
                  return (
                    <li key={label}>
                      {href ? (
                        <Link
                          href={href}
                          aria-pressed={active}
                          className={`block rounded-md px-2 py-1 transition-colors ${
                            active
                              ? "bg-accent-soft font-medium text-accent-soft-ink"
                              : "text-ink-soft hover:bg-bg-sunken hover:text-ink"
                          }`}
                        >
                          {content}
                        </Link>
                      ) : (
                        <div className="px-2 py-1 text-ink-soft">{content}</div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
