import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  ChevronDown,
  FlaskConical,
  History,
  LoaderCircle,
  Plus,
  RefreshCw,
} from "lucide-react";
import { api, date, label } from "./api";
import type {
  Brand,
  BriefContract,
  Hook,
  Mode,
  Platform,
  Run,
  Source,
} from "./api";
import { contractError } from "./BriefContract";

interface Slot {
  id: string;
  ordinal: number;
  hook: Hook;
  run_id?: string;
  post_id?: string;
  status: string;
  reason?: string;
  post_title?: string;
}
interface Analysis {
  id: string;
  version: number;
  created_at: string;
  status: string;
  preferred_hook?: Hook | null;
  stats?: {
    hook: Hook;
    posts: number;
    impressions: number;
    rate: number | null;
    interval?: [number, number];
  }[];
  evidence?: {
    post_id?: string;
    post_title?: string;
    hook?: Hook;
    opening?: string;
    observation_id?: string;
  }[];
  excluded?: { post_id?: string; reason: string }[];
  explanation?: string;
  uncertainty_note?: string;
}
interface Comparison {
  id: string;
  brief: string;
  registered_at: string;
  policy_contrast?: boolean;
  note?: string;
  mode: Mode;
  model_preset?: string | null;
  contract: BriefContract;
  branches: {
    id: string;
    condition: string;
    hook: Hook;
    run_id?: string;
    post_id?: string;
    status: string;
    opening?: string;
    content?: string;
  }[];
}
interface Experiment {
  id: string;
  name: string;
  hypothesis: string;
  brand_id: string;
  platform: Platform;
  source: Source;
  window: string;
  slots_per_hook: number;
  metric: string;
  profile_version: number;
  registered_at: string;
  slots: Slot[];
  counts: Record<string, number>;
  latest_analysis?: Analysis | null;
  analyses: Analysis[];
  limitations: string[];
  comparison?: Comparison | null;
}

const cleanContract = (contract: BriefContract): BriefContract => ({
  ...contract,
  required_sections: (contract.required_sections || [])
    .map((value) => value.trim())
    .filter(Boolean),
});

export default function ExperimentLab({
  brand,
  platform,
  source,
  windowValue,
  mode,
  modelPreset,
  contract,
  onOpenRun,
  onOpenPost,
  onSaved,
  onModeChange,
}: {
  brand: Brand;
  platform: Platform;
  source: Source;
  windowValue: string;
  mode: Mode;
  modelPreset: string;
  contract: BriefContract;
  onOpenRun: (run: Run) => void;
  onOpenPost: (id: string) => void;
  onSaved: () => Promise<unknown>;
  onModeChange: (mode: Mode) => void;
}) {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [analysisId, setAnalysisId] = useState("");
  const [historicalAnalysis, setHistoricalAnalysis] = useState<Analysis | null>(
    null,
  );
  const [name, setName] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [slotCount, setSlotCount] = useState(3);
  const [brief, setBrief] = useState("");
  const [comparisonBrief, setComparisonBrief] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const experiment =
    experiments.find((item) => item.id === selectedId) || experiments[0];
  const analysis =
    historicalAnalysis?.id === analysisId
      ? historicalAnalysis
      : experiment?.latest_analysis;
  const modeMatches =
    !experiment ||
    (mode === "demo"
      ? experiment.source === "simulated"
      : experiment.source === "manual");
  const invalidContract = contractError(contract);
  const load = useCallback(async () => {
    const values = await api<Experiment[]>(
      `/experiments?brand_id=${encodeURIComponent(brand.id)}`,
    );
    setExperiments(values);
    return values;
  }, [brand.id]);
  useEffect(() => {
    let cancelled = false;
    api<Experiment[]>(`/experiments?brand_id=${encodeURIComponent(brand.id)}`)
      .then((values) => {
        if (!cancelled) setExperiments(values);
      })
      .catch((error) => {
        if (!cancelled) setError(error.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [brand.id]);
  const perform = async (key: string, work: () => Promise<void>) => {
    setBusy(key);
    setError("");
    setNotice("");
    try {
      await work();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy("");
    }
  };
  const request = (text: string) => ({
    brief: text.trim(),
    mode,
    generate_image: false,
    ...(modelPreset ? { model_preset: modelPreset } : {}),
    contract: cleanContract(contract),
  });
  const create = async () =>
    perform("create", async () => {
      const created = await api<Experiment>("/experiments", "POST", {
        brand_id: brand.id,
        name: name.trim(),
        hypothesis: hypothesis.trim(),
        platform,
        source,
        window: windowValue,
        slots_per_hook: slotCount,
      });
      await load();
      setSelectedId(created.id);
      setAnalysisId("");
      setName("");
      setHypothesis("");
      setNotice(
        "Experiment registered. Its hypothesis, scope, opening assignments, and voice profile are frozen.",
      );
    });
  const launch = async (slot: Slot) =>
    perform(slot.id, async () => {
      if (!experiment) return;
      const run = await api<Run>(
        `/experiments/${experiment.id}/slots/${slot.id}/run`,
        "POST",
        request(brief),
      );
      await load();
      await onSaved();
      onOpenRun(run);
    });
  const saveAnalysis = async () =>
    perform("analyze", async () => {
      if (!experiment) return;
      const result = await api<Analysis>(
        `/experiments/${experiment.id}/analyze`,
        "POST",
        {},
      );
      await load();
      setAnalysisId(result.id);
      setNotice(
        "Analysis saved with the exact observations available now. Earlier analyses remain unchanged.",
      );
    });
  const compare = async () =>
    perform("compare", async () => {
      if (!experiment) return;
      const saved = experiment.comparison;
      try {
        await api(
          `/experiments/${experiment.id}/comparisons`,
          "POST",
          saved
            ? {
                brief: saved.brief,
                mode: saved.mode,
                model_preset: saved.model_preset,
                contract: saved.contract,
                generate_image: false,
              }
            : request(comparisonBrief),
        );
      } finally {
        await load();
      }
      await onSaved();
      setNotice(
        "Matched drafts started. Refresh the experiment to see their saved openings, or open a branch to follow its run.",
      );
    });
  const selectAnalysis = async (id: string) =>
    perform("history", async () => {
      if (!experiment) return;
      const saved = await api<Analysis>(
        `/experiments/${experiment.id}/analyses/${id}`,
      );
      setHistoricalAnalysis(saved);
      setAnalysisId(saved.id);
    });
  const scope = `${label(platform)} · ${source === "manual" ? "Real metrics" : "Simulated metrics"} · ${windowValue}`;
  return (
    <section
      className="card feature-card experiment-lab"
      aria-label="Experiment Lab"
    >
      <div className="section-heading">
        <div>
          <div className="feature-kicker">
            <FlaskConical size={16} /> EXPERIMENT LAB
          </div>
          <h2>Make a prediction. Then follow the evidence.</h2>
          <p className="muted small">
            Register a balanced opening-style experiment before collecting
            results. Every planned slot stays visible, including failures and
            exclusions.
          </p>
        </div>
      </div>
      <details className="feature-details" open={!experiments.length}>
        <summary>
          <span>
            <Plus size={14} /> Register an experiment
          </span>
          <ChevronDown size={14} />
        </summary>
        <form
          className="experiment-register"
          onSubmit={(event) => {
            event.preventDefault();
            void create();
          }}
        >
          <div className="feature-scope">
            <span className="badge">{scope}</span>
            <span>{brand.name}</span>
          </div>
          <label>
            Experiment name
            <input
              required
              minLength={3}
              maxLength={120}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Which opening earns a thoughtful response?"
            />
          </label>
          <label>
            Hypothesis
            <textarea
              required
              minLength={10}
              maxLength={1200}
              rows={3}
              value={hypothesis}
              onChange={(event) => setHypothesis(event.target.value)}
              placeholder="I expect problem-first openings to earn more comments and reposts per 1,000 impressions because they make the reader's challenge concrete."
            />
          </label>
          <div className="experiment-register-footer">
            <label>
              Posts per opening style
              <select
                value={slotCount}
                onChange={(event) => setSlotCount(Number(event.target.value))}
              >
                {[1, 2, 3, 4, 5, 6, 8, 10].map((count) => (
                  <option key={count} value={count}>
                    {count} each · {count * 3} total
                  </option>
                ))}
              </select>
            </label>
            <button
              className="button primary"
              type="submit"
              disabled={
                !!busy ||
                (brand.is_demo && source === "manual") ||
                !brand.profile
              }
            >
              {busy === "create" ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <FlaskConical size={15} />
              )}
              Register fixed plan
            </button>
          </div>
          <p className="small muted">
            Registration makes no AI request. All three opening styles receive
            the same number of randomly ordered slots. The metric is fixed:
            comments + reposts per 1,000 impressions. Your current voice profile
            is captured.
          </p>
          {!brand.profile && (
            <p className="feature-notice">
              Extract a brand voice before registering an experiment.
            </p>
          )}
        </form>
      </details>
      {error && (
        <p className="feature-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="feature-success" role="status">
          {notice}
        </p>
      )}
      {loading && (
        <p className="small muted">
          <LoaderCircle size={14} className="spin" /> Loading registered
          experiments…
        </p>
      )}
      {experiment && (
        <div className="experiment-workspace">
          <div className="experiment-picker">
            <label>
              Registered experiment
              <select
                value={experiment.id}
                onChange={(event) => {
                  setSelectedId(event.target.value);
                  setAnalysisId("");
                  setBrief("");
                  setComparisonBrief("");
                }}
              >
                {experiments.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} ·{" "}
                    {item.source === "simulated" ? "Demo" : "Real"}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="button quiet"
              disabled={!!busy}
              onClick={() =>
                perform("refresh", async () => {
                  await load();
                })
              }
            >
              <RefreshCw
                size={14}
                className={busy === "refresh" ? "spin" : ""}
              />
              Refresh
            </button>
          </div>
          <div className="registered-hypothesis">
            <span className="feature-kicker">
              REGISTERED {date(experiment.registered_at)}
            </span>
            <h3>{experiment.name}</h3>
            <p>{experiment.hypothesis}</p>
            <div className="feature-scope">
              <span
                className={`badge ${experiment.source === "simulated" ? "amber" : "green"}`}
              >
                {experiment.source === "simulated"
                  ? "Simulated experiment"
                  : "Real observations"}
              </span>
              <span>
                {label(experiment.platform)} · {experiment.window} · Voice v
                {experiment.profile_version} · {experiment.slots.length} planned
                posts
              </span>
            </div>
            <small>{experiment.metric}</small>
          </div>
          <div className="feature-summary experiment-counts">
            {Object.entries(experiment.counts || {}).map(([key, value]) => (
              <div key={key}>
                <strong>{value}</strong>
                <span>{label(key)}</span>
              </div>
            ))}
          </div>
          <label className="feature-field">
            Brief for the next assigned post
            <textarea
              rows={3}
              maxLength={6000}
              value={brief}
              onChange={(event) => setBrief(event.target.value)}
              placeholder="Write the topic and the useful takeaway. The registered slot determines the opening style."
            />
          </label>
          <div className="feature-scope">
            <label>
              Experiment generation mode
              <select
                value={mode}
                disabled={!!busy}
                onChange={(event) => onModeChange(event.target.value as Mode)}
              >
                <option value="demo">Demo fixture · free</option>
                <option value="live">Live · paid Mesh requests</option>
              </select>
            </label>
            <span>
              {modelPreset
                ? `${label(modelPreset)} model preset`
                : "Configured model"}{" "}
              · Current studio brief contract applies
            </span>
          </div>
          {!modeMatches && (
            <p className="feature-notice">
              {experiment.source === "manual"
                ? "Choose Live mode above to create posts for this real-metrics experiment."
                : "Choose Demo fixture mode above to create posts for this simulated experiment."}
            </p>
          )}
          {invalidContract && (
            <p className="feature-error">
              Fix the studio brief contract first: {invalidContract}
            </p>
          )}
          <div className="experiment-slots">
            {experiment.slots.map((slot) => (
              <div className="experiment-slot" key={slot.id}>
                <div className="slot-number">
                  {String(slot.ordinal).padStart(2, "0")}
                </div>
                <div>
                  <strong>{label(slot.hook)}</strong>
                  <span className="small muted">
                    {slot.post_title || "Assigned before results"}
                  </span>
                  {slot.reason && <p className="small muted">{slot.reason}</p>}
                </div>
                <span
                  className={`badge ${slot.status === "eligible" ? "green" : "neutral"}`}
                >
                  {label(slot.status)}
                </span>
                {slot.post_id ? (
                  <button
                    className="button quiet"
                    onClick={() => onOpenPost(slot.post_id!)}
                  >
                    Open draft <ArrowRight size={14} />
                  </button>
                ) : (
                  <button
                    className="button quiet"
                    disabled={
                      !!busy ||
                      brief.trim().length < 10 ||
                      !modeMatches ||
                      !!invalidContract
                    }
                    onClick={() => launch(slot)}
                  >
                    {busy === slot.id ? (
                      <LoaderCircle size={14} className="spin" />
                    ) : (
                      <Plus size={14} />
                    )}
                    {mode === "demo"
                      ? "Create demo draft"
                      : "Create live draft"}
                  </button>
                )}
              </div>
            ))}
          </div>
          <div className="feature-actions">
            <button className="button" disabled={!!busy} onClick={saveAnalysis}>
              {busy === "analyze" ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <FlaskConical size={15} />
              )}
              Save evidence analysis
            </button>
            <span className="small muted">
              Only comparable observations from assigned posts enter the
              analysis. No automatic publishing.
            </span>
          </div>
          {analysis && (
            <div className="experiment-analysis">
              <div className="section-heading">
                <div>
                  <h3>Evidence at this checkpoint</h3>
                  <p className="small muted">
                    {date(analysis.created_at)} · {label(analysis.status)}
                  </p>
                </div>
                <label className="analysis-history">
                  <History size={14} />
                  <span className="sr-only">Analysis history</span>
                  <select
                    value={analysis.id}
                    disabled={!!busy}
                    onChange={(event) => selectAnalysis(event.target.value)}
                  >
                    {experiment.analyses.map((item) => (
                      <option key={item.id} value={item.id}>
                        Analysis v{item.version} · {date(item.created_at)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p>
                {analysis.explanation ||
                  "This saved checkpoint preserves the evidence available at the time."}
              </p>
              {analysis.stats && (
                <div className="experiment-stats">
                  {analysis.stats.map((stat) => (
                    <div key={stat.hook}>
                      <span>{label(stat.hook)}</span>
                      <strong>
                        {stat.rate == null ? "—" : stat.rate.toFixed(1)}{" "}
                        <small>/ 1k</small>
                      </strong>
                      <small>
                        {stat.posts} posts · {stat.impressions.toLocaleString()}{" "}
                        impressions
                      </small>
                      {stat.interval && (
                        <small>
                          90% descriptive range: {stat.interval[0].toFixed(1)}–
                          {stat.interval[1].toFixed(1)}
                        </small>
                      )}
                    </div>
                  ))}
                </div>
              )}
              <p className="small muted">
                {analysis.uncertainty_note ||
                  "These are descriptive observations. Posting time, topic, audience, and reach may differ; this is not a causal estimate."}
              </p>
              {!!analysis.excluded?.length && (
                <details className="feature-details">
                  <summary>
                    Excluded observations ({analysis.excluded.length}){" "}
                    <ChevronDown size={14} />
                  </summary>
                  <ul className="feature-warnings">
                    {analysis.excluded.map((item, index) => (
                      <li key={index}>
                        {item.post_id && <code>{item.post_id}: </code>}
                        {item.reason}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {!!analysis.evidence?.length && (
                <details className="feature-details">
                  <summary>
                    Frozen observations ({analysis.evidence.length}){" "}
                    <ChevronDown size={14} />
                  </summary>
                  <div className="experiment-evidence">
                    {analysis.evidence.map((item, index) => (
                      <div key={item.observation_id || index}>
                        <strong>{item.post_title || item.post_id}</strong>
                        <span>{label(item.hook)}</span>
                        {item.opening && (
                          <blockquote>{item.opening}</blockquote>
                        )}
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}
          <details className="feature-details matched-comparison">
            <summary>
              <span>
                <FlaskConical size={15} /> Matched learning on / off drafts
              </span>
              <ChevronDown size={14} />
            </summary>
            <p className="small muted">
              Freeze one brief, voice, contract, and model setup, then generate
              both branches using the learning snapshot captured at
              registration. This shows the policy's effect on a draft; it does
              not measure audience uplift.
            </p>
            {!experiment.comparison ? (
              <>
                <label className="feature-field">
                  Shared comparison brief
                  <textarea
                    rows={3}
                    maxLength={6000}
                    value={comparisonBrief}
                    onChange={(event) => setComparisonBrief(event.target.value)}
                    placeholder="Use the exact same brief for both branches."
                  />
                </label>
                <div className="feature-actions">
                  <button
                    className="button"
                    disabled={
                      !!busy ||
                      comparisonBrief.trim().length < 10 ||
                      !modeMatches ||
                      !!invalidContract
                    }
                    onClick={compare}
                  >
                    {busy === "compare" ? (
                      <LoaderCircle size={15} className="spin" />
                    ) : (
                      <FlaskConical size={15} />
                    )}
                    Create{" "}
                    {mode === "demo" ? "two demo drafts" : "two live drafts"}
                  </button>
                  <span className="small muted">
                    {mode === "demo"
                      ? "Free deterministic fixtures."
                      : "Starts two paid Mesh generation runs; images are off."}{" "}
                    One fixed pair per experiment.
                  </span>
                </div>
              </>
            ) : (
              <>
                <div className="registered-hypothesis">
                  <p>{experiment.comparison.brief}</p>
                  <small>
                    Frozen {date(experiment.comparison.registered_at)}
                  </small>
                </div>
                {experiment.comparison.note && (
                  <p className="small muted">{experiment.comparison.note}</p>
                )}
                {experiment.comparison.branches.some(
                  (branch) => !branch.post_id,
                ) && (
                  <div className="feature-actions">
                    <button
                      className="button"
                      disabled={!!busy}
                      onClick={compare}
                    >
                      {busy === "compare" ? (
                        <LoaderCircle size={15} className="spin" />
                      ) : (
                        <RefreshCw size={15} />
                      )}
                      Continue saved comparison
                    </button>
                    <span className="small muted">
                      Uses its original{" "}
                      {experiment.comparison.mode === "demo"
                        ? "free demo"
                        : "paid Mesh"}{" "}
                      settings and preserves branches already created.
                    </span>
                  </div>
                )}
                {experiment.comparison.branches.length === 2 &&
                  experiment.comparison.branches[0].hook ===
                    experiment.comparison.branches[1].hook && (
                    <p className="feature-notice">
                      Both branches selected the same opening style. This pair
                      does not identify a contrast between opening policies.
                    </p>
                  )}
                <div className="comparison-branches">
                  {experiment.comparison.branches.map((branch) => (
                    <article key={branch.id}>
                      <span className="feature-kicker">
                        {label(branch.condition)}
                      </span>
                      <h3>{label(branch.hook)}</h3>
                      <span className="badge">{label(branch.status)}</span>
                      <blockquote>
                        {branch.opening ||
                          "Opening appears after generation. Refresh to load progress."}
                      </blockquote>
                      {branch.post_id && (
                        <button
                          className="text-button"
                          onClick={() => onOpenPost(branch.post_id!)}
                        >
                          Open saved draft <ArrowRight size={13} />
                        </button>
                      )}
                    </article>
                  ))}
                </div>
              </>
            )}
          </details>
          {!!experiment.limitations?.length && (
            <details className="feature-details">
              <summary>
                How to read this experiment <ChevronDown size={14} />
              </summary>
              <ul className="feature-warnings">
                {experiment.limitations.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
