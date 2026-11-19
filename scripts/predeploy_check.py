"""Pre-deployment / pre-publication check for IDK Clips.

Run from the repository root with the backend's Python:

    backend/.venv/Scripts/python scripts/predeploy_check.py          (Windows)
    backend/.venv/bin/python scripts/predeploy_check.py              (Linux/macOS)
    ... --quick      only the file and secret checks (no tests or builds)

It never changes, deletes, pushes or deploys anything. It reports:

1. files that must not be published (.env files, keys, databases, media, credentials);
2. possible secrets in publishable files (detect-secrets);
3. lint, tests and production builds;
4. known vulnerabilities in dependencies (pip-audit, npm audit);
5. that the exported web interface contains no media files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
PYTHON = Path(sys.executable)

# Folders that are never published (all ignored by .gitignore).
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", ".next", "out", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", "data", "tools", ".claude", "dist", "build",
}  # fmt: skip
FORBIDDEN = [
    (re.compile(r"(^|/)\.env(\..+)?$"), "environment file"),
    (re.compile(r"\.env$"), "environment file"),
    (re.compile(r"\.(pem|key|p12|pfx)$", re.I), "private key or certificate"),
    (re.compile(r"(^|/)credentials[^/]*\.json$", re.I), "credentials file"),
    (re.compile(r"\.(db|sqlite3?|db-wal|db-shm)$", re.I), "database"),
    (re.compile(r"\.(mp4|mov|mkv|webm|avi|m4v|wav|mp3|m4a|aac|flac|ogg|opus)$", re.I), "media file"),
    (re.compile(r"\.(gguf|safetensors|ckpt|pt|pth|bin)$", re.I), "model weights"),
]
ALLOWED = re.compile(r"\.example$|(^|/)\.env\.example$")

results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool | None, detail: str = "") -> None:
    state = "PASS" if ok else ("SKIP" if ok is None else "FAIL")
    results.append((state, name, detail))
    print(f"[{state}] {name}{f' - {detail}' if detail else ''}", flush=True)


# Build artifacts that .gitignore excludes and that are never published.
SKIP_FILES = re.compile(r"\.tsbuildinfo$|(^|/)next-env\.d\.ts$|\.pyc$")
# Files .gitignore excludes from commits; reported as warnings when they are present.
GIT_IGNORED = re.compile(r"\.(mp4|mov|mkv|webm|avi|m4v|wav|mp3|m4a|aac|flac|ogg|opus|db|sqlite3?)$|(^|/)\.env$", re.I)


def git_files() -> list[Path] | None:
    """Files git would publish (tracked plus untracked, minus .gitignore), or None without git."""
    if not (ROOT / ".git").exists() or shutil.which("git") is None:
        return None
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=False,
        cwd=ROOT,
        capture_output=True,
        timeout=60,
    )
    if completed.returncode != 0:
        return None
    names = completed.stdout.decode("utf-8").split("\0")
    return [ROOT / name for name in names if name and (ROOT / name).is_file()]


def publishable_files() -> list[Path]:
    # In a git repository, .gitignore decides; it is what a push would publish.
    listed = git_files()
    if listed is not None:
        return [p for p in listed if not SKIP_FILES.search(p.relative_to(ROOT).as_posix())]
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if not SKIP_FILES.search(path.relative_to(ROOT).as_posix()):
                files.append(path)
    return files


def check_forbidden_files() -> None:
    problems, ignored = [], []
    for path in publishable_files():
        rel = path.relative_to(ROOT).as_posix()
        if ALLOWED.search(rel):
            continue
        for pattern, label in FORBIDDEN:
            if pattern.search(rel):
                (ignored if GIT_IGNORED.search(rel) else problems).append(f"{rel} ({label})")
                break
    record(
        "No secrets, databases or media among publishable files",
        not problems,
        "; ".join(problems[:15]) + (" ..." if len(problems) > 15 else ""),
    )
    if ignored:
        # Excluded by .gitignore (so not committed), but present: check before sharing the folder.
        results.append(("WARN", "Present but ignored by .gitignore", "; ".join(ignored[:15])))
        print(f"[WARN] Present but ignored by .gitignore - {'; '.join(ignored[:15])}", flush=True)


def run(name: str, command: list[str], cwd: Path, timeout: int = 1800) -> bool:
    executable = shutil.which(command[0]) if not Path(command[0]).is_absolute() else command[0]
    if executable is None:
        record(name, None, f"{command[0]} not found")
        return False
    try:
        completed = subprocess.run(
            [executable, *command[1:]],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        record(name, False, "timed out")
        return False
    tail = (completed.stdout + completed.stderr).strip().splitlines()[-3:]
    record(name, completed.returncode == 0, " | ".join(line.strip() for line in tail))
    return completed.returncode == 0


BASELINE = ROOT / ".secrets.baseline"


def scan_for_secrets(files: list[str]) -> dict[str, list[dict]]:
    """Run detect-secrets on an explicit list of files (in batches for long command lines)."""
    results: dict[str, list[dict]] = {}
    for start in range(0, len(files), 80):
        completed = subprocess.run(
            [str(PYTHON), "-m", "detect_secrets", "scan", *files[start : start + 80]],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip()[-300:])
        for name, items in json.loads(completed.stdout or "{}").get("results", {}).items():
            results[name.replace("\\", "/")] = items
    return results


def check_secrets() -> None:
    files = [
        p.relative_to(ROOT).as_posix()
        for p in publishable_files()
        if p.name not in {"package-lock.json", ".secrets.baseline"}
    ]
    try:
        findings = scan_for_secrets(files)
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        record("Secret scan (detect-secrets)", None, str(exc))
        return
    # `.secrets.baseline` lists findings a maintainer reviewed and marked as not secret
    # (placeholders such as user:password@host in examples). Anything else fails.
    reviewed: set[tuple[str, str]] = set()
    if BASELINE.is_file():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8")).get("results", {})
        reviewed = {
            (name.replace("\\", "/"), item["hashed_secret"])
            for name, items in baseline.items()
            for item in items
            if item.get("is_secret") is False
        }
    new = {
        name: [i for i in items if (name, i["hashed_secret"]) not in reviewed]
        for name, items in findings.items()
    }
    new = {name: items for name, items in new.items() if items}
    detail = ", ".join(
        f"{name}:{items[0]['line_number']} ({items[0]['type']})" for name, items in list(new.items())[:10]
    )
    record("Secret scan (detect-secrets)", not new, detail or f"{len(findings)} reviewed false positive file(s)")


def check_web_export() -> None:
    out = FRONTEND / "out"
    if not (out / "index.html").is_file():
        record("Exported web interface contains no media", None, "frontend/out not built")
        return
    media = [p.relative_to(out).as_posix() for p in out.rglob("*") if FORBIDDEN[5][0].search(p.name)]
    headers = (out / "_headers").is_file()
    record("Exported web interface contains no media", not media, ", ".join(media[:5]))
    record("Security headers file written (out/_headers)", headers)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true", help="Only the file and secret checks.")
    args = parser.parse_args()

    print(f"IDK Clips pre-deployment check in {ROOT}\n")
    check_forbidden_files()
    check_secrets()
    if not args.quick:
        run("Backend lint (ruff)", [str(PYTHON), "-m", "ruff", "check", "app", "tests"], BACKEND)
        run("Backend tests (pytest)", [str(PYTHON), "-m", "pytest", "-q", "-p", "no:cacheprovider"], BACKEND)
        run("Processing tests (pytest)", [str(PYTHON), "-m", "pytest", "-q", "-p", "no:cacheprovider"], ROOT / "processing")
        run("Python dependency audit (pip-audit)", [str(PYTHON), "-m", "pip_audit", "-r", "requirements.txt"], BACKEND)
        npm = "npm.cmd" if os.name == "nt" else "npm"
        run("Web lint (eslint)", [npm, "run", "lint"], FRONTEND)
        run("Web typecheck (tsc)", [npm, "run", "typecheck"], FRONTEND)
        run("Web tests (vitest)", [npm, "test"], FRONTEND)
        run("Web production build", [npm, "run", "build"], FRONTEND)
        run("npm dependency audit", [npm, "audit", "--omit=dev"], FRONTEND)
    check_web_export()

    failed = [r for r in results if r[0] == "FAIL"]
    skipped = [r for r in results if r[0] == "SKIP"]
    warned = [r for r in results if r[0] == "WARN"]
    passed = len(results) - len(failed) - len(skipped) - len(warned)
    print(f"\n{passed} passed, {len(failed)} failed, {len(warned)} warning(s), {len(skipped)} skipped.")
    print("This script does not push, publish or deploy anything.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
