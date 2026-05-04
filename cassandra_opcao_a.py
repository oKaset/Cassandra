#!/usr/bin/env python3
"""
CASSANDRA - Opcao A pipeline.

End-to-end workflow:
1. Extract Arquivo.pt CDX records with resumable checkpoints.
2. Engineer domain and municipality features.
3. Merge features into the existing CASSANDRA matrix.
4. Retrain baseline and V2 XGBoost classifiers with optional SMOTE and compare weighted F1.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import unicodedata
import warnings
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_recall_fscore_support
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier


CDX_ENDPOINT = "https://arquivo.pt/wayback/cdx"
CDX_LIMIT = 5000
REQUEST_TIMEOUT_SECONDS = 30

DOMAINS_CSV = Path("municipios_dominios.csv")
SOURCE_MATRIX_CSV = Path("relatorio_produto_cassandra.csv")
CHECKPOINT_JSON = Path("cdx_checkpoint.json")
FAILURES_LOG = Path("failures.log")
FEATURES_CSV = Path("features_opcao_a.csv")
MERGED_MATRIX_CSV = Path("feature_matrix_v2.csv")
COMPARISON_TXT = Path("model_comparison.txt")
SMOTE_REPORT_TXT = Path("model_smote_report.txt")

TARGET_COL = "CASSANDRA_Risk_Tier"
SCORE_COL = "CASSANDRA_Risk_Score"
MUNICIPIO_COL = "Município"
RANDOM_STATE = 42
N_SPLITS = 5
PREVIOUS_WEIGHTED_F1 = 0.8614

BASELINE_FEATURE_COLUMNS = [
    "Var_Pop",
    "IEI_Score",
    "Total_Arquivo_Captures",
    "Live_StatusCode",
]

NEW_FEATURE_COLUMNS = [
    "site_mortality_rate",
    "unique_domains",
    "capture_acceleration",
    "last_capture_gap_days",
]

XGB_DEFAULT_HYPERPARAMS: dict[str, Any] = {
    "n_estimators": 100,
    "max_depth": 6,
    "learning_rate": 0.3,
    "subsample": 1.0,
    "colsample_bytree": 1.0,
    "min_child_weight": 1,
}

XGB_FIXED_PARAMS: dict[str, Any] = {
    "random_state": RANDOM_STATE,
    "verbosity": 0,
    "eval_metric": "mlogloss",
    "n_jobs": -1,
}

CDX_DEFAULT_FIELDS = [
    "urlkey",
    "timestamp",
    "original",
    "mimetype",
    "statuscode",
    "digest",
    "length",
]


def print_step(title: str) -> None:
    print(f"\n=== {title} ===")


def normalize_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return " ".join(text.split())


def normalize_header(value: Any) -> str:
    text = normalize_text(value)
    chars = [char if char.isalnum() else "_" for char in text]
    return "_".join("".join(chars).split("_")).strip("_")


def read_csv_utf8(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def write_csv_utf8(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8")


def resolve_column(df: pd.DataFrame, candidates: list[str], label: str) -> str:
    normalized_to_original = {normalize_header(col): col for col in df.columns}
    for candidate in candidates:
        normalized = normalize_header(candidate)
        if normalized in normalized_to_original:
            return normalized_to_original[normalized]
    available = ", ".join(df.columns)
    raise KeyError(f"Could not find {label}. Available columns: {available}")


def load_domain_mapping(path: Path = DOMAINS_CSV) -> pd.DataFrame:
    df = read_csv_utf8(path)
    municipio_col = resolve_column(df, ["municipio", "município"], "municipality column")
    domain_col = resolve_column(df, ["dominio", "domínio", "domain"], "domain column")

    mapping = df[[municipio_col, domain_col]].rename(
        columns={municipio_col: "municipio_raw", domain_col: "domain"}
    )
    mapping["municipio"] = mapping["municipio_raw"].map(normalize_text)
    mapping["domain"] = mapping["domain"].astype(str).str.strip()
    mapping = mapping[(mapping["municipio"] != "") & (mapping["domain"] != "")]
    mapping["domain_key"] = mapping["domain"].map(normalize_domain_key)
    mapping = mapping.drop_duplicates(subset=["municipio", "domain_key"]).reset_index(drop=True)
    return mapping


def normalize_domain_key(domain: Any) -> str:
    text = str(domain).strip().lower().rstrip("/")
    if text.endswith("/*"):
        text = text[:-2]
    return text


def cdx_url_pattern(domain: str) -> str:
    clean = str(domain).strip().rstrip("/")
    return clean if clean.endswith("/*") else f"{clean}/*"


def load_checkpoint(path: Path = CHECKPOINT_JSON) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object keyed by domain.")
    return payload


def save_checkpoint(checkpoint: dict[str, list[dict[str, Any]]], path: Path = CHECKPOINT_JSON) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(checkpoint, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, path)


def append_failure(domain: str, error: str, path: Path = FAILURES_LOG) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp}\t{domain}\t{error}\n")


def extract_resume_key(item: Any) -> str | None:
    resume_names = {"resume_key", "resumekey"}
    if isinstance(item, dict):
        for key, value in item.items():
            if normalize_header(key) in resume_names and value:
                return str(value)
    if isinstance(item, list) and len(item) >= 2:
        first = normalize_header(item[0])
        if first in resume_names and item[1]:
            return str(item[1])
    return None


def extract_resume_key_from_text(line: str) -> str | None:
    text = line.strip()
    if not text:
        return None
    for separator in [":", "\t", "="]:
        if separator not in text:
            continue
        key, value = text.split(separator, 1)
        if normalize_header(key) in {"resume_key", "resumekey"} and value.strip():
            return value.strip()
    return None


def looks_like_cdx_header(row: Any) -> bool:
    if not isinstance(row, list) or not row or not all(isinstance(value, str) for value in row):
        return False
    normalized = {normalize_header(value) for value in row}
    return bool({"timestamp", "original", "statuscode", "status_code", "url"} & normalized)


def list_row_to_record(row: list[Any], header: list[str] | None = None) -> dict[str, Any]:
    fields = header if header else CDX_DEFAULT_FIELDS
    record = {str(field): value for field, value in zip(fields, row)}
    if len(row) > len(fields):
        for idx, value in enumerate(row[len(fields) :], start=len(fields)):
            record[f"extra_{idx}"] = value
    return record


def sequence_to_records(sequence: list[Any]) -> tuple[list[dict[str, Any]], str | None]:
    resume_key: str | None = None
    data_items: list[Any] = []

    for item in sequence:
        item_resume_key = extract_resume_key(item)
        if item_resume_key:
            resume_key = item_resume_key
            continue
        data_items.append(item)

    if not data_items:
        return [], resume_key

    header: list[str] | None = None
    start_idx = 0
    if looks_like_cdx_header(data_items[0]):
        header = [str(value) for value in data_items[0]]
        start_idx = 1

    records: list[dict[str, Any]] = []
    for item in data_items[start_idx:]:
        if isinstance(item, dict):
            records.append(item)
        elif isinstance(item, list):
            records.append(list_row_to_record(item, header))

    return records, resume_key


def payload_to_records(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    resume_key = extract_resume_key(payload)

    if isinstance(payload, list):
        return sequence_to_records(payload)

    if isinstance(payload, dict):
        records_payload: Any | None = None
        for key in ["records", "results", "items", "data", "rows"]:
            if key in payload and isinstance(payload[key], list):
                records_payload = payload[key]
                break

        if records_payload is None:
            record_like_keys = {"timestamp", "original", "statuscode", "url", "status"}
            normalized_keys = {normalize_header(key) for key in payload}
            if record_like_keys & normalized_keys:
                return [payload], resume_key
            return [], resume_key

        records, nested_resume_key = sequence_to_records(records_payload)
        return records, nested_resume_key or resume_key

    return [], resume_key


def parse_cdx_response(response: requests.Response) -> tuple[list[dict[str, Any]], str | None]:
    text = response.text.strip()
    if not text:
        return [], None

    payload = [json.loads(line) for line in text.splitlines() if line.strip()]
    return payload_to_records(payload)


def get_cdx_page(
    session: requests.Session,
    domain: str,
    resume_key: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    request_url = (
        f"{CDX_ENDPOINT}?url={cdx_url_pattern(domain)}"
        f"&output=json&limit={CDX_LIMIT}&showResumeKey=true"
    )
    if resume_key:
        request_url += f"&resumeKey={resume_key}"

    try:
        response = session.get(request_url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return parse_cdx_response(response)
    finally:
        time.sleep(1)


def fetch_domain_cdx(session: requests.Session, domain: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    resume_key: str | None = None
    seen_resume_keys: set[str] = set()

    while True:
        page_records, next_resume_key = get_cdx_page(session, domain, resume_key)
        records.extend(page_records)

        if len(page_records) == CDX_LIMIT and next_resume_key:
            if next_resume_key in seen_resume_keys:
                raise RuntimeError(f"Repeated resume_key detected: {next_resume_key}")
            seen_resume_keys.add(next_resume_key)
            resume_key = next_resume_key
            continue

        return records


def run_cdx_extraction(mapping: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    import requests
    from tqdm import tqdm

    print_step("STEP 1: CDX Extraction")
    checkpoint = load_checkpoint()
    total_domains = len(mapping)
    skipped = sum(1 for key in mapping["domain_key"] if key in checkpoint)
    print(f"Domains in input: {total_domains}")
    print(f"Already checkpointed: {skipped}")
    print(f"Checkpoint file: {CHECKPOINT_JSON}")

    with requests.Session() as session:
        session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "CASSANDRA-Opcao-A/1.0 (+https://arquivo.pt)",
            }
        )

        progress = tqdm(mapping.itertuples(index=False), total=total_domains, unit="domain")
        for row in progress:
            domain = row.domain
            domain_key = row.domain_key
            progress.set_description(f"CDX {domain_key[:35]}")

            if domain_key in checkpoint:
                continue

            try:
                records = fetch_domain_cdx(session, domain)
            except requests.exceptions.Timeout as exc:
                append_failure(domain_key, f"timeout: {exc}")
                tqdm.write(f"[WARN] {domain_key}: timeout")
                continue
            except requests.exceptions.HTTPError as exc:
                append_failure(domain_key, f"http_error: {exc}")
                tqdm.write(f"[WARN] {domain_key}: HTTP error: {exc}")
                continue
            except requests.exceptions.RequestException as exc:
                append_failure(domain_key, f"request_error: {exc}")
                tqdm.write(f"[WARN] {domain_key}: request error: {exc}")
                continue
            except (ValueError, json.JSONDecodeError, RuntimeError) as exc:
                append_failure(domain_key, f"parse_or_pagination_error: {exc}")
                tqdm.write(f"[WARN] {domain_key}: parse/pagination error: {exc}")
                continue

            checkpoint[domain_key] = records
            save_checkpoint(checkpoint)

    print(f"Extraction complete. Checkpointed domains: {len(checkpoint)}")
    return checkpoint


def record_get(record: Any, candidate_keys: list[str]) -> Any:
    normalized_candidates = {normalize_header(key) for key in candidate_keys}
    if isinstance(record, dict):
        for key, value in record.items():
            if normalize_header(key) in normalized_candidates:
                return value
        return None
    if isinstance(record, list):
        as_record = list_row_to_record(record)
        return record_get(as_record, candidate_keys)
    return None


def parse_status_code(value: Any) -> int | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        return int(float(text))
    except (TypeError, ValueError):
        return None


def parse_cdx_timestamp(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) < 8 or not text[:8].isdigit():
        return None
    try:
        if len(text) >= 14 and text[:14].isdigit():
            return datetime.strptime(text[:14], "%Y%m%d%H%M%S").date()
        return datetime.strptime(text[:8], "%Y%m%d").date()
    except ValueError:
        return None


def extract_hostname(url: Any) -> str | None:
    if url is None:
        return None
    text = str(url).strip()
    if not text:
        return None
    parsed = urlsplit(text if "://" in text else f"http://{text}")
    hostname = parsed.hostname
    return hostname.lower() if hostname else None


def shift_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(month=2, day=28, year=day.year + years)


def compute_domain_features(records: list[dict[str, Any]], today: date) -> dict[str, float]:
    total_captures = len(records)
    statuses = [
        parse_status_code(record_get(record, ["statuscode", "status_code", "status", "statusCode"]))
        for record in records
    ]

    if total_captures == 0:
        site_mortality_rate = np.nan
    else:
        failures = sum(1 for status in statuses if status is not None and 400 <= status <= 599)
        site_mortality_rate = failures / total_captures

    hostnames = {
        hostname
        for hostname in (
            extract_hostname(record_get(record, ["original", "url", "url_original"])) for record in records
        )
        if hostname
    }

    capture_dates = [
        parsed_date
        for parsed_date in (
            parse_cdx_timestamp(record_get(record, ["timestamp", "capture_timestamp"])) for record in records
        )
        if parsed_date is not None
    ]

    start_last_3y = shift_years(today, -3)
    start_previous_3y = shift_years(today, -6)
    captures_last_3y = sum(start_last_3y <= captured <= today for captured in capture_dates)
    captures_previous_3y = sum(start_previous_3y <= captured < start_last_3y for captured in capture_dates)

    if total_captures < 10 or captures_previous_3y == 0:
        capture_acceleration = np.nan
    else:
        capture_acceleration = captures_last_3y / captures_previous_3y

    status_200_dates = [
        captured
        for captured, status in zip(capture_dates_by_record(records), statuses)
        if captured is not None and status == 200
    ]
    if status_200_dates:
        last_capture_gap_days = float((today - max(status_200_dates)).days)
    else:
        last_capture_gap_days = np.nan

    return {
        "site_mortality_rate": float(site_mortality_rate) if not pd.isna(site_mortality_rate) else np.nan,
        "unique_domains": float(len(hostnames)),
        "capture_acceleration": float(capture_acceleration) if not pd.isna(capture_acceleration) else np.nan,
        "last_capture_gap_days": last_capture_gap_days,
    }


def capture_dates_by_record(records: list[dict[str, Any]]) -> list[date | None]:
    return [
        parse_cdx_timestamp(record_get(record, ["timestamp", "capture_timestamp"]))
        for record in records
    ]


def run_feature_engineering(
    mapping: pd.DataFrame,
    checkpoint: dict[str, list[dict[str, Any]]] | None = None,
) -> pd.DataFrame:
    print_step("STEP 2: Feature Engineering")
    if checkpoint is None:
        checkpoint = load_checkpoint()

    today = date.today()
    domain_rows: list[dict[str, Any]] = []
    for row in mapping.itertuples(index=False):
        records = checkpoint.get(row.domain_key, [])
        features = compute_domain_features(records, today)
        domain_rows.append(
            {
                "municipio": row.municipio,
                "domain": row.domain_key,
                **features,
            }
        )

    domain_features = pd.DataFrame(domain_rows)
    municipality_features = (
        domain_features.groupby("municipio", as_index=False)[NEW_FEATURE_COLUMNS]
        .median(numeric_only=True)
        .sort_values("municipio")
        .reset_index(drop=True)
    )

    for feature in NEW_FEATURE_COLUMNS:
        national_median = municipality_features[feature].median(skipna=True)
        if pd.isna(national_median):
            national_median = 0.0
            print(f"[WARN] {feature}: national median is NaN; filling with 0.0")
        municipality_features[feature] = municipality_features[feature].fillna(national_median)

    write_csv_utf8(municipality_features[["municipio", *NEW_FEATURE_COLUMNS]], FEATURES_CSV)
    print(f"Saved {FEATURES_CSV} with {len(municipality_features)} municipalities.")
    return municipality_features


def add_normalized_municipio(df: pd.DataFrame) -> pd.DataFrame:
    municipio_col = resolve_column(df, ["municipio", "município"], "municipality column")
    out = df.copy()
    out["municipio"] = out[municipio_col].map(normalize_text)
    return out


def drop_sparse_columns(df: pd.DataFrame) -> pd.DataFrame:
    critical = {
        normalize_header("municipio"),
        normalize_header(MUNICIPIO_COL),
        normalize_header(TARGET_COL),
        normalize_header(SCORE_COL),
    }
    nan_rates = df.isna().mean()
    drop_cols = [
        col for col, rate in nan_rates.items() if rate > 0.40 and normalize_header(col) not in critical
    ]
    if drop_cols:
        print(f"Dropping columns with NaN rate > 40%: {', '.join(drop_cols)}")
    return df.drop(columns=drop_cols)


def drop_correlated_new_features(df: pd.DataFrame) -> pd.DataFrame:
    available = [feature for feature in NEW_FEATURE_COLUMNS if feature in df.columns]
    if len(available) < 2:
        return df

    numeric_new = df[available].apply(pd.to_numeric, errors="coerce")
    variances = numeric_new.var(skipna=True)
    corr = numeric_new.corr(method="pearson")
    to_drop: set[str] = set()

    for idx, left in enumerate(available):
        if left in to_drop:
            continue
        for right in available[idx + 1 :]:
            if right in to_drop:
                continue
            r_value = corr.loc[left, right]
            if pd.notna(r_value) and r_value > 0.85:
                left_var = variances.get(left, np.nan)
                right_var = variances.get(right, np.nan)
                if pd.isna(left_var):
                    left_var = -np.inf
                if pd.isna(right_var):
                    right_var = -np.inf
                drop_feature = left if left_var < right_var else right
                to_drop.add(drop_feature)
                print(
                    f"Dropping correlated new feature {drop_feature} "
                    f"({left} vs {right}, r={r_value:.3f})"
                )

    return df.drop(columns=sorted(to_drop)) if to_drop else df


def run_merge() -> pd.DataFrame:
    print_step("STEP 3: Merge with Existing Feature Matrix")
    if not FEATURES_CSV.exists():
        raise FileNotFoundError(
            f"{FEATURES_CSV} not found. Run extraction first or provide the file before --skip-extraction."
        )

    source = add_normalized_municipio(read_csv_utf8(SOURCE_MATRIX_CSV))
    features = read_csv_utf8(FEATURES_CSV)
    if "municipio" not in features.columns:
        features = add_normalized_municipio(features)
    features["municipio"] = features["municipio"].map(normalize_text)

    merged = source.merge(features[["municipio", *NEW_FEATURE_COLUMNS]], on="municipio", how="left")
    merged = drop_sparse_columns(merged)
    merged = drop_correlated_new_features(merged)

    write_csv_utf8(merged, MERGED_MATRIX_CSV)
    print(f"Saved {MERGED_MATRIX_CSV} with shape {merged.shape}.")
    return merged


def prepare_features(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    raw = df[feature_cols].copy()
    numeric_parts: list[pd.Series] = []
    categorical_parts: list[pd.Series] = []

    for col in raw.columns:
        series = raw[col]
        if pd.api.types.is_numeric_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
            median = numeric.median(skipna=True)
            numeric_parts.append(numeric.fillna(0.0 if pd.isna(median) else median).rename(col))
            continue

        parsed = pd.to_numeric(series, errors="coerce")
        numeric_ratio = parsed.notna().mean()
        if numeric_ratio >= 0.95:
            parsed = parsed.replace([np.inf, -np.inf], np.nan)
            median = parsed.median(skipna=True)
            numeric_parts.append(parsed.fillna(0.0 if pd.isna(median) else median).rename(col))
        else:
            categorical_parts.append(series.fillna("MISSING").astype(str).rename(col))

    frames: list[pd.DataFrame] = []
    if numeric_parts:
        frames.append(pd.concat(numeric_parts, axis=1))
    if categorical_parts:
        categorical = pd.concat(categorical_parts, axis=1)
        frames.append(pd.get_dummies(categorical, dummy_na=False, dtype=float))

    if not frames:
        raise ValueError("No usable feature columns found for training.")

    features = pd.concat(frames, axis=1)
    features = features.astype(float)
    return features


class ReportWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines: list[str] = []

    def write(self, line: str = "") -> None:
        text = str(line)
        print(text)
        self.lines.append(text)

    def write_lines(self, lines: list[str]) -> None:
        for line in lines:
            self.write(line)

    def save(self) -> None:
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def new_xgb_classifier(hyperparams: dict[str, Any] | None = None) -> XGBClassifier:
    params = {**XGB_DEFAULT_HYPERPARAMS, **(hyperparams or {}), **XGB_FIXED_PARAMS}
    return XGBClassifier(**params)


def smote_resample_training_fold(X_train: pd.DataFrame, y_train: np.ndarray) -> tuple[pd.DataFrame, np.ndarray]:
    from imblearn.over_sampling import SMOTE

    sm = SMOTE(random_state=42)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="`BaseEstimator._validate_data` is deprecated.*",
            category=FutureWarning,
        )
        X_train_res, y_train_res = sm.fit_resample(X_train, y_train)
    if not isinstance(X_train_res, pd.DataFrame):
        X_train_res = pd.DataFrame(X_train_res, columns=X_train.columns)
    return X_train_res, np.asarray(y_train_res)


def top_feature_importances(model: XGBClassifier, feature_names: list[str], n: int = 10) -> list[tuple[str, float]]:
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        return []
    series = pd.Series(importances, index=feature_names).sort_values(ascending=False)
    return [(str(name), float(value)) for name, value in series.head(n).items()]


def load_evaluation_matrix(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input matrix not found: {path}")

    df = read_csv_utf8(path)
    if TARGET_COL not in df.columns:
        raise KeyError(f"Target column not found: {TARGET_COL}")

    df = df.dropna(subset=[TARGET_COL]).copy()
    df[TARGET_COL] = df[TARGET_COL].astype(str).str.strip()

    class_counts = df[TARGET_COL].value_counts()
    too_small = class_counts[class_counts < N_SPLITS]
    if not too_small.empty:
        details = ", ".join(f"{label}: {count}" for label, count in too_small.items())
        raise ValueError(f"StratifiedKFold({N_SPLITS}) requires at least {N_SPLITS} rows per class. {details}")

    return df.reset_index(drop=True)


def dropped_training_columns(df: pd.DataFrame) -> list[str]:
    excluded = {normalize_header(MUNICIPIO_COL), normalize_header(SCORE_COL)}
    return [col for col in df.columns if normalize_header(col) in excluded]


def feature_columns_for_training(df: pd.DataFrame, baseline_only: bool = False) -> list[str]:
    excluded = {
        normalize_header(MUNICIPIO_COL),
        normalize_header("municipio"),
        normalize_header(TARGET_COL),
        normalize_header(SCORE_COL),
    }

    if baseline_only:
        missing = [col for col in BASELINE_FEATURE_COLUMNS if col not in df.columns]
        if missing:
            raise KeyError(f"Missing baseline feature columns: {', '.join(missing)}")
        candidates = BASELINE_FEATURE_COLUMNS
    else:
        candidates = list(df.columns)

    return [col for col in candidates if normalize_header(col) not in excluded]


def summarize_cv_metrics(
    name: str,
    feature_names: list[str],
    weighted_f1s: list[float],
    per_fold_metrics: list[dict[str, np.ndarray]],
    importance_matrix: np.ndarray,
    class_names: np.ndarray,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for class_idx, class_name in enumerate(class_names):
        precision_values = np.array([fold["precision"][class_idx] for fold in per_fold_metrics], dtype=float)
        recall_values = np.array([fold["recall"][class_idx] for fold in per_fold_metrics], dtype=float)
        f1_values = np.array([fold["f1"][class_idx] for fold in per_fold_metrics], dtype=float)
        support_total = int(sum(int(fold["support"][class_idx]) for fold in per_fold_metrics))
        rows.append(
            {
                "class": str(class_name),
                "precision": float(precision_values.mean()),
                "recall": float(recall_values.mean()),
                "f1": float(f1_values.mean()),
                "support": support_total,
            }
        )

    return {
        "name": name,
        "feature_names": feature_names,
        "weighted_f1s": weighted_f1s,
        "weighted_f1_mean": float(np.mean(weighted_f1s)),
        "weighted_f1_std": float(np.std(weighted_f1s, ddof=1)) if len(weighted_f1s) > 1 else 0.0,
        "class_summary": rows,
        "importance_matrix": importance_matrix,
    }


def run_stratified_cv(
    name: str,
    X: pd.DataFrame,
    y: np.ndarray,
    class_names: np.ndarray,
    hyperparams: dict[str, Any] | None = None,
    use_smote: bool = True,
) -> dict[str, Any]:
    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    labels = list(range(len(class_names)))
    weighted_f1s: list[float] = []
    per_fold_metrics: list[dict[str, np.ndarray]] = []
    fold_importances: list[np.ndarray] = []

    for train_idx, test_idx in skf.split(X, y):
        X_train = X.iloc[train_idx]
        X_test = X.iloc[test_idx]
        y_train = y[train_idx]
        y_test = y[test_idx]
        X_fit = X_train
        y_fit = y_train

        if use_smote:
            X_fit, y_fit = smote_resample_training_fold(X_train, y_train)

        model = new_xgb_classifier(hyperparams)
        sample_weights = compute_sample_weight(class_weight="balanced", y=y_fit)
        model.fit(X_fit, y_fit, sample_weight=sample_weights)

        y_pred = model.predict(X_test)
        weighted_f1s.append(float(f1_score(y_test, y_pred, average="weighted", zero_division=0)))
        precision, recall, f1, support = precision_recall_fscore_support(
            y_test,
            y_pred,
            labels=labels,
            zero_division=0,
        )
        per_fold_metrics.append(
            {
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "support": support,
            }
        )
        fold_importances.append(np.asarray(model.feature_importances_, dtype=float))

    return summarize_cv_metrics(
        name=name,
        feature_names=list(X.columns),
        weighted_f1s=weighted_f1s,
        per_fold_metrics=per_fold_metrics,
        importance_matrix=np.vstack(fold_importances),
        class_names=class_names,
    )


def format_class_metric_table(rows: list[dict[str, Any]], include_support: bool = True) -> list[str]:
    class_width = max(32, *(len(row["class"]) for row in rows))
    if include_support:
        lines = [f"{'class':<{class_width}} {'precision':>10} {'recall':>10} {'f1-score':>10} {'support':>9}"]
    else:
        lines = [f"{'class':<{class_width}} {'precision':>10} {'recall':>10} {'f1-score':>10}"]

    for row in rows:
        if include_support:
            lines.append(
                f"{row['class']:<{class_width}} "
                f"{row['precision']:>10.4f} {row['recall']:>10.4f} {row['f1']:>10.4f} {row['support']:>9d}"
            )
        else:
            lines.append(
                f"{row['class']:<{class_width}} "
                f"{row['precision']:>10.4f} {row['recall']:>10.4f} {row['f1']:>10.4f}"
            )

    return lines


def write_cv_result(report: ReportWriter, result: dict[str, Any], include_support: bool = True) -> None:
    report.write(
        f"{result['name']} weighted F1: "
        f"{result['weighted_f1_mean']:.4f} ± {result['weighted_f1_std']:.4f}"
    )
    report.write("Mean per-class metrics across 5 folds:")
    report.write_lines(format_class_metric_table(result["class_summary"], include_support=include_support))


def top_mean_importances(result: dict[str, Any], n: int = 10) -> list[tuple[str, float]]:
    mean_importances = pd.Series(
        result["importance_matrix"].mean(axis=0),
        index=result["feature_names"],
    ).sort_values(ascending=False)
    return [(str(name), float(value)) for name, value in mean_importances.head(n).items()]


def analyze_and_clean_features(
    X: pd.DataFrame,
    importance_matrix: np.ndarray,
    report: ReportWriter,
) -> list[str]:
    mean_importance = pd.Series(importance_matrix.mean(axis=0), index=X.columns)
    zero_features = [
        feature
        for idx, feature in enumerate(X.columns)
        if bool(np.all(importance_matrix[:, idx] <= 0.0))
    ]

    if zero_features:
        report.write("Zero-importance features removed:")
        for feature in zero_features:
            report.write(f"  - {feature}")
    else:
        report.write("Zero-importance features removed: none")

    remaining = [feature for feature in X.columns if feature not in set(zero_features)]
    correlation_drops: set[str] = set()

    if len(remaining) > 1:
        corr = X[remaining].corr(method="pearson")
        report.write("Correlation pruning threshold: Pearson r > 0.85")
        for left_idx, left in enumerate(remaining):
            if left in correlation_drops:
                continue
            for right in remaining[left_idx + 1 :]:
                if right in correlation_drops:
                    continue
                r_value = corr.loc[left, right]
                if pd.isna(r_value) or r_value <= 0.85:
                    continue

                left_importance = float(mean_importance[left])
                right_importance = float(mean_importance[right])
                drop_feature = left if left_importance < right_importance else right
                keep_feature = right if drop_feature == left else left
                correlation_drops.add(drop_feature)
                report.write(
                    f"  - Dropping {drop_feature} "
                    f"({left} vs {right}, r={r_value:.4f}; "
                    f"kept {keep_feature} with higher mean importance)"
                )
                if drop_feature == left:
                    break

    if not correlation_drops:
        report.write("Correlation-pruned features removed: none")

    clean_features = [feature for feature in remaining if feature not in correlation_drops]
    report.write(f"Final clean feature list ({len(clean_features)} features):")
    for feature in clean_features:
        report.write(f"  - {feature}")
    return clean_features


def ensure_optuna(report: ReportWriter) -> Any:
    try:
        import optuna

        return optuna
    except ImportError:
        report.write("Optuna not found. Installing with pip install optuna ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "optuna"])
        import optuna

        return optuna


def cross_validated_weighted_f1(
    X: pd.DataFrame,
    y: np.ndarray,
    hyperparams: dict[str, Any],
    use_smote: bool = True,
) -> float:
    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    fold_scores: list[float] = []

    for train_idx, test_idx in skf.split(X, y):
        X_train = X.iloc[train_idx]
        y_train = y[train_idx]
        X_fit = X_train
        y_fit = y_train

        if use_smote:
            X_fit, y_fit = smote_resample_training_fold(X_train, y_train)

        model = new_xgb_classifier(hyperparams)
        sample_weights = compute_sample_weight(class_weight="balanced", y=y_fit)
        model.fit(X_fit, y_fit, sample_weight=sample_weights)
        y_pred = model.predict(X.iloc[test_idx])
        fold_scores.append(float(f1_score(y[test_idx], y_pred, average="weighted", zero_division=0)))

    return float(np.mean(fold_scores))


def run_optuna_tuning(
    X: pd.DataFrame,
    y: np.ndarray,
    report: ReportWriter,
    n_trials: int = 50,
    use_smote: bool = True,
) -> tuple[dict[str, Any], float]:
    optuna = ensure_optuna(report)
    optuna.logging.set_verbosity(optuna.logging.ERROR)

    def objective(trial: Any) -> float:
        hyperparams = {
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 100, 500),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
        }
        return cross_validated_weighted_f1(X, y, hyperparams, use_smote=use_smote)

    sampler = optuna.samplers.TPESampler(seed=RANDOM_STATE)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_params = dict(study.best_params)
    best_value = float(study.best_value)
    report.write(f"Best Optuna CV weighted F1: {best_value:.4f}")
    report.write(f"Best Optuna params: {json.dumps(best_params, sort_keys=True)}")
    return best_params, best_value


def fit_final_model(
    X: pd.DataFrame,
    y: np.ndarray,
    hyperparams: dict[str, Any],
    use_smote: bool = True,
) -> tuple[XGBClassifier, int]:
    X_fit = X
    y_fit = y
    if use_smote:
        X_fit, y_fit = smote_resample_training_fold(X, y)

    model = new_xgb_classifier(hyperparams)
    sample_weights = compute_sample_weight(class_weight="balanced", y=y_fit)
    model.fit(X_fit, y_fit, sample_weight=sample_weights)
    return model, len(y_fit)


def conclusion_for_score(score: float) -> str:
    if score > 0.92:
        return "ROBUST MODEL — report this as the production metric"
    if 0.85 <= score <= 0.92:
        return "GOOD MODEL — solid but note confidence interval"
    return "INVESTIGATE — possible data leakage or overfitting in original split"


def smote_conclusion_for_score(score: float) -> str:
    if score > PREVIOUS_WEIGHTED_F1:
        return "SMOTE improved the model"
    return "SMOTE did not help — class balance may already be acceptable"


def run_evaluation_pipeline(input_path: Path, skip_tuning: bool = False, use_smote: bool = True) -> None:
    report = ReportWriter(SMOTE_REPORT_TXT)
    report.write("CASSANDRA Opcao A - Rigorous Evaluation and Optimization Report")
    report.write(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.write(f"Input: {input_path}")
    report.write(f"Target: {TARGET_COL}")
    report.write(f"SMOTE: {'enabled' if use_smote else 'disabled (--no-smote)'}")
    report.write("")

    df = load_evaluation_matrix(input_path)
    dropped_cols = dropped_training_columns(df)
    report.write(f"Rows after dropping missing targets: {len(df)}")
    report.write(f"Columns excluded before training: {', '.join(dropped_cols) if dropped_cols else 'none'}")
    if "municipio" in df.columns and "municipio" not in dropped_cols:
        report.write("Identifier alias excluded before training: municipio")

    encoder = LabelEncoder()
    y = encoder.fit_transform(df[TARGET_COL].astype(str))
    class_names = encoder.classes_

    baseline_cols = feature_columns_for_training(df, baseline_only=True)
    v2_cols = feature_columns_for_training(df, baseline_only=False)
    X_baseline = prepare_features(df, baseline_cols)
    X_v2 = prepare_features(df, v2_cols)

    report.write(f"Class distribution for {TARGET_COL} (value_counts):")
    report.write(df[TARGET_COL].value_counts().to_string())
    report.write("")
    report.write("=== STEP A — Stratified K-Fold Cross-Validation (Baseline and V2) ===")
    report.write(f"CV: StratifiedKFold(n_splits={N_SPLITS}, shuffle=True, random_state={RANDOM_STATE})")
    report.write("SMOTE is applied to training folds only; test folds remain unchanged." if use_smote else "SMOTE disabled.")
    report.write(f"Baseline raw columns: {', '.join(baseline_cols)}")
    report.write(f"Baseline encoded feature count: {X_baseline.shape[1]}")
    report.write(f"V2 raw columns: {', '.join(v2_cols)}")
    report.write(f"V2 encoded feature count: {X_v2.shape[1]}")
    report.write("")

    baseline_result = run_stratified_cv("Baseline", X_baseline, y, class_names, use_smote=use_smote)
    v2_result = run_stratified_cv("V2 all features", X_v2, y, class_names, use_smote=use_smote)
    write_cv_result(report, baseline_result, include_support=False)
    report.write("")
    write_cv_result(report, v2_result, include_support=False)
    report.write(
        f"V2 minus baseline mean weighted F1: "
        f"{v2_result['weighted_f1_mean'] - baseline_result['weighted_f1_mean']:+.4f}"
    )

    report.write("")
    report.write("=== STEP B — Feature Analysis ===")
    clean_features = analyze_and_clean_features(X_v2, v2_result["importance_matrix"], report)
    X_clean = X_v2[clean_features].copy()

    report.write("")
    report.write("=== STEP C — Hyperparameter Tuning with Optuna ===")
    if skip_tuning:
        best_params = dict(XGB_DEFAULT_HYPERPARAMS)
        best_cv_f1 = cross_validated_weighted_f1(X_clean, y, best_params, use_smote=use_smote)
        report.write("--skip-tuning provided; using default XGBoost hyperparameters.")
        report.write(f"Default-parameter CV weighted F1 on clean V2 features: {best_cv_f1:.4f}")
        report.write(f"Default params: {json.dumps(best_params, sort_keys=True)}")
    else:
        best_params, best_cv_f1 = run_optuna_tuning(X_clean, y, report, n_trials=50, use_smote=use_smote)

    report.write("")
    report.write("=== STEP D — Final Model Evaluation ===")
    final_result = run_stratified_cv(
        "Final clean V2 model",
        X_clean,
        y,
        class_names,
        hyperparams=best_params,
        use_smote=use_smote,
    )
    write_cv_result(report, final_result, include_support=True)
    report.write("Top 10 feature importances, mean across 5 folds:")
    for rank, (feature, importance) in enumerate(top_mean_importances(final_result, n=10), start=1):
        report.write(f"  {rank:>2}. {feature}: {importance:.6f}")

    _, final_training_rows = fit_final_model(X_clean, y, best_params, use_smote=use_smote)
    report.write(
        f"Final model trained on the full dataset: {final_training_rows} training rows "
        f"from {len(y)} original rows, {X_clean.shape[1]} clean features."
    )
    report.write(f"Best Step C CV weighted F1 used for parameter selection: {best_cv_f1:.4f}")
    report.write(f"Previous weighted F1 benchmark: {PREVIOUS_WEIGHTED_F1:.4f}")
    report.write(f"Final model delta vs previous benchmark: {final_result['weighted_f1_mean'] - PREVIOUS_WEIGHTED_F1:+.4f}")
    report.write("")
    report.write(conclusion_for_score(final_result["weighted_f1_mean"]))
    if use_smote:
        report.write(smote_conclusion_for_score(final_result["weighted_f1_mean"]))
    else:
        report.write("--no-smote run; SMOTE comparison conclusion skipped.")
    report.save()
    print(f"\nSaved {SMOTE_REPORT_TXT}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the CASSANDRA Opcao A pipeline.")
    parser.add_argument(
        "--input",
        default=str(MERGED_MATRIX_CSV),
        help="Input feature matrix CSV. Defaults to feature_matrix_v2.csv.",
    )
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Deprecated compatibility flag. Evaluation now reads feature_matrix_v2.csv directly.",
    )
    parser.add_argument(
        "--skip-tuning",
        action="store_true",
        help="Skip Optuna and use default XGBoost parameters for the final clean V2 model.",
    )
    parser.add_argument(
        "--no-smote",
        action="store_true",
        help="Disable SMOTE oversampling for comparison runs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.skip_extraction:
        print("--skip-extraction is deprecated; reading the supplied feature matrix directly.")

    run_evaluation_pipeline(Path(args.input), skip_tuning=args.skip_tuning, use_smote=not args.no_smote)


if __name__ == "__main__":
    main()
