"""
ArquivoPT2026 — Group A Domain Corrections (8 municipalities)
==============================================================
Replaces 8 generic/wrong domains with verified official ones.
6 legitimate acronym domains are whitelisted and untouched.
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
METRICS_FILE  = "metricas_iei_completo.csv"
CDX_ENDPOINT  = "https://arquivo.pt/wayback/cdx"
CDX_PARAMS    = {
    "matchType": "domain",
    "output":    "json",
    "fl":        "timestamp,statuscode,original",
    "from":      "20100101",
    "limit":     200,
}
MAX_REF       = 365.0
REQUEST_DELAY = 0.3
TOTAL         = 308

# Corrections: 'Município': ('old_domain', 'new_domain')
CORRECTIONS = {
    "Trofa":                    ("trofa.pt",         "mun-trofa.pt"),
    "Alter do Chão":            ("alter.pt",          "cm-alter.pt"),
    "Vila Nova da Barquinha":   ("barquinha.pt",      "cm-vnbarquinha.pt"),
    "Cabeceiras de Basto":      ("cabeceiras.pt",     "cabeceirasdebasto.pt"),
    "Freixo de Espada à Cinta": ("freixo.pt",         "cm-freixoespadacinta.pt"),
    "Marco de Canaveses":       ("marco.pt",          "cm-marco-canaveses.pt"),
    "Paredes de Coura":         ("paredesdecoura.pt", "cm-paredes-coura.pt"),
    "São Brás de Alportel":     ("sba.pt",            "cm-sbras.pt"),
}

# These short/acronym domains are legitimate — do not touch
WHITELIST = {
    "cm-fcr.pt", "cm-oaz.pt", "cm-sjm.pt",
    "cm-olb.pt", "cmpv.pt",   "cmvfc.pt",
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


def fetch_timestamps(domain: str, session: requests.Session) -> list:
    """Return list of raw timestamp strings from CDX for domain."""
    response = session.get(
        CDX_ENDPOINT,
        params={**CDX_PARAMS, "url": domain},
        timeout=20,
    )
    response.raise_for_status()
    ts_list = []
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
        t = obj.get("timestamp", "")
        if t:
            ts_list.append(t)
    return ts_list


def compute_iei(raw_timestamps: list) -> tuple:
    """
    Compute (mean_gap_days, IEI_Score) from a list of timestamp strings.
    Uses pd.Series wrapping after sort to guarantee .dt accessor works.
    Returns (NaN, NaN) if fewer than 2 valid timestamps.
    """
    ts = pd.Series(
        pd.to_datetime(raw_timestamps, format="%Y%m%d%H%M%S", errors="coerce")
    )
    ts = ts.dropna().sort_values().reset_index(drop=True)

    if len(ts) < 2:
        return np.nan, np.nan

    gaps     = pd.Series(ts.values).diff().dt.total_seconds().dropna() / 86_400
    mean_gap = gaps.mean()
    iei      = max(0.0, 100.0 - (mean_gap / MAX_REF) * 100.0)
    return round(mean_gap, 4), round(iei, 4)


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    print("=" * 65)
    print("  ArquivoPT2026 — Group A Domain Corrections")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)
    print(f"  Whitelisted domains (untouched): {', '.join(sorted(WHITELIST))}")
    print()

    try:
        df = pd.read_csv(METRICS_FILE)
    except FileNotFoundError:
        print(f"ERROR: {METRICS_FILE} not found.")
        sys.exit(1)

    print(f"  Loaded {len(df)} rows.\n")

    # -----------------------------------------------------------------------
    # Phase 1+2 — Verify & apply
    # -----------------------------------------------------------------------
    print("PHASE 1+2 — CDX verification & correction")
    print("-" * 65)

    results = []

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})

        for municipio, (old_domain, new_domain) in CORRECTIONS.items():
            print(f"  Verifying: {new_domain}")
            try:
                timestamps = fetch_timestamps(new_domain, session)
            except requests.exceptions.RequestException as exc:
                print(f"    ✗ CDX error: {exc} — keeping old domain.")
                results.append((municipio, old_domain, None, None, "ERROR"))
                time.sleep(REQUEST_DELAY)
                continue
            finally:
                time.sleep(REQUEST_DELAY)

            if not timestamps:
                print(f"    ✗ 0 records — keeping old domain '{old_domain}'.")
                results.append((municipio, old_domain, None, None, "NOT FOUND"))
                continue

            mean_gap, iei = compute_iei(timestamps)
            print(f"    ✓ {len(timestamps)} records | mean_gap={mean_gap} d | IEI={iei}")

            # Update row in DataFrame
            norm = normalize_name(municipio)
            mask = df["Município"].astype(str).map(normalize_name) == norm

            if not mask.any():
                print(f"    ✗ Row for '{municipio}' not found in CSV — skipping.")
                results.append((municipio, old_domain, new_domain, iei, "ROW NOT FOUND"))
                continue

            df.loc[mask, "Domain"]                    = new_domain
            df.loc[mask, "Media_Dias_Entre_Capturas"] = mean_gap
            df.loc[mask, "IEI_Score"]                 = iei
            results.append((municipio, old_domain, new_domain, iei, "UPDATED"))

    # Save
    df.to_csv(METRICS_FILE, index=False, encoding="utf-8")
    print(f"\n  Saved {len(df)} rows → {METRICS_FILE}")

    # -----------------------------------------------------------------------
    # Phase 3 — Final report
    # -----------------------------------------------------------------------
    print()
    print("PHASE 3 — Results")
    print("-" * 65)

    for municipio, old, new, iei, status in results:
        if status == "UPDATED":
            print(f"  ✓ {municipio}: {old} → {new}  (IEI: {iei})")
        else:
            label = f"kept {old}" if status == "NOT FOUND" else status
            print(f"  ✗ {municipio}: no records found — {label}")

    # Duplicate domain check
    dup = df[df.duplicated(subset=["Domain"], keep=False)]
    total_rows = len(df)

    print()
    print("=" * 65)
    print(f"  Total rows          : {total_rows}")
    print(f"  Rows with IEI_Score : {df['IEI_Score'].notna().sum()}")

    if dup.empty:
        print("  Duplicate domains   : none ✓")
    else:
        print(f"  Duplicate domains   : {len(dup)} ⚠")
        for _, r in dup.iterrows():
            print(f"    {r['Município']:<30}  {r['Domain']}")

    print()
    if total_rows == TOTAL and dup.empty:
        print("  ✓ DATASET LIMPO E COMPLETO — 308/308")
    elif total_rows == TOTAL:
        print(f"  ✓ 308/308 — but {len(dup)} duplicate domain(s) remain.")
    else:
        print(f"  TOTAL: {total_rows}/{TOTAL}  ({TOTAL - total_rows} missing)")

    print("=" * 65)
    print()


if __name__ == "__main__":
    main()
