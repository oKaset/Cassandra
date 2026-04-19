"""
ArquivoPT2026 — Single Municipality Rescue: Vila Franca do Campo
"""

import json
import sys
import time
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd
import requests

METRICS_FILE = "metricas_iei_completo.csv"
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

MUNICIPIO  = "Vila Franca do Campo"
CANDIDATES = ["cmvfc.pt", "cm-vfc.pt"]


def normalize_name(s: str) -> str:
    return (
        unicodedata.normalize("NFKD", s)
        .encode("ascii", "ignore")
        .decode()
        .strip()
        .lower()
    )


def fetch_cdx(domain: str, session: requests.Session) -> list:
    response = session.get(
        CDX_ENDPOINT, params={**CDX_PARAMS, "url": domain}, timeout=20
    )
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
            "Município":  MUNICIPIO,
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
    df = df.sort_values("Timestamp").reset_index(drop=True)
    n  = len(df)
    if n < 2:
        return pd.DataFrame([{
            "Domain":                    df["Domain"].iloc[0] if n else "",
            "Município":                 MUNICIPIO,
            "Media_Dias_Entre_Capturas": np.nan,
            "IEI_Score":                 np.nan,
        }])
    gaps     = df["Timestamp"].diff().dt.total_seconds() / 86_400
    mean_gap = gaps.dropna().mean()
    iei      = max(0.0, 100.0 - (mean_gap / MAX_REF) * 100.0)
    return pd.DataFrame([{
        "Domain":                    df["Domain"].iloc[0],
        "Município":                 MUNICIPIO,
        "Media_Dias_Entre_Capturas": round(mean_gap, 4),
        "IEI_Score":                 round(iei,      4),
    }])


def main() -> None:
    print(f"  Rescuing: {MUNICIPIO}")
    print(f"  Candidates: {CANDIDATES}")
    print()

    found_records = []
    found_domain  = None

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})
        for domain in CANDIDATES:
            try:
                records = fetch_cdx(domain, session)
            except requests.exceptions.RequestException as exc:
                print(f"  ! [{domain}] error: {exc}")
                time.sleep(REQUEST_DELAY)
                continue
            finally:
                time.sleep(REQUEST_DELAY)

            if records:
                found_records = records
                found_domain  = domain
                print(f"  ✓ {MUNICIPIO} → {domain}  ({len(records)} records)")
                break

    if not found_records:
        print(f"  ✗ {MUNICIPIO} → all candidates failed")
        sys.exit(0)

    # IEI
    new_row = calculate_iei(found_records)

    # Merge
    try:
        existing = pd.read_csv(METRICS_FILE)
    except FileNotFoundError:
        print(f"  ERROR: {METRICS_FILE} not found.")
        sys.exit(1)

    combined = pd.concat([existing, new_row], ignore_index=True)
    combined["_norm"] = combined["Município"].astype(str).map(normalize_name)
    combined = combined.drop_duplicates(subset="_norm", keep="first")
    combined = combined.drop(columns=["_norm"])
    combined.to_csv(METRICS_FILE, index=False, encoding="utf-8")

    total_with_iei = combined["IEI_Score"].notna().sum()
    print(f"  IEI_Score      : {new_row['IEI_Score'].iloc[0]:.2f}")
    print(f"  Total CSV rows : {len(combined)}")
    print(f"  Total with IEI : {total_with_iei} / 308")


if __name__ == "__main__":
    main()
