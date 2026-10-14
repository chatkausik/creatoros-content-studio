import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  Copy,
  Download,
  FileText,
  FlaskConical,
  History,
  ImagePlus,
  Layers3,
  Lightbulb,
  Linkedin,
  LoaderCircle,
  Menu,
  MessageCircle,
  PenLine,
  Plus,
  RefreshCw,
  Send,
  Settings2,
  Sparkles,
  ThumbsUp,
  TrendingUp,
  WandSparkles,
  X,
} from "lucide-react";
import { api, date, hooks, label } from "./api";
import type {
  Bootstrap,
  Brand,
  Feedback,
  Mode,
  Post,
  Run,
  Source,
} from "./api";

type Page = "studio" | "brand" | "queue" | "learning";
type Dialog =
  | { type: "schedule"; post: Post }
  | { type: "feedback"; post: Post }
  | { type: "brand" }
  | { type: "import" }
  | null;
const nav = [
  { id: "studio" as Page, label: "Content studio", icon: PenLine },
  { id: "brand" as Page, label: "Brand voice", icon: AudioLines },
  { id: "queue" as Page, label: "Publishing queue", icon: CalendarDays },
  { id: "learning" as Page, label: "Learning lab", icon: FlaskConical },
];
const examples = [
  "Why AI evaluations deserve a place in your product roadmap",
  "The hidden cost of shipping AI without feedback",
  "One practical lesson from building with AI agents",
];
function Star({ className = "" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 32 32"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M16 1C16 11 11 16 1 16c10 0 15 5 15 15 0-10 5-15 15-15C21 16 16 11 16 1Z" />
    </svg>
  );
}
function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function Button({
  children,
  onClick,
  kind = "",
  disabled = false,
  type = "button",
  className = "",
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  kind?: string;
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
  title?: string;
}) {
  return (
    <button
      className={`button ${kind} ${className}`}
      onClick={onClick}
      disabled={disabled}
      type={type}
      title={title}
    >
      {children}
    </button>
  );
}
function Empty({
  icon: Icon = FileText,
  title,
  children,
}: {
  icon?: typeof FileText;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={24} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function ProfileList({ value }: { value?: string[] | string }) {
  const values = Array.isArray(value) ? value : value ? [value] : [];
  return values.length ? (
    <div className="tags">
      {values.map((v, i) => (
        <span key={i}>{v}</span>
      ))}
    </div>
  ) : (
    <span className="muted">Not extracted yet</span>
  );
}
function Diff({ before, after }: { before: string; after: string }) {
  const chunks = useMemo(() => {
    const a = before.match(/\S+\s*/g) || [],
      b = after.match(/\S+\s*/g) || [];
    if (a.length * b.length > 400000)
      return [
        { text: before, type: "removed" },
        { text: "\n\n" + after, type: "added" },
      ];
    const dp = Array.from(
      { length: a.length + 1 },
      () => new Uint16Array(b.length + 1),
    );
    for (let i = a.length - 1; i >= 0; i--)
      for (let j = b.length - 1; j >= 0; j--)
        dp[i][j] =
          a[i] === b[j]
            ? 1 + dp[i + 1][j + 1]
            : Math.max(dp[i + 1][j], dp[i][j + 1]);
    const result: { text: string; type: string }[] = [];
    let i = 0,
      j = 0;
    while (i < a.length || j < b.length) {
      if (i < a.length && j < b.length && a[i] === b[j]) {
        result.push({ text: a[i++], type: "same" });
        j++;
      } else if (
        j < b.length &&
        (i === a.length || dp[i][j + 1] >= dp[i + 1][j])
      )
        result.push({ text: b[j++], type: "added" });
      else result.push({ text: a[i++], type: "removed" });
    }
    return result;
  }, [before, after]);
  return (
    <div className="diff-text">
      {chunks.map((part, i) => (
        <span key={i} className={part.type}>
          {part.text}
        </span>
      ))}
    </div>
  );
}

export default function App() {
  const [data, setData] = useState<Bootstrap | null>(null),
    [page, setPage] = useState<Page>("studio"),
    [brandId, setBrandId] = useState(""),
    [selectedId, setSelectedId] = useState(""),
    [brief, setBrief] = useState(""),
    [mode, setMode] = useState<Mode>("demo"),
    [source, setSource] = useState<Source>("simulated"),
    [windowValue, setWindowValue] = useState("24h"),
    [useLearning, setUseLearning] = useState(true),
    [tab, setTab] = useState("revised"),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [toast, setToast] = useState(""),
    [dialog, setDialog] = useState<Dialog>(null),
    [sidebar, setSidebar] = useState(false),
    [activeRunId, setActiveRunId] = useState("");
  const sidebarRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!sidebar) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sidebarRef.current
      ?.querySelector<HTMLButtonElement>(".sidebar-close")
      ?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSidebar(false);
      if (event.key !== "Tab") return;
      const focusable = sidebarRef.current?.querySelectorAll<HTMLElement>(
        "button:not([disabled]),select,a[href]",
      );
      if (!focusable?.length) return;
      const first = focusable[0],
        last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    const desktop = window.matchMedia("(min-width: 761px)");
    const closeOnDesktop = () => {
      if (desktop.matches) setSidebar(false);
    };
    document.addEventListener("keydown", handleKey);
    desktop.addEventListener("change", closeOnDesktop);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKey);
      desktop.removeEventListener("change", closeOnDesktop);
      previousFocus?.focus();
    };
  }, [sidebar]);
  const refresh = useCallback(async () => {
    const next = await api<Bootstrap>("/bootstrap");
    setData(next);
    return next;
  }, []);
  useEffect(() => {
    refresh()
      .then((next) => {
        const initial =
          next.brands.find((b) => !b.is_demo && b.profile) || next.brands[0];
        setBrandId(initial?.id || "");
        setSource(initial?.is_demo ? "simulated" : "manual");
        setMode(next.settings.mesh_configured ? "live" : "demo");
      })
      .catch((e) => setError(e.message));
  }, [refresh]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(timer);
  }, [toast]);
  const brand =
    data?.brands.find((b) => b.id === brandId) ||
    data?.brands.find((b) => !b.is_demo && b.profile) ||
    data?.brands[0];
  const posts = data?.posts.filter((p) => p.brand_id === brand?.id) || [];
  const post =
    posts.find((p) => p.id === selectedId) ||
    posts.find((p) => p.original_draft) ||
    posts[0];
  const activeRun = data?.runs.find(
    (r) => r.id === (activeRunId || post?.run_id),
  );
  const pending =
    activeRun?.status === "queued" || activeRun?.status === "running";
  useEffect(() => {
    if (pending && activeRun && !activeRunId) setActiveRunId(activeRun.id);
  }, [pending, activeRun, activeRunId]);
  useEffect(() => {
    if (page !== "queue") return;
    const timer = setInterval(() => {
      refresh().catch((e) => setError(e.message));
    }, 15000);
    return () => clearInterval(timer);
  }, [page, refresh]);
  useEffect(() => {
    if (!activeRunId) return;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const result = await api<{ run: Run; post: Post }>(
          `/runs/${activeRunId}`,
        );
        if (cancelled) return;
        setData((prev) =>
          prev
            ? {
                ...prev,
                runs: [
                  ...prev.runs.filter((r) => r.id !== result.run.id),
                  result.run,
                ],
                posts: [
                  result.post,
                  ...prev.posts.filter((p) => p.id !== result.post.id),
                ],
              }
            : prev,
        );
        if (!["queued", "running"].includes(result.run.status)) {
          setActiveRunId("");
          await refresh();
          if (result.run.error) setError(result.run.error);
          else setToast("Your draft is ready. Take a look at what changed.");
        }
      } catch (e) {
        if (!cancelled) {
          setError((e as Error).message);
          setActiveRunId("");
        }
      }
    }, 1200);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [activeRunId, refresh]);
  const action = async (
    name: string,
    work: () => Promise<unknown>,
    success = "Saved",
  ) => {
    setBusy(name);
    setError("");
    try {
      await work();
      await refresh();
      setToast(success);
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy("");
    }
  };
  const snapshots = (data?.snapshots || [])
    .filter(
      (s) =>
        s.brand_id === brand?.id &&
        s.source === source &&
        s.window === windowValue,
    )
    .sort((a, b) => b.version - a.version);
  const snapshot = snapshots[0];
  const previousSnapshot = snapshots[1];
  const studioSnapshot = post?.learning_snapshot;
  const selectedRun = data?.runs.find((r) => r.id === post?.run_id);
  const latestReview = post?.reviews?.at(-1);
  const editorialReview = post?.reviews?.find(
    (review) => review.requests?.length,
  );
  const feedbackPosts = posts
    .filter((p) => ["published", "published_manually"].includes(p.status))
    .filter((p) =>
      source === "simulated"
        ? p.is_demo ||
          p.feedback_observations?.some((f) => f.source === "simulated")
        : !p.is_demo,
    )
    .map((p) => ({
      ...p,
      feedback: (
        p.feedback_observations || (p.feedback ? [p.feedback] : [])
      ).find((f) => f.source === source && f.window === windowValue),
    }));
  const startRun = async () => {
    if (!brand || !brief.trim()) return;
    await action(
      "generate",
      async () => {
        const run = await api<Run>("/runs", "POST", {
          brand_id: brand.id,
          brief: brief.trim(),
          mode,
          use_learning: useLearning,
          feedback_source: source,
          window: windowValue,
          generate_image: false,
        });
        setActiveRunId(run.id);
        setSelectedId(run.post_id);
        setTab("revised");
      },
      "Your agents are getting to work.",
    );
  };
  const selectBrand = (id: string) => {
    setBrandId(id);
    setSelectedId("");
    setActiveRunId("");
    setSource(
      data?.brands.find((b) => b.id === id)?.is_demo ? "simulated" : "manual",
    );
  };
  const copy = async () => {
    if (!post) return;
    try {
      await navigator.clipboard.writeText(post.content);
      setToast("Post copied to clipboard.");
    } catch {
      setError(
        "Clipboard access is unavailable. Select and copy the post text.",
      );
    }
  };
  const download = () => {
    if (!post) return;
    const link = document.createElement("a");
    link.href = URL.createObjectURL(
      new Blob([post.content], { type: "text/plain" }),
    );
    link.download = `${(post.title || "creatoros-post").toLowerCase().replace(/[^a-z0-9]+/g, "-")}.txt`;
    link.click();
    URL.revokeObjectURL(link.href);
  };
  const switchPage = (next: Page) => {
    setPage(next);
    setSidebar(false);
  };
  const queue = posts.filter((p) =>
    ["scheduled", "ready", "ready_to_publish", "approved"].includes(p.status),
  );
  if (!data)
    return (
      <div className="loading-screen">
        <Star className="loading-star" />
        <h1>CreatorOS</h1>
        <p>{error || "Opening your creative workspace…"}</p>
        {error ? (
          <Button
            onClick={() => {
              setError("");
              refresh().catch((e) => setError(e.message));
            }}
          >
            <RefreshCw size={16} />
            Try again
          </Button>
        ) : (
          <LoaderCircle className="spin" size={20} />
        )}
      </div>
    );
  return (
    <div className="app-shell">
      {sidebar && (
        <button
          aria-label="Close navigation"
          className="sidebar-backdrop"
          onClick={() => setSidebar(false)}
        />
      )}
      <aside
        ref={sidebarRef}
        id="workspace-navigation"
        aria-label="Workspace navigation"
        className={`sidebar ${sidebar ? "open" : ""}`}
      >
        <button
          className="icon-button sidebar-close"
          aria-label="Close navigation drawer"
          onClick={() => setSidebar(false)}
        >
          <X size={21} />
        </button>
        <a
          className="wordmark"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            switchPage("studio");
          }}
        >
          <span className="brand-symbol">
            <Star />
          </span>
          <span>
            Creator<span className="wordmark-light">OS</span>
          </span>
        </a>
        <p className="sidebar-tagline">Content that compounds.</p>
        <div className="workspace-picker">
          <span className="workspace-avatar">
            {brand?.name?.slice(0, 1) || "C"}
          </span>
          <div>
            <span className="eyebrow">YOUR WORKSPACE</span>
            <select
              aria-label="Select brand workspace"
              value={brand?.id || ""}
              onChange={(e) => selectBrand(e.target.value)}
            >
              {data.brands.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </div>
          <ChevronDown size={14} />
        </div>
        <div className="nav-label">CREATE & IMPROVE</div>
        <nav>
          {nav.map(({ id, label: navLabel, icon: Icon }) => (
            <button
              key={id}
              className={page === id ? "active" : ""}
              onClick={() => switchPage(id)}
            >
              <Icon size={18} />
              <span>{navLabel}</span>
              {id === "queue" && queue.length > 0 ? (
                <span className="nav-count">{queue.length}</span>
              ) : id === "learning" ? (
                <span className="nav-new">↗</span>
              ) : null}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="loop-card">
            <div className="loop-icon">
              <TrendingUp size={17} />
              <span>Better with every post</span>
            </div>
            <p>
              Your audience teaches.
              <br />
              Your next draft listens.
            </p>
            <button onClick={() => switchPage("learning")}>
              Explore the learning loop <ArrowUpRight size={14} />
            </button>
          </div>
          <div className="connection">
            <span
              className={`status-dot ${data.settings.mesh_configured ? "" : "off"}`}
            />
            <span>
              {data.settings.mesh_configured
                ? "Mesh configured"
                : "Demo workspace"}
            </span>
            <span className="small-tag">
              {data.settings.mesh_configured ? "API" : "LOCAL"}
            </span>
          </div>
          <div className="user-row">
            <div className="user-avatar">{brand?.name?.slice(0, 1) || "Y"}</div>
            <div>
              <strong>{brand?.name || "Your workspace"}</strong>
              <span>
                {brand?.is_demo
                  ? "Illustrative demo brand"
                  : "Creator workspace"}
              </span>
            </div>
            <Settings2 size={17} />
          </div>
        </div>
      </aside>
      <main className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              aria-expanded={sidebar}
              aria-controls="workspace-navigation"
              onClick={() => setSidebar(true)}
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{nav.find((n) => n.id === page)?.label}</strong>
          </div>
          <div className="topbar-right">
            <span className="autosave">
              <span className="status-dot" /> Local workspace
            </span>
            <a
              href="https://developers.meshapi.ai"
              target="_blank"
              rel="noreferrer"
              className="mesh-link"
            >
              Powered by <strong>mesh</strong>
              <ArrowUpRight size={12} />
            </a>
          </div>
        </header>
        {error && (
          <div className="error-banner" role="alert">
            <CircleHelp size={18} />
            <span>{error}</span>
            <button
              className="icon-button"
              aria-label="Dismiss error"
              onClick={() => setError("")}
            >
              <X size={17} />
            </button>
          </div>
        )}
        <div className="page-content">
          {page === "studio" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="overline">
                    <span /> YOUR CREATIVE WORKBENCH
                  </div>
                  <h1>
                    Good ideas. <span>Getting better.</span>
                  </h1>
                  <p>
                    From a first spark to your next best post — in your voice.
                  </p>
                </div>
                <div className="heading-actions">
                  <Badge tone="green">
                    <span className="status-dot" />
                    {brand?.profile ? "Voice connected" : "Add your voice"}
                  </Badge>
                  <Button
                    kind="quiet"
                    onClick={() => setDialog({ type: "import" })}
                  >
                    <Plus size={16} />
                    Import a post
                  </Button>
                </div>
              </div>
              <div className="studio-grid">
                <div className="studio-main">
                  <section className="card composer">
                    <div className="section-heading">
                      <div className="section-title">
                        <span className="icon-tile">
                          <Sparkles size={17} />
                        </span>
                        <h2>What’s on your mind?</h2>
                      </div>
                      <Badge>
                        <Linkedin size={12} />
                        LinkedIn post
                      </Badge>
                    </div>
                    <label className="sr-only" htmlFor="brief">
                      Content brief
                    </label>
                    <textarea
                      id="brief"
                      minLength={10}
                      maxLength={6000}
                      value={brief}
                      onChange={(e) => setBrief(e.target.value)}
                      placeholder={
                        "An idea, a lesson learned, a strong opinion…\nTell your agents what you want to say."
                      }
                    />
                    <div className="ideas-row">
                      <span>Try an idea</span>
                      {examples.slice(0, 2).map((example, i) => (
                        <button
                          key={example}
                          title={example}
                          onClick={() => setBrief(example)}
                        >
                          {i === 0
                            ? "Building better AI"
                            : "Learning in public"}
                          <ArrowUpRight size={11} />
                        </button>
                      ))}
                    </div>
                    <div className="composer-bottom">
                      <div className="composer-settings">
                        <label className="learning-toggle">
                          <input
                            type="checkbox"
                            checked={useLearning}
                            onChange={(e) => setUseLearning(e.target.checked)}
                          />
                          <span className="switch" />
                          <TrendingUp size={13} />
                          Use audience learnings
                        </label>
                        <div className="mode-select">
                          <select
                            aria-label="Generation mode"
                            value={mode}
                            onChange={(e) => setMode(e.target.value as Mode)}
                          >
                            <option value="demo">Demo fixture</option>
                            <option value="live">Live · Mesh API</option>
                          </select>
                          <ChevronDown size={12} />
                        </div>
                      </div>
                      <Button
                        kind="primary"
                        onClick={startRun}
                        disabled={
                          brief.trim().length < 10 ||
                          !!busy ||
                          pending ||
                          !brand
                        }
                      >
                        {busy === "generate" || pending ? (
                          <LoaderCircle size={16} className="spin" />
                        ) : (
                          <WandSparkles size={16} />
                        )}
                        Create a post
                        <ArrowRight size={15} />
                      </Button>
                    </div>
                    <div className="composer-caption">
                      {mode === "demo"
                        ? "Demo uses clearly labeled, deterministic fixtures. No AI request or API cost."
                        : data.settings.mesh_configured
                          ? "Live generation uses Mesh. Your configured API account is charged."
                          : "Add MESH_API_KEY to your local .env and restart the server to generate live."}
                    </div>
                  </section>
                  <section className="agent-strip" aria-label="Agent pipeline">
                    <div className="agent-label">
                      <span className="mini-star">✦</span>
                      <div>
                        <strong>Your creative team</strong>
                        <span>
                          {pending
                            ? "Working on your next post"
                            : post?.content
                              ? "A thoughtful process, every time"
                              : "Ready when you are"}
                        </span>
                      </div>
                    </div>
                    <div className="agent-steps">
                      {[
                        { name: "Strategist", key: "strateg", icon: Lightbulb },
                        { name: "Writer", key: "writ", icon: PenLine },
                        { name: "Editor", key: "edit", icon: ClipboardCheck },
                        { name: "Visual", key: "visual", icon: ImagePlus },
                      ].map(({ name, key, icon: Icon }, i) => {
                        const current =
                          pending &&
                          (activeRun?.stage?.toLowerCase().includes(key) ||
                            (key === "writ" &&
                              activeRun?.stage?.startsWith("revision")));
                        const done =
                          !current &&
                          (i === 0
                            ? post?.decisions?.some(
                                (d) => d.node === "strategist",
                              )
                            : i === 1
                              ? !!post?.versions?.length && !!post.run_id
                              : i === 2
                                ? !!post?.reviews?.length
                                : !!post?.image_url);
                        return (
                          <div
                            className={`agent-step ${current ? "working" : ""} ${done ? "done" : ""}`}
                            key={name}
                          >
                            <span className="agent-node">
                              {current ? (
                                <LoaderCircle size={15} className="spin" />
                              ) : done ? (
                                <Check size={14} />
                              ) : (
                                <Icon size={14} />
                              )}
                            </span>
                            <span>{name}</span>
                            {i < 3 && <span className="agent-connector" />}
                          </div>
                        );
                      })}
                    </div>
                  </section>
                  <div className="draft-heading">
                    <div>
                      <h2>Your working draft</h2>
                      <span>
                        {post
                          ? `${label(post.status)} · ${post.created_at ? date(post.created_at) : "Just now"}`
                          : "A blank page with potential"}
                      </span>
                    </div>
                    {posts.length > 0 && (
                      <div className="history-select">
                        <History size={14} />
                        <select
                          aria-label="Select a previous post"
                          value={post?.id || ""}
                          onChange={(e) => {
                            setSelectedId(e.target.value);
                            setActiveRunId("");
                            setTab("revised");
                          }}
                        >
                          {posts.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.title || p.brief || "Untitled draft"}
                            </option>
                          ))}
                        </select>
                        <ChevronDown size={13} />
                      </div>
                    )}
                  </div>
                  {post ? (
                    <section className="card draft-card">
                      <div className="draft-toolbar">
                        <div
                          className="tabs"
                          role="tablist"
                          aria-label="Draft versions"
                        >
                          {[
                            { id: "revised", name: "Refined draft" },
                            { id: "original", name: "First draft" },
                            { id: "diff", name: "See changes" },
                          ].map((t) => (
                            <button
                              key={t.id}
                              role="tab"
                              aria-selected={tab === t.id}
                              className={tab === t.id ? "active" : ""}
                              onClick={() => setTab(t.id)}
                            >
                              {t.id === "diff" && <Layers3 size={13} />}{" "}
                              {t.name}
                            </button>
                          ))}
                        </div>
                        <Badge tone={post.is_demo ? "amber" : "green"}>
                          {post.is_demo
                            ? "Demo fixture"
                            : post.source === "manual"
                              ? "Imported post"
                              : "Mesh generated"}
                        </Badge>
                      </div>
                      {pending && (
                        <div className="run-progress">
                          <LoaderCircle size={16} className="spin" />
                          <span>
                            {label(activeRun?.stage) || "Starting"} is in
                            progress. Completed steps are saved.
                          </span>
                        </div>
                      )}
                      {selectedRun &&
                        ["failed", "interrupted"].includes(
                          selectedRun.status,
                        ) && (
                          <div className="run-failed">
                            <span>
                              {selectedRun.error || "This run needs a retry."}
                            </span>
                            <Button
                              onClick={() =>
                                action(
                                  "resume",
                                  async () => {
                                    await api(
                                      `/runs/${selectedRun.id}/resume`,
                                      "POST",
                                      {},
                                    );
                                    setActiveRunId(selectedRun.id);
                                  },
                                  "Resuming from the last saved step.",
                                )
                              }
                              disabled={!!busy}
                            >
                              <RefreshCw size={14} />
                              Resume run
                            </Button>
                          </div>
                        )}
                      <div className="post-preview">
                        <div className="post-author">
                          <div className="post-avatar">
                            {brand?.name?.slice(0, 1)}
                          </div>
                          <div>
                            <strong>{brand?.name}</strong>
                            <p>{brand?.description || "Ideas worth sharing"}</p>
                            <span>
                              LinkedIn preview ·{" "}
                              <span aria-label="Public">◉</span>
                            </span>
                          </div>
                          <Linkedin size={21} className="linkedin-logo" />
                        </div>
                        {post.content ? (
                          <>
                            {tab === "diff" ? (
                              <>
                                <div className="diff-legend">
                                  <span>
                                    <i className="add-swatch" />
                                    Added
                                  </span>
                                  <span>
                                    <i className="remove-swatch" />
                                    Removed
                                  </span>
                                </div>
                                <Diff
                                  before={post.original_draft || post.content}
                                  after={post.content}
                                />
                              </>
                            ) : (
                              <div className="post-text">
                                {tab === "original"
                                  ? post.original_draft || post.content
                                  : post.content}
                              </div>
                            )}
                            {post.image_url && tab === "revised" && (
                              <a
                                href={post.image_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <img
                                  className="post-image"
                                  src={post.image_url}
                                  alt={`Visual for ${post.title}`}
                                />
                              </a>
                            )}
                          </>
                        ) : (
                          <Empty
                            icon={PenLine}
                            title={
                              pending
                                ? "A new idea is taking shape"
                                : "Your post will appear here"
                            }
                          >
                            The strategist finds an angle. The writer gives it a
                            voice. The editor makes it sharper.
                          </Empty>
                        )}
                        <div className="linkedin-actions">
                          <span>
                            <ThumbsUp size={15} />
                            Like
                          </span>
                          <span>
                            <MessageCircle size={15} />
                            Comment
                          </span>
                          <span>
                            <RefreshCw size={14} />
                            Repost
                          </span>
                          <span>
                            <Send size={14} />
                            Send
                          </span>
                        </div>
                      </div>
                      <div className="draft-footer">
                        <span>
                          <FileText size={13} />
                          {post.content?.split(/\s+/).filter(Boolean).length ||
                            0}{" "}
                          words<span className="dot-separator">·</span>
                          {post.content?.length || 0} characters
                        </span>
                        <div>
                          <button
                            className="icon-button"
                            title="Copy post text"
                            aria-label="Copy post text"
                            onClick={copy}
                          >
                            <Copy size={16} />
                          </button>
                          <button
                            className="icon-button"
                            title="Download post text"
                            aria-label="Download post text"
                            onClick={download}
                          >
                            <Download size={16} />
                          </button>
                        </div>
                      </div>
                      <div className="post-actions">
                        <div>
                          <Badge tone="green">
                            <CheckCheck size={12} />
                            {post.versions?.length || 1} saved version
                            {(post.versions?.length || 1) === 1 ? "" : "s"}
                          </Badge>
                          {!!post.learning_version && (
                            <span className="muted small">
                              Learning v{post.learning_version}
                            </span>
                          )}
                        </div>
                        <div>
                          <Button
                            onClick={() =>
                              action(
                                "approve",
                                () =>
                                  api(`/posts/${post.id}/approve`, "POST", {}),
                                "Post approved and ready to schedule.",
                              )
                            }
                            disabled={
                              !!busy ||
                              pending ||
                              !post.content ||
                              [
                                "approved",
                                "scheduled",
                                "ready",
                                "ready_to_publish",
                                "published",
                                "published_manually",
                              ].includes(post.status)
                            }
                          >
                            <Check size={15} />
                            {[
                              "approved",
                              "scheduled",
                              "ready",
                              "ready_to_publish",
                              "published",
                              "published_manually",
                            ].includes(post.status)
                              ? "Approved"
                              : "Approve"}
                          </Button>
                          <Button
                            kind="primary"
                            onClick={() =>
                              setDialog({ type: "schedule", post })
                            }
                            title={
                              !post.image_url
                                ? "Create a matching visual before scheduling"
                                : "Choose when to publish"
                            }
                            disabled={
                              !!busy ||
                              !post.image_url ||
                              ![
                                "approved",
                                "scheduled",
                                "ready",
                                "ready_to_publish",
                              ].includes(post.status)
                            }
                          >
                            <CalendarDays size={15} />
                            Schedule
                            <ChevronDown size={13} />
                          </Button>
                        </div>
                      </div>
                    </section>
                  ) : (
                    <section className="card">
                      <Empty
                        icon={PenLine}
                        title="Your next great post starts above"
                      >
                        Give your agents a brief. They’ll bring a strategy, a
                        draft, and a thoughtful second pass.
                      </Empty>
                    </section>
                  )}
                </div>
                <aside className="evidence-rail">
                  <section className="card insight-card">
                    <div className="rail-kicker">
                      <TrendingUp size={15} /> THE LEARNING LOOP{" "}
                      <span className="live-dot" />
                    </div>
                    <h3>
                      Your audience.
                      <br />
                      <em>Your advantage.</em>
                    </h3>
                    <p>Every response is a signal for what to create next.</p>
                    <div className="loop-diagram">
                      <span>Create</span>
                      <ArrowRight size={12} />
                      <span>Publish</span>
                      <ArrowRight size={12} />
                      <span className="highlight">Learn</span>
                      <span className="loop-return">
                        ↶ feeds your next draft
                      </span>
                    </div>
                    {studioSnapshot ? (
                      <div className="learning-callout">
                        <div>
                          <Badge tone="green">Early signal</Badge>
                          <span className="small muted">
                            v{studioSnapshot.version}
                          </span>
                        </div>
                        <strong>
                          {studioSnapshot.preferred_hook
                            ? `${label(studioSnapshot.preferred_hook)} hooks`
                            : "Still exploring opening styles"}
                        </strong>
                        <p>{studioSnapshot.explanation}</p>
                        <button onClick={() => switchPage("learning")}>
                          Explore the evidence <ArrowUpRight size={13} />
                        </button>
                      </div>
                    ) : (
                      <div className="learning-callout">
                        <strong>Make your next post smarter.</strong>
                        <p>
                          Add performance metrics, then update what your studio
                          learns.
                        </p>
                        <button onClick={() => switchPage("learning")}>
                          Open the learning lab <ArrowUpRight size={13} />
                        </button>
                      </div>
                    )}
                    <div className="rail-footnote">
                      {studioSnapshot
                        ? studioSnapshot.source === "simulated"
                          ? "This draft used illustrative feedback"
                          : "This draft used manually entered feedback"
                        : "No performance feedback used for this draft"}
                    </div>
                  </section>
                  <section className="card editor-card">
                    <div className="section-title">
                      <ClipboardCheck size={16} />
                      <h3>The editor’s desk</h3>
                      {post?.reviews?.length ? (
                        <Badge tone="green">Reviewed</Badge>
                      ) : null}
                    </div>
                    {editorialReview?.requests?.length ? (
                      <>
                        <p className="muted small">
                          Small changes. A stronger piece.
                        </p>
                        <div className="editor-requests">
                          {editorialReview.requests
                            .slice(0, 3)
                            .map((request, i) => (
                              <div key={i}>
                                <span className="request-number">0{i + 1}</span>
                                <div>
                                  <strong>{request.issue}</strong>
                                  <p>{request.instruction}</p>
                                </div>
                              </div>
                            ))}
                        </div>
                        {latestReview?.criteria?.length ? (
                          <div className="review-scores">
                            {latestReview.criteria.map((c) => (
                              <div key={c.name} title={c.reason}>
                                <span>{label(c.name)}</span>
                                <strong>
                                  {c.score}
                                  <small>/5</small>
                                </strong>
                              </div>
                            ))}
                          </div>
                        ) : null}
                        <button
                          className="text-button"
                          onClick={() => setTab("diff")}
                        >
                          See what changed
                          <ArrowRight size={13} />
                        </button>
                      </>
                    ) : (
                      <p className="rail-empty">
                        Actionable edits will appear here after your editor
                        reviews a draft.
                      </p>
                    )}
                  </section>
                  <section className="card visual-card">
                    <div className="section-title">
                      <ImagePlus size={16} />
                      <h3>Make it visual</h3>
                    </div>
                    {post?.image_url ? (
                      <img
                        src={post.image_url}
                        alt={
                          post.image_source === "demo"
                            ? "Illustrative demo visual"
                            : "Generated post visual"
                        }
                      />
                    ) : (
                      <div className="visual-placeholder">
                        <div className="visual-orbit orbit-one" />
                        <div className="visual-orbit orbit-two" />
                        <div className="visual-orbit orbit-three" />
                        <Star />
                        <span>A visual that tells your story</span>
                      </div>
                    )}
                    <p>
                      {post?.image_url
                        ? post.image_source === "demo"
                          ? "Illustrative SVG fixture, not an AI-generated image."
                          : "Generated through Mesh. Open the preview to download."
                        : mode === "demo"
                          ? "Demo mode attaches a code-authored SVG fixture. Choose Live for a Mesh-generated image."
                          : "Turn your final idea into a matching image through Mesh."}
                    </p>
                    {post?.image_url && (
                      <a className="button full" href={post.image_url} download>
                        <Download size={14} />
                        Download visual
                      </a>
                    )}
                    {(!post?.image_url ||
                      (post.image_source === "demo" && mode === "live")) && (
                      <Button
                        onClick={() =>
                          post &&
                          action(
                            "image",
                            () =>
                              api(`/posts/${post.id}/image`, "POST", { mode }),
                            "Visual saved to your post.",
                          )
                        }
                        disabled={
                          !!busy ||
                          !post?.content ||
                          pending ||
                          !["draft", "needs_review", "approved"].includes(
                            post.status,
                          )
                        }
                        kind="full"
                      >
                        {busy === "image" ? (
                          <LoaderCircle size={14} className="spin" />
                        ) : (
                          <Sparkles size={14} />
                        )}{" "}
                        {post?.image_url
                          ? "Generate through Mesh"
                          : "Create matching visual"}
                      </Button>
                    )}
                  </section>
                  {post?.decisions?.length ? (
                    <section className="decision-section">
                      <div className="section-title">
                        <History size={14} />
                        <h3>Nothing behind a curtain.</h3>
                      </div>
                      <details>
                        <summary>
                          View {post.decisions.length} saved decisions
                          <ChevronDown size={13} />
                        </summary>
                        <div className="decision-list">
                          {post.decisions.map((d) => (
                            <div key={d.id}>
                              <span>{label(d.node)}</span>
                              <strong>{d.choice}</strong>
                              <p>{d.reason}</p>
                              {!!d.evidence_ids?.length && (
                                <small>
                                  Evidence: {d.evidence_ids.join(", ")}
                                </small>
                              )}
                            </div>
                          ))}
                        </div>
                      </details>
                    </section>
                  ) : null}
                </aside>
              </div>
            </>
          )}
          {page === "brand" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="overline">
                    <span /> SOUND LIKE YOURSELF
                  </div>
                  <h1>
                    Your voice. <span>Your signature.</span>
                  </h1>
                  <p>
                    A brand profile learned from your writing, carried into
                    every draft.
                  </p>
                </div>
                <Button
                  kind="primary"
                  onClick={() => setDialog({ type: "brand" })}
                >
                  <Plus size={16} />
                  New brand
                </Button>
              </div>
              <div className="brand-grid">
                <section className="card brand-profile">
                  <div className="profile-hero">
                    <div className="large-avatar">
                      {brand?.name?.slice(0, 1)}
                    </div>
                    <div>
                      <h2>{brand?.name}</h2>
                      <p>{brand?.description}</p>
                      <div className="tags">
                        {brand?.is_demo && (
                          <Badge tone="amber">Illustrative demo brand</Badge>
                        )}
                        {brand?.profile_source === "demo" && !brand.is_demo && (
                          <Badge tone="amber">Demo profile fixture</Badge>
                        )}
                        <Badge>
                          {brand?.profile_version
                            ? `Profile v${brand.profile_version}`
                            : "Profile not yet learned"}
                        </Badge>
                      </div>
                    </div>
                  </div>
                  {brand?.profile ? (
                    <>
                      <div className="profile-summary">
                        <span className="eyebrow">
                          YOUR VOICE, IN A FEW WORDS
                        </span>
                        <p>
                          {brand.profile.summary ||
                            "A distinctive voice, grounded in your writing samples."}
                        </p>
                      </div>
                      <div className="profile-traits">
                        {[
                          {
                            label: "Tone & personality",
                            key: "tone",
                            icon: AudioLines,
                          },
                          {
                            label: "Writing style",
                            key: "style",
                            icon: PenLine,
                          },
                          {
                            label: "Words that feel like you",
                            key: "vocabulary",
                            icon: MessageCircle,
                          },
                          {
                            label: "Keep out of the draft",
                            key: "avoid",
                            icon: X,
                          },
                        ].map(({ label: traitLabel, key, icon: Icon }) => (
                          <div key={key}>
                            <h3>
                              <Icon size={16} />
                              {traitLabel}
                            </h3>
                            <ProfileList
                              value={brand.profile?.[key as "tone"]}
                            />
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <Empty
                      icon={AudioLines}
                      title="Let your writing do the talking"
                    >
                      Add at least three substantial writing samples, then
                      extract your voice profile.
                    </Empty>
                  )}
                  <div className="profile-action">
                    <div className="mode-select">
                      <select
                        aria-label="Profile extraction mode"
                        value={mode}
                        onChange={(e) => setMode(e.target.value as Mode)}
                      >
                        <option value="demo">Demo fixture</option>
                        <option value="live">Live · Mesh API</option>
                      </select>
                      <ChevronDown size={12} />
                    </div>
                    <Button
                      kind="primary"
                      disabled={
                        !!busy ||
                        !brand ||
                        !brand.samples ||
                        brand.samples.length < 3
                      }
                      onClick={() =>
                        brand &&
                        action(
                          "profile",
                          () =>
                            api(`/brands/${brand.id}/profile`, "POST", {
                              mode,
                            }),
                          "Brand voice profile saved.",
                        )
                      }
                    >
                      {busy === "profile" ? (
                        <LoaderCircle className="spin" size={15} />
                      ) : (
                        <Sparkles size={15} />
                      )}{" "}
                      {brand?.profile
                        ? "Refresh voice profile"
                        : "Learn my voice"}
                    </Button>
                  </div>
                </section>
                <div className="brand-side">
                  <section className="card samples-card">
                    <div className="section-heading">
                      <h2>The source material</h2>
                      <Badge>{brand?.samples?.length || 0} samples</Badge>
                    </div>
                    <p className="muted small">
                      The writing behind your profile.
                    </p>
                    {brand?.samples?.length ? (
                      brand.samples.map((sample, i) => (
                        <details className="sample" key={i}>
                          <summary>
                            <FileText size={15} />
                            <strong>
                              {sample.source || `Writing sample ${i + 1}`}
                            </strong>
                            <ChevronDown size={14} />
                          </summary>
                          <p>{sample.text}</p>
                          {sample.source?.startsWith("https://") && (
                            <a
                              className="source-link"
                              href={sample.source}
                              target="_blank"
                              rel="noreferrer"
                            >
                              View original source
                              <ArrowUpRight size={12} />
                            </a>
                          )}
                        </details>
                      ))
                    ) : (
                      <p className="rail-empty">
                        Create a brand with at least three writing samples to
                        get started.
                      </p>
                    )}
                  </section>
                  <section className="card evidence-quotes">
                    <div className="section-title">
                      <MessageCircle size={17} />
                      <h2>Grounded in your words</h2>
                    </div>
                    <p className="muted small">Every trait has a reason.</p>
                    {brand?.profile?.evidence?.length ? (
                      brand.profile.evidence.map((e, i) => (
                        <blockquote key={i}>
                          <p>“{e.quote}”</p>
                          <footer>
                            <span /> {e.trait}
                          </footer>
                        </blockquote>
                      ))
                    ) : (
                      <p className="rail-empty">
                        Supporting excerpts will appear after profile
                        extraction.
                      </p>
                    )}
                  </section>
                </div>
              </div>
            </>
          )}
          {page === "queue" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="overline">
                    <span /> MAKE ROOM FOR CONSISTENCY
                  </div>
                  <h1>
                    Ideas, <span>out in the world.</span>
                  </h1>
                  <p>
                    Your approved drafts, ready for their moment. You handle the
                    final publish.
                  </p>
                </div>
                <Button kind="primary" onClick={() => switchPage("studio")}>
                  <Plus size={15} />
                  Create a post
                </Button>
              </div>
              <div className="queue-banner">
                <span className="icon-tile">
                  <CalendarDays size={19} />
                </span>
                <div>
                  <strong>Your content calendar, without the noise.</strong>
                  <p>
                    Scheduled posts become ready at their due time. Publish on
                    LinkedIn, then mark them published here.
                  </p>
                </div>
                <Badge>Manual publishing</Badge>
              </div>
              <section className="card queue-section">
                <div className="section-heading">
                  <h2>
                    Coming up next{" "}
                    <span className="heading-count">{queue.length}</span>
                  </h2>
                  <span className="small muted">
                    {Intl.DateTimeFormat().resolvedOptions().timeZone}
                  </span>
                </div>
                {queue.length ? (
                  <div className="queue-list">
                    {queue
                      .sort((a, b) =>
                        (a.scheduled_at || "z").localeCompare(
                          b.scheduled_at || "z",
                        ),
                      )
                      .map((p) => (
                        <div className="queue-item" key={p.id}>
                          <div className="queue-date">
                            <strong>
                              {p.scheduled_at
                                ? new Date(p.scheduled_at).getDate()
                                : "—"}
                            </strong>
                            <span>
                              {p.scheduled_at
                                ? new Intl.DateTimeFormat(undefined, {
                                    month: "short",
                                  }).format(new Date(p.scheduled_at))
                                : "DRAFT"}
                            </span>
                          </div>
                          <div className="queue-content">
                            <div>
                              <Badge
                                tone={
                                  ["ready", "ready_to_publish"].includes(
                                    p.status,
                                  )
                                    ? "green"
                                    : "neutral"
                                }
                              >
                                {label(p.status)}
                              </Badge>
                              {p.is_demo && <Badge tone="amber">Demo</Badge>}
                              <span>
                                <Linkedin size={13} />
                                {p.hook ? label(p.hook) : "LinkedIn"}
                              </span>
                            </div>
                            <h3>{p.title || p.brief || "Untitled post"}</h3>
                            <p>
                              {p.content.slice(0, 145)}
                              {p.content.length > 145 ? "…" : ""}
                            </p>
                            <small>{date(p.scheduled_at)}</small>
                          </div>
                          <div className="queue-actions">
                            <Button
                              onClick={() => {
                                setSelectedId(p.id);
                                switchPage("studio");
                              }}
                              kind="quiet"
                            >
                              Open
                              <ArrowUpRight size={13} />
                            </Button>
                            <Button
                              disabled={!!busy || !p.image_url}
                              title={
                                !p.image_url
                                  ? "Open this post and create a visual first"
                                  : "Choose a publish time"
                              }
                              onClick={() =>
                                setDialog({ type: "schedule", post: p })
                              }
                            >
                              <CalendarDays size={14} />
                              {p.scheduled_at ? "Reschedule" : "Schedule"}
                            </Button>
                            <Button
                              kind="primary"
                              disabled={!!busy}
                              onClick={() =>
                                action(
                                  "publish",
                                  () =>
                                    api(`/posts/${p.id}/publish`, "POST", {
                                      published_at: new Date().toISOString(),
                                    }),
                                  "Marked as published. Add its performance when you have it.",
                                )
                              }
                            >
                              <Check size={14} />
                              Mark published
                            </Button>
                          </div>
                        </div>
                      ))}
                  </div>
                ) : (
                  <Empty
                    icon={CalendarDays}
                    title="A little planning goes a long way"
                  >
                    Approve a draft in the studio, then choose when you want to
                    publish.
                  </Empty>
                )}
              </section>
              <section className="card queue-section">
                <div className="section-heading">
                  <h2>Out in the world</h2>
                  <Button
                    kind="quiet"
                    onClick={() => setDialog({ type: "import" })}
                  >
                    <Plus size={14} />
                    Import past post
                  </Button>
                </div>
                {posts.filter((p) =>
                  ["published", "published_manually"].includes(p.status),
                ).length ? (
                  <div className="published-table">
                    <div className="table-head">
                      <span>POST</span>
                      <span>PUBLISHED</span>
                      <span>FEEDBACK</span>
                      <span />
                    </div>
                    {posts
                      .filter((p) =>
                        ["published", "published_manually"].includes(p.status),
                      )
                      .map((p) => (
                        <div className="table-row" key={p.id}>
                          <button
                            onClick={() => {
                              setSelectedId(p.id);
                              switchPage("studio");
                            }}
                          >
                            <strong>
                              {p.title || p.brief || "Untitled post"}
                            </strong>
                            <span>
                              {label(p.hook)}{" "}
                              {p.is_demo ? "· Demo fixture" : ""}
                            </span>
                          </button>
                          <span className="small muted">
                            {date(p.published_at)}
                          </span>
                          <Badge tone={p.feedback ? "green" : "neutral"}>
                            {p.feedback ? "Recorded" : "Awaiting metrics"}
                          </Badge>
                          <Button
                            kind="quiet"
                            onClick={() =>
                              setDialog({ type: "feedback", post: p })
                            }
                          >
                            <TrendingUp size={14} />
                            {p.feedback ? "Edit metrics" : "Add metrics"}
                          </Button>
                        </div>
                      ))}
                  </div>
                ) : (
                  <Empty icon={Send} title="Your story is just beginning">
                    Published posts will appear here, ready to teach you
                    something.
                  </Empty>
                )}
              </section>
            </>
          )}
          {page === "learning" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="overline">
                    <span /> CLOSE THE LOOP
                  </div>
                  <h1>
                    Every post <span>teaches you something.</span>
                  </h1>
                  <p>
                    Audience feedback becomes a better-informed next draft.
                    Follow the evidence.
                  </p>
                </div>
                <Button
                  kind="primary"
                  disabled={!!busy || !brand}
                  onClick={() =>
                    brand &&
                    action(
                      "learn",
                      () =>
                        api(`/brands/${brand.id}/learn`, "POST", {
                          source,
                          window: windowValue,
                        }),
                      "Learning snapshot saved. Your next post can use this evidence.",
                    )
                  }
                >
                  {busy === "learn" ? (
                    <LoaderCircle size={15} className="spin" />
                  ) : (
                    <RefreshCw size={15} />
                  )}
                  Update learnings
                </Button>
              </div>
              <div className="learning-controls">
                <div className="segmented">
                  <button
                    className={source === "manual" ? "active" : ""}
                    onClick={() => setSource("manual")}
                  >
                    Your real metrics
                  </button>
                  <button
                    className={source === "simulated" ? "active" : ""}
                    onClick={() => setSource("simulated")}
                  >
                    Demo feedback
                  </button>
                </div>
                <div>
                  <label htmlFor="window">Observation window</label>
                  <select
                    id="window"
                    value={windowValue}
                    onChange={(e) => setWindowValue(e.target.value)}
                  >
                    <option value="24h">First 24 hours</option>
                    <option value="7d">First 7 days</option>
                  </select>
                </div>
              </div>
              {source === "simulated" && (
                <div className="demo-note">
                  <FlaskConical size={16} />
                  <span>
                    Illustrative feedback for exploring the loop. These numbers
                    are simulated and kept separate from your real metrics.
                  </span>
                </div>
              )}
              <div className="learning-grid">
                <section className="card performance-card">
                  <div className="section-heading">
                    <div>
                      <h2>Which opening earns a response?</h2>
                      <p className="muted small">
                        Comments + reposts per 1,000 impressions
                      </p>
                    </div>
                    <Badge tone="green">Early signal</Badge>
                  </div>
                  {snapshot ? (
                    <>
                      <div className="hook-chart">
                        {hooks.map((hook) => {
                          const stat = snapshot.stats.find(
                            (s) => s.hook === hook,
                          );
                          const rate = stat?.rate ?? 0;
                          const maximum = Math.max(
                            1,
                            ...snapshot.stats.map((s) => s.rate || 0),
                          );
                          return (
                            <div
                              className={`chart-row ${snapshot.preferred_hook === hook ? "preferred" : ""}`}
                              key={hook}
                            >
                              <div className="chart-label">
                                <span>{label(hook)}</span>
                                {snapshot.preferred_hook === hook && (
                                  <span>
                                    <Star />
                                    Current preference
                                  </span>
                                )}
                                <strong>
                                  {stat?.rate == null ? "—" : rate.toFixed(1)}
                                </strong>
                              </div>
                              <div className="chart-track">
                                <div
                                  style={{
                                    width: `${(rate / maximum) * 100}%`,
                                  }}
                                />
                              </div>
                              <small>
                                {stat?.posts || 0} post
                                {stat?.posts === 1 ? "" : "s"} ·{" "}
                                {(stat?.impressions || 0).toLocaleString()}{" "}
                                impressions
                              </small>
                            </div>
                          );
                        })}
                      </div>
                      <div className="chart-footnote">
                        <CircleHelp size={14} />
                        An observed association, not proof that a hook caused
                        engagement. Once all three styles have feedback, every
                        fourth selection explores another opening.
                      </div>
                    </>
                  ) : (
                    <Empty
                      icon={TrendingUp}
                      title="Your feedback becomes the next step"
                    >
                      Record performance for your published posts, then update
                      learnings to compare opening styles.
                    </Empty>
                  )}
                </section>
                <section className="policy-card">
                  <div className="rail-kicker">
                    <Sparkles size={14} /> WHY THE NEXT POST CHANGES
                  </div>
                  <h2>
                    A feedback loop
                    <br />
                    you can follow.
                  </h2>
                  <div className="policy-step">
                    <span className="policy-dot" />
                    <div>
                      <span className="eyebrow">BEFORE</span>
                      <strong>
                        {previousSnapshot?.preferred_hook
                          ? `${label(previousSnapshot.preferred_hook)} opening`
                          : "Explore the three opening styles"}
                      </strong>
                      <p>
                        {previousSnapshot
                          ? `Learning snapshot v${previousSnapshot.version}`
                          : "With no comparable evidence, rotate through each approach."}
                      </p>
                    </div>
                  </div>
                  <ArrowDown className="policy-arrow" size={17} />
                  <div className="policy-step">
                    <span className="policy-dot filled" />
                    <div>
                      <span className="eyebrow">WHAT YOUR AUDIENCE SAID</span>
                      <strong>
                        {snapshot
                          ? `${snapshot.evidence_ids.length} feedback observation${snapshot.evidence_ids.length === 1 ? "" : "s"}`
                          : "Waiting for the first signal"}
                      </strong>
                      <p>
                        {snapshot?.explanation ||
                          "Feedback stays linked to the post that earned it."}
                      </p>
                    </div>
                  </div>
                  <ArrowDown className="policy-arrow" size={17} />
                  <div className="policy-step">
                    <span className="policy-dot filled" />
                    <div>
                      <span className="eyebrow">NEXT TIME</span>
                      <strong>
                        {snapshot?.preferred_hook
                          ? `Prefer ${label(snapshot.preferred_hook).toLowerCase()} hooks`
                          : "Let the evidence inform your next draft"}
                      </strong>
                      <p>
                        Your brand voice stays constant. Your opening strategy
                        adapts.
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setUseLearning(true);
                      switchPage("studio");
                    }}
                  >
                    Put this learning to work
                    <ArrowUpRight size={15} />
                  </button>
                </section>
              </div>
              <section className="card feedback-section">
                <div className="section-heading">
                  <div>
                    <h2>Behind every signal, a post</h2>
                    <p className="muted small">
                      Record comparable metrics at the same point after
                      publication.
                    </p>
                  </div>
                  <Button
                    kind="quiet"
                    onClick={() => setDialog({ type: "import" })}
                  >
                    <Plus size={14} />
                    Import a post
                  </Button>
                </div>
                <div className="feedback-table">
                  <div className="feedback-head">
                    <span>POST & OPENING</span>
                    <span>IMPRESSIONS</span>
                    <span>COMMENTS</span>
                    <span>REPOSTS</span>
                    <span>RATE / 1K</span>
                    <span />
                  </div>
                  {feedbackPosts.length ? (
                    feedbackPosts.map((p) => (
                      <div className="feedback-row" key={p.id}>
                        <div>
                          <strong>
                            {p.title || p.brief || "Untitled post"}
                          </strong>
                          <span>
                            {label(p.hook)}
                            <span>
                              {" "}
                              · {p.feedback?.window || "No observation"}
                            </span>
                          </span>
                        </div>
                        <span>
                          {p.feedback?.impressions?.toLocaleString() ?? "—"}
                        </span>
                        <span>{p.feedback?.comments ?? "—"}</span>
                        <span>{p.feedback?.reposts ?? "—"}</span>
                        <span className="rate">
                          {p.feedback?.impressions
                            ? (
                                ((p.feedback.comments + p.feedback.reposts) *
                                  1000) /
                                p.feedback.impressions
                              ).toFixed(1)
                            : "—"}
                        </span>
                        <Button
                          kind="quiet"
                          onClick={() =>
                            setDialog({ type: "feedback", post: p })
                          }
                        >
                          <PenLine size={13} />
                          <span>{p.feedback ? "Edit" : "Add"}</span>
                        </Button>
                      </div>
                    ))
                  ) : (
                    <Empty
                      icon={TrendingUp}
                      title="No feedback in this view yet"
                    >
                      Import a published post or choose demo feedback to explore
                      how learning works.
                    </Empty>
                  )}
                </div>
              </section>
              <section className="card evaluation-card">
                <div className="section-heading">
                  <div className="section-title">
                    <FlaskConical size={19} />
                    <h2>Does the editor actually help?</h2>
                  </div>
                  <Badge>Self-evaluation</Badge>
                </div>
                <p>
                  Blind comparisons of original and revised drafts, scored on
                  brief fulfillment, specificity, clarity, and brand fit.
                </p>
                {data.evaluation && Object.keys(data.evaluation).length > 0 ? (
                  <EvaluationReport evaluation={data.evaluation} />
                ) : (
                  <div className="evaluation-empty">
                    <div>
                      <strong>The evaluation harness is ready.</strong>
                      <p>
                        Run the evaluation script to measure improvement.
                        Results will appear here when saved.
                      </p>
                    </div>
                    <code>python scripts/evaluate.py</code>
                  </div>
                )}
                <div className="evaluation-note">
                  <CircleHelp size={14} />
                  <span>
                    Model judging is subjective. Demo fixtures validate the
                    workflow; only live evaluation measures generated output.
                  </span>
                </div>
              </section>
            </>
          )}
        </div>
        <footer className="page-footer">
          <span>
            <Star />
            CreatorOS
          </span>
          <p>Built around your voice. Improved by your audience.</p>
          <span className="footer-right">Create. Reflect. Repeat.</span>
        </footer>
      </main>
      {toast && (
        <div className="toast" role="status">
          <span>
            <Check size={15} />
          </span>
          {toast}
          <button
            aria-label="Dismiss notification"
            className="icon-button"
            onClick={() => setToast("")}
          >
            <X size={14} />
          </button>
        </div>
      )}
      {dialog && (
        <Modal
          error={error}
          title={
            dialog.type === "brand"
              ? "Make room for your voice"
              : dialog.type === "import"
                ? "Bring a past post into the loop"
                : dialog.type === "schedule"
                  ? "Pick its moment"
                  : "What did your audience say?"
          }
          subtitle={
            dialog.type === "brand"
              ? "Your writing samples become the foundation for every draft."
              : dialog.type === "import"
                ? "Import a published LinkedIn post, then add its performance."
                : dialog.type === "schedule"
                  ? "Your post will be ready at this time. You publish it on LinkedIn."
                  : "Enter the metrics from a consistent observation window."
          }
          onClose={() => !busy && setDialog(null)}
        >
          {dialog.type === "brand" ? (
            <BrandForm
              busy={!!busy}
              onSubmit={(body) =>
                action(
                  "brand",
                  async () => {
                    const created = await api<Brand>("/brands", "POST", body);
                    selectBrand(created.id);
                    setPage("brand");
                    setDialog(null);
                  },
                  "Brand created. Extract your voice profile to start creating.",
                )
              }
            />
          ) : dialog.type === "import" ? (
            <ImportForm
              busy={!!busy}
              onSubmit={(body) =>
                action(
                  "import",
                  async () => {
                    const created = await api<Post>("/posts/import", "POST", {
                      ...body,
                      brand_id: brand?.id,
                    });
                    setSelectedId(created.id);
                    setDialog(null);
                  },
                  "Past post imported. Add metrics in the learning lab.",
                )
              }
            />
          ) : dialog.type === "schedule" ? (
            <ScheduleForm
              post={dialog.post}
              busy={!!busy}
              onSubmit={(scheduled_at) =>
                action(
                  "schedule",
                  async () => {
                    await api(`/posts/${dialog.post.id}/schedule`, "POST", {
                      scheduled_at,
                    });
                    setDialog(null);
                  },
                  "Scheduled. Your post will be ready when the time arrives.",
                )
              }
            />
          ) : (
            <FeedbackForm
              post={dialog.post}
              source={source}
              busy={!!busy}
              onSubmit={(body) =>
                action(
                  "feedback",
                  async () => {
                    await api(`/posts/${dialog.post.id}/feedback`, "PUT", body);
                    setDialog(null);
                  },
                  "Feedback saved. Update learnings to apply this signal.",
                )
              }
            />
          )}
        </Modal>
      )}
    </div>
  );
}

function EvaluationReport({
  evaluation,
}: {
  evaluation: Bootstrap["evaluation"];
}) {
  if (!evaluation) return null;
  const summary = evaluation.summary || {};
  const cases = evaluation.cases || evaluation.results || [];
  const pending =
    typeof evaluation.status === "string" &&
    ["not_run", "pending", "unavailable", "not_available"].includes(
      evaluation.status,
    );
  if (pending)
    return (
      <div className="evaluation-empty">
        <div>
          <strong>No scored runs yet.</strong>
          <p>
            Run the evaluation harness to record honest before-and-after
            results.
          </p>
        </div>
        <code>python scripts/evaluate.py</code>
      </div>
    );
  const totalPairs =
    typeof summary.pairs === "number" ? summary.pairs : cases.length;
  const scoredPairs =
    typeof summary.scored_pairs === "number"
      ? summary.scored_pairs
      : cases.filter((item) => item.scores != null).length;
  const errorCount =
    typeof summary.errors === "number"
      ? summary.errors
      : cases.filter((item) => item.error).length;
  const isLive = evaluation.mode === "live";
  const incomplete = isLive && scoredPairs < totalPairs;
  const metrics = [
    ["Scored / attempted", `${scoredPairs} / ${totalPairs}`],
    ["Failed cases", errorCount],
    ["Mean first · scored only", summary.mean_before],
    ["Mean refined · scored only", summary.mean_after],
    ["Mean change · scored only", summary.mean_delta],
    [
      "Wins / ties / losses · scored only",
      summary.wins == null
        ? null
        : `${summary.wins} / ${summary.ties} / ${summary.losses}`,
    ],
  ];
  const checks = Array.isArray(evaluation.learning_checks)
    ? (evaluation.learning_checks as {
        id: string;
        passed: boolean;
        description: string;
      }[])
    : [];
  return (
    <>
      <div className="evaluation-meta">
        <Badge tone={isLive && !incomplete ? "green" : "amber"}>
          {isLive
            ? incomplete
              ? "Live Mesh evaluation · incomplete"
              : "Live Mesh evaluation"
            : "Fixture mechanics · quality unmeasured"}
        </Badge>
        {!!evaluation.generated_at && (
          <span className="small muted">
            {date(String(evaluation.generated_at))}
          </span>
        )}
      </div>
      {isLive && (
        <div
          className={`evaluation-completion ${incomplete ? "incomplete" : ""}`}
          role="status"
        >
          <CircleHelp size={15} />
          <span>
            <strong>
              {scoredPairs} of {totalPairs} pairs scored; {errorCount} failed.
            </strong>{" "}
            Quality means and win/tie/loss counts include only scored pairs.{" "}
            {incomplete
              ? "Unscored and failed cases are excluded, so this is a partial result."
              : "All attempted pairs are represented in these quality scores."}
          </span>
        </div>
      )}
      <div className="evaluation-stats">
        {metrics.map(([name, value]) => (
          <div key={String(name)}>
            <span>{String(name)}</span>
            <strong className={value == null ? "unmeasured" : ""}>
              {value == null
                ? "Unmeasured"
                : typeof value === "number"
                  ? Number.isInteger(value)
                    ? value
                    : value.toFixed(2)
                  : String(value)}
            </strong>
          </div>
        ))}
      </div>
      {checks.length > 0 && (
        <div className="evaluation-checks">
          {checks.map((check) => (
            <div key={check.id}>
              {check.passed ? <Check size={14} /> : <CircleHelp size={14} />}
              <span>{check.description}</span>
              <Badge tone={check.passed ? "green" : "amber"}>
                {check.passed ? "Passed" : "Needs attention"}
              </Badge>
            </div>
          ))}
        </div>
      )}
      {cases.length > 0 && (
        <details className="evaluation-details">
          <summary>
            Inspect {cases.length} evaluation cases
            <ChevronDown size={14} />
          </summary>
          <div className="evaluation-cases">
            {cases.map((item, i) => {
              const score = item.scores as {
                mean_before?: number;
                mean_after?: number;
                delta?: number;
              } | null;
              return (
                <details key={String(item.id || i)}>
                  <summary>
                    <span>{String(item.id || `Case ${i + 1}`)}</span>
                    <span>
                      {score
                        ? `${score.mean_before?.toFixed(2)} → ${score.mean_after?.toFixed(2)}`
                        : item.error
                          ? "Failed · unscored"
                          : isLive
                            ? "Unscored"
                            : "Mechanics only"}
                      <ChevronDown size={13} />
                    </span>
                  </summary>
                  <p className="case-brief">{String(item.brief || "")}</p>
                  {!!item.error && (
                    <p className="case-error">{String(item.error)}</p>
                  )}
                  <div className="case-drafts">
                    <div>
                      <h3>First draft</h3>
                      <p>{String(item.before || "Not available")}</p>
                    </div>
                    <div>
                      <h3>Refined draft</h3>
                      <p>{String(item.after || "Not available")}</p>
                    </div>
                  </div>
                </details>
              );
            })}
          </div>
        </details>
      )}
      <details className="evaluation-details">
        <summary>
          View saved report and limitations
          <ChevronDown size={14} />
        </summary>
        <pre>{JSON.stringify(evaluation, null, 2)}</pre>
      </details>
    </>
  );
}
function Modal({
  title,
  subtitle,
  children,
  onClose,
  error,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  onClose: () => void;
  error?: string;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
          "button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),a[href]",
        );
        if (!focusable?.length) return;
        const first = focusable[0],
          last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", listener);
    const prior = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prior;
      document.removeEventListener("keydown", listener);
    };
  }, [onClose]);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        className="modal"
      >
        <button
          className="icon-button modal-close"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
        <span className="icon-tile">
          <Star />
        </span>
        <h2 id="modal-title">{title}</h2>
        <p>{subtitle}</p>
        {error && (
          <div className="modal-error" role="alert">
            <CircleHelp size={15} />
            {error}
          </div>
        )}
        {children}
      </section>
    </div>
  );
}
function Submit({
  busy,
  children,
  disabled = false,
}: {
  busy: boolean;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <Button type="submit" kind="primary full" disabled={busy || disabled}>
      {busy ? <LoaderCircle size={15} className="spin" /> : <Check size={15} />}{" "}
      {children}
    </Button>
  );
}
function BrandForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (body: Record<string, unknown>) => Promise<unknown>;
}) {
  const [samples, setSamples] = useState("");
  return (
    <form
      className="form"
      onSubmit={(e) => {
        e.preventDefault();
        const values = new FormData(e.currentTarget);
        onSubmit({
          name: values.get("name"),
          description: values.get("description"),
          samples: samples
            .split(/\n\s*---\s*\n/)
            .map((t) => t.trim())
            .filter(Boolean)
            .map((text, i) => ({ text, source: `Writing sample ${i + 1}` })),
        });
      }}
    >
      <label>
        Brand name
        <input
          autoFocus
          required
          name="name"
          placeholder="Your name or brand"
          maxLength={100}
        />
      </label>
      <label>
        A short description
        <input
          required
          name="description"
          placeholder="e.g. Practical lessons from building AI products"
          maxLength={500}
        />
      </label>
      <label>
        Your writing samples
        <textarea
          value={samples}
          onChange={(e) => setSamples(e.target.value)}
          required
          rows={8}
          placeholder={
            "Paste your first writing sample here…\n\n---\n\nPaste your second writing sample here…\n\n---\n\nPaste your third writing sample here…"
          }
        />
        <small>
          Include at least three samples. Put --- on its own line between
          samples.
        </small>
      </label>
      <div className="form-info">
        <AudioLines size={15} />
        {samples.split(/\n\s*---\s*\n/).filter((s) => s.trim()).length}{" "}
        sample(s) detected
      </div>
      <Submit
        busy={busy}
        disabled={
          samples.split(/\n\s*---\s*\n/).filter((s) => s.trim()).length < 3
        }
      >
        Create brand
      </Submit>
    </form>
  );
}
function ImportForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (body: Record<string, unknown>) => Promise<unknown>;
}) {
  return (
    <form
      className="form"
      onSubmit={(e) => {
        e.preventDefault();
        const values = new FormData(e.currentTarget);
        onSubmit({
          title: values.get("title"),
          content: values.get("content"),
          hook: values.get("hook"),
          published_at: new Date(
            String(values.get("published_at")),
          ).toISOString(),
          source: "manual",
        });
      }}
    >
      <label>
        Post title
        <input
          required
          autoFocus
          name="title"
          placeholder="A short name to find this post later"
          maxLength={200}
        />
      </label>
      <label>
        Published content
        <textarea
          required
          minLength={20}
          maxLength={12000}
          name="content"
          rows={7}
          placeholder="Paste the post exactly as it was published…"
        />
      </label>
      <div className="form-row">
        <label>
          Opening style
          <select name="hook">
            {hooks.map((h) => (
              <option key={h} value={h}>
                {label(h)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Published at
          <input
            required
            type="datetime-local"
            name="published_at"
            defaultValue={localDate(new Date())}
          />
        </label>
      </div>
      <Submit busy={busy}>Import published post</Submit>
    </form>
  );
}
function localDate(d: Date) {
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
function ScheduleForm({
  post,
  busy,
  onSubmit,
}: {
  post: Post;
  busy: boolean;
  onSubmit: (value: string) => Promise<unknown>;
}) {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(9, 0, 0, 0);
  return (
    <form
      className="form"
      onSubmit={(e) => {
        e.preventDefault();
        const form = new FormData(e.currentTarget);
        onSubmit(new Date(String(form.get("time"))).toISOString());
      }}
    >
      <div className="form-post">
        <Linkedin size={20} />
        <strong>{post.title || post.brief}</strong>
      </div>
      <label>
        Publish date & time
        <input
          autoFocus
          required
          type="datetime-local"
          name="time"
          min={localDate(new Date())}
          defaultValue={localDate(
            post.scheduled_at ? new Date(post.scheduled_at) : tomorrow,
          )}
        />
        <small>
          {Intl.DateTimeFormat().resolvedOptions().timeZone} · saved in UTC
        </small>
      </label>
      <div className="form-info">
        <CalendarDays size={16} />
        Scheduling creates a ready-to-publish reminder in your queue.
      </div>
      <Submit busy={busy}>Save to publishing queue</Submit>
    </form>
  );
}
function FeedbackForm({
  post,
  source,
  busy,
  onSubmit,
}: {
  post: Post;
  source: Source;
  busy: boolean;
  onSubmit: (value: Feedback) => Promise<unknown>;
}) {
  const [feedbackSource, setFeedbackSource] = useState<Source>(
    post.feedback?.source || (post.is_demo ? "simulated" : source),
  );
  const [feedbackWindow, setFeedbackWindow] = useState(
    post.feedback?.window || "24h",
  );
  const observations =
    post.feedback_observations || (post.feedback ? [post.feedback] : []);
  const existing = observations.find(
    (f) => f.source === feedbackSource && f.window === feedbackWindow,
  );
  return (
    <form
      className="form"
      onSubmit={(e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const form = new FormData(e.currentTarget);
        onSubmit({
          impressions: Number(form.get("impressions")),
          reactions: Number(form.get("reactions")),
          comments: Number(form.get("comments")),
          reposts: Number(form.get("reposts")),
          source: feedbackSource,
          window: feedbackWindow,
        });
      }}
    >
      <div className="form-post">
        <FileText size={19} />
        <strong>{post.title || post.brief}</strong>
      </div>
      <div className="form-row">
        <label>
          Feedback source
          <select
            name="source"
            value={feedbackSource}
            onChange={(e) => setFeedbackSource(e.target.value as Source)}
          >
            <option value="manual" disabled={post.is_demo}>
              Real · manually entered
            </option>
            <option value="simulated">Simulated · demonstration</option>
          </select>
        </label>
        <label>
          Observation window
          <select
            name="window"
            value={feedbackWindow}
            onChange={(e) => setFeedbackWindow(e.target.value)}
          >
            <option value="24h">First 24 hours</option>
            <option value="7d">First 7 days</option>
          </select>
        </label>
      </div>
      <div className="form-row" key={`${feedbackSource}:${feedbackWindow}`}>
        {(["impressions", "reactions", "comments", "reposts"] as const).map(
          (field) => (
            <label key={field}>
              {label(field)}
              <input
                autoFocus={field === "impressions"}
                type="number"
                required
                min="0"
                max="1000000000000"
                step="1"
                name={field}
                defaultValue={existing?.[field] ?? 0}
              />
            </label>
          ),
        )}
      </div>
      <div className="form-info">
        <TrendingUp size={16} />
        Learning uses comments + reposts per 1,000 impressions. Reactions are
        stored for context.{" "}
        {existing
          ? "Saving updates this observation without double-counting it."
          : ""}
      </div>
      <Submit busy={busy}>Save performance feedback</Submit>
    </form>
  );
}
