export type Mode = "demo" | "live";
export type Platform = "linkedin" | "newsletter";
export type Source = "manual" | "simulated";
export type Hook = "problem-first" | "outcome-first" | "question-first";
export interface BriefContract {
  min_words?: number | null;
  max_words?: number | null;
  max_characters?: number | null;
  min_bullets?: number | null;
  max_bullets?: number | null;
  max_hashtags?: number | null;
  required_sections?: string[];
  plain_text?: boolean;
}
export interface ContractChecks {
  passed: boolean | null;
  checks: {
    key: string;
    label: string;
    expected: unknown;
    actual: unknown;
    passed: boolean;
  }[];
  violations: string[];
  content_sha256?: string;
  scope?: string;
}
export interface BrandProfile {
  summary?: string;
  tone?: string[] | string;
  style?: string[] | string;
  vocabulary?: string[] | string;
  avoid?: string[] | string;
  evidence?: { trait: string; quote: string }[];
}
export interface Brand {
  id: string;
  name: string;
  description: string;
  is_demo?: boolean;
  samples?: { text: string; source?: string }[];
  profile?: BrandProfile;
  profile_version?: number;
  profile_source?: string;
}
export interface Review {
  criteria?: { name: string; score: number; reason: string }[];
  requests?: { issue: string; instruction: string }[];
  approved?: boolean;
  version?: number;
  created_at?: string;
}
export interface Decision {
  id: string;
  node: string;
  choice: string;
  reason: string;
  created_at?: string;
  evidence_ids?: string[];
}
export interface Feedback {
  id?: string;
  revision?: number;
  observed_at?: string;
  window_start?: string;
  window_end?: string;
  source_url?: string;
  notes?: string;
  timing_status?: string;
  impressions: number;
  reactions: number;
  comments: number;
  reposts: number;
  window: string;
  source: Source;
}
export interface Post {
  id: string;
  brand_id: string;
  brief: string;
  title: string;
  content: string;
  platform?: Platform;
  source_url?: string;
  contract?: BriefContract;
  contract_checks?: ContractChecks;
  original_draft?: string;
  review_stale?: boolean;
  image_stale?: boolean;
  status: string;
  hook: Hook;
  source: string;
  is_demo?: boolean;
  created_at: string;
  scheduled_at?: string;
  published_at?: string;
  image_url?: string;
  image_source?: string;
  pending_image_request?: { id: string; mode: Mode; feedback: string } | null;
  image_error?: {
    message: string;
    diagnostics?: Record<string, unknown>;
  } | null;
  image_variants?: {
    id: string;
    url: string;
    source?: string;
    feedback?: string;
    created_at?: string;
  }[];
  selected_image_variant_id?: string;
  run_id?: string;
  profile_version?: number;
  learning_version?: number;
  learning_snapshot?: Snapshot;
  learning_snapshot_id?: string;
  feedback?: Feedback;
  feedback_observations?: Feedback[];
  feedback_history?: Feedback[];
  versions?: {
    version: number;
    content: string;
    kind: string;
    reason?: string;
    created_at?: string;
  }[];
  reviews?: Review[];
  decisions?: Decision[];
}
export interface Evidence extends Partial<Feedback> {
  observation_id?: string;
  post_id?: string;
  post_title?: string;
  hook?: Hook;
  opening?: string;
  content?: string;
  metrics?: Partial<Feedback>;
}
export interface Snapshot {
  platform?: Platform;
  id: string;
  brand_id: string;
  source: Source;
  window: string;
  version: number;
  preferred_hook: Hook | null;
  status?: "collecting_evidence" | "early_signal" | "inconclusive";
  thresholds?: Record<string, number | string>;
  evidence?: Evidence[];
  uncertainty_note?: string;
  evidence_integrity?: string;
  excluded?: { id: string; post_id?: string; reason: string }[];
  stats: {
    hook: Hook;
    posts: number;
    impressions: number;
    comments: number;
    reposts: number;
    rate: number | null;
    interval?: [number, number] | { low: number; high: number };
  }[];
  evidence_ids: string[];
  explanation: string;
  created_at: string;
}
export interface Run {
  id: string;
  post_id: string;
  status: string;
  stage: string;
  error?: string;
  mode?: Mode;
}
export interface Evaluation {
  status?: string;
  mode?: string;
  summary?: Record<string, unknown>;
  cases?: Record<string, unknown>[];
  results?: Record<string, unknown>[];
  recovery?: {
    initial_summary: {
      pairs: number;
      scored_pairs: number;
      completed_pairs: number;
      errors: number;
    };
    attempts: Record<string, unknown>[];
    note?: string;
  };
  [key: string]: unknown;
}
export interface Bootstrap {
  brands: Brand[];
  posts: Post[];
  snapshots: Snapshot[];
  runs: Run[];
  settings: {
    mesh_configured: boolean;
    chat_model: string;
    image_model: string;
    mode?: Mode;
  };
  evaluation?: Evaluation;
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response
    .json()
    .catch(() => ({ detail: "The server returned an unreadable response." }));
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail
              .map((issue: { msg?: string }) => issue.msg || "Invalid field")
              .join(" ")
          : "Something went wrong. Please try again.",
    );
  return data;
}
export function label(value?: string | null) {
  return (value || "")
    .replace(/[_-]/g, " ")
    .replace(/^./, (s) => s.toUpperCase());
}
export function date(value?: string) {
  return value
    ? new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }).format(new Date(value))
    : "Not scheduled";
}
export const hooks: Hook[] = [
  "problem-first",
  "outcome-first",
  "question-first",
];
