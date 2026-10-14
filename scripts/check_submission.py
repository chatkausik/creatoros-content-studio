#!/usr/bin/env python3
"""Local, credential-safe submission preflight. Does not certify organizer CI."""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    source_dirs = [ROOT / "backend", ROOT / "scripts", ROOT / "tests"]
    py_files = [p for directory in source_dirs if directory.exists() for p in directory.rglob("*.py")]
    syntax_errors = []
    for path in py_files:
        try:
            ast.parse(path.read_text(), filename=str(path.relative_to(ROOT)))
        except (SyntaxError, UnicodeError) as exc:
            syntax_errors.append(f"{path.relative_to(ROOT)}:{getattr(exc, 'lineno', '?')}")
    checks.append(("Python syntax", bool(py_files) and not syntax_errors,
                   f"{len(py_files)} files inspected" if not syntax_errors else ", ".join(syntax_errors)))
    requirements = (ROOT / "requirements.txt").read_text() if (ROOT / "requirements.txt").exists() else ""
    checks.append(("Web framework + LLM client", bool(re.search(r"(?im)^fastapi\b|^flask\b", requirements))
                   and bool(re.search(r"(?im)^openai\b|^httpx\b|^meshapi\b", requirements)), "requirements.txt"))
    backend_source = "\n".join(p.read_text() for p in py_files if "backend" in p.parts)
    checks.append(("Mesh gateway configured", "api.meshapi.ai" in backend_source, "Static source inspection only"))
    checks.append(("README present", (ROOT / "README.md").is_file(), "Setup, architecture, evaluation"))
    ignore = (ROOT / ".gitignore").read_text() if (ROOT / ".gitignore").exists() else ""
    checks.append(("Local .env ignored", bool(re.search(r"(?m)^\.?/?\.env(?:\*|$|\n)", ignore)), ".gitignore"))
    workflow = ROOT / ".github/workflows/agent-arena-2026-checks.yml"
    checks.append(("Organizer workflow present", workflow.is_file(), str(workflow.relative_to(ROOT))))
    if workflow.is_file():
        text = workflow.read_text()
        checks.append(("Required CI secret references", all(secret in text for secret in ("MESH_API_KEY", "SUBMISSION_TOKEN")), "Checks names only, never values"))
    reports = [ROOT / "evals" / name / "results.json" for name in ("fresh-recovered", "fresh")]
    results_file = next((report for report in reports if report.is_file()), ROOT / "evals/results.json")
    if results_file.is_file():
        try:
            result = json.loads(results_file.read_text())
            summary = result.get("summary", {})
            cases = result.get("cases", [])
            valid = bool(cases) and len(cases) == summary.get("pairs") and result.get("mode") in {"fixture", "live"}
            checks.append(("Recorded evaluation", valid,
                           f"{results_file.relative_to(ROOT)}; mode: {result.get('mode', 'unknown')}; completed: {summary.get('completed_pairs', 0)}/{len(cases)}; quality-scored: {summary.get('scored_pairs', 0)}"))
        except (ValueError, TypeError):
            checks.append(("Recorded evaluation", False, "Invalid result JSON"))
    else:
        checks.append(("Recorded evaluation", False, "Run scripts/evaluate.py"))
    top = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    isolated_repo = top.returncode == 0 and Path(top.stdout.strip()).resolve() == ROOT.resolve()
    checks.append(("Project Git repository initialized", isolated_repo, "Repository root must be this project, not an ancestor directory"))
    if isolated_repo:
        git = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", ".env", ".env.*"], capture_output=True, text=True)
        tracked = [path for path in git.stdout.splitlines() if path not in {".env.example", ".env.sample"}]
        checks.append(("No tracked environment secrets", git.returncode == 0 and not tracked, "No secret values read"))
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'}  {name}: {detail}")
    print("INFO  Credential validity, public visibility, submitted commit, and organizer CI are not certified by this local check.")
    return 0 if all(passed for _, passed, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
