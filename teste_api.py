"""
ArquivoPT2026 — Day 1 Proof of Concept
---------------------------------------
Tests the data extraction pipeline by querying the Arquivo.pt CDX API
for historical snapshots of the target domain (cm-penamacor.pt).

API reference: https://arquivo.pt/api
"""

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CDX_ENDPOINT = "https://arquivo.pt/wayback/cdx"

PARAMS = {
    "url": "cm-penamacor.pt",
    "matchType": "domain",
    "output": "json",
    "fl": "timestamp,statuscode",
    "limit": 5,
}

# ---------------------------------------------------------------------------
# HTTP request
# ---------------------------------------------------------------------------
print("=" * 55)
print("  ArquivoPT2026 — CDX API Connection Test")
print("=" * 55)
print(f"\n  Endpoint : {CDX_ENDPOINT}")
print(f"  Target   : {PARAMS['url']}")
print(f"  Fields   : {PARAMS['fl']}")
print(f"  Limit    : {PARAMS['limit']}\n")
print("-" * 55)

try:
    response = requests.get(CDX_ENDPOINT, params=PARAMS, timeout=15)
    response.raise_for_status()
except requests.exceptions.ConnectionError:
    print("[ERROR] Could not reach the API. Check your internet connection.")
    raise SystemExit(1)
except requests.exceptions.Timeout:
    print("[ERROR] The request timed out (>15 s). Try again later.")
    raise SystemExit(1)
except requests.exceptions.HTTPError as exc:
    print(f"[ERROR] HTTP error: {exc}")
    raise SystemExit(1)
except requests.exceptions.RequestException as exc:
    print(f"[ERROR] Unexpected request error: {exc}")
    raise SystemExit(1)

# ---------------------------------------------------------------------------
# JSON parsing
# NOTE: Arquivo.pt CDX returns NDJSON — one JSON object per line.
#       Each line is a self-contained record like:
#         {"timestamp": "20001018210819", "statuscode": "200"}
#       We parse line-by-line; malformed lines are skipped with a warning.
# ---------------------------------------------------------------------------
raw_text = response.text.strip()

if not raw_text:
    print("[WARNING] The API returned an empty response. No snapshots found.")
    raise SystemExit(0)

records = []
for line_number, line in enumerate(raw_text.splitlines(), start=1):
    line = line.strip()
    if not line:
        continue
    try:
        obj = __import__('json').loads(line)
        records.append(obj)
    except ValueError:
        print(f"[WARNING] Could not parse line {line_number}: {line[:80]}")

if not records:
    print("[WARNING] No valid records could be parsed from the response.")
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
print(f"  {'#':<4}  {'Timestamp':<18}  {'Status'}")
print(f"  {'-'*4}  {'-'*18}  {'-'*6}")

for i, record in enumerate(records, start=1):
    timestamp  = record.get("timestamp", "—")
    statuscode = record.get("statuscode", "—")
    print(f"  {i:<4}  {timestamp:<18}  {statuscode}")

print("-" * 55)
print(f"\n  ✓ {len(records)} record(s) retrieved successfully.\n")
