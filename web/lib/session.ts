import { cache } from "react";
import { redirect } from "next/navigation";
import { authedFetch } from "@/lib/backend";
import type {
  ApiEnvelope,
  Application,
  ApplicationListResponse,
  Company,
  DueTodayResponse,
  EmailAccount,
  JobDetail,
  JobProfile,
  JobSearchResult,
  Match,
  MatchListResponse,
  MatchStats,
  OutreachCampaign,
  OutreachContact,
  Resume,
  SearchFacets,
  RoleCategories,
  MatchState,
  Member,
  SearchMetadata,
  TemplateDefaults,
  User,
} from "@/lib/types";

async function get<T>(path: string): Promise<T> {
  const { res } = await authedFetch(path);
  if (res.status === 401) redirect("/login");
  const body = (await res.json()) as ApiEnvelope<T>;
  if (!res.ok || !body.status || body.data === null) {
    throw new Error(body.error_message ?? `Request to ${path} failed`);
  }
  return body.data;
}

/**
 * The jobs/* endpoints wrap their own {status,data,message} response model
 * inside APIResponse's own {status,data,message} envelope — double-nested,
 * unlike profiles/matches. Unwrap both layers here.
 */
async function getJobsEnvelope<T>(path: string, init: RequestInit = {}): Promise<{ data: T; metadata?: SearchMetadata }> {
  const { res } = await authedFetch(path, init);
  if (res.status === 401) redirect("/login");
  const body = await res.json();
  const inner = body?.data;
  if (!res.ok || !body.status || !inner || inner.status === false) {
    throw new Error(body?.error_message ?? inner?.message ?? `Request to ${path} failed`);
  }
  return { data: inner.data as T, metadata: inner.metadata };
}

/**
 * The four fetchers below are wrapped in React's `cache()` because the layout
 * and the page it wraps both need them, and each call is a real round trip to
 * a 512 MB Render instance with a five-connection pool. Rendering `/` fanned
 * out to seven backend requests -- /auth/me, /profiles and /matches/stats twice
 * over -- which is how a normal page load exhausted the pool and returned 500.
 *
 * `cache()` is per-render, not a cache layer: nothing survives the request, so
 * there is nothing to invalidate and no staleness to reason about.
 */
export const getCurrentUser = cache((): Promise<User> => get<User>("/auth/me"));

export const getProfiles = cache((): Promise<JobProfile[]> => get<JobProfile[]>("/profiles"));

export function getMatches(query: string): Promise<MatchListResponse> {
  return get<MatchListResponse>(`/matches${query}`);
}

export const getMatchStats = cache(
  (profileId: number): Promise<MatchStats> =>
    get<MatchStats>(`/matches/stats?profile_id=${profileId}`)
);

export async function getMatchForJob(jobId: number, profileId: number): Promise<Match | null> {
  const { res } = await authedFetch(`/matches/${jobId}?profile_id=${profileId}`);
  if (res.status === 401) redirect("/login");
  if (res.status === 404) return null;
  const body = (await res.json()) as ApiEnvelope<Match>;
  if (!res.ok || !body.status || body.data === null) return null;
  return body.data;
}

export async function searchJobs(query: string): Promise<{ jobs: JobSearchResult[]; metadata: SearchMetadata }> {
  const { data, metadata } = await getJobsEnvelope<JobSearchResult[]>(`/jobs/search${query}`);
  return { jobs: data, metadata: metadata as SearchMetadata };
}

export async function getJobFacets(query: string): Promise<SearchFacets> {
  const { data } = await getJobsEnvelope<SearchFacets>(`/jobs/facets${query}`, { method: "POST" });
  return data;
}

export async function getJobDetail(jobId: number): Promise<JobDetail | null> {
  try {
    const { data } = await getJobsEnvelope<JobDetail>(`/jobs/${jobId}`);
    return data;
  } catch {
    return null;
  }
}

/** Null when the id doesn't exist, so the page can 404 rather than error. */
export async function getCompany(companyId: number): Promise<Company | null> {
  try {
    return await get<Company>(`/companies/${companyId}`);
  } catch {
    return null;
  }
}

export function getApplications(query: string = ""): Promise<ApplicationListResponse> {
  return get<ApplicationListResponse>(`/applications${query}`);
}

export const getDueToday = cache((): Promise<DueTodayResponse> =>
  get<DueTodayResponse>("/applications/due-today")
);

/** Null when no sending account is configured yet — the backend 404s in that case. */
export async function getEmailAccount(): Promise<EmailAccount | null> {
  const { res } = await authedFetch("/outreach/email-account");
  if (res.status === 401) redirect("/login");
  if (res.status === 404) return null;
  const body = (await res.json()) as ApiEnvelope<EmailAccount>;
  if (!res.ok || !body.status || body.data === null) return null;
  return body.data;
}

export function getOutreachContacts(): Promise<{ contacts: OutreachContact[]; total_count: number }> {
  return get<{ contacts: OutreachContact[]; total_count: number }>("/outreach/contacts");
}

export function getCampaigns(): Promise<{ campaigns: OutreachCampaign[]; total_count: number }> {
  return get<{ campaigns: OutreachCampaign[]; total_count: number }>("/outreach/campaigns");
}

/** Null when the campaign doesn't exist or isn't this user's. */
export async function getCampaign(campaignId: number): Promise<OutreachCampaign | null> {
  try {
    return await get<OutreachCampaign>(`/outreach/campaigns/${campaignId}`);
  } catch {
    return null;
  }
}

export function getTemplateDefaults(): Promise<TemplateDefaults> {
  return get<TemplateDefaults>("/outreach/template-defaults");
}

/** Null when the user hasn't uploaded a resume yet — the backend 404s in that case. */
export async function getResume(): Promise<Resume | null> {
  const { res } = await authedFetch("/resume");
  if (res.status === 401) redirect("/login");
  if (res.status === 404) return null;
  const body = (await res.json()) as ApiEnvelope<Resume>;
  if (!res.ok || !body.status || body.data === null) return null;
  return body.data;
}

export type {
  User,
  JobProfile,
  Match,
  MatchListResponse,
  MatchStats,
  JobSearchResult,
  JobDetail,
  SearchFacets,
  SearchMetadata,
  Application,
  ApplicationListResponse,
  DueTodayResponse,
  Resume,
  EmailAccount,
  OutreachContact,
  OutreachCampaign,
  TemplateDefaults,
};

/** Everyone on the deployment. Admin only — 403 for anyone else. */
export function getMembers(): Promise<{ members: Member[] }> {
  return get<{ members: Member[] }>("/invites/members");
}

/**
 * Feed state for specific job ids. Search runs against the whole corpus and
 * has no idea what you already dismissed or applied to; this fills that in for
 * the page being rendered. Never worth failing a search over, so it degrades
 * to "no states known".
 */
export async function getMatchStates(
  profileId: number,
  jobIds: number[]
): Promise<Record<number, MatchState>> {
  if (jobIds.length === 0) return {};
  try {
    const data = await get<{ states: Record<number, MatchState> }>(
      `/matches/states?profile_id=${profileId}&job_ids=${jobIds.join(",")}`
    );
    return data.states ?? {};
  } catch {
    return {};
  }
}

/** Which role categories the scrapers collect, plus whether this user may change them. */
export async function getRoleCategories(): Promise<RoleCategories> {
  return get<RoleCategories>("/scraping/roles");
}
