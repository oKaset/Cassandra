"""
ArquivoPT2026 — Final Audit: 308 Municipalities
================================================
Read-only verification of metricas_iei_completo.csv.
Makes NO changes to the source file.

Check 1 : Duplicate domains.
Check 2 : Suspicious/short/generic domains.
Check 3 : Row count — confirms 308/308.
"""

import sys
import unicodedata

import pandas as pd

# ---------------------------------------------------------------------------
METRICS_FILE  = "metricas_iei_completo.csv"
OUTPUT_FILE   = "relatorio_auditoria_final.csv"
TOTAL         = 308

# Domains explicitly known to be wrong or too generic
KNOWN_BAD = {
    "guarda.pt", "angra.pt", "alter.pt", "marco.pt", "trofa.pt",
    "freixo.pt", "sba.pt", "torresvedras.pt", "barquinha.pt",
    "cabeceiras.pt", "paredesdecoura.pt",
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


def municipality_slug(municipio: str) -> str:
    """Accent-stripped, lowercased, spaces→hyphens slug of the municipality."""
    import string
    s = normalize_name(municipio).replace(" ", "-")
    allowed = set(string.ascii_lowercase + string.digits + "-")
    s = "".join(ch for ch in s if ch in allowed)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def is_suspicious(domain: str, municipio: str) -> bool:
    """
    Returns True if the domain looks suspicious:
      - In the explicit known-bad list, OR
      - Shorter than 10 chars, OR
      - Doesn't start with 'cm-' AND the municipality name
        isn't embedded anywhere in the domain.
    """
    if domain in KNOWN_BAD:
        return True
    if len(domain) < 10:
        return True
    if not domain.startswith("cm-"):
        # Check if any word of the slug appears in the domain
        slug = municipality_slug(municipio)
        words = [w for w in slug.split("-") if len(w) > 3]  # skip short words
        if words and not any(w in domain for w in words):
            return True
    return False


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    print("=" * 65)
    print("  ArquivoPT2026 — Final Audit Report")
    print("=" * 65)
    print()

    try:
        df = pd.read_csv(METRICS_FILE)
    except FileNotFoundError:
        print(f"ERROR: {METRICS_FILE} not found.")
        sys.exit(1)

    print(f"  Loaded {len(df)} rows from {METRICS_FILE}\n")

    # Initialise status column (all OK by default)
    df["Status"] = "OK"

    # -----------------------------------------------------------------------
    # CHECK 1 — Duplicate domains
    # -----------------------------------------------------------------------
    print("CHECK 1 — Duplicate domains")
    print("-" * 65)

    dup_mask   = df.duplicated(subset=["Domain"], keep=False)
    dup_df     = df[dup_mask].copy()
    dup_count  = 0

    if dup_df.empty:
        print("  ✓ No duplicate domains found.\n")
    else:
        df.loc[dup_mask, "Status"] = "DUPLICATE"
        for domain, group in dup_df.groupby("Domain"):
            dup_count += len(group)
            muns = " | ".join(group["Município"].tolist())
            print(f"  ⚠ {domain:<38}  [{muns}]")
        print(f"\n  {dup_count} row(s) flagged as DUPLICATE.\n")

    # -----------------------------------------------------------------------
    # CHECK 2 — Suspicious domains
    # -----------------------------------------------------------------------
    print("CHECK 2 — Suspicious / generic domains")
    print("-" * 65)

    susp_indices = []
    for idx, row in df.iterrows():
        if df.at[idx, "Status"] == "DUPLICATE":
            continue   # already flagged — don't double-count
        if is_suspicious(str(row["Domain"]), str(row["Município"])):
            susp_indices.append(idx)

    if not susp_indices:
        print("  ✓ No suspicious domains found.\n")
    else:
        df.loc[susp_indices, "Status"] = "SUSPICIOUS"
        for idx in susp_indices:
            reason = ""
            d = str(df.at[idx, "Domain"])
            m = str(df.at[idx, "Município"])
            if d in KNOWN_BAD:
                reason = "known-bad list"
            elif len(d) < 10:
                reason = f"too short ({len(d)} chars)"
            else:
                reason = "no municipality word in domain"
            print(f"  ⚠  {m:<30}  {d:<35}  [{reason}]")
        print(f"\n  {len(susp_indices)} row(s) flagged as SUSPICIOUS.\n")

    # -----------------------------------------------------------------------
    # CHECK 3 — Row count
    # -----------------------------------------------------------------------
    print("CHECK 3 — Total count")
    print("-" * 65)
    total_rows = len(df)
    total_iei  = df["IEI_Score"].notna().sum()

    if total_rows == TOTAL:
        print(f"  ✓ DATASET COMPLETO — {total_rows} / {TOTAL}")
    else:
        print(f"  ✗ TOTAL: {total_rows} / {TOTAL}  ({TOTAL - total_rows} missing)")

    print(f"  Rows with IEI_Score : {total_iei}")
    print()

    # -----------------------------------------------------------------------
    # Save audit report
    # -----------------------------------------------------------------------
    report = df[["Município", "Domain", "Status"]].copy()
    report.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    print(f"  Audit report saved → {OUTPUT_FILE}")

    # -----------------------------------------------------------------------
    # Final summary table
    # -----------------------------------------------------------------------
    ok_count   = (df["Status"] == "OK").sum()
    dup_total  = (df["Status"] == "DUPLICATE").sum()
    susp_total = (df["Status"] == "SUSPICIOUS").sum()

    print()
    print("=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    print(f"  {'OK':<20} {ok_count:>5}  ({ok_count/total_rows*100:.1f}%)")
    print(f"  {'DUPLICATE':<20} {dup_total:>5}  ({dup_total/total_rows*100:.1f}%)")
    print(f"  {'SUSPICIOUS':<20} {susp_total:>5}  ({susp_total/total_rows*100:.1f}%)")
    print(f"  {'TOTAL':<20} {total_rows:>5}")

    flagged_total = dup_total + susp_total
    if flagged_total == 0:
        print()
        print("  ✓ All 308 domains are clean — dataset ready for modelling.")
    else:
        print()
        print(f"  ⚠ {flagged_total} domain(s) require manual review.")
        print(f"    See {OUTPUT_FILE} for full details.")

    print("=" * 65)
    print()


if __name__ == "__main__":
    main()
