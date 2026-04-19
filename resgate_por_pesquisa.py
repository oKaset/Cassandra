"""
ArquivoPT2026 — Search-Based Domain Rescue
===========================================
Uses the Arquivo.pt full-text search API to discover the correct
institutional domain for municipalities that all pattern-guessing
strategies failed to find.

NO hardcoding. NO guessing. Every domain is discovered forensically
from archived evidence, then validated against the CDX index.

Phase 1 : Full-text search → root domain extraction + frequency vote.
Phase 2 : CDX validation — confirm the domain exists in the archive.
Phase 3 : IEI calculation (fixed-reference, MAX_REF = 365).
Phase 4 : Append + deduplicate metricas_iei_completo.csv.
"""

import json
import logging
import string
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime
from urllib.parse import urlparse

from typing import Optional, Union

import numpy as np
import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("arquivopt.pesquisa")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MISSING_FILE       = "dominios_nao_encontrados_final.txt"
METRICS_FILE       = "metricas_iei_completo.csv"
UNRESOLVABLE_FILE  = "municipios_sem_arquivo_web.txt"

SEARCH_ENDPOINT = "https://arquivo.pt/textsearch"
CDX_ENDPOINT    = "https://arquivo.pt/wayback/cdx"

CDX_PARAMS = {
    "matchType": "domain",
    "output":    "json",
    "fl":        "timestamp,statuscode,original",
    "from":      "20100101",
    "limit":     200,
}

# Domains that are never the municipality's own website
REJECT_DOMAINS = frozenset({
    "wikipedia.org", "facebook.com", "publico.pt", "rtp.pt",
    "dn.pt", "jn.pt", "sapo.pt", "google.com", "youtube.com",
    "twitter.com", "instagram.com", "linkedin.com", "governo.pt",
    "dgterritorio.gov.pt", "anmp.pt", "pordata.pt", "ine.pt",
    "arquivo.pt", "web.archive.org",
})

MAX_REF       = 365.0
REQUEST_DELAY = 0.5   # seconds between every API call


# ===========================================================================
# Utilities  (identical to previous scripts — single source of truth)
# ===========================================================================

def normalize_name(s: str) -> str:
    """Accent-stripped, lowercased, whitespace-stripped for safe comparison."""
    return (
        unicodedata.normalize("NFKD", s)
        .encode("ascii", "ignore")
        .decode()
        .strip()
        .lower()
    )


def extract_root_domain(url: str) -> Optional[str]:
    """
    Parse a URL and return its cleaned root domain.
    - Strips scheme, path, query, port.
    - Removes leading 'www.' prefix.
    - Returns None if domain does not end with '.pt' or is in REJECT_DOMAINS.
    """
    try:
        netloc = urlparse(url).netloc.lower().strip()
    except Exception:
        return None

    # Remove port if present (e.g. host:8080)
    netloc = netloc.split(":")[0]

    # Strip www. prefix
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Also strip other common subdomains that mask the root
    # e.g. "portal.cm-braganca.pt" → "cm-braganca.pt"
    parts = netloc.split(".")
    if len(parts) > 2:
        # Rejoin from [-2] to keep "cm-braganca.pt" from "portal.cm-braganca.pt"
        netloc = ".".join(parts[-2:])

    if not netloc.endswith(".pt"):
        return None

    if netloc in REJECT_DOMAINS:
        return None

    return netloc


# ===========================================================================
# Phase 1 — Full-text search → candidate domain
# ===========================================================================

def discover_domain(
    municipio: str,
    session: requests.Session,
) -> tuple:
    """
    Query Arquivo.pt textsearch for "Câmara Municipal de {municipio}".
    Extract root domains from results, return the most frequent .pt domain.

    Returns:
        (candidate_domain, votes, total_results)
        candidate_domain is None if no clean domain was found.
    """
    query  = f"Câmara Municipal de {municipio}"
    params = {"q": query, "maxItems": 5, "prettyPrint": "false"}

    response = session.get(SEARCH_ENDPOINT, params=params, timeout=20)
    response.raise_for_status()

    try:
        data = response.json()
    except json.JSONDecodeError:
        log.warning("  [%s] Search API returned non-JSON.", municipio)
        return None, 0, 0

    # The textsearch API wraps results in a 'response' → 'docs' structure
    # but also sometimes a flat 'items' list depending on the endpoint version.
    # Handle both gracefully.
    items = (
        data.get("response", {}).get("docs", [])
        or data.get("items", [])
        or (data if isinstance(data, list) else [])
    )

    if not items:
        return None, 0, 0

    domain_votes: Counter = Counter()

    for item in items:
        url = (
            item.get("originalURL")
            or item.get("url")
            or item.get("linkToArchive")  # fallback field names
            or ""
        )
        if not url:
            continue
        root = extract_root_domain(url)
        if root:
            domain_votes[root] += 1

    if not domain_votes:
        return None, 0, len(items)

    best_domain, votes = domain_votes.most_common(1)[0]
    return best_domain, votes, len(items)


# ===========================================================================
# Phase 2 — CDX validation
# ===========================================================================

def validate_via_cdx(
    domain: str,
    municipio: str,
    session: requests.Session,
) -> list[dict]:
    """
    Confirm the domain exists in the Arquivo.pt CDX index.
    Returns all extracted records (may be empty → unresolvable).
    """
    params   = {**CDX_PARAMS, "url": domain}
    response = session.get(CDX_ENDPOINT, params=params, timeout=20)
    response.raise_for_status()

    raw = response.text.strip()
    if not raw:
        return []

    records: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, list):   # CDX header row in some response modes
            continue
        records.append({
            "Domain":     domain,
            "Município":  municipio,
            "Timestamp":  obj.get("timestamp",  ""),
            "StatusCode": obj.get("statuscode", ""),
            "URL":        obj.get("original",   ""),
        })
    return records


# ===========================================================================
# Phase 3 — IEI calculation  (identical to all previous scripts)
# ===========================================================================

def calculate_iei(raw_records: list[dict]) -> pd.DataFrame:
    """
    Fixed-reference IEI normalisation (MAX_REF = 365 days).
    Score 0 = updated < once/year (abandoned).
    Score ~100 = updated daily (vital).
    Scale is stable; adding new domains does not shift existing scores.
    """
    df = pd.DataFrame(raw_records)
    df["Timestamp"] = pd.to_datetime(
        df["Timestamp"], format="%Y%m%d%H%M%S", errors="coerce"
    )
    nat_n = df["Timestamp"].isna().sum()
    if nat_n:
        log.warning("  Dropping %d row(s) with unparseable timestamps.", nat_n)
    df = df.dropna(subset=["Timestamp"])
    df = df.sort_values(["Domain", "Timestamp"]).reset_index(drop=True)

    results: list[dict] = []
    for domain, grp in df.groupby("Domain", sort=False):
        municipio = grp["Município"].iloc[0]
        n         = len(grp)

        if n < 2:
            log.warning("  [%s] Only %d record — IEI_Score = NaN.", domain, n)
            results.append({
                "Domain":                    domain,
                "Município":                 municipio,
                "Media_Dias_Entre_Capturas": np.nan,
                "IEI_Score":                 np.nan,
            })
            continue

        gaps     = grp["Timestamp"].diff().dt.total_seconds() / 86_400
        mean_gap = gaps.dropna().mean()
        iei      = max(0.0, 100.0 - (mean_gap / MAX_REF) * 100.0)

        results.append({
            "Domain":                    domain,
            "Município":                 municipio,
            "Media_Dias_Entre_Capturas": round(mean_gap, 4),
            "IEI_Score":                 round(iei,      4),
        })

    return pd.DataFrame(results)


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    log.info("=" * 65)
    log.info("  ArquivoPT2026 — Search-Based Domain Rescue")
    log.info("  Started : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 65)

    # -----------------------------------------------------------------------
    # Load missing municipality list
    # -----------------------------------------------------------------------
    log.info("Loading missing municipalities from '%s' …", MISSING_FILE)
    try:
        with open(MISSING_FILE, encoding="utf-8") as fh:
            missing = [
                line.strip() for line in fh if line.strip()
            ]
    except FileNotFoundError:
        log.error("File not found: %s — run resgatar_dominios.py first.", MISSING_FILE)
        sys.exit(1)

    total = len(missing)
    log.info("  %d municipalities to attempt.", total)

    if total == 0:
        log.info("  Nothing to do. Exiting.")
        sys.exit(0)

    # -----------------------------------------------------------------------
    # Phase 1+2 — Search discovery + CDX validation
    # -----------------------------------------------------------------------
    log.info("")
    log.info("PHASE 1+2 — Search discovery & CDX validation …")
    log.info("  (%.1f s delay between every API call)", REQUEST_DELAY)
    log.info("")

    all_rescued_records: list[dict] = []
    discovered_count    = 0
    validated_count     = 0
    unresolvable:    list[str] = []

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})

        for idx, municipio in enumerate(missing, start=1):
            prefix = f"  [{idx:>3}/{total}]"

            # --- Phase 1: full-text search ---
            try:
                candidate, votes, n_results = discover_domain(municipio, session)
            except requests.exceptions.RequestException as exc:
                log.warning("%s [%s] Search API error: %s — skipping.", prefix, municipio, exc)
                unresolvable.append(municipio)
                time.sleep(REQUEST_DELAY)
                continue

            time.sleep(REQUEST_DELAY)   # delay after search call

            if not candidate:
                print(f"{prefix} {municipio:<32} → no clean domain found, skipping")
                unresolvable.append(municipio)
                continue

            discovered_count += 1
            print(
                f"{prefix} {municipio:<32} → discovered: {candidate}"
                f" (from {votes}/{n_results} results)"
            )

            # --- Phase 2: CDX validation ---
            try:
                records = validate_via_cdx(candidate, municipio, session)
            except requests.exceptions.RequestException as exc:
                log.warning("  CDX validation error for %s: %s — skipping.", candidate, exc)
                unresolvable.append(municipio)
                time.sleep(REQUEST_DELAY)
                continue

            time.sleep(REQUEST_DELAY)   # delay after CDX call

            if not records:
                print(
                    f"{'':>13} ↳ CDX: {candidate} — 0 records in archive "
                    f"→ UNRESOLVABLE"
                )
                unresolvable.append(municipio)
                continue

            validated_count += 1
            all_rescued_records.extend(records)
            print(
                f"{'':>13} ↳ CDX: {candidate} — {len(records)} records ✓"
            )

    # -----------------------------------------------------------------------
    # Phase 3 — IEI
    # -----------------------------------------------------------------------
    new_metrics_df = pd.DataFrame()

    if all_rescued_records:
        log.info("")
        log.info(
            "PHASE 3 — Calculating IEI for %d new records …",
            len(all_rescued_records),
        )
        new_metrics_df = calculate_iei(all_rescued_records)
        log.info("  IEI computed for %d domains.", len(new_metrics_df))
    else:
        log.info("No new records to process for IEI.")

    # -----------------------------------------------------------------------
    # Phase 4 — Append + deduplicate
    # -----------------------------------------------------------------------
    log.info("")
    log.info("PHASE 4 — Merging into '%s' …", METRICS_FILE)

    if not new_metrics_df.empty:
        try:
            existing = pd.read_csv(METRICS_FILE)
        except FileNotFoundError:
            log.error("Metrics file '%s' not found.", METRICS_FILE)
            sys.exit(1)

        combined = pd.concat([existing, new_metrics_df], ignore_index=True)

        # Deduplicate on normalised municipality name — original data wins
        combined["_norm"] = combined["Município"].astype(str).map(normalize_name)
        combined = combined.drop_duplicates(subset="_norm", keep="first")
        combined = combined.drop(columns=["_norm"])

        combined.to_csv(METRICS_FILE, index=False, encoding="utf-8")
        log.info(
            "  Saved %d total rows → %s", len(combined), METRICS_FILE
        )
        total_with_iei = combined["IEI_Score"].notna().sum()
    else:
        try:
            total_with_iei = pd.read_csv(METRICS_FILE)["IEI_Score"].notna().sum()
        except FileNotFoundError:
            total_with_iei = 0

    # Save unresolvable list
    with open(UNRESOLVABLE_FILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sorted(set(unresolvable))))
        if unresolvable:
            fh.write("\n")
    log.info(
        "  Unresolvable list → %s  (%d municipalities)",
        UNRESOLVABLE_FILE, len(set(unresolvable)),
    )

    # -----------------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------------
    unresolvable_count = len(set(unresolvable))
    print()
    print("=" * 65)
    print("  SEARCH RESCUE COMPLETE")
    print("=" * 65)
    print(f"  {'Municipalities attempted':<38} {total:>5}")
    print(f"  {'Discovered via search':<38} {discovered_count:>5}")
    print(f"  {'Validated in CDX archive':<38} {validated_count:>5}")
    print(f"  {'Unresolvable (no web presence)':<38} {unresolvable_count:>5}")
    print(f"  {'Total with IEI score (cumulative)':<38} {total_with_iei:>5}")
    print("-" * 65)
    print(f"  Metrics file     : {METRICS_FILE}")
    print(f"  Unresolvable log : {UNRESOLVABLE_FILE}")
    print("=" * 65)
    print()

    if unresolvable:
        print("  Municipalities with no verifiable web archive presence:")
        for m in sorted(set(unresolvable)):
            print(f"    · {m}")
        print()
        print(
            "  NOTE: These municipalities may have used non-.pt domains,\n"
            "  had no web presence before archiving began, or their pages\n"
            "  were never crawled. This is itself a demographic signal.\n"
        )


if __name__ == "__main__":
    main()
