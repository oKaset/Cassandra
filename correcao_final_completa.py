"""
ArquivoPT2026 — Final Complete Correction
==========================================
Fixes domain collisions and wrong assignments identified by the
domain audit, then adds the 1 still-missing municipality to reach 308/308.

Phase 1 : CDX verification of all new/added domains.
Phase 2 : IEI recalculation for verified domains.
Phase 3 : Apply corrections in-place + append addition.
Phase 4 : Final validation report.
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
METRICS_FILE         = "metricas_iei_completo.csv"
TOTAL_MUNICIPALITIES = 308
MAX_REF              = 365.0
REQUEST_DELAY        = 0.3

CDX_ENDPOINT = "https://arquivo.pt/wayback/cdx"
CDX_PARAMS   = {
    "matchType": "domain",
    "output":    "json",
    "fl":        "timestamp,statuscode,original",
    "from":      "20100101",
    "limit":     200,
}

# ---------------------------------------------------------------------------
# Corrections: 'Município': ('old_domain', 'new_domain')
# ---------------------------------------------------------------------------
CORRECTIONS = {
    "Vila do Porto":     ("cm-porto.pt",    "cm-viladoporto.pt"),
    "Miranda do Corvo":  ("cm-corvo.pt",    "cm-mirandadocorvo.pt"),
    "Guarda":            ("guarda.pt",      "mun-guarda.pt"),
    "Torres Vedras":     ("torresvedras.pt","cm-tvedras.pt"),
    "Angra do Heroísmo": ("angra.pt",       "angradoheroismo.pt"),
}

# ---------------------------------------------------------------------------
# Addition: municipality missing entirely from CSV
# ---------------------------------------------------------------------------
ADDITION = {
    "Vila Franca do Campo": "cmvfc.pt",
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


def fetch_cdx(domain: str, session: requests.Session) -> list:
    """Fetch NDJSON records for domain; returns list of raw dicts."""
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
            "Timestamp":  obj.get("timestamp",  ""),
            "StatusCode": obj.get("statuscode", ""),
            "URL":        obj.get("original",   ""),
        })
    return records


def compute_iei(records: list) -> tuple:
    """
    Given a list of CDX record dicts, return (mean_gap, iei_score).
    Returns (NaN, NaN) for < 2 valid timestamps.
    """
    if not records:
        return np.nan, np.nan

    ts = pd.to_datetime(
        [r["Timestamp"] for r in records],
        format="%Y%m%d%H%M%S",
        errors="coerce",
    )
    ts = ts.dropna().sort_values()

    if len(ts) < 2:
        return np.nan, np.nan

    ts       = pd.Series(ts.values)   # re-wrap: sort_values on Index loses Series type
    gaps     = ts.diff().dt.total_seconds().dropna() / 86_400
    mean_gap = gaps.mean()
    iei      = max(0.0, 100.0 - (mean_gap / MAX_REF) * 100.0)
    return round(mean_gap, 4), round(iei, 4)


# ===========================================================================
# Phase 1+2 — Verify & compute IEI for all new domains
# ===========================================================================

def verify_and_compute(
    domains: dict,       # {municipio: new_domain}
    session: requests.Session,
) -> dict:
    """
    For each (municipio, domain) pair: CDX-fetch and compute IEI.
    Returns {municipio: {'domain': ..., 'mean_gap': ..., 'iei': ..., 'ok': bool}}
    """
    results = {}
    for municipio, domain in domains.items():
        print(f"  Verifying: {municipio:<32} → {domain}")
        try:
            records = fetch_cdx(domain, session)
        except requests.exceptions.RequestException as exc:
            print(f"    ✗ CDX error: {exc}")
            results[municipio] = {"domain": domain, "ok": False, "notes": str(exc)}
            time.sleep(REQUEST_DELAY)
            continue
        finally:
            time.sleep(REQUEST_DELAY)

        if not records:
            print(f"    ✗ 0 records — WARNING: domain not in archive. Old data kept.")
            results[municipio] = {"domain": domain, "ok": False, "notes": "0 CDX records"}
            continue

        mean_gap, iei = compute_iei(records)
        results[municipio] = {
            "domain":   domain,
            "mean_gap": mean_gap,
            "iei":      iei,
            "ok":       True,
            "n_records": len(records),
        }
        print(f"    ✓ {len(records)} records | mean_gap={mean_gap} days | IEI={iei}")

    return results


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    print("=" * 65)
    print("  ArquivoPT2026 — Final Complete Correction")
    print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)
    print()

    # Load CSV
    try:
        df = pd.read_csv(METRICS_FILE)
    except FileNotFoundError:
        print(f"ERROR: {METRICS_FILE} not found.")
        sys.exit(1)

    print(f"  Loaded {len(df)} rows from {METRICS_FILE}")
    print()

    # ------------------------------------------------------------------
    # Phase 1+2 — Verify all new domains
    # ------------------------------------------------------------------
    print("PHASE 1+2 — CDX verification & IEI calculation")
    print("-" * 65)

    # Build flat map of municipio → new_domain for all operations
    all_new: dict = {}
    for municipio, (_, new_domain) in CORRECTIONS.items():
        all_new[municipio] = new_domain
    for municipio, new_domain in ADDITION.items():
        all_new[municipio] = new_domain

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})
        verified = verify_and_compute(all_new, session)

    print()

    # ------------------------------------------------------------------
    # Phase 3 — Apply corrections in-place
    # ------------------------------------------------------------------
    print("PHASE 3 — Applying corrections & addition")
    print("-" * 65)

    # Work on a copy; we'll rebuild at the end
    df["_norm"] = df["Município"].astype(str).map(normalize_name)

    # 3a. Corrections — update existing rows
    for municipio, (old_domain, new_domain) in CORRECTIONS.items():
        info = verified.get(municipio, {})
        if not info.get("ok", False):
            print(f"  SKIP correction [{municipio}]: new domain not verified, keeping old data.")
            continue

        # Find row by old domain OR by município name (in case domain was already fixed)
        mask_domain = df["Domain"] == old_domain
        mask_mun    = df["_norm"] == normalize_name(municipio)
        mask        = mask_domain | mask_mun

        if not mask.any():
            print(f"  WARN [{municipio}]: row with domain '{old_domain}' not found in CSV.")
            continue

        df.loc[mask, "Domain"]                    = new_domain
        df.loc[mask, "Media_Dias_Entre_Capturas"] = info["mean_gap"]
        df.loc[mask, "IEI_Score"]                 = info["iei"]

        print(
            f"  ✓ [{municipio}] {old_domain} → {new_domain}  "
            f"(IEI: {info['iei']})"
        )

    # 3b. Addition — append if município not already present
    for municipio, new_domain in ADDITION.items():
        info = verified.get(municipio, {})
        norm = normalize_name(municipio)

        already_present = (df["_norm"] == norm).any()
        if already_present:
            if info.get("ok", False):
                # Update existing row with correct domain/IEI
                mask = df["_norm"] == norm
                df.loc[mask, "Domain"]                    = new_domain
                df.loc[mask, "Media_Dias_Entre_Capturas"] = info["mean_gap"]
                df.loc[mask, "IEI_Score"]                 = info["iei"]
                print(f"  ✓ [{municipio}] updated existing row → {new_domain}  (IEI: {info['iei']})")
            else:
                print(f"  SKIP addition [{municipio}]: already present and new domain unverified.")
            continue

        if not info.get("ok", False):
            print(f"  SKIP addition [{municipio}]: not in archive — cannot add.")
            continue

        new_row = pd.DataFrame([{
            "Domain":                    new_domain,
            "Município":                 municipio,
            "Media_Dias_Entre_Capturas": info["mean_gap"],
            "IEI_Score":                 info["iei"],
            "_norm":                     norm,
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        print(f"  ✓ [{municipio}] added → {new_domain}  (IEI: {info['iei']})")

    # 3c. Deduplicate on município — keep='last' so corrections win
    before = len(df)
    df = df.drop_duplicates(subset="_norm", keep="last")
    after  = len(df)
    if before != after:
        print(f"  Removed {before - after} duplicate município row(s).")

    # Drop helper column and save
    df = df.drop(columns=["_norm"])
    df.to_csv(METRICS_FILE, index=False, encoding="utf-8")
    print(f"  Saved {len(df)} rows → {METRICS_FILE}")
    print()

    # ------------------------------------------------------------------
    # Phase 4 — Validation report
    # ------------------------------------------------------------------
    print("PHASE 4 — Final validation report")
    print("=" * 65)

    total_rows  = len(df)
    total_iei   = df["IEI_Score"].notna().sum()

    # Duplicate domains
    dup_domains = df[df.duplicated(subset=["Domain"], keep=False)][["Município", "Domain"]]
    # Duplicate municípios
    dup_norms   = df.copy()
    dup_norms["_norm"] = dup_norms["Município"].astype(str).map(normalize_name)
    dup_muns    = dup_norms[dup_norms.duplicated(subset=["_norm"], keep=False)][["Município", "Domain"]]

    print(f"  Total rows in CSV     : {total_rows}")
    print(f"  Rows with IEI_Score   : {total_iei}")
    print(f"  Duplicate domains     : {len(dup_domains)}")
    print(f"  Duplicate municípios  : {len(dup_muns)}")
    print()

    if not dup_domains.empty:
        print("  ⚠ Duplicate domain entries:")
        for _, r in dup_domains.iterrows():
            print(f"    {r['Município']:<30}  {r['Domain']}")
        print()

    if not dup_muns.empty:
        print("  ⚠ Duplicate município entries:")
        for _, r in dup_muns.iterrows():
            print(f"    {r['Município']:<30}  {r['Domain']}")
        print()

    # Check which of the 308 are missing
    # We compare against the demographic file if available, otherwise just report count
    print("=" * 65)
    if total_rows >= TOTAL_MUNICIPALITIES:
        print(f"  ✓ DATASET COMPLETO — {total_rows} / {TOTAL_MUNICIPALITIES}")
    else:
        missing_n = TOTAL_MUNICIPALITIES - total_rows
        print(f"  TOTAL: {total_rows} / {TOTAL_MUNICIPALITIES}  ({missing_n} still missing)")

        # Try to identify missing by cross-referencing demo file
        try:
            demo = pd.read_excel("dados_demograficos.csv", header=1)
            if "Município" in demo.columns:
                all_muns = set(
                    demo["Município"].dropna().astype(str).str.strip()
                    .map(normalize_name)
                )
                found_muns = set(df["Município"].astype(str).map(normalize_name))
                missing_names = all_muns - found_muns
                if missing_names:
                    print()
                    print("  Still missing:")
                    for m in sorted(missing_names):
                        print(f"    · {m}")
        except Exception:
            pass   # demo file not available — that's fine

    print("=" * 65)
    print()


if __name__ == "__main__":
    main()
