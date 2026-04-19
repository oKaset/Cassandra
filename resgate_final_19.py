"""
ArquivoPT2026 — Final Rescue: 19 Municipalities
================================================
CDX-verifies a manually researched domain dictionary and appends
validated records + IEI scores to metricas_iei_completo.csv.
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
MISSING_FILE  = "municipios_sem_web.txt"   # updated at the end

CDX_ENDPOINT = "https://arquivo.pt/wayback/cdx"
CDX_PARAMS   = {
    "matchType": "domain",
    "output":    "json",
    "fl":        "timestamp,statuscode,original",
    "from":      "20100101",
    "limit":     200,
}

MAX_REF       = 365.0
REQUEST_DELAY = 0.3

# ---------------------------------------------------------------------------
# Manually researched domain candidates — CDX is the final arbiter
# ---------------------------------------------------------------------------
MUNICIPIOS_FINAIS = {
    "Castelo de Paiva":        ["cm-castelo-de-paiva.pt",    "cm-castelo-paiva.pt"],
    "Castelo de Vide":         ["cm-castelo-de-vide.pt",     "cm-casteldevide.pt"],
    "Lajes das Flores":        ["cm-lajes-flores.pt",        "lajes-flores.pt"],
    "Marinha Grande":          ["cm-marinhagrande.pt",       "cm-marinha-grande.pt"],
    "Miranda do Douro":        ["cm-miranda-douro.pt",       "cm-mirandadouro.pt"],
    "Montemor-o-Velho":        ["cm-mvo.pt",                 "cm-montemor-o-velho.pt"],
    "Oliveira do Bairro":      ["cm-olbairro.pt",            "cm-oliveira-bairro.pt"],
    "Paços de Ferreira":       ["cm-pacos-ferreira.pt",      "cm-pacosferreira.pt"],
    "Reguengos de Monsaraz":   ["cm-reguengos.pt",           "cm-reguengos-monsaraz.pt"],
    "Santa Cruz das Flores":   ["cm-santacruzdasflores.pt",  "cm-santa-cruz-flores.pt"],
    "Santana":                 ["cm-santana.pt",             "santana.pt"],
    "Santo Tirso":             ["cm-santotirso.pt",          "cm-santo-tirso.pt"],
    "Sever do Vouga":          ["cm-severvouga.pt",          "cm-sever-vouga.pt"],
    "Terras de Bouro":         ["cm-terrasbouro.pt",         "cm-terras-bouro.pt"],
    "Vieira do Minho":         ["cm-vieiraminho.pt",         "cm-vieira-minho.pt"],
    "Vila Franca do Campo":    ["cm-vfcampo.pt",             "cm-vilafrancadocampo.pt"],
    "Vila Nova de Cerveira":   ["cm-vncerveira.pt",          "cm-cerveira.pt"],
    "Vila Nova de Poiares":    ["cm-poiares.pt",             "cm-vlnovapoiares.pt"],
    "Vila da Praia da Vitória":["cm-praia-vitoria.pt",       "cm-praiavitoria.pt"],
}

TOTAL_MUNICIPALITIES = 308


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
    print("=" * 60)
    print("  ArquivoPT2026 — Final Rescue (19 Municipalities)")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    total          = len(MUNICIPIOS_FINAIS)
    rescued_count  = 0
    still_missing  = []
    all_records    = []

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})

        for idx, (municipio, candidates) in enumerate(MUNICIPIOS_FINAIS.items(), start=1):
            found = False

            for domain in candidates:
                try:
                    records = fetch_cdx(domain, municipio, session)
                except requests.exceptions.RequestException as exc:
                    print(f"  ! [{domain}] request error: {exc}")
                    time.sleep(REQUEST_DELAY)
                    continue
                finally:
                    time.sleep(REQUEST_DELAY)

                if records:
                    all_records.extend(records)
                    rescued_count += 1
                    found = True
                    print(
                        f"  ✓ [{idx:>2}/{total}] {municipio:<32} "
                        f"→ {domain}  ({len(records)} records)"
                    )
                    break

            if not found:
                still_missing.append(municipio)
                print(
                    f"  ✗ [{idx:>2}/{total}] {municipio:<32} "
                    f"→ all {len(candidates)} candidate(s) failed"
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

    # Update the unresolvable list if it exists
    if still_missing:
        with open(MISSING_FILE, "w", encoding="utf-8") as fh:
            fh.write("\n".join(sorted(still_missing)) + "\n")
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
        for m in still_missing:
            print(f"  · {m}")

    print()


if __name__ == "__main__":
    main()
