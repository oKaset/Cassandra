#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "metricas_iei_completo.csv"
OUTPUT_CSV = ROOT / "data" / "arquivo_temporal_features.csv"
API_ENDPOINT = "https://arquivo.pt/wayback/cdx"
START_DATE = "20130101"
END_DATE = "20241231"
RATE_LIMIT_SECONDS = 1
TIMEOUT_SECONDS = 60
OUTPUT_COLUMNS = [
    "Município",
    "captures_2013_2018",
    "captures_2019_2024",
    "capture_trend",
    "last_capture_year",
    "years_since_last_capture",
]


def build_url(domain: str) -> str:
    params = {
        "url": domain,
        "output": "json",
        "fl": "timestamp",
        "limit": "100000",
        "from": START_DATE,
        "to": END_DATE,
    }
    return f"{API_ENDPOINT}?{urlencode(params)}"


def fetch_timestamps(domain: str) -> list[str]:
    result = subprocess.run(
        [
            "curl",
            "-L",
            "-sS",
            "--fail",
            "--max-time",
            str(TIMEOUT_SECONDS),
            build_url(domain),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = parse_cdx_payload(result.stdout)
    timestamps: list[str] = []
    for row in data:
        if isinstance(row, list):
            if not row or row[0] == "timestamp":
                continue
            timestamp = str(row[0])
        elif isinstance(row, dict):
            timestamp = str(row.get("timestamp", ""))
        else:
            continue
        if len(timestamp) >= 4 and timestamp[:4].isdigit():
            timestamps.append(timestamp)
    return timestamps


def parse_cdx_payload(payload: str) -> list[object]:
    payload = payload.strip()
    if not payload:
        return []
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        rows: list[object] = []
        for line in payload.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows


def calculate_features(municipio: str, timestamps: list[str]) -> dict[str, object]:
    years = [int(timestamp[:4]) for timestamp in timestamps]
    captures_2013_2018 = sum(2013 <= year <= 2018 for year in years)
    captures_2019_2024 = sum(2019 <= year <= 2024 for year in years)
    last_capture_year = max(years) if years else None

    return {
        "Município": municipio,
        "captures_2013_2018": captures_2013_2018,
        "captures_2019_2024": captures_2019_2024,
        "capture_trend": captures_2019_2024 - captures_2013_2018,
        "last_capture_year": last_capture_year,
        "years_since_last_capture": 2025 - last_capture_year if last_capture_year else None,
    }


def main() -> int:
    if not INPUT_CSV.exists():
        print(f"[ERROR] Missing input file: {INPUT_CSV}", file=sys.stderr)
        return 1

    df = pd.read_csv(INPUT_CSV, dtype=str)
    required_columns = {"Domain", "Município"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        print(f"[ERROR] Missing columns: {sorted(missing_columns)}", file=sys.stderr)
        return 1

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    total = len(df)

    for index, row in df.iterrows():
        municipio = str(row["Município"]).strip()
        domain = str(row["Domain"]).strip()
        print(f"[{index + 1:03d}/{total}] {municipio} | {domain}", file=sys.stderr)

        try:
            timestamps = fetch_timestamps(domain) if domain else []
        except Exception as exc:
            print(f"[WARN] {municipio}: {exc}", file=sys.stderr)
            timestamps = []

        rows.append(calculate_features(municipio, timestamps))

        if index < total - 1:
            time.sleep(RATE_LIMIT_SECONDS)

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] Saved {len(rows)} rows to {OUTPUT_CSV}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
