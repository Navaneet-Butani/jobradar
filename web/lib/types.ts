export type User = {
  id: number;
  uuid: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  is_active: boolean;
  email_verified: boolean;
  is_admin: boolean;
  last_login_at: string | null;
  created_at: string;
  profile_picture_url: string | null;
};

/** One account on the deployment — accepted, or an invite nobody has claimed. */
export type Member = {
  id: number;
  email: string;
  first_name: string | null;
  last_name: string | null;
  is_active: boolean;
  is_admin: boolean;
  is_self: boolean;
  pending: boolean;
  /** Present only while pending — the link to hand over. */
  invite_url: string | null;
  invite_expires_at: string | null;
  invite_expired: boolean;
  last_login_at: string | null;
  created_at: string;
};

export type InviteResult = {
  member: Member;
  emailed: boolean;
  email_error: string | null;
};

export type InvitePreview = {
  email: string;
  first_name: string | null;
  last_name: string | null;
  invited_by: string | null;
};

export type JobProfile = {
  id: number;
  uuid: string;
  name: string;
  years_exp: number;
  seniority_floor: string | null;
  seniority_ceiling: string | null;
  must_have_skills: string[];
  nice_to_have_skills: string[];
  target_titles: string[];
  cities: string[];
  metro_cities: string[];
  accepts_remote: boolean;
  remote_only: boolean;
  remote_scope: string;
  min_salary_inr: number | null;
  exclude_companies: string[];
  exclude_keywords: string[];
  include_staffing: boolean;
  domain_keywords: string[];
  no_cs_degree: boolean;
  notify_webhook_url: string | null;
  notice_period_days: number | null;
  current_ctc_inr: number | null;
  expected_ctc_inr: number | null;
  willing_to_relocate: boolean;
  is_active: boolean;
};

export type Resume = {
  id: number;
  filename: string;
  content_type: string | null;
  char_count: number;
  content_text: string;
  file_size: number | null;
  created_at: string;
  updated_at: string;
};

export type EmailAccount = {
  id: number;
  from_name: string;
  from_email: string;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  daily_send_cap: number;
  send_interval_seconds: number;
  signature: string | null;
  is_verified: boolean;
  last_verified_at: string | null;
  last_synced_at: string | null;
  last_sync_error: string | null;
  sent_today: number;
  remaining_today: number;
};

export type SyncResult = {
  scanned: number;
  replies: number;
  bounces: number;
  followups_queued: number;
  skipped_replied: number;
  skipped_bounced: number;
  error: string | null;
};

export type OutreachContact = {
  id: number;
  email: string;
  contact_name: string | null;
  company_name: string | null;
  title: string | null;
  role_hint: string | null;
  notes: string | null;
  source: string;
  last_emailed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type OutreachMessage = {
  id: number;
  to_email: string;
  to_name: string | null;
  company_name: string | null;
  subject: string;
  body: string;
  attached_resume: boolean;
  status: "queued" | "sent" | "failed" | "skipped" | "cancelled";
  error: string | null;
  sent_at: string | null;
  step: number;
  replied_at: string | null;
  reply_from: string | null;
  reply_snippet: string | null;
  bounced_at: string | null;
  bounce_reason: string | null;
};

export type CampaignCounts = {
  queued: number;
  sent: number;
  failed: number;
  skipped: number;
  cancelled: number;
  total: number;
  replied: number;
  bounced: number;
  awaiting: number;
  followups: number;
};

export type OutreachCampaign = {
  id: number;
  name: string;
  subject_template: string;
  body_template: string;
  status: "draft" | "running" | "paused" | "completed";
  attach_resume: boolean;
  personalize_with_llm: boolean;
  followup_enabled: boolean;
  followup_after_days: number;
  followup_subject_template: string | null;
  followup_body_template: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  counts: CampaignCounts;
  messages: OutreachMessage[];
};

export type PreviewItem = {
  contact_id: number;
  to_email: string;
  to_name: string | null;
  company_name: string | null;
  subject: string;
  body: string;
  previously_emailed_at: string | null;
};

export type CampaignPreview = {
  items: PreviewItem[];
  total_selected: number;
  remaining_today: number;
  pacing_note: string;
  warnings: string[];
};

export type ApplicationEmailDraft = {
  subject: string;
  body: string;
  to_email: string | null;
  to_name: string | null;
  company_name: string | null;
  job_title: string;
  previously_emailed_at: string | null;
  remaining_today: number;
  warnings: string[];
};

export type TemplateDefaults = {
  subject_template: string;
  body_template: string;
  merge_fields: string[];
};

export type ApplicationPacket = {
  job_id: number;
  title: string;
  company_name: string | null;
  apply: {
    url: string;
    is_direct_ats: boolean;
    ats_label: string | null;
    note: string;
  };
  bullets: string[];
  cover_note: string | null;
  contact: {
    method: string | null;
    label: string;
    email: string | null;
    url: string | null;
    note: string;
  };
  answers: {
    notice_period: string | null;
    current_ctc: string | null;
    expected_ctc: string | null;
    willing_to_relocate: string;
    total_experience: string;
  };
  resume_filename: string | null;
  warnings: string[];
};

export type MatchState = "new" | "seen" | "interested" | "applied" | "dismissed";

export type Match = {
  job_id: number;
  title: string;
  company_name: string | null;
  company_id: number | null;
  company_logo_url: string | null;
  company_rating: number | null;
  company_rating_count: number | null;
  poster_name: string | null;
  poster_title: string | null;
  source_applicant_count: number | null;
  has_description: boolean;
  city: string | null;
  is_remote: boolean;
  remote_scope: string | null;
  min_exp_years: number | null;
  max_exp_years: number | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  salary_period: string;
  salary_disclosed: boolean;
  posted_date: string | null;
  apply_url: string;
  source_name: string | null;
  score: number;
  reasons: Record<string, number>;
  explanation: string | null;
  state: MatchState;
  surfaced_at: string;
};

export type MatchListResponse = {
  matches: Match[];
  total_count: number;
  page: number;
  limit: number;
};

export type MatchStats = {
  profile_id: number;
  by_state: Record<MatchState, number>;
  new_today: number;
  total: number;
};

export type ApplicationStatus = "applied" | "screening" | "interview" | "offer" | "rejected" | "ghosted";

export type TimelineEntry = {
  at: string;
  from_status: string;
  to_status: string;
  note: string | null;
};

export type Application = {
  id: number;
  job_id: number;
  job_profile_id: number | null;
  job_title: string;
  company_name: string;
  status: ApplicationStatus;
  applied_date: string;
  application_method: string;
  resume_version: string | null;
  cover_letter: boolean;
  referral_name: string | null;
  contact_name: string | null;
  contact_email: string | null;
  notes: string | null;
  next_step: string | null;
  next_step_date: string | null;
  timeline: TimelineEntry[];
  response_received: boolean;
  response_date: string | null;
  interview_scheduled: boolean;
  created_at: string;
  updated_at: string;
};

export type ApplicationListResponse = {
  applications: Application[];
  total_count: number;
  limit: number;
  offset: number;
};

export type DueTodayResponse = {
  applications: Application[];
  total_count: number;
};

/** Company fields carried alongside a job. Everything past name is optional:
 *  it comes from whatever the source board published about the employer. */
export type CompanySummary = {
  id: number | null;
  name: string;
  slug?: string | null;
  logo_url: string | null;
  website: string | null;
  industry?: string | null;
  headquarters?: string | null;
  ats_type?: string | null;
  tagline?: string | null;
  description?: string | null;
  founded_year?: number | null;
  employee_count?: number | null;
  employee_range?: string | null;
  rating?: number | null;
  rating_count?: number | null;
  rating_url?: string | null;
  rating_source?: string | null;
};

export type JobSearchResult = {
  id: number;
  uuid: string;
  title: string;
  company: CompanySummary;
  location: { raw: string | null; city: string | null; country: string; is_remote: boolean };
  employment_type: string | null;
  experience_level: string | null;
  salary: { min: number | null; max: number | null; currency: string; disclosed: boolean };
  posted_date: string | null;
  apply_url: string;
  skills_required: string[];
  skills_preferred: string[];
  quality_score: number;
  relevance_score: number | null;
  views_count: number;
  is_saved: boolean;
};

export type JobDetail = JobSearchResult & {
  description: string | null;
  requirements: string | null;
  responsibilities: string | null;
  benefits: string[];
  apply_email: string | null;
  application_deadline: string | null;
  clicks_count: number;
  applications_count: number;
  // Provenance — which board it came from and when we actually saw it.
  source_name: string | null;
  source_url: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  remote_scope: string | null;
  min_exp_years: number | null;
  max_exp_years: number | null;
  department: string | null;
  work_arrangement: string | null;
  how_to_apply: string | null;
  // Who posted it, and how crowded it already is. Only sources that publish
  // this have it — Hirist does, most do not.
  poster_name: string | null;
  poster_title: string | null;
  source_applicant_count: number | null;
  source_view_count: number | null;
};

export type CompanyJob = {
  id: number;
  title: string;
  city: string | null;
  is_remote: boolean;
  remote_scope: string | null;
  min_exp_years: number | null;
  max_exp_years: number | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  salary_disclosed: boolean;
  posted_date: string | null;
  first_seen_at: string | null;
  source_name: string | null;
  apply_url: string;
  poster_name: string | null;
  source_applicant_count: number | null;
};

export type Company = {
  id: number;
  name: string;
  slug: string;
  website: string | null;
  career_page_url: string | null;
  logo_url: string | null;
  tagline: string | null;
  description: string | null;
  industry: string | null;
  headquarters: string | null;
  founded_year: number | null;
  employee_count: number | null;
  employee_range: string | null;
  rating: number | null;
  rating_count: number | null;
  rating_url: string | null;
  rating_source: string | null;
  ats_type: string | null;
  contact_email: string | null;
  active_jobs: number;
  sources: string[];
  jobs: CompanyJob[];
};

export type SearchMetadata = {
  total: number;
  page: number;
  limit: number;
  pages: number;
  filters_applied: string[];
  has_next: boolean;
  has_previous: boolean;
};

export type SearchFacets = {
  employment_types: Record<string, number>;
  experience_levels: Record<string, number>;
  locations: Record<string, number>;
  companies: Record<string, number>;
  salary_ranges: Record<string, number>;
  remote_work: Record<string, number>;
  posted_dates: Record<string, number>;
};

export type ApiEnvelope<T> = {
  status: boolean;
  data: T | null;
  message: string | null;
  error: string | null;
  error_message: string | null;
};

export type RoleCategory = {
  key: string;
  label: string;
  enabled: boolean;
  examples: string[];
};

export type RoleCategories = {
  categories: RoleCategory[];
  /** False for non-admin accounts — the form renders read-only. */
  editable: boolean;
};

/** job_id -> feed state, for the handful of jobs a search page is rendering. */
export type MatchStateMap = Record<number, MatchState>;
