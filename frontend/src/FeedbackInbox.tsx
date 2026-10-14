import { useState } from "react";
import {
  Check,
  ChevronDown,
  Download,
  FileUp,
  Inbox,
  LoaderCircle,
  Search,
} from "lucide-react";
import { api, label } from "./api";
import type { Brand, Platform, Post, Source } from "./api";

const columns = [
  "post_id",
  "source_url",
  "published_at",
  "observed_at",
  "window",
  "window_start",
  "window_end",
  "impressions",
  "reactions",
  "comments",
  "reposts",
  "notes",
];
const aliases: Record<string, string> = {
  post_url: "source_url",
  url: "source_url",
  published_time: "published_at",
  measurement_time: "observed_at",
  measured_at: "observed_at",
  shares: "reposts",
};
// Read just the header so custom exports can be mapped before server validation.
function readHeaders(text: string): string[] {
  const input = text.replace(/^\uFEFF/, "");
  const result: string[] = [];
  let value = "",
    quoted = false;
  for (let index = 0; index < input.length; index++) {
    const character = input[index];
    if (character === '"') {
      if (quoted && input[index + 1] === '"') {
        value += '"';
        index++;
      } else quoted = !quoted;
    } else if (!quoted && (character === "\n" || character === "\r")) break;
    else if (!quoted && character === ",") {
      result.push(value);
      value = "";
    } else value += character;
    if (result.length > 30) return [];
  }
  result.push(value);
  return result
    .filter((item) => !!item.trim())
    .filter((item, index, all) => all.indexOf(item) === index);
}
function suggestedMapping(text: string): Record<string, string> {
  return Object.fromEntries(
    readHeaders(text).flatMap((column) => {
      const normalized = column
        .trim()
        .toLowerCase()
        .replace(/[\s-]+/g, "_");
      const key = aliases[normalized] || normalized;
      return columns.includes(key) ? [[key, column]] : [];
    }),
  );
}
interface ImportRow {
  row_number: number;
  post_id?: string;
  post_title?: string;
  status: "new" | "update" | "unchanged" | "invalid" | "duplicate";
  eligible: boolean;
  exclusion_reason?: string;
  errors: string[];
  observation?: Record<string, unknown>;
}
interface ImportPreview {
  id: string;
  columns: string[];
  mapping: Record<string, string>;
  rows: ImportRow[];
  summary: Record<string, number>;
  committed: boolean;
}
interface ImportResult extends ImportPreview {
  saved: number;
  updated: number;
  unchanged: number;
  skipped: number;
}

export default function FeedbackInbox({
  brand,
  platform,
  source,
  posts,
  onSaved,
  onImportPost,
}: {
  brand: Brand;
  platform: Platform;
  source: Source;
  posts: Post[];
  onSaved: () => Promise<unknown>;
  onImportPost: () => void;
}) {
  const [csv, setCsv] = useState("");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [previewDirty, setPreviewDirty] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const eligiblePosts = posts.filter(
    (post) =>
      (post.platform || "linkedin") === platform &&
      ["published", "published_manually"].includes(post.status) &&
      (source !== "manual" || !post.is_demo),
  );
  const writable = (preview?.summary.new || 0) + (preview?.summary.update || 0);
  const blocked = brand.is_demo && source === "manual";
  const headerColumns = readHeaders(csv);
  const changeCsv = (value: string) => {
    setCsv(value);
    setPreviewDirty(true);
    setResult(null);
    setMapping(suggestedMapping(value));
  };
  const loadFile = async (file?: File) => {
    if (!file) return;
    setError("");
    if (file.size > 1_000_000) {
      setError("Choose a CSV smaller than 1 MB.");
      return;
    }
    try {
      changeCsv(await file.text());
    } catch {
      setError("This file could not be read. Try pasting its CSV text.");
    }
  };
  const inspect = async () => {
    setBusy("preview");
    setError("");
    setResult(null);
    try {
      const next = await api<ImportPreview>(
        "/feedback-imports/preview",
        "POST",
        {
          brand_id: brand.id,
          platform,
          source,
          csv_text: csv,
          ...(Object.keys(mapping).length ? { mapping } : {}),
        },
      );
      setPreview(next);
      setMapping(next.mapping);
      setPreviewDirty(false);
    } catch (error) {
      setError((error as Error).message);
      setPreviewDirty(true);
    } finally {
      setBusy("");
    }
  };
  const commit = async () => {
    if (!preview || previewDirty || !writable) return;
    setBusy("commit");
    setError("");
    try {
      const saved = await api<ImportResult>(
        `/feedback-imports/${preview.id}/commit`,
        "POST",
        {},
      );
      setResult(saved);
      setPreview(saved);
      await onSaved();
    } catch (error) {
      setError((error as Error).message);
      setPreviewDirty(true);
    } finally {
      setBusy("");
    }
  };
  const template = async () => {
    setBusy("template");
    setError("");
    try {
      const value = await api<{ csv_text: string }>(
        "/feedback-imports/template",
      );
      const url = URL.createObjectURL(
        new Blob([value.csv_text], { type: "text/csv;charset=utf-8" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = "creatoros-feedback-template.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy("");
    }
  };
  return (
    <section
      className="card feature-card feedback-inbox"
      aria-label="Feedback import inbox"
    >
      <div className="section-heading">
        <div>
          <div className="feature-kicker">
            <Inbox size={16} /> FEEDBACK INBOX
          </div>
          <h2>Bring your results into the loop.</h2>
          <p className="muted small">
            Match CSV rows to published {label(platform)} posts in {brand.name}.
            Preview every change before saving.
          </p>
        </div>
        <div className="feature-actions">
          <button
            className="button quiet"
            disabled={!!busy}
            onClick={onImportPost}
          >
            Import a published post
          </button>
          <button className="button quiet" disabled={!!busy} onClick={template}>
            <Download size={14} /> CSV template
          </button>
        </div>
      </div>
      <div className="feature-scope">
        <span className={`badge ${source === "simulated" ? "amber" : "green"}`}>
          {source === "simulated" ? "Simulated metrics" : "Real metrics"}
        </span>
        <span>
          {label(platform)} · {brand.name}
        </span>
      </div>
      {blocked && (
        <p className="feature-error">
          Fictional workspaces accept simulated feedback only. Select Demo
          feedback above.
        </p>
      )}
      <div className="import-intake">
        <label className="file-drop">
          <FileUp size={22} />
          <strong>Choose a CSV file</strong>
          <span>UTF-8 CSV · up to 1 MB</span>
          <input
            type="file"
            accept=".csv,text/csv"
            aria-label="Upload feedback CSV"
            disabled={!!busy || blocked}
            onChange={(event) => {
              void loadFile(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </label>
        <label className="feature-field">
          Or paste CSV
          <textarea
            rows={6}
            value={csv}
            spellCheck={false}
            disabled={!!busy || blocked}
            placeholder="post_id,window,observed_at,impressions,reactions,comments,reposts"
            onChange={(event) => changeCsv(event.target.value)}
          />
        </label>
      </div>
      <p className="small muted">
        Use a post ID or its saved source URL. Real metrics need an observation
        time and a comparable window (24h or 7d) to inform learning. Ineligible
        observations remain available as records.
      </p>
      <details className="feature-details">
        <summary>
          Find published post IDs and URLs ({eligiblePosts.length}){" "}
          <ChevronDown size={14} />
        </summary>
        {eligiblePosts.length ? (
          <div className="import-post-hints">
            {eligiblePosts.map((post) => (
              <div key={post.id}>
                <strong>{post.title || post.brief}</strong>
                <code>{post.id}</code>
                {post.source_url && <span>{post.source_url}</span>}
                <small>
                  Published {post.published_at || "time unavailable"}
                </small>
              </div>
            ))}
          </div>
        ) : (
          <p>
            Import a published post from the section below first. This inbox
            adds metrics to existing posts.
          </p>
        )}
      </details>
      {!!headerColumns.length && (
        <details className="feature-details mapping-details" open>
          <summary>
            Map your columns <ChevronDown size={14} />
          </summary>
          <p className="small muted">
            Choose the source column for each field, then preview. Impressions
            and a post ID or source URL are required. Blank means this field is
            not supplied by the CSV.
          </p>
          <div className="mapping-grid">
            {columns.map((column) => (
              <label key={column}>
                {label(column)}
                <select
                  value={mapping[column] || ""}
                  disabled={!!busy || !!result}
                  onChange={(event) => {
                    setMapping({ ...mapping, [column]: event.target.value });
                    setPreviewDirty(true);
                  }}
                >
                  <option value="">Not provided</option>
                  {headerColumns.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        </details>
      )}
      <div className="feature-actions">
        <button
          className="button"
          disabled={!!busy || blocked || !csv.trim()}
          onClick={inspect}
        >
          {busy === "preview" ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <Search size={15} />
          )}
          {previewDirty && preview ? "Preview changes again" : "Preview import"}
        </button>
        <span className="small muted">
          Preview does not change your posts or metrics.
        </span>
      </div>
      {error && (
        <p className="feature-error" role="alert">
          {error}
        </p>
      )}
      {preview && (
        <div className="import-preview" aria-live="polite">
          <div className="feature-summary">
            {[
              "new",
              "update",
              "unchanged",
              "invalid",
              "duplicate",
              "eligible",
              "excluded",
            ].map((key) => (
              <div key={key}>
                <strong>{preview.summary[key] || 0}</strong>
                <span>{label(key)}</span>
              </div>
            ))}
          </div>
          {previewDirty && (
            <p className="feature-notice">
              This preview is out of date. Preview again before importing.
            </p>
          )}
          <div
            className="feature-table-scroll"
            tabIndex={0}
            aria-label="Feedback import preview"
          >
            <table className="feature-table">
              <thead>
                <tr>
                  <th>Row / post</th>
                  <th>Change</th>
                  <th>Learning eligibility</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => (
                  <tr key={row.row_number}>
                    <td>
                      <strong>
                        {row.row_number} ·{" "}
                        {row.post_title || row.post_id || "Unmatched post"}
                      </strong>
                      {row.post_id && <small>{row.post_id}</small>}
                    </td>
                    <td>
                      <span
                        className={`badge ${["invalid", "duplicate"].includes(row.status) ? "amber" : "neutral"}`}
                      >
                        {label(row.status)}
                      </span>
                    </td>
                    <td>
                      {["invalid", "duplicate"].includes(row.status)
                        ? "Skipped"
                        : row.eligible
                          ? "Eligible"
                          : "Stored; excluded"}
                    </td>
                    <td>
                      {row.errors?.map((item, index) => (
                        <p className="import-row-error" key={index}>
                          {item}
                        </p>
                      ))}
                      {row.exclusion_reason && <p>{row.exclusion_reason}</p>}
                      {row.observation && (
                        <details>
                          <summary>View observation</summary>
                          <dl>
                            {Object.entries(row.observation)
                              .filter(
                                ([, value]) =>
                                  value !== null &&
                                  value !== "" &&
                                  typeof value !== "object",
                              )
                              .map(([key, value]) => (
                                <div key={key}>
                                  <dt>{label(key)}</dt>
                                  <dd>{String(value)}</dd>
                                </div>
                              ))}
                          </dl>
                        </details>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result ? (
            <div className="feature-success" role="status">
              <Check size={17} />
              <span>
                Imported: {result.saved} new, {result.updated} updated,{" "}
                {result.unchanged} unchanged, {result.skipped} skipped. Update
                learnings when you are ready to save a new decision.
              </span>
            </div>
          ) : (
            <div className="feature-actions">
              <button
                className="button primary"
                disabled={!!busy || previewDirty || !writable || blocked}
                onClick={commit}
              >
                {busy === "commit" ? (
                  <LoaderCircle size={15} className="spin" />
                ) : (
                  <Check size={15} />
                )}
                Import {writable} valid row{writable === 1 ? "" : "s"}
              </button>
              <span className="small muted">
                Invalid and duplicate rows are skipped. Existing observations
                receive an auditable revision.
              </span>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
