"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           CASSANDRA ENGINE — PHASE 2 ADVANCED EXTRACTOR                    ║
║           extrator_fase2_avancado.py                                        ║
║           Extracts live HTTP status + Arquivo.pt CDX capture counts         ║
║           for 308 Portuguese municipalities (2011–2021).                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import csv
import os
import time

import requests
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

INPUT_FILE  = "municipios_dominios.csv"   # Columns: Município, Domain
OUTPUT_FILE = "metricas_fase2_avancadas.csv"

ARQUIVO_CDX_URL = "https://arquivo.pt/wayback/cdx"
CDX_FROM        = "20110101"
CDX_TO          = "20211231"

REQUEST_TIMEOUT = 10  # seconds
SLEEP_BETWEEN   = 1   # seconds — ethical rate-limiting

# Standard Chrome/Windows User-Agent to bypass basic bot-detection
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ──────────────────────────────────────────────────────────────────────────────
# HTTP Session with retry adapter
# ──────────────────────────────────────────────────────────────────────────────

def build_session() -> requests.Session:
    """Return a requests.Session with a retry-capable HTTPAdapter mounted."""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://",  adapter)
    session.headers.update(HEADERS)
    return session


# ──────────────────────────────────────────────────────────────────────────────
# Core extraction functions
# ──────────────────────────────────────────────────────────────────────────────

def check_live_status(session: requests.Session, domain: str) -> str:
    """
    Perform a live HTTP GET on http://<domain> and return the status code as
    a string, or 'Timeout' / 'Dead' on failure.
    """
    url = f"http://{domain}"
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return str(response.status_code)
    except requests.exceptions.Timeout:
        return "Timeout"
    except Exception:
        return "Dead"


def fetch_arquivo_captures(session: requests.Session, domain: str) -> int:
    """
    Query the Arquivo.pt CDX API and count the number of snapshots captured
    for <domain> between CDX_FROM and CDX_TO.

    The API returns one JSON record per line (NDJSON), so we count non-empty
    lines (skipping the optional header line that starts with '[').
    """
    params = {
        "url":    domain,
        "output": "json",
        "from":   CDX_FROM,
        "to":     CDX_TO,
        "fl":     "timestamp",
    }
    try:
        response = session.get(
            ARQUIVO_CDX_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        lines = [
            line.strip()
            for line in response.text.splitlines()
            if line.strip()               # skip blank lines
            and not line.strip().startswith("[")  # skip array-open bracket
            and line.strip() != "]"       # skip array-close bracket
        ]
        return len(lines)
    except Exception:
        return 0


# ──────────────────────────────────────────────────────────────────────────────
# Resume logic — load already-processed domains if output file exists
# ──────────────────────────────────────────────────────────────────────────────

def load_processed_domains(output_path: str) -> set:
    """Return the set of Domain values already written to the output CSV."""
    processed = set()
    if not os.path.exists(output_path):
        return processed
    with open(output_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            domain = row.get("Domain", "").strip()
            if domain:
                processed.add(domain)
    return processed


# ──────────────────────────────────────────────────────────────────────────────
# Main extraction pipeline
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # ── 1. Read input ─────────────────────────────────────────────────────────
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(
            f"Input file '{INPUT_FILE}' not found.\n"
            "Please ensure municipios_dominios.csv (columns: Município, Domain) "
            "is in the working directory."
        )

    with open(INPUT_FILE, encoding="utf-8-sig", newline="") as fh:
        reader    = csv.DictReader(fh)
        all_rows  = list(reader)

    # ── 2. Resume logic ────────────────────────────────────────────────────────
    file_existed    = os.path.exists(OUTPUT_FILE)
    processed_set   = load_processed_domains(OUTPUT_FILE)
    pending_rows    = [
        r for r in all_rows
        if r.get("Domain", "").strip() not in processed_set
    ]

    skipped_count = len(all_rows) - len(pending_rows)
    if skipped_count:
        print(f"[RESUME] Skipping {skipped_count} already-processed domain(s).")

    # ── 3. Build session ───────────────────────────────────────────────────────
    session = build_session()

    # ── 4. Open output in append mode ─────────────────────────────────────────
    with open(OUTPUT_FILE, mode="a", encoding="utf-8-sig", newline="") as out_fh:
        fieldnames = ["Município", "Domain", "Live_StatusCode", "Total_Arquivo_Captures"]
        writer = csv.DictWriter(out_fh, fieldnames=fieldnames)

        # Write header only if the file is brand-new
        if not file_existed:
            writer.writeheader()
            out_fh.flush()

        # ── 5. Main loop with tqdm progress bar ───────────────────────────────
        with tqdm(
            pending_rows,
            desc="Extraindo métricas",
            unit="município",
            dynamic_ncols=True,
            colour="cyan",
        ) as pbar:
            for row in pbar:
                municipio = row.get("Município", "").strip()
                domain    = row.get("Domain",    "").strip()

                if not domain:
                    continue  # guard against empty rows

                pbar.set_postfix_str(domain, refresh=True)

                # ── Live HTTP status ──────────────────────────────────────────
                status_code = check_live_status(session, domain)
                if status_code in ("Timeout", "Dead"):
                    tqdm.write(
                        f"  ⚠  [{status_code.upper()}] {municipio} — {domain}"
                    )

                # ── Arquivo.pt CDX captures ───────────────────────────────────
                total_captures = fetch_arquivo_captures(session, domain)

                # ── Write row immediately (fault-tolerant) ────────────────────
                writer.writerow({
                    "Município":              municipio,
                    "Domain":                 domain,
                    "Live_StatusCode":        status_code,
                    "Total_Arquivo_Captures": total_captures,
                })
                out_fh.flush()

                # ── Rate-limit ────────────────────────────────────────────────
                time.sleep(SLEEP_BETWEEN)

    print(f"\n✅ Extraction complete. Results saved to '{OUTPUT_FILE}'.")
    print(f"   Total processed this run : {len(pending_rows)}")
    print(f"   Previously skipped       : {skipped_count}")
    print(f"   Grand total rows         : {len(all_rows)}")


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
