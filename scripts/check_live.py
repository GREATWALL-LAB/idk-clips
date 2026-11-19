"""Check that the live website (and optionally the API) is up and correctly configured.

    python scripts/check_live.py https://idk-clips.vercel.app [https://api.example.com]

Checks: the homepage answers over HTTPS with security headers, the canonical URL and
sitemap use the production address, robots.txt and llms.txt exist, a documentation page
loads, and (with an API address) /api/v1/health reports "ok". Exits with code 1 on any
failure. Uses only the Python standard library, so it runs anywhere.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request

USER_AGENT = "IDKClips-uptime-check/1.0"
problems: list[str] = []


def fetch(url: str) -> tuple[int, dict[str, str], str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 (https only)
            body = response.read(2_000_000).decode("utf-8", "replace")
            return response.status, {k.lower(): v for k, v in response.headers.items()}, body
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, ""
    except (urllib.error.URLError, TimeoutError) as exc:
        problems.append(f"{url}: not reachable ({exc})")
        return 0, {}, ""


def check(condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


def check_site(site: str) -> None:
    site = site.rstrip("/")
    check(site.startswith("https://"), f"{site}: the website must use HTTPS")
    status, headers, html = fetch(f"{site}/")
    check(status == 200, f"homepage answered {status}")
    if status == 200:
        check("IDK Clips" in html, "homepage does not mention IDK Clips")
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', html)
        check(
            bool(canonical) and canonical.group(1).rstrip("/") == site,
            f"homepage canonical is {canonical.group(1) if canonical else 'missing'}",
        )
        check(
            "application/ld+json" in html, "homepage has no structured data (JSON-LD)"
        )
        for header in ("strict-transport-security", "x-content-type-options"):
            check(header in headers, f"homepage is missing the {header} header")
    status, _, robots = fetch(f"{site}/robots.txt")
    check(status == 200 and f"{site}/sitemap.xml" in robots, "robots.txt missing or wrong")
    status, _, sitemap = fetch(f"{site}/sitemap.xml")
    check(status == 200 and f"<loc>{site}/</loc>" in sitemap, "sitemap.xml missing or wrong")
    status, _, _ = fetch(f"{site}/llms.txt")
    check(status == 200, "llms.txt missing")
    status, _, doc = fetch(f"{site}/docs/installation/")
    check(status == 200 and "<h1" in doc, "documentation page did not load")


def check_api(api: str) -> None:
    status, headers, body = fetch(f"{api.rstrip('/')}/api/v1/health")
    check(status == 200, f"API health answered {status}")
    if status == 200:
        try:
            check(json.loads(body).get("status") == "ok", "API health is not ok")
        except ValueError:
            problems.append("API health did not return JSON")
        check("no-store" in headers.get("cache-control", ""), "API responses are cacheable")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    check_site(argv[0])
    if len(argv) > 1:
        check_api(argv[1])
    if problems:
        for problem in problems:
            print(f"FAIL {problem}")
        return 1
    print(f"OK   {', '.join(argv)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
