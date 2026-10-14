import { useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  ClipboardCheck,
  LoaderCircle,
  WandSparkles,
} from "lucide-react";
import { api } from "./api";
import type { BriefContract, ContractChecks, Platform } from "./api";

const numericFields = [
  ["min_words", "Minimum words"],
  ["max_words", "Maximum words"],
  ["max_characters", "Maximum characters"],
  ["min_bullets", "Minimum bullets"],
  ["max_bullets", "Maximum bullets"],
  ["max_hashtags", "Maximum hashtags"],
] as const;

export function contractError(contract: BriefContract): string {
  if (
    numericFields.some(
      ([key]) =>
        contract[key] != null &&
        (!Number.isInteger(contract[key]) || Number(contract[key]) < 0),
    )
  )
    return "Limits must be whole numbers of zero or more.";
  if (
    contract.min_words != null &&
    contract.max_words != null &&
    contract.min_words > contract.max_words
  )
    return "Minimum words must be less than or equal to maximum words.";
  if (
    contract.min_bullets != null &&
    contract.max_bullets != null &&
    contract.min_bullets > contract.max_bullets
  )
    return "Minimum bullets must be less than or equal to maximum bullets.";
  if (contract.max_characters != null && contract.max_characters < 100)
    return "Maximum characters must be at least 100.";
  const sections = (contract.required_sections || [])
    .map((value) => value.trim())
    .filter(Boolean);
  if (sections.length > 12 || sections.some((value) => value.length > 80))
    return "Use up to 12 section headings, each no longer than 80 characters.";
  const normalized = sections.map((value) =>
    value.replace(/:+$/, "").replace(/\s+/g, " ").toLowerCase(),
  );
  if (new Set(normalized).size !== normalized.length)
    return "Required section headings must be distinct.";
  return "";
}

export function BriefContractEditor({
  brief,
  platform,
  value,
  onChange,
  disabled = false,
}: {
  brief: string;
  platform: Platform;
  value: BriefContract;
  onChange: (value: BriefContract) => void;
  disabled?: boolean;
}) {
  const [suggesting, setSuggesting] = useState(false);
  const [notice, setNotice] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const current = useRef({ brief, platform, value });
  current.current = { brief, platform, value };
  const invalid = contractError(value);
  const count =
    numericFields.filter(([key]) => value[key] != null).length +
    (value.required_sections?.filter((value) => value.trim()).length || 0) +
    (value.plain_text ? 1 : 0);
  const suggest = async () => {
    const input = current.current;
    setSuggesting(true);
    setNotice("");
    setWarnings([]);
    try {
      const result = await api<{ contract: BriefContract; warnings: string[] }>(
        "/contracts/suggest",
        "POST",
        { brief, platform },
      );
      if (
        input.brief !== current.current.brief ||
        input.platform !== current.current.platform ||
        input.value !== current.current.value
      ) {
        setNotice(
          "Your brief or rules changed. Suggest again to use the current version.",
        );
        return;
      }
      onChange(result.contract);
      setWarnings(result.warnings || []);
      setNotice(
        "Suggested rules are ready. Review and adjust them before creating a draft.",
      );
    } catch (error) {
      setNotice((error as Error).message);
    } finally {
      setSuggesting(false);
    }
  };
  return (
    <details
      className="brief-contract"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <span>
          <ClipboardCheck size={15} /> Brief contract{" "}
          <small>
            {count ? `${count} explicit rules` : "Add checkable requirements"}
          </small>
        </span>
        <ChevronDown size={14} />
      </summary>
      <div className="contract-editor">
        <p>
          Set requirements the studio can measure. These rules are saved with
          the draft and checked again after every edit.
        </p>
        <button
          className="button quiet"
          type="button"
          disabled={disabled || suggesting || brief.trim().length < 10}
          onClick={suggest}
        >
          {suggesting ? (
            <LoaderCircle size={14} className="spin" />
          ) : (
            <WandSparkles size={14} />
          )}{" "}
          Suggest rules from brief
        </button>
        <p className="small muted">
          Suggestions use local parsing and make no AI request. Unrecognized
          instructions still need your review.
        </p>
        {notice && (
          <p className="feature-notice" role="status">
            {notice}
          </p>
        )}
        {!!warnings.length && (
          <ul className="feature-warnings">
            {warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        )}
        <div className="contract-fields">
          {numericFields.map(([key, title]) => (
            <label key={key}>
              {title}
              <input
                type="number"
                min="0"
                step="1"
                inputMode="numeric"
                value={value[key] ?? ""}
                disabled={disabled || suggesting}
                placeholder="No extra limit"
                onChange={(event) =>
                  onChange({
                    ...value,
                    [key]:
                      event.target.value === ""
                        ? null
                        : Number(event.target.value),
                  })
                }
              />
            </label>
          ))}
        </div>
        <label>
          Required section headings <small>One exact heading per line</small>
          <textarea
            rows={3}
            value={(value.required_sections || []).join("\n")}
            disabled={disabled || suggesting}
            placeholder={"The example\nThe trade-off\nTry this"}
            onChange={(event) =>
              onChange({
                ...value,
                required_sections: event.target.value.split("\n"),
              })
            }
          />
        </label>
        <label className="feature-checkbox">
          <input
            type="checkbox"
            checked={!!value.plain_text}
            disabled={disabled || suggesting}
            onChange={(event) =>
              onChange({ ...value, plain_text: event.target.checked })
            }
          />{" "}
          Plain text only
        </label>
        <p className="small muted">
          Platform limits still apply. Blank fields add no extra limit. Zero
          bullets or hashtags prohibits those items. Headings match whole lines;
          case, repeated spaces, and trailing colons are ignored.
        </p>
        {invalid && (
          <p className="feature-error" role="alert">
            {invalid}
          </p>
        )}
      </div>
    </details>
  );
}

function readable(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (value != null && typeof value === "object") return JSON.stringify(value);
  return value == null ? "—" : String(value);
}

export function BriefContractReport({
  contract,
  checks,
  pending = false,
}: {
  contract?: BriefContract;
  checks?: ContractChecks;
  pending?: boolean;
}) {
  if (!contract && !checks) return null;
  return (
    <section
      className={`contract-report ${checks?.passed === false && !pending ? "failed" : ""}`}
      aria-label="Draft contract checks"
    >
      <div className="section-title">
        <ClipboardCheck size={16} />
        <h3>Brief contract</h3>
        <span
          className={`badge ${checks?.passed === true ? "green" : "amber"}`}
        >
          {pending
            ? "In progress"
            : checks?.passed === true
              ? "All rules pass"
              : checks?.passed === false
                ? "Repair needed"
                : "Not checked"}
        </span>
      </div>
      {pending && (
        <p className="small muted">
          The draft is being written. These counts will update as each version
          is saved.
        </p>
      )}
      {checks?.checks?.length ? (
        <div className="contract-results">
          {checks.checks.map((check, index) => (
            <div key={`${check.key}:${index}`}>
              <span
                className={`contract-result-icon ${check.passed ? "pass" : "fail"}`}
              >
                {check.passed ? <Check size={13} /> : "!"}
              </span>
              <div>
                <strong>{check.label}</strong>
                <small>
                  Expected: {readable(check.expected)} · Actual:{" "}
                  {readable(check.actual)}
                </small>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="small muted">
          The saved rules have not been assessed for this version.
        </p>
      )}
      {checks?.passed === false && !pending && (
        <div className="contract-repair">
          <strong>Approval is paused until these rules pass.</strong>
          <p>
            Use Edit draft to repair the text. Saving checks the new version
            against the same rules.
          </p>
          {!!checks.violations?.length && (
            <ul>
              {checks.violations.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {checks?.scope && (
        <details className="feature-details">
          <summary>
            What these checks cover <ChevronDown size={13} />
          </summary>
          <p>{checks.scope}</p>
        </details>
      )}
    </section>
  );
}
