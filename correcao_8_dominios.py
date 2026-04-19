"""ArquivoPT2026 — 7 Domain Corrections (batch 8)."""

import json, sys, time, unicodedata
import numpy as np
import pandas as pd
import requests

METRICS_FILE  = "metricas_iei_completo.csv"
CDX_ENDPOINT  = "https://arquivo.pt/wayback/cdx"
CDX_PARAMS    = {"matchType": "domain", "output": "json",
                 "fl": "timestamp,statuscode,original",
                 "from": "20100101", "limit": 200}
MAX_REF       = 365.0
REQUEST_DELAY = 0.3

CORRECTIONS = {
    "Albergaria-a-Velha":  ("albergaria-a-velha.pt",      "cm-albergaria.pt"),
    "Arcos de Valdevez":   ("arcosdevaldevez.pt",         "cmav.pt"),
    "Caldas da Rainha":    ("caldasdarainha.pt",           "mcr.pt"),
    "Castanheira de Pêra": ("castanheiradepera.pt",        "cm-castanheiradepera.pt"),
    "Ferreira do Alentejo":("ferreiradoalentejo.pt",       "cm-ferreira-alentejo.pt"),
    "Lajes do Pico":       ("municipio-lajes-do-pico.pt",  "cm-lajesdopico.pt"),
    "Porto de Mós":        ("portodemos.pt",               "municipio-portodemos.pt"),
}


def normalize_name(s):
    return (unicodedata.normalize("NFKD", s)
            .encode("ascii", "ignore").decode().strip().lower())


def fetch_timestamps(domain, session):
    r = session.get(CDX_ENDPOINT,
                    params={**CDX_PARAMS, "url": domain}, timeout=20)
    r.raise_for_status()
    out = []
    for line in r.text.strip().splitlines():
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
            out.append(t)
    return out


def compute_iei(raw_ts):
    ts = pd.Series(
        pd.to_datetime(raw_ts, format="%Y%m%d%H%M%S", errors="coerce")
    )
    ts = ts.dropna().sort_values().reset_index(drop=True)
    if len(ts) < 2:
        return np.nan, np.nan
    gaps     = pd.Series(ts.values).diff().dt.total_seconds().dropna() / 86_400
    mean_gap = gaps.mean()
    iei      = max(0.0, 100.0 - (mean_gap / MAX_REF) * 100.0)
    return round(mean_gap, 4), round(iei, 4)


def main():
    try:
        df = pd.read_csv(METRICS_FILE)
    except FileNotFoundError:
        print(f"ERROR: {METRICS_FILE} not found.")
        sys.exit(1)

    print(f"Loaded {len(df)} rows.\n")

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})

        for municipio, (old, new) in CORRECTIONS.items():
            try:
                ts_raw = fetch_timestamps(new, session)
            except requests.exceptions.RequestException as exc:
                print(f"  ✗ {municipio}: CDX error — {exc}")
                time.sleep(REQUEST_DELAY)
                continue
            finally:
                time.sleep(REQUEST_DELAY)

            if not ts_raw:
                print(f"  ✗ {municipio}: 0 records for {new} — kept {old}")
                continue

            mean_gap, iei = compute_iei(ts_raw)
            norm = normalize_name(municipio)
            mask = df["Município"].astype(str).map(normalize_name) == norm

            if not mask.any():
                print(f"  ✗ {municipio}: row not found in CSV")
                continue

            df.loc[mask, "Domain"]                    = new
            df.loc[mask, "Media_Dias_Entre_Capturas"] = mean_gap
            df.loc[mask, "IEI_Score"]                 = iei
            print(f"  ✓ {municipio}: {old} → {new}  (IEI: {iei})")

    df.to_csv(METRICS_FILE, index=False, encoding="utf-8")

    dup = df[df.duplicated(subset=["Domain"], keep=False)]
    print(f"\nTotal rows: {len(df)} | Duplicate domains: {len(dup)}")
    if len(df) == 308 and dup.empty:
        print("✓ DATASET LIMPO E COMPLETO — 308/308")
    else:
        if not dup.empty:
            print("⚠ Remaining duplicates:")
            for _, r in dup.iterrows():
                print(f"  {r['Município']:<30}  {r['Domain']}")


if __name__ == "__main__":
    main()
