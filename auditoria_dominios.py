"""
ArquivoPT2026 — Domain Audit Pipeline
======================================
Verifies that every domain in metricas_iei_completo.csv genuinely
belongs to a câmara municipal by inspecting archived HTML content.

Strategy (two-pass per domain):
  Pass 1 — Auto-pass: "cm-" in the domain string → VERIFIED instantly,
            no network call needed (covers ~90% of our domains).
  Pass 2 — CDX query (limit=1) to get earliest timestamp,
            then fetch archived HTML and scan for verification signals.

Verification signals (case-insensitive):
  · "câmara municipal"
  · "município de"
  · "autarquia"
  · email pattern "geral@cm-"  or  "geral@{domain}"

Status codes:
  VERIFIED   — at least one signal found (or cm- auto-pass)
  SUSPICIOUS — fetched successfully but no signal found
  ERROR      — CDX lookup or HTML fetch failed / empty content
"""

import csv
import json
import logging
import re
import sys
import time
import unicodedata
from datetime import datetime

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
log = logging.getLogger("arquivopt.auditoria")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
METRICS_FILE = "metricas_iei_completo.csv"
OUTPUT_FILE  = "auditoria_resultados.csv"

CDX_ENDPOINT     = "https://arquivo.pt/wayback/cdx"
WAYBACK_ENDPOINT = "https://arquivo.pt/wayback"

REQUEST_DELAY    = 0.5   # seconds between every network call

# Signals that confirm an institutional camara municipal site
SIGNALS = [
    "câmara municipal",
    "camara municipal",      # accent-stripped fallback
    "município de",
    "municipio de",          # accent-stripped fallback
    "autarquia",
]

OUTPUT_COLS = ["Município", "Domain", "Status", "Signal_Found", "Notes"]


# ===========================================================================
# Helpers
# ===========================================================================

def auto_pass(domain: str) -> bool:
    """
    Domains containing 'cm-' are almost certainly câmara municipal sites
    by Portuguese naming convention. Auto-verify without fetching HTML.
    """
    return "cm-" in domain


def get_earliest_timestamp(domain: str, session: requests.Session) -> str:
    """
    Re-query CDX with limit=1 to obtain the earliest archived timestamp
    for this domain. Returns empty string on failure.
    """
    params = {
        "url":       domain,
        "matchType": "domain",
        "output":    "json",
        "fl":        "timestamp",
        "from":      "20100101",
        "limit":     1,
    }
    response = session.get(CDX_ENDPOINT, params=params, timeout=15)
    response.raise_for_status()

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
        ts = obj.get("timestamp", "")
        if ts:
            return ts

    return ""


def fetch_archived_html(timestamp: str, domain: str, session: requests.Session) -> str:
    """
    Fetch the archived homepage from Arquivo.pt Wayback Machine.
    URL format: https://arquivo.pt/wayback/{timestamp}/http://{domain}/
    Returns raw text content, or empty string on failure.
    """
    url = f"{WAYBACK_ENDPOINT}/{timestamp}/http://{domain}/"
    response = session.get(url, timeout=20, allow_redirects=True)
    response.raise_for_status()
    # Decode with detected encoding, fall back to latin-1 for Portuguese pages
    encoding = response.encoding or "latin-1"
    try:
        return response.content.decode(encoding, errors="replace")
    except Exception:
        return response.text


def check_signals(html: str, domain: str) -> tuple:
    """
    Scan HTML for verification signals.
    Returns (signal_found: str, verified: bool).
    """
    lowered = html.lower()

    # Remove HTML tags for cleaner text matching
    clean = re.sub(r"<[^>]+>", " ", lowered)

    for signal in SIGNALS:
        if signal in clean:
            return signal, True

    # Email pattern: geral@cm-  or  geral@{domain}
    email_patterns = [r"geral@cm-", rf"geral@{re.escape(domain)}"]
    for pat in email_patterns:
        if re.search(pat, clean):
            return f"email: {pat}", True

    return "", False


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    log.info("=" * 65)
    log.info("  ArquivoPT2026 — Domain Audit Pipeline")
    log.info("  Started : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 65)

    # Load metrics
    log.info("Loading '%s' …", METRICS_FILE)
    try:
        metrics = pd.read_csv(METRICS_FILE)
    except FileNotFoundError:
        log.error("File not found: %s", METRICS_FILE)
        sys.exit(1)

    total = len(metrics)
    log.info("  %d domains to audit.", total)
    log.info("")

    results    = []
    verified   = 0
    suspicious = 0
    errors     = 0

    with requests.Session() as session:
        session.headers.update({
            "User-Agent": "ArquivoPT2026-Audit/1.0 (academic research)",
            "Accept": "text/html,application/xhtml+xml",
        })

        for idx, row in metrics.iterrows():
            domain    = str(row["Domain"]).strip()
            municipio = str(row["Município"]).strip()
            counter   = f"[{int(idx)+1:>3}/{total}]"

            # ----------------------------------------------------------
            # Pass 1 — Auto-pass for cm- domains
            # ----------------------------------------------------------
            if auto_pass(domain):
                results.append({
                    "Município":    municipio,
                    "Domain":       domain,
                    "Status":       "VERIFIED",
                    "Signal_Found": "cm- in domain (auto-pass)",
                    "Notes":        "",
                })
                verified += 1
                log.info("%s %-32s %-35s → VERIFIED (auto)", counter, municipio, domain)
                continue

            # ----------------------------------------------------------
            # Pass 2a — CDX: get earliest timestamp
            # ----------------------------------------------------------
            timestamp = ""
            try:
                timestamp = get_earliest_timestamp(domain, session)
            except requests.exceptions.RequestException as exc:
                log.warning("%s %-32s CDX error: %s", counter, domain, exc)
            finally:
                time.sleep(REQUEST_DELAY)

            if not timestamp:
                results.append({
                    "Município":    municipio,
                    "Domain":       domain,
                    "Status":       "ERROR",
                    "Signal_Found": "",
                    "Notes":        "CDX returned no timestamp",
                })
                errors += 1
                log.warning("%s %-32s %-35s → ERROR (no timestamp)", counter, municipio, domain)
                continue

            # ----------------------------------------------------------
            # Pass 2b — Fetch archived HTML
            # ----------------------------------------------------------
            html = ""
            fetch_error = ""
            try:
                html = fetch_archived_html(timestamp, domain, session)
            except requests.exceptions.RequestException as exc:
                fetch_error = str(exc)[:120]
            finally:
                time.sleep(REQUEST_DELAY)

            if not html:
                results.append({
                    "Município":    municipio,
                    "Domain":       domain,
                    "Status":       "ERROR",
                    "Signal_Found": "",
                    "Notes":        fetch_error or "Empty HTML response",
                })
                errors += 1
                log.warning("%s %-32s %-35s → ERROR (empty HTML)", counter, municipio, domain)
                continue

            # ----------------------------------------------------------
            # Pass 2c — Signal check
            # ----------------------------------------------------------
            signal_found, is_verified = check_signals(html, domain)

            if is_verified:
                status = "VERIFIED"
                verified += 1
            else:
                status = "SUSPICIOUS"
                suspicious += 1

            results.append({
                "Município":    municipio,
                "Domain":       domain,
                "Status":       status,
                "Signal_Found": signal_found,
                "Notes":        f"Archived: {WAYBACK_ENDPOINT}/{timestamp}/http://{domain}/",
            })

            log.info(
                "%s %-32s %-35s → %s  %s",
                counter, municipio, domain, status,
                f"[{signal_found}]" if signal_found else "",
            )

    # -----------------------------------------------------------------------
    # Save results
    # -----------------------------------------------------------------------
    log.info("")
    log.info("Saving audit results → %s", OUTPUT_FILE)
    results_df = pd.DataFrame(results, columns=OUTPUT_COLS)
    results_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print()
    print("=" * 65)
    print("  AUDIT COMPLETE")
    print("=" * 65)
    print(f"  {'VERIFIED':<20} {verified:>5}  ({verified/total*100:.1f}%)")
    print(f"  {'SUSPICIOUS':<20} {suspicious:>5}  ({suspicious/total*100:.1f}%)")
    print(f"  {'ERROR':<20} {errors:>5}  ({errors/total*100:.1f}%)")
    print(f"  {'Total audited':<20} {total:>5}")
    print("-" * 65)
    print(f"  Results file : {OUTPUT_FILE}")
    print("=" * 65)

    suspicious_rows = [r for r in results if r["Status"] == "SUSPICIOUS"]
    if suspicious_rows:
        print()
        print("  ⚠  SUSPICIOUS DOMAINS — manual review required:")
        print(f"  {'Município':<30}  {'Domain':<35}")
        print(f"  {'-'*30}  {'-'*35}")
        for r in suspicious_rows:
            print(f"  {r['Município']:<30}  {r['Domain']:<35}")
            if r["Notes"]:
                print(f"  {'':30}  Archive: {r['Notes']}")
    else:
        print()
        print("  ✓ No suspicious domains found.")

    print()


if __name__ == "__main__":
    main()
