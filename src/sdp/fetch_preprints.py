"""Fetch the CMS preprint listing and the preprint PDFs.

    python -m src.sdp.fetch_preprints manifest          # listing only, fast
    python -m src.sdp.fetch_preprints download          # PDFs, resumable
    python -m src.sdp.fetch_preprints download --limit 20

Two steps on purpose. The manifest is twelve requests and answers most questions
about coverage; the download is over a thousand files and a gigabyte or so. There
is no reason to make the second one a prerequisite for looking at the first.

This reads somebody's public web server. It rate limits, it caches, and it never
re-downloads a file whose content hash is unchanged. Re-running it after a CMS
update fetches only what is new.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.sdp.listing import BASE as BASE_HOST, listing_url, parse_listing

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "sdp"
PDF_DIR = RAW / "pdf"
MANIFEST = RAW / "manifest.json"

# medicaid.gov's robots.txt sets Crawl-delay: 1, so this matches it rather than
# choosing its own number. A government site does not need to be hammered by a
# portfolio project.
DELAY_SECONDS = 1.0
TIMEOUT = 60

# The conventional identified-crawler form. A bare descriptive string is refused
# with 403 by the site's edge, while this is accepted; curl and python-requests
# defaults are accepted too, so the block is on the string's shape rather than on
# automation. This names the project and gives somewhere to complain to, which a
# borrowed browser string would not.
USER_AGENT = (
    "Mozilla/5.0 (compatible; medicaid-finance-intelligence/0.1; "
    "+https://github.com/Himansh97/medicaid-finance-intelligence)"
)

# medicaid.gov/robots.txt contains "Disallow: /media/*", and roughly 7% of
# preprints are served from /media/file/. This fetcher honours that.
#
# The consequence is a real and declared coverage gap: those arrangements keep
# their full listing metadata (identifier, state, provider class, payment type,
# rating period, description) and lose only the PDF-derived fields, of which the
# Q4 total dollar amount is the one that matters.
#
# A person reading the site in a browser is not a crawler and is not bound by
# this. If a file is placed at its expected local path by hand, the pipeline
# picks it up and marks its provenance as manual, so the gap is closable without
# this code ignoring a published rule.
ROBOTS_DISALLOWED = ("/media/",)
ROBOTS_NOTE = "medicaid.gov/robots.txt disallows /media/*"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def fetch_manifest(session: requests.Session | None = None, max_pages: int = 60) -> dict:
    """Walk the listing and record every preprint it advertises.

    Stops when a page yields no identifier it has not already seen, rather than
    trusting a page count: the listing paginates server side and a wrong count
    would silently truncate the dataset.
    """
    session = session or _session()
    seen: dict[str, dict] = {}
    pages_read = 0

    for page in range(max_pages):
        response = session.get(listing_url(page=page), timeout=TIMEOUT)
        response.raise_for_status()
        pages_read += 1

        refs = parse_listing(response.text)
        new = {r.sdp_identifier: r.as_dict() for r in refs if r.sdp_identifier not in seen}
        if not new:
            break
        seen.update(new)
        time.sleep(DELAY_SECONDS)

    return {
        "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": listing_url(page=0),
        "pages_read": pages_read,
        "count": len(seen),
        "preprints": sorted(seen.values(), key=lambda r: r["sdp_identifier"]),
    }


def load_manifest() -> dict:
    if not MANIFEST.exists():
        raise SystemExit(f"no manifest at {MANIFEST}; run 'manifest' first")
    return json.loads(MANIFEST.read_text())


def _local_path(identifier: str) -> Path:
    # The identifier can carry a suffix with spaces and an apostrophe, so it is
    # not safe as a filename. Hashing keeps it deterministic and collision free.
    stem = hashlib.sha256(identifier.encode()).hexdigest()[:24]
    return PDF_DIR / f"{stem}.pdf"


def download_pdfs(manifest: dict, limit: int | None = None,
                  session: requests.Session | None = None) -> dict:
    """Download preprint PDFs, skipping any already held unchanged."""
    session = session or _session()
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    downloaded, cached, failed, excluded = 0, 0, [], 0
    entries = manifest["preprints"][:limit] if limit else manifest["preprints"]

    for entry in entries:
        target = _local_path(entry["sdp_identifier"])

        # A file already present is used whatever its origin. That is what lets a
        # person supply one of the robots-excluded PDFs by hand.
        if target.exists() and target.stat().st_size > 0:
            entry["content_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
            entry["local_path"] = str(target.relative_to(ROOT))
            entry["fetch_provenance"] = entry.get("fetch_provenance", "manual")
            entry.pop("excluded_reason", None)
            cached += 1
            continue

        path = entry["pdf_url"].replace(BASE_HOST, "")
        if any(path.startswith(prefix) for prefix in ROBOTS_DISALLOWED):
            entry["excluded_reason"] = ROBOTS_NOTE
            excluded += 1
            continue

        try:
            response = session.get(entry["pdf_url"], timeout=TIMEOUT)
            response.raise_for_status()
            # A listing link that serves HTML is a broken preprint, not a PDF.
            if not response.content.startswith(b"%PDF"):
                failed.append((entry["sdp_identifier"], "response is not a PDF"))
                continue
            target.write_bytes(response.content)
            entry["content_sha256"] = hashlib.sha256(response.content).hexdigest()
            entry["local_path"] = str(target.relative_to(ROOT))
            entry["retrieved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            entry["fetch_provenance"] = "fetched"
            downloaded += 1
        except requests.RequestException as exc:
            failed.append((entry["sdp_identifier"], str(exc)[:120]))
        time.sleep(DELAY_SECONDS)

    return {"downloaded": downloaded, "cached": cached,
            "excluded": excluded, "failed": failed}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=["manifest", "download"])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    RAW.mkdir(parents=True, exist_ok=True)

    if args.step == "manifest":
        manifest = fetch_manifest()
        MANIFEST.write_text(json.dumps(manifest, indent=1))
        parsed = sum(1 for p in manifest["preprints"] if p["identifier_parsed"])
        print(f"{manifest['count']} preprints across {manifest['pages_read']} pages")
        print(f"  identifier parsed cleanly: {parsed} "
              f"({100 * parsed / manifest['count']:.1f}%)")
        print(f"  written to {MANIFEST.relative_to(ROOT)}")
        return 0

    manifest = load_manifest()
    result = download_pdfs(manifest, limit=args.limit)
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    print(f"downloaded {result['downloaded']}, already held {result['cached']}, "
          f"excluded {result['excluded']}, failed {len(result['failed'])}")
    if result["excluded"]:
        print(f"  {result['excluded']} not fetched: {ROBOTS_NOTE}.")
        print("  Their listing metadata is kept; only PDF-derived fields are missing.")
        print("  Place a file at its expected path by hand and it will be used.")
    for identifier, reason in result["failed"][:10]:
        print(f"  FAILED {identifier}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
