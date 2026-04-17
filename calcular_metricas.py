"""
ArquivoPT2026 — Metrics Engine: Índice de Entropia Institucional (IEI)
=======================================================================
Loads the extracted CDX data, cleans timestamps, and computes the IEI
for each domain.

IEI interpretation
------------------
The score measures how frequently an institution updates its web presence
relative to a fixed annual reference (MAX_REF = 365 days).

  Score ~100 → captures nearly every day  → institutionally active
  Score ~50  → captures every ~6 months   → moderately active
  Score  0   → gap ≥ 1 year between updates → institutionally stagnant/abandoned

WHY fixed reference instead of min-max normalisation:
  Min-max would rescale scores relative to whoever happens to be in the
  current dataset.  Adding a new domain (even a very active one) would
  silently shift every other domain's score.  The fixed MAX_REF = 365
  produces a stable, interpretable scale that does not change as we add
  more domains in later sprints.
"""

import sys
import logging

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("arquivopt.metricas")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INPUT_FILE  = "dados_extraidos_teste.csv"
OUTPUT_FILE = "metricas_iei.csv"

# Fixed reference: a domain updated less than once per year scores 0.
# Rationale: see module docstring above.
MAX_REF = 365.0

# ---------------------------------------------------------------------------
# 1. Load
# ---------------------------------------------------------------------------
log.info("=" * 60)
log.info("  ArquivoPT2026 — IEI Metrics Engine")
log.info("=" * 60)
log.info("Loading data from '%s' …", INPUT_FILE)

try:
    df = pd.read_csv(INPUT_FILE, dtype=str)
except FileNotFoundError:
    log.error("File not found: '%s'. Run extracao_massiva.py first.", INPUT_FILE)
    sys.exit(1)

log.info("  Rows loaded   : %d", len(df))
log.info("  Columns       : %s", list(df.columns))

# ---------------------------------------------------------------------------
# 2. Data Cleaning
# ---------------------------------------------------------------------------
log.info("")
log.info("Cleaning data …")

# Parse 14-digit compact timestamps (YYYYMMDDHHmmss)
df["Timestamp"] = pd.to_datetime(
    df["Timestamp"],
    format="%Y%m%d%H%M%S",
    errors="coerce",
)

nat_count = df["Timestamp"].isna().sum()
if nat_count:
    log.warning("  Dropping %d row(s) with unparseable timestamps.", nat_count)

df = df.dropna(subset=["Timestamp"])
log.info("  Rows after cleaning : %d", len(df))

# Sort — required so that diff() produces meaningful positive gaps
df = df.sort_values(["Domain", "Timestamp"]).reset_index(drop=True)

# ---------------------------------------------------------------------------
# 3. IEI Calculation per domain
# ---------------------------------------------------------------------------
log.info("")
log.info("Calculating IEI per domain …")

results = []

for domain, group in df.groupby("Domain", sort=False):

    n = len(group)

    # Need at least 2 captures to compute a gap
    if n < 2:
        log.warning(
            "  [%s] Only %d record(s) — cannot compute gaps. IEI_Score = NaN.",
            domain, n,
        )
        results.append({
            "Domain":                    domain,
            "N_Captures":                n,
            "Media_Dias_Entre_Capturas": np.nan,
            "IEI_Score":                 np.nan,
        })
        continue

    # diff() on datetime → Timedelta; convert to fractional days
    gaps_days = group["Timestamp"].diff().dt.total_seconds() / 86_400

    # First element is always NaT after diff(); dropna removes it
    mean_gap = gaps_days.dropna().mean()

    # Fixed-reference normalisation (see module docstring)
    iei_score = max(0.0, 100.0 - (mean_gap / MAX_REF) * 100.0)

    log.info(
        "  [%s] %d captures | mean gap = %.2f days | IEI = %.2f",
        domain, n, mean_gap, iei_score,
    )

    results.append({
        "Domain":                    domain,
        "N_Captures":                n,
        "Media_Dias_Entre_Capturas": round(mean_gap,  4),
        "IEI_Score":                 round(iei_score, 4),
    })

metrics_df = pd.DataFrame(results)

# ---------------------------------------------------------------------------
# 4. Export
# ---------------------------------------------------------------------------
output_cols = ["Domain", "Media_Dias_Entre_Capturas", "IEI_Score"]
metrics_df[output_cols].to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
log.info("")
log.info("Metrics saved → %s", OUTPUT_FILE)

# ---------------------------------------------------------------------------
# 5. Terminal summary table
# ---------------------------------------------------------------------------
separator  = "=" * 60
col_domain = 22
col_gap    = 28
col_score  = 10

header = (
    f"  {'Domain':<{col_domain}}"
    f"{'Media_Dias_Entre_Capturas':>{col_gap}}"
    f"{'IEI_Score':>{col_score}}"
)

print()
print(separator)
print("  RESULTADOS — Índice de Entropia Institucional (IEI)")
print(separator)
print(header)
print("-" * 60)

for _, row in metrics_df.iterrows():
    gap_str   = f"{row['Media_Dias_Entre_Capturas']:.2f}" if pd.notna(row["Media_Dias_Entre_Capturas"]) else "N/A"
    score_str = f"{row['IEI_Score']:.2f}"                  if pd.notna(row["IEI_Score"])                else "N/A"
    print(
        f"  {row['Domain']:<{col_domain}}"
        f"{gap_str:>{col_gap}}"
        f"{score_str:>{col_score}}"
    )

print(separator)
print(f"  Domínios processados : {len(metrics_df)}")
print(f"  Referência MAX_REF   : {int(MAX_REF)} dias")
print(f"  Ficheiro exportado   : {OUTPUT_FILE}")
print(separator)
print()
