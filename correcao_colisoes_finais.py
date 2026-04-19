"""
ArquivoPT2026 — Collision & Missing Municipality Fix
=====================================================
Resolves the 3 remaining issues in metricas_iei_completo.csv:
  1. Corvo            → wrong domain cm-mirandadocorvo.pt → cm-corvo.pt
  2. Lagoa [R.A.A.]  → collision on cm-lagoa.pt → lagoa-acores.pt
  3. Calheta [R.A.M.] → missing entirely → cmcalheta.pt
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
TOTAL         = 308

# ---------------------------------------------------------------------------
# Issues to fix:  (municipio, new_domain, action)
#   action: 'update' = find existing row and replace domain + IEI
#           'add'    = append new row
# ---------------------------------------------------------------------------
FIXES = [
    ("Corvo",            "cm-corvo.pt",      "update"),
    ("Lagoa [R.A.A.]",  "lagoa-acores.pt",   "update"),
    ("Calheta [R.A.M.]","cmcalheta.pt",       "add"),
]


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
        records.append(obj.get("timestamp", ""))
    return [r for r in records if r]   # list of timestamp strings


def compute_iei(timestamps: list) -> tuple:
    ts = pd.to_datetime(timestamps, format="%Y%m%d%H%M%S", errors="coerce")
    ts = ts.dropna().sort_values()
    if len(ts) < 2:
        return np.nan, np.nan
    ts       = pd.Series(ts.values)   # re-wrap to Series so .dt works after sort
    gaps     = ts.diff().dt.total_seconds().dropna() / 86_400
    mean_gap = gaps.mean()
    iei      = max(0.0, 100.0 - (mean_gap / MAX_REF) * 100.0)
    return round(mean_gap, 4), round(iei, 4)


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    print("=" * 60)
    print("  ArquivoPT2026 — Collision & Missing Municipality Fix")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    try:
        df = pd.read_csv(METRICS_FILE)
    except FileNotFoundError:
        print(f"ERROR: {METRICS_FILE} not found.")
        sys.exit(1)

    print(f"  Loaded {len(df)} rows.\n")

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})

        for municipio, domain, action in FIXES:
            print(f"  [{action.upper()}] {municipio:<28} → {domain}")

            # CDX verify
            try:
                timestamps = fetch_cdx(domain, session)
            except requests.exceptions.RequestException as exc:
                print(f"    ✗ CDX error: {exc} — skipping.")
                time.sleep(REQUEST_DELAY)
                continue
            finally:
                time.sleep(REQUEST_DELAY)

            if not timestamps:
                print(f"    ✗ 0 records in archive — skipping.")
                continue

            mean_gap, iei = compute_iei(timestamps)
            print(f"    ✓ {len(timestamps)} records | mean_gap={mean_gap} d | IEI={iei}")

            norm = normalize_name(municipio)
            mask = df["Município"].astype(str).map(normalize_name) == norm

            if action == "update":
                if not mask.any():
                    print(f"    ✗ Row for '{municipio}' not found in CSV — skipping.")
                    continue
                df.loc[mask, "Domain"]                    = domain
                df.loc[mask, "Media_Dias_Entre_Capturas"] = mean_gap
                df.loc[mask, "IEI_Score"]                 = iei
                print(f"    → Row updated.")

            elif action == "add":
                if mask.any():
                    # Already present — just update domain/IEI
                    df.loc[mask, "Domain"]                    = domain
                    df.loc[mask, "Media_Dias_Entre_Capturas"] = mean_gap
                    df.loc[mask, "IEI_Score"]                 = iei
                    print(f"    → Already present — domain/IEI updated.")
                else:
                    new_row = pd.DataFrame([{
                        "Domain":                    domain,
                        "Município":                 municipio,
                        "Media_Dias_Entre_Capturas": mean_gap,
                        "IEI_Score":                 iei,
                    }])
                    df = pd.concat([df, new_row], ignore_index=True)
                    print(f"    → Row appended.")

    # Deduplicate on Município (keep='first' — originals preserved, dupes removed)
    df["_norm"] = df["Município"].astype(str).map(normalize_name)
    before = len(df)
    df = df.drop_duplicates(subset="_norm", keep="first")
    df = df.drop(columns=["_norm"])
    if len(df) < before:
        print(f"\n  Removed {before - len(df)} duplicate row(s).")

    df.to_csv(METRICS_FILE, index=False, encoding="utf-8")

    # ------------------------------------------------------------------
    # Final report
    # ------------------------------------------------------------------
    total_rows = len(df)
    total_iei  = df["IEI_Score"].notna().sum()

    dup_domains = df[df.duplicated(subset=["Domain"], keep=False)]

    print()
    print("=" * 60)
    print("  FINAL REPORT")
    print("=" * 60)
    print(f"  Total rows          : {total_rows}")
    print(f"  Rows with IEI_Score : {total_iei}")

    if dup_domains.empty:
        print("  Duplicate domains   : none ✓")
    else:
        print(f"  Duplicate domains   : {len(dup_domains)} ⚠")
        for _, r in dup_domains.iterrows():
            print(f"    {r['Município']:<32}  {r['Domain']}")

    print()
    if total_rows >= TOTAL:
        print(f"  ✓ {total_rows}/{TOTAL} — DATASET COMPLETO")
    else:
        print(f"  TOTAL: {total_rows}/{TOTAL}  ({TOTAL - total_rows} still missing)")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
