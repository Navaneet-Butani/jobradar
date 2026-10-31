export function formatSalary(match: {
  salary_disclosed: boolean;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  salary_period: string;
}): string | null {
  if (!match.salary_disclosed || (!match.salary_min && !match.salary_max)) return null;

  const fmt = (n: number) => {
    if (match.salary_currency === "INR") {
      return n >= 100000 ? `₹${(n / 100000).toFixed(n % 100000 === 0 ? 0 : 1)}L` : `₹${n.toLocaleString("en-IN")}`;
    }
    return `${match.salary_currency} ${n.toLocaleString()}`;
  };

  const suffix = match.salary_period === "year" ? "/yr" : match.salary_period === "month" ? "/mo" : "/hr";
  if (match.salary_min && match.salary_max && match.salary_min !== match.salary_max) {
    return `${fmt(match.salary_min)}-${fmt(match.salary_max)}${suffix}`;
  }
  return `${fmt(match.salary_max ?? match.salary_min ?? 0)}${suffix}`;
}

export function formatExperience(min: number | null, max: number | null): string | null {
  if (min == null && max == null) return null;
  if (min != null && max != null) return `${min}-${max} yrs`;
  if (min != null) return `${min}+ yrs`;
  return `up to ${max} yrs`;
}

export function formatRelativeDate(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const days = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (days <= 0) {
    const hours = Math.floor((Date.now() - date.getTime()) / 3_600_000);
    if (hours < 1) return "just now";
    return hours === 1 ? "1h ago" : `${hours}h ago`;
  }
  if (days === 1) return "yesterday";
  if (days < 14) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  return `${weeks}w ago`;
}

/** Full timestamp for a `title` attribute, so a relative label stays checkable. */
export function formatAbsolute(iso: string | null): string {
  if (!iso) return "Unknown";
  return new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

const REMOTE_SCOPE_LABELS: Record<string, string> = {
  india_only: "India-remote",
  global: "Remote, worldwide",
  us_only: "US-only remote",
  eu_only: "EU-only remote",
  uk_only: "UK-only remote",
  canada_only: "Canada-only remote",
};

export function remoteScopeLabel(scope: string | null): string | null {
  if (!scope) return null;
  return REMOTE_SCOPE_LABELS[scope] ?? scope.replace(/_/g, " ");
}

/** Source label plus whether applying there reaches the employer directly. */
export function sourceMeta(source: string | null): { label: string; direct: boolean } {
  const NAMES: Record<string, string> = {
    ats: "ATS", jobspy: "Indeed", linkedin: "LinkedIn", remoteok: "RemoteOK",
    instahyre: "Instahyre", hirist: "Hirist", himalayas: "Himalayas", remotive: "Remotive", arbeitnow: "Arbeitnow",
  };
  const label = NAMES[source ?? ""] ?? (source ?? "unknown").replace(/_/g, " ");
  return { label, direct: source === "ats" };
}

export function formatDueDate(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const days = Math.floor((date.getTime() - Date.now()) / 86_400_000);
  if (days < 0) return `${Math.abs(days)}d overdue`;
  if (days === 0) return "due today";
  if (days === 1) return "due tomorrow";
  return `due in ${days}d`;
}

export function locationLabel(match: { city: string | null; is_remote: boolean; remote_scope: string | null }): string {
  if (match.city && match.is_remote) return `${match.city} · Remote`;
  if (match.city) return match.city;
  if (match.is_remote) return match.remote_scope === "global" ? "Remote (global)" : "Remote (India)";
  return "Location unspecified";
}
