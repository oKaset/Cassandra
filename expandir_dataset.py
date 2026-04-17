"""
ArquivoPT2026 — Expanded Dataset Pipeline (308 Municipalities)
===============================================================
Phase 1 : Generate candidate cm-X.pt domains from municipality names.
Phase 2 : Bulk extraction from Arquivo.pt CDX API (NDJSON).
Phase 3 : IEI calculation (fixed-reference, MAX_REF = 365 days).
Phase 4 : Export consolidated metrics + not-found domain list.
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
log = logging.getLogger("arquivopt.expandir")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INPUT_FILE          = "dados_demograficos.csv"
OUTPUT_METRICS      = "metricas_iei_completo.csv"
OUTPUT_NOT_FOUND    = "dominios_nao_encontrados.txt"

CDX_ENDPOINT = "https://arquivo.pt/wayback/cdx"
CDX_PARAMS   = {
    "matchType": "domain",
    "output":    "json",
    "fl":        "timestamp,statuscode,original",
    "from":      "20100101",
    "limit":     200,
}

MAX_REF          = 365.0   # fixed IEI reference (see calcular_metricas.py)
REQUEST_DELAY    = 0.5     # seconds between API calls — be polite to Arquivo.pt


# ===========================================================================
# PHASE 1 — Domain generation
# ===========================================================================

def slugify(name: str) -> str:
    """
    Convert a municipality name to a cm-X.pt slug:
      1. lowercase
      2. NFKD normalise → strip combining characters (accents)
      3. encode ASCII, ignore non-ASCII
      4. replace spaces with hyphens
      5. strip punctuation (apostrophes, dots, parentheses, commas …)
    """
    # Step 1 — lowercase
    name = name.lower().strip()

    # Step 2+3 — remove accents
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    # Step 4 — spaces → hyphens
    name = name.replace(" ", "-")

    # Step 5 — strip punctuation (keep hyphens and alphanumerics)
    allowed = set(string.ascii_lowercase + string.digits + "-")
    name = "".join(ch for ch in name if ch in allowed)

    # Collapse multiple consecutive hyphens
    while "--" in name:
        name = name.replace("--", "-")

    return name.strip("-")


def generate_domains(municipalities: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """
    Returns a list of (domain, municipio, slug) triples.
    municipalities: list of (municipio_raw,) — extra fields ignored.
    """
    domains = []
    for municipio in municipalities:
        slug   = slugify(municipio)
        domain = f"cm-{slug}.pt"
        domains.append((domain, municipio, slug))
    return domains


# ===========================================================================
# PHASE 2 — Bulk CDX extraction (reuses NDJSON logic from extracao_massiva.py)
# ===========================================================================

def fetch_domain_records(
    domain: str,
    municipio: str,
    session: requests.Session,
) -> list[dict]:
    """
    Query CDX for *domain*.  Returns a list of record dicts, possibly empty.
    Parses NDJSON line-by-line; skips empties and non-object lines.
    """
    params = {**CDX_PARAMS, "url": domain}

    response = session.get(CDX_ENDPOINT, params=params, timeout=20)
    response.raise_for_status()

    raw_text = response.text.strip()
    if not raw_text:
        return []

    records: list[dict] = []
    for line_no, line in enumerate(raw_text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            log.debug("  Line %d — JSON parse error, skipped: %.60s", line_no, line)
            continue
        if isinstance(obj, list):          # header row in some CDX modes
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
# PHASE 3 — IEI calculation (identical formula to calcular_metricas.py)
# ===========================================================================

def calculate_iei(all_records: list[dict]) -> pd.DataFrame:
    """
    Given all raw records, compute IEI per domain.

    IEI fixed-reference normalisation
    ----------------------------------
    MAX_REF = 365 days.
    IEI_Score = max(0, 100 - (mean_gap_days / MAX_REF) * 100)

    A domain updated daily → IEI ≈ 100 (institutionally vital).
    A domain updated less than once per year → IEI = 0 (abandoned).
    Fixed scale: adding more domains later does NOT shift existing scores,
    unlike min-max normalisation.  See calcular_metricas.py for full rationale.
    """
    df = pd.DataFrame(all_records)

    # Parse timestamps
    df["Timestamp"] = pd.to_datetime(
        df["Timestamp"],
        format="%Y%m%d%H%M%S",
        errors="coerce",
    )
    nat_count = df["Timestamp"].isna().sum()
    if nat_count:
        log.warning("Dropping %d row(s) with unparseable timestamps.", nat_count)
    df = df.dropna(subset=["Timestamp"])

    # Sort — required for diff() to produce positive gaps
    df = df.sort_values(["Domain", "Timestamp"]).reset_index(drop=True)

    results = []
    for domain, group in df.groupby("Domain", sort=False):
        municipio = group["Município"].iloc[0]
        n         = len(group)

        if n < 2:
            log.warning(
                "  [%s] Only %d record — cannot compute gaps. IEI_Score = NaN.",
                domain, n,
            )
            results.append({
                "Domain":                    domain,
                "Município":                 municipio,
                "Media_Dias_Entre_Capturas": np.nan,
                "IEI_Score":                 np.nan,
            })
            continue

        gaps_days = group["Timestamp"].diff().dt.total_seconds() / 86_400
        mean_gap  = gaps_days.dropna().mean()
        iei_score = max(0.0, 100.0 - (mean_gap / MAX_REF) * 100.0)

        results.append({
            "Domain":                    domain,
            "Município":                 municipio,
            "Media_Dias_Entre_Capturas": round(mean_gap,  4),
            "IEI_Score":                 round(iei_score, 4),
        })

    return pd.DataFrame(results)


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:

    # -----------------------------------------------------------------------
    # Banner
    # -----------------------------------------------------------------------
    log.info("=" * 65)
    log.info("  ArquivoPT2026 — Expanded Dataset Pipeline")
    log.info("  Started : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 65)

    # -----------------------------------------------------------------------
    # Load demographic file
    # NOTE: file has .csv extension but is actually an Excel workbook.
    #       header=1 skips the first row (metadata) and uses row 2 as header.
    # -----------------------------------------------------------------------
    log.info("Loading municipality list from '%s' …", INPUT_FILE)
    try:
        demo_df = pd.read_excel(INPUT_FILE, header=1)
    except FileNotFoundError:
        log.error("File not found: '%s'. Place it in the project root.", INPUT_FILE)
        sys.exit(1)
    except Exception as exc:
        log.error("Could not read '%s': %s", INPUT_FILE, exc)
        sys.exit(1)

    if "Município" not in demo_df.columns:
        log.error(
            "Column 'Município' not found. Available columns: %s",
            list(demo_df.columns),
        )
        sys.exit(1)

    # Drop any rows where the municipality name is missing
    municipios_raw = (
        demo_df["Município"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )
    log.info("  Municipalities found : %d", len(municipios_raw))

    # -----------------------------------------------------------------------
    # Phase 1 — Domain generation
    # -----------------------------------------------------------------------
    log.info("")
    log.info("PHASE 1 — Generating candidate domains …")
    domain_list = generate_domains(municipios_raw)
    total = len(domain_list)

    log.info("")
    log.info("  %-35s  %s", "Domain", "Município")
    log.info("  %s  %s", "-" * 35, "-" * 25)
    for domain, municipio, _ in domain_list:
        log.info("  %-35s  %s", domain, municipio)
    log.info("")
    log.info("  Total domains to query : %d", total)

    # -----------------------------------------------------------------------
    # Phase 2 — Bulk extraction
    # -----------------------------------------------------------------------
    log.info("")
    log.info("PHASE 2 — Bulk CDX extraction (limit=%s per domain) …", CDX_PARAMS["limit"])

    all_records:    list[dict] = []
    not_found:      list[str]  = []
    failed_domains: list[str]  = []

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})

        for idx, (domain, municipio, _) in enumerate(domain_list, start=1):
            try:
                records = fetch_domain_records(domain, municipio, session)

                if not records:
                    log.info("  [%d/%d] %-35s — NOT FOUND", idx, total, domain)
                    not_found.append(domain)
                else:
                    log.info(
                        "  [%d/%d] %-35s — %d records",
                        idx, total, domain, len(records),
                    )
                    all_records.extend(records)

            except requests.exceptions.ConnectionError:
                log.error("  [%d/%d] [%s] Connection error — skipping.", idx, total, domain)
                failed_domains.append(domain)

            except requests.exceptions.Timeout:
                log.error("  [%d/%d] [%s] Timeout (>20 s) — skipping.", idx, total, domain)
                failed_domains.append(domain)

            except requests.exceptions.HTTPError as exc:
                log.error("  [%d/%d] [%s] HTTP error: %s — skipping.", idx, total, domain, exc)
                failed_domains.append(domain)

            except Exception as exc:  # noqa: BLE001
                log.error("  [%d/%d] [%s] Unexpected error: %s — skipping.", idx, total, domain, exc)
                failed_domains.append(domain)

            # Polite rate-limiting — do not hammer Arquivo.pt
            if idx < total:
                time.sleep(REQUEST_DELAY)

    found_count = total - len(not_found) - len(failed_domains)

    # -----------------------------------------------------------------------
    # Phase 3 — IEI calculation
    # -----------------------------------------------------------------------
    log.info("")
    log.info("PHASE 3 — Calculating IEI for %d records …", len(all_records))

    if not all_records:
        log.warning("No records extracted. Cannot compute IEI. Exiting.")
        sys.exit(0)

    metrics_df = calculate_iei(all_records)

    nan_count = metrics_df["IEI_Score"].isna().sum()

    # -----------------------------------------------------------------------
    # Phase 4 — Export
    # -----------------------------------------------------------------------
    log.info("")
    log.info("PHASE 4 — Exporting results …")

    # 1. Full metrics CSV
    metrics_df.to_csv(OUTPUT_METRICS, index=False, encoding="utf-8")
    log.info("  Metrics saved      → %s  (%d rows)", OUTPUT_METRICS, len(metrics_df))

    # 2. Not-found domain list
    all_not_found = sorted(set(not_found + failed_domains))
    with open(OUTPUT_NOT_FOUND, "w", encoding="utf-8") as fh:
        fh.write("\n".join(all_not_found))
        if all_not_found:
            fh.write("\n")
    log.info("  Not-found list saved → %s  (%d domains)", OUTPUT_NOT_FOUND, len(all_not_found))

    # -----------------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------------
    print()
    print("=" * 65)
    print("  EXTRACTION COMPLETE")
    print("=" * 65)
    print(
        f"  {'Domains queried':<30} {total:>5}"
    )
    print(
        f"  {'Found (returned records)':<30} {found_count:>5}"
    )
    print(
        f"  {'Not found (0 records)':<30} {len(not_found):>5}"
    )
    print(
        f"  {'Failed (connection/HTTP)':<30} {len(failed_domains):>5}"
    )
    print(
        f"  {'IEI = NaN (< 2 records)':<30} {nan_count:>5}"
    )
    print("-" * 65)
    print(f"  Total raw records extracted : {len(all_records)}")
    print(f"  Metrics file                : {OUTPUT_METRICS}")
    print(f"  Not-found list              : {OUTPUT_NOT_FOUND}")
    print("=" * 65)
    print()

    # Ranked preview (top 10 by IEI descending)
    ranked = metrics_df.dropna(subset=["IEI_Score"]).sort_values("IEI_Score", ascending=False)
    if not ranked.empty:
        print("  Top municipalities by IEI_Score:")
        print(f"  {'Município':<28}  {'Domain':<32}  {'IEI':>6}")
        print(f"  {'-'*28}  {'-'*32}  {'-'*6}")
        for _, row in ranked.head(10).iterrows():
            print(
                f"  {row['Município']:<28}  {row['Domain']:<32}  {row['IEI_Score']:>6.2f}"
            )
        print()


if __name__ == "__main__":
    main()
