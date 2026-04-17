"""
ArquivoPT2026 — Mass Extraction Pipeline
=========================================
Queries the Arquivo.pt CDX API for multiple domains, filters results
from a given start date, and exports all records to a CSV file.

API reference: https://arquivo.pt/api
"""

import csv
import json
import logging
import os
import sys
import time
from datetime import datetime

import requests

# ---------------------------------------------------------------------------
# Logging setup — clean timestamped output to stdout
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("arquivopt")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CDX_ENDPOINT = "https://arquivo.pt/wayback/cdx"

DOMAINS = [
    "cm-penamacor.pt",
    "jornaldofundao.pt",
]

BASE_PARAMS = {
    "matchType": "domain",
    "output":    "json",
    "fl":        "timestamp,statuscode,original",
    "from":      "20100101",
    "limit":     50,
}

OUTPUT_FILE = "dados_extraidos_teste.csv"
CSV_FIELDS  = ["Domain", "Timestamp", "StatusCode", "URL"]

# ---------------------------------------------------------------------------
# Helper: fetch one domain
# ---------------------------------------------------------------------------
def fetch_domain(domain: str, session: requests.Session) -> list[dict]:
    """
    Query the CDX API for *domain* and return a list of record dicts.

    The server returns NDJSON — one JSON object per line, e.g.:
        {"timestamp": "20150312103045", "statuscode": "200", "original": "http://..."}

    Lines that are empty or cannot be parsed as a JSON object are skipped
    with a warning.  If the first line happens to be an array (header row
    from an alternative CDX mode), it is also skipped.
    """
    params = {**BASE_PARAMS, "url": domain}
    records: list[dict] = []

    response = session.get(CDX_ENDPOINT, params=params, timeout=20)
    response.raise_for_status()

    raw_text = response.text.strip()
    if not raw_text:
        log.warning("  [%s] API returned an empty body.", domain)
        return records

    lines = raw_text.splitlines()
    skipped = 0

    for line_no, line in enumerate(lines, start=1):
        line = line.strip()

        # Skip blank lines
        if not line:
            skipped += 1
            continue

        # Parse JSON
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            log.warning("  [%s] Line %d — not valid JSON, skipped: %.80s",
                        domain, line_no, line)
            skipped += 1
            continue

        # Skip header rows (arrays) that some CDX modes emit as line 0
        if isinstance(obj, list):
            log.debug("  [%s] Line %d — array (header row), skipped.", domain, line_no)
            skipped += 1
            continue

        # Build normalised record
        records.append({
            "Domain":     domain,
            "Timestamp":  obj.get("timestamp", ""),
            "StatusCode": obj.get("statuscode", ""),
            "URL":        obj.get("original",   ""),
        })

    log.info("  [%s] %d record(s) parsed  |  %d line(s) skipped.",
             domain, len(records), skipped)
    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    banner = "=" * 60
    log.info(banner)
    log.info("  ArquivoPT2026 — Mass Extraction Pipeline")
    log.info("  Started  : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("  Domains  : %d", len(DOMAINS))
    log.info("  Output   : %s", OUTPUT_FILE)
    log.info(banner)

    all_records: list[dict] = []
    failed_domains: list[str] = []

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})

        for idx, domain in enumerate(DOMAINS, start=1):
            log.info("")
            log.info("(%d/%d) Fetching → %s", idx, len(DOMAINS), domain)

            try:
                domain_records = fetch_domain(domain, session)
                all_records.extend(domain_records)

            except requests.exceptions.ConnectionError:
                log.error("  [%s] Connection failed. Check your network.", domain)
                failed_domains.append(domain)

            except requests.exceptions.Timeout:
                log.error("  [%s] Request timed out (>20 s).", domain)
                failed_domains.append(domain)

            except requests.exceptions.HTTPError as exc:
                log.error("  [%s] HTTP error: %s", domain, exc)
                failed_domains.append(domain)

            except Exception as exc:  # noqa: BLE001
                log.error("  [%s] Unexpected error: %s", domain, exc)
                failed_domains.append(domain)

            # Polite delay between requests
            if idx < len(DOMAINS):
                time.sleep(0.5)

    # -----------------------------------------------------------------------
    # Export to CSV
    # -----------------------------------------------------------------------
    log.info("")
    log.info("Writing CSV → %s", OUTPUT_FILE)

    try:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(all_records)
    except OSError as exc:
        log.error("Could not write CSV: %s", exc)
        sys.exit(1)

    abs_path = os.path.abspath(OUTPUT_FILE)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    log.info("")
    log.info(banner)
    log.info("  EXTRACTION COMPLETE")
    log.info(banner)
    log.info("  Total records saved : %d", len(all_records))
    log.info("  CSV file            : %s", abs_path)
    log.info("  Domains succeeded   : %d / %d",
             len(DOMAINS) - len(failed_domains), len(DOMAINS))

    if failed_domains:
        log.warning("  Domains with errors : %s", ", ".join(failed_domains))

    log.info(banner)


if __name__ == "__main__":
    main()
