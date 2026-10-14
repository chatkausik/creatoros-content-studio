export type Mode = "demo" | "live";
export type Source = "manual" | "simulated";
export type Hook = "problem-first" | "outcome-first" | "question-first";
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
  original_draft?: string;
  status: string;
  hook: Hook;
  source: string;
  is_demo?: boolean;
  created_at: string;
  scheduled_at?: string;
  published_at?: string;
  image_url?: string;
  image_source?: string;
  run_id?: string;
  profile_version?: number;
  learning_version?: number;
  learning_snapshot?: Snapshot;
  learning_snapshot_id?: string;
  feedback?: Feedback;
  feedback_observations?: Feedback[];
  versions?: { version: number; content: string; kind: string }[];
  reviews?: Review[];
  decisions?: Decision[];
}
export interface Snapshot {
  id: string;
  brand_id: string;
  source: Source;
  window: string;
  version: number;
  preferred_hook: Hook | null;
  stats: {
    hook: Hook;
    posts: number;
    impressions: number;
    comments: number;
    reposts: number;
    rate: number | null;
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
