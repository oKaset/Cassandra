"""
ArquivoPT2026 — Domain Rescue Pipeline
=======================================
Identifies municipalities missing from the existing metrics file and
attempts to recover them using 6 fallback domain patterns.

Phase 1 : Identify missing (normalised string comparison).
Phase 2 : Generate fallback pattern list per municipality.
Phase 3 : CDX extraction — try patterns in order, stop on first hit.
Phase 4 : IEI calculation (identical formula to previous scripts).
Phase 5 : Append & deduplicate metricas_iei_completo.csv.
"""

import json
import logging
import string
import sys
import time
import unicodedata
from datetime import datetime

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
log = logging.getLogger("arquivopt.resgatar")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEMO_FILE       = "dados_demograficos.csv"
METRICS_FILE    = "metricas_iei_completo.csv"
NOT_FOUND_FILE  = "dominios_nao_encontrados_final.txt"

CDX_ENDPOINT = "https://arquivo.pt/wayback/cdx"
CDX_PARAMS   = {
    "matchType": "domain",
    "output":    "json",
    "fl":        "timestamp,statuscode,original",
    "from":      "20100101",
    "limit":     200,
}

MAX_REF       = 365.0
REQUEST_DELAY = 0.5   # seconds between EVERY API call (patterns included)


# ===========================================================================
# Utilities
# ===========================================================================

def normalize_name(s: str) -> str:
    """
    Canonical normalisation for municipality name comparison.
    Removes accents, lowercases, strips whitespace.
    Used on BOTH sides of the comparison to avoid encoding false-mismatches.
    """
    return (
        unicodedata.normalize("NFKD", s)
        .encode("ascii", "ignore")
        .decode()
        .strip()
        .lower()
    )


def slugify(name: str) -> str:
    """ASCII slug: lowercase → strip accents → spaces→hyphens → strip punctuation."""
    name = normalize_name(name)
    name = name.replace(" ", "-")
    allowed = set(string.ascii_lowercase + string.digits + "-")
    name = "".join(ch for ch in name if ch in allowed)
    while "--" in name:
        name = name.replace("--", "-")
    return name.strip("-")


def build_patterns(municipio: str) -> list[str]:
    """
    Return the 6 candidate domain patterns to try, in priority order.
    Stops at the first one that returns > 0 CDX records.
    """
    slug      = slugify(municipio)
    last_word = slug.split("-")[-1]   # e.g. "gaia" from "vila-nova-de-gaia"

    return [
        f"cm-{slug}.pt",             # 1 — canonical (already tried)
        f"{slug}.pt",                # 2 — bare domain
        f"mun-{slug}.pt",            # 3 — mun- prefix
        f"municipio-{slug}.pt",      # 4 — full word prefix
        f"cm{slug}.pt",              # 5 — no hyphen
        f"cm-{last_word}.pt",        # 6 — abbreviate to last word only
    ]


# ===========================================================================
# CDX helpers  (reused from extracao_massiva.py / expandir_dataset.py)
# ===========================================================================

def fetch_records(
    domain: str,
    municipio: str,
    session: requests.Session,
) -> list[dict]:
    """
    Query CDX API for *domain*. Parse NDJSON line-by-line.
    Returns list of record dicts (may be empty).
    Raises requests exceptions — caller handles them.
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
        if isinstance(obj, list):      # header row in some CDX modes
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
# Phase 4 — IEI calculation  (identical to calcular_metricas.py)
# ===========================================================================

def calculate_iei(raw_records: list[dict]) -> pd.DataFrame:
    """
    IEI fixed-reference normalisation.
    MAX_REF = 365 days → score 0 (abandoned) … 100 (daily updates).
    Fixed scale: stable when new domains are added; see calcular_metricas.py.
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
            log.warning(
                "  [%s] Only %d record — IEI_Score = NaN.", domain, n
            )
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
    log.info("  ArquivoPT2026 — Domain Rescue Pipeline")
    log.info("  Started : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 65)

    # -----------------------------------------------------------------------
    # Load sources
    # -----------------------------------------------------------------------
    log.info("Loading '%s' …", DEMO_FILE)
    try:
        demo_df = pd.read_excel(DEMO_FILE, header=1)
    except FileNotFoundError:
        log.error("File not found: %s", DEMO_FILE)
        sys.exit(1)
    except Exception as exc:
        log.error("Could not read %s — %s", DEMO_FILE, exc)
        sys.exit(1)

    if "Município" not in demo_df.columns:
        log.error(
            "Column 'Município' not found. Available: %s", list(demo_df.columns)
        )
        sys.exit(1)

    all_municipios = (
        demo_df["Município"].dropna().astype(str).str.strip().unique().tolist()
    )
    log.info("  %d municipalities in demographic file.", len(all_municipios))

    log.info("Loading '%s' …", METRICS_FILE)
    try:
        metrics_df = pd.read_csv(METRICS_FILE, dtype=str)
    except FileNotFoundError:
        log.error("File not found: %s — run expandir_dataset.py first.", METRICS_FILE)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Phase 1 — Identify missing (normalised comparison)
    # -----------------------------------------------------------------------
    log.info("")
    log.info("PHASE 1 — Identifying missing municipalities …")

    found_norm = {
        normalize_name(m) for m in metrics_df["Município"].dropna().astype(str)
    }

    missing: list[str] = [
        m for m in all_municipios if normalize_name(m) not in found_norm
    ]

    log.info("  Already found : %d", len(found_norm))
    log.info("  Missing       : %d municipalities", len(missing))
    total_missing = len(missing)

    if total_missing == 0:
        log.info("  Nothing to rescue. Exiting.")
        sys.exit(0)

    # -----------------------------------------------------------------------
    # Phase 2+3 — Fallback pattern attempts
    # -----------------------------------------------------------------------
    log.info("")
    log.info("PHASE 2+3 — Trying fallback domain patterns …")

    all_rescued_records: list[dict] = []
    still_missing:       list[str]  = []

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})

        for idx, municipio in enumerate(missing, start=1):
            patterns    = build_patterns(municipio)
            rescued     = False
            tried_domain = ""

            for pattern in patterns:
                tried_domain = pattern

                try:
                    records = fetch_records(pattern, municipio, session)
                except requests.exceptions.RequestException as exc:
                    log.debug("  [%s] %s — %s", municipio, pattern, exc)
                    time.sleep(REQUEST_DELAY)
                    continue

                # Polite delay between EVERY API call, including pattern attempts
                time.sleep(REQUEST_DELAY)

                if records:
                    all_rescued_records.extend(records)
                    rescued = True
                    print(
                        f"  [{idx:>3}/{total_missing}] {municipio:<30} — "
                        f"tried {tried_domain:<35} — {len(records):>4} records ✓"
                    )
                    break   # stop at first successful pattern

            if not rescued:
                still_missing.append(municipio)
                print(
                    f"  [{idx:>3}/{total_missing}] {municipio:<30} — "
                    f"all patterns failed ✗"
                )

    rescued_count = total_missing - len(still_missing)
    log.info("")
    log.info(
        "Pattern search complete: %d rescued, %d still missing.",
        rescued_count, len(still_missing),
    )

    # -----------------------------------------------------------------------
    # Phase 4 — IEI for newly rescued domains
    # -----------------------------------------------------------------------
    new_metrics_df = pd.DataFrame()

    if all_rescued_records:
        log.info("")
        log.info(
            "PHASE 4 — Calculating IEI for %d new records …",
            len(all_rescued_records),
        )
        new_metrics_df = calculate_iei(all_rescued_records)
        log.info("  IEI computed for %d domains.", len(new_metrics_df))
    else:
        log.info("No new records to process for IEI.")

    # -----------------------------------------------------------------------
    # Phase 5 — Append + deduplicate + save
    # -----------------------------------------------------------------------
    log.info("")
    log.info("PHASE 5 — Merging and saving …")

    if not new_metrics_df.empty:
        # Re-load the existing file with correct dtypes for concat
        existing = pd.read_csv(METRICS_FILE)
        combined = pd.concat([existing, new_metrics_df], ignore_index=True)

        # Deduplicate on normalised municipality name (keep first = original data)
        combined["_norm"] = combined["Município"].astype(str).map(normalize_name)
        combined = combined.drop_duplicates(subset="_norm", keep="first")
        combined = combined.drop(columns=["_norm"])

        combined.to_csv(METRICS_FILE, index=False, encoding="utf-8")
        log.info(
            "  Saved %d total rows → %s", len(combined), METRICS_FILE
        )
        total_with_iei = combined["IEI_Score"].notna().sum()
    else:
        total_with_iei = pd.read_csv(METRICS_FILE)["IEI_Score"].notna().sum()

    # Save still-missing list
    with open(NOT_FOUND_FILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sorted(still_missing)))
        if still_missing:
            fh.write("\n")
    log.info(
        "  Not-found list → %s  (%d domains)", NOT_FOUND_FILE, len(still_missing)
    )

    # -----------------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------------
    total_domains = len(all_municipios)
    print()
    print("=" * 65)
    print("  RESCUE COMPLETE")
    print("=" * 65)
    print(f"  {'Rescued':<35} {rescued_count:>5}")
    print(f"  {'Still missing':<35} {len(still_missing):>5}")
    print(f"  {'Total with IEI score':<35} {total_with_iei:>5} / {total_domains}")
    print(f"  {'Output file':<35} {METRICS_FILE}")
    print(f"  {'Unresolved domains file':<35} {NOT_FOUND_FILE}")
    print("=" * 65)
    print()

    if still_missing:
        print("  Still missing (check manually or add URL overrides):")
        for m in sorted(still_missing):
            print(f"    - {m}")
        print()


if __name__ == "__main__":
    main()
