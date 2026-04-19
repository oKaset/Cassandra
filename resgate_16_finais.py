"""
ArquivoPT2026 — Final Rescue: 16 Municipalities
================================================
CDX-verifies manually researched official domains for the
16 municipalities still missing after all previous rescue passes.
"""

import json
import sys
import time
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
METRICS_FILE  = "metricas_iei_completo.csv"
MISSING_FILE  = "municipios_sem_web.txt"

CDX_ENDPOINT = "https://arquivo.pt/wayback/cdx"
CDX_PARAMS   = {
    "matchType": "domain",
    "output":    "json",
    "fl":        "timestamp,statuscode,original",
    "from":      "20100101",
    "limit":     200,
}

MAX_REF            = 365.0
REQUEST_DELAY      = 0.3
TOTAL_MUNICIPALITIES = 308

# ---------------------------------------------------------------------------
# Manually verified official domains — CDX is the final arbiter
# ---------------------------------------------------------------------------
MUNICIPIOS_FINAIS = {
    "Castelo de Vide":          ["cm-castelo-vide.pt"],
    "Lajes das Flores":         ["cmlajesdasflores.pt",      "cm-lajesdasflores.pt"],
    "Marinha Grande":           ["cm-mgrande.pt"],
    "Miranda do Douro":         ["cm-mdouro.pt"],
    "Montemor-o-Velho":         ["cm-montemorvelho.pt",      "cm-montemor-o-velho.pt"],
    "Oliveira do Bairro":       ["cm-olb.pt"],
    "Paços de Ferreira":        ["cm-pacosdeferreira.pt"],
    "Santa Cruz das Flores":    ["cmscflores.pt",            "cm-scflores.pt"],
    "Santana":                  ["cm-santana.com",           "cm-santana.pt"],
    "Santo Tirso":              ["cm-stirso.pt"],
    "Sever do Vouga":           ["cm-sever.pt"],
    "Terras de Bouro":          ["cm-terrasdebouro.pt"],
    "Vieira do Minho":          ["cm-vminho.pt",             "cm-vieirademinho.pt",
                                 "cm-vieira-minho.pt"],
    "Vila Franca do Campo":     ["cm-vfc.pt",                "cm-vilafrancadocampo.pt",
                                 "vilafrancadocampo.pt"],
    "Vila Nova de Poiares":     ["cm-vilanovadepoiares.pt",  "cm-poiares.pt"],
    "Vila da Praia da Vitória": ["cmpv.pt",                  "cm-praiadavitoria.pt"],
}


# ===========================================================================
# Helpers
# ===========================================================================

def normalize_name(s: str) -> str:
    return (
        unicodedata.normalize("NFKD", s)
        .encode("ascii", "ignore")
        .decode()
        .strip()
        .lower()
    )


def fetch_cdx(domain: str, municipio: str, session: requests.Session) -> list:
    params   = {**CDX_PARAMS, "url": domain}
    response = session.get(CDX_ENDPOINT, params=params, timeout=20)
    response.raise_for_status()

    records = []
    for line in response.text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, list):
            continue
        records.append({
            "Domain":     domain,
            "Município":  municipio,
            "Timestamp":  obj.get("timestamp",  ""),
            "StatusCode": obj.get("statuscode", ""),
            "URL":        obj.get("original",   ""),
        })
    return records


def calculate_iei(raw_records: list) -> pd.DataFrame:
    df = pd.DataFrame(raw_records)
    df["Timestamp"] = pd.to_datetime(
        df["Timestamp"], format="%Y%m%d%H%M%S", errors="coerce"
    )
    df = df.dropna(subset=["Timestamp"])
    df = df.sort_values(["Domain", "Timestamp"]).reset_index(drop=True)

    results = []
    for domain, grp in df.groupby("Domain", sort=False):
        municipio = grp["Município"].iloc[0]
        n         = len(grp)
        if n < 2:
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
    total = len(MUNICIPIOS_FINAIS)

    print("=" * 60)
    print("  ArquivoPT2026 — Final Rescue (16 Municipalities)")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    rescued_count = 0
    still_missing = []
    all_records   = []

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})

        for idx, (municipio, candidates) in enumerate(MUNICIPIOS_FINAIS.items(), start=1):
            found = False

            for domain in candidates:
                try:
                    records = fetch_cdx(domain, municipio, session)
                except requests.exceptions.RequestException as exc:
                    print(f"    ! [{domain}] error: {exc}")
                    time.sleep(REQUEST_DELAY)
                    continue
                finally:
                    time.sleep(REQUEST_DELAY)

                if records:
                    all_records.extend(records)
                    rescued_count += 1
                    found = True
                    print(
                        f"  ✓ [{idx:>2}/{total}] {municipio:<34}"
                        f" → {domain}  ({len(records)} records)"
                    )
                    break

            if not found:
                still_missing.append(municipio)
                print(
                    f"  ✗ [{idx:>2}/{total}] {municipio:<34}"
                    f" → all {len(candidates)} candidate(s) failed"
                )

    # -----------------------------------------------------------------------
    # IEI
    # -----------------------------------------------------------------------
    new_metrics = pd.DataFrame()
    if all_records:
        print()
        print(f"  Calculating IEI for {len(all_records)} records …")
        new_metrics = calculate_iei(all_records)

    # -----------------------------------------------------------------------
    # Merge + deduplicate
    # -----------------------------------------------------------------------
    total_with_iei = 0

    if not new_metrics.empty:
        try:
            existing = pd.read_csv(METRICS_FILE)
        except FileNotFoundError:
            print(f"  ERROR: {METRICS_FILE} not found.")
            sys.exit(1)

        combined = pd.concat([existing, new_metrics], ignore_index=True)
        combined["_norm"] = combined["Município"].astype(str).map(normalize_name)
        combined = combined.drop_duplicates(subset="_norm", keep="first")
        combined = combined.drop(columns=["_norm"])
        combined.to_csv(METRICS_FILE, index=False, encoding="utf-8")
        total_with_iei = combined["IEI_Score"].notna().sum()
        print(f"  Saved {len(combined)} rows → {METRICS_FILE}")
    else:
        try:
            total_with_iei = pd.read_csv(METRICS_FILE)["IEI_Score"].notna().sum()
        except FileNotFoundError:
            pass

    # Overwrite the unresolvable list with whatever remains
    with open(MISSING_FILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sorted(still_missing)))
        if still_missing:
            fh.write("\n")
    if still_missing:
        print(f"  Unresolved → {MISSING_FILE}")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print()
    print("=" * 60)
    print(f"  Rescued        : {rescued_count}")
    print(f"  Still missing  : {len(still_missing)}")
    print(f"  TOTAL with IEI : {total_with_iei} / {TOTAL_MUNICIPALITIES}")
    print("=" * 60)

    if still_missing:
        print()
        for m in sorted(still_missing):
            print(f"  · {m}")

    print()


if __name__ == "__main__":
    main()
