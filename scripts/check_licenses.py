"""List the licenses of IDK Clips' runtime dependencies and flag incompatible ones.

    python scripts/check_licenses.py

IDK Clips is MIT licensed. Permissive licenses (MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0
for unmodified use, ...) are compatible. Strong copyleft licenses (GPL, AGPL) in a
dependency that ships with the project would not be; they make this script fail.
FFmpeg and Ollama are separate programs the user installs; they are not bundled.

Python packages are read from the active environment (install backend/requirements.txt
first). JavaScript packages are read from frontend/node_modules (run `npm ci` first);
only production dependencies of the web interface are checked.
"""

from __future__ import annotations

import json
import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"\b(A?GPL|GNU (Affero )?General Public)\b", re.IGNORECASE)
LGPL = re.compile(r"\bLGPL|Lesser General Public", re.IGNORECASE)


def python_licenses() -> dict[str, str]:
    found: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name") or "?"
        expression = dist.metadata.get("License-Expression") or ""
        classifiers = [
            c.split("::")[-1].strip()
            for c in dist.metadata.get_all("Classifier") or []
            if c.startswith("License ::")
        ]
        text = expression or "; ".join(classifiers) or (dist.metadata.get("License") or "")
        found[name] = " ".join(text.split())[:120] or "UNKNOWN"
    return found


def npm_licenses() -> dict[str, str]:
    lock = ROOT / "frontend" / "package-lock.json"
    if not lock.exists():
        return {}
    packages = json.loads(lock.read_text(encoding="utf-8")).get("packages", {})
    found: dict[str, str] = {}
    for path, info in packages.items():
        if not path or info.get("dev"):
            continue
        name = path.split("node_modules/")[-1]
        found[name] = str(info.get("license") or "UNKNOWN")
    return found


def main() -> int:
    failures: list[str] = []
    notes: list[str] = []
    for ecosystem, licenses in (("python", python_licenses()), ("npm", npm_licenses())):
        for name, text in sorted(licenses.items()):
            dual = " OR " in text or "/" in text
            if FORBIDDEN.search(text) and not LGPL.search(text) and not dual:
                failures.append(f"{ecosystem}: {name} ({text})")
            elif LGPL.search(text) or text == "UNKNOWN":
                notes.append(f"{ecosystem}: {name} ({text})")
        print(f"{ecosystem}: {len(licenses)} packages checked")
    for note in notes:
        print(f"  review: {note}")
    for failure in failures:
        print(f"  INCOMPATIBLE: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
