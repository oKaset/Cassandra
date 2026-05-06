#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import warnings
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MPLCONFIG_DIR = PROJECT_ROOT / "reports" / ".matplotlib-cache"
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from imblearn.over_sampling import SMOTE
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_charts import FEATURES, load_training_data

warnings.filterwarnings("ignore")

OPTUNA_REPORT = PROJECT_ROOT / "model_smote_report.txt"
RESULTS_TABLE_PNG = PROJECT_ROOT / "arquivo_ablation_results.png"
SHAP_COMPARISON_PNG = PROJECT_ROOT / "shap_comparison.png"
RESULTS_JSON = PROJECT_ROOT / "arquivo_ablation_results.json"

RANDOM_STATE = 42
TEST_SIZE = 0.20
TARGET_COL = "CASSANDRA_Risk_Tier"
INDETERMINATE_TIER = "TIER - Indeterminado"
ARQUIVO_FEATURES = [
    "Total_Arquivo_Captures",
    "capture_density",
    "digital_decay_rate",
]

XGB_FIXED_PARAMS: dict[str, Any] = {
    "random_state": RANDOM_STATE,
    "verbosity": 0,
    "eval_metric": "mlogloss",
    "n_jobs": -1,
}

FALLBACK_OPTUNA_PARAMS: dict[str, Any] = {
    "colsample_bytree": 0.6624074561769746,
    "learning_rate": 0.2536999076681771,
    "max_depth": 5,
    "min_child_weight": 2,
    "n_estimators": 393,
    "subsample": 0.8394633936788146,
}

BG = "#fdf8f8"
TEXT = "#1A1A1A"
MUTED = "#747878"
RED = "#FF3366"
AMBER = "#FFAA00"
CYAN = "#00AFC7"
GREEN = "#24935B"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "figure.facecolor": BG,
        "axes.facecolor": BG,
        "savefig.facecolor": BG,
        "text.color": TEXT,
        "axes.labelcolor": TEXT,
        "xtick.color": TEXT,
        "ytick.color": TEXT,
    }
)


def load_optuna_params() -> dict[str, Any]:
    if not OPTUNA_REPORT.exists():
        return dict(FALLBACK_OPTUNA_PARAMS)

    text = OPTUNA_REPORT.read_text(encoding="utf-8")
    match = re.search(r"Best Optuna params:\s*(\{.*?\})", text)
    if not match:
        return dict(FALLBACK_OPTUNA_PARAMS)
    return json.loads(match.group(1))


def short_tier_name(label: str) -> str:
    match = re.search(r"TIER\s+(\d)", str(label))
    return f"Tier {match.group(1)}" if match else str(label)


def tier4_index(class_names: np.ndarray) -> int:
    for idx, label in enumerate(class_names):
        if str(label).startswith("TIER 4"):
            return idx
    raise ValueError(f"Tier 4 class not found in {class_names.tolist()}")


def shap_values_for_class(model: xgb.XGBClassifier, X: pd.DataFrame, class_idx: int) -> np.ndarray:
    explainer = shap.TreeExplainer(model)
    values = explainer.shap_values(X)

    if isinstance(values, list):
        return np.asarray(values[class_idx])

    values_array = np.asarray(values)
    if values_array.ndim == 2:
        return values_array
    if values_array.ndim == 3:
        if values_array.shape[1] == X.shape[1]:
            return values_array[:, :, class_idx]
        if values_array.shape[2] == X.shape[1]:
            return values_array[class_idx, :, :]
    raise ValueError(f"Unexpected SHAP values shape: {values_array.shape}")


def format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def format_delta(value: float) -> str:
    return f"{value * 100:+.2f} pp"


def fit_and_evaluate(
    name: str,
    df: pd.DataFrame,
    feature_cols: list[str],
    y: np.ndarray,
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    encoder: LabelEncoder,
    model_params: dict[str, Any],
) -> dict[str, Any]:
    X = df[feature_cols].copy()
    X_train = X.iloc[train_idx].copy()
    X_test = X.iloc[test_idx].copy()
    y_train = y[train_idx]
    y_test = y[test_idx]

    X_fit, y_fit = SMOTE(random_state=RANDOM_STATE).fit_resample(X_train, y_train)
    if not isinstance(X_fit, pd.DataFrame):
        X_fit = pd.DataFrame(X_fit, columns=X_train.columns)

    model = xgb.XGBClassifier(**model_params)
    sample_weights = compute_sample_weight(class_weight="balanced", y=y_fit)
    model.fit(X_fit, y_fit, sample_weight=sample_weights)

    y_pred = model.predict(X_test)
    precision, recall, _, support = precision_recall_fscore_support(
        y_test,
        y_pred,
        labels=list(range(len(encoder.classes_))),
        zero_division=0,
    )

    per_tier = {
        short_tier_name(label): {
            "precision": float(precision[idx]),
            "recall": float(recall[idx]),
            "support": int(support[idx]),
        }
        for idx, label in enumerate(encoder.classes_)
    }

    return {
        "name": name,
        "features": feature_cols,
        "model": model,
        "X_test": X_test,
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "f1_weighted": float(f1_score(y_test, y_pred, average="weighted", zero_division=0)),
        "per_tier": per_tier,
    }


def build_comparison_rows(full: dict[str, Any], ablated: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    metric_pairs = [
        ("Accuracy", full["accuracy"], ablated["accuracy"]),
        ("F1-score (weighted)", full["f1_weighted"], ablated["f1_weighted"]),
    ]

    for tier in ["Tier 1", "Tier 2", "Tier 3", "Tier 4"]:
        metric_pairs.append(
            (
                f"{tier} precision",
                full["per_tier"][tier]["precision"],
                ablated["per_tier"][tier]["precision"],
            )
        )
        metric_pairs.append(
            (
                f"{tier} recall",
                full["per_tier"][tier]["recall"],
                ablated["per_tier"][tier]["recall"],
            )
        )

    for metric, with_value, without_value in metric_pairs:
        rows.append(
            {
                "Metric": metric,
                "With Arquivo.pt": format_pct(with_value),
                "Without Arquivo.pt": format_pct(without_value),
                "Delta": format_delta(without_value - with_value),
            }
        )

    return pd.DataFrame(rows)


def save_results_table(table: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11.5, 5.8))
    ax.axis("off")

    table_artist = ax.table(
        cellText=table.values,
        colLabels=table.columns,
        cellLoc="center",
        colLoc="center",
        loc="center",
        colWidths=[0.34, 0.20, 0.24, 0.16],
    )
    table_artist.auto_set_font_size(False)
    table_artist.set_fontsize(10.5)
    table_artist.scale(1.0, 1.45)

    for (row, col), cell in table_artist.get_celld().items():
        cell.set_edgecolor("#D7D1D1")
        cell.set_linewidth(0.8)
        if row == 0:
            cell.set_facecolor(TEXT)
            cell.get_text().set_color("#FFFFFF")
            cell.get_text().set_fontweight("bold")
            continue
        cell.set_facecolor("#FFFFFF" if row % 2 else "#F6EFEF")
        if col == 0:
            cell.get_text().set_ha("left")
        if col == 3:
            delta_text = cell.get_text().get_text()
            cell.get_text().set_color(RED if delta_text.startswith("-") else GREEN)
            cell.get_text().set_fontweight("bold")

    ax.set_title(
        "CASSANDRA Arquivo.pt Ablation (Delta = Without - With)",
        loc="left",
        fontsize=15,
        fontweight="bold",
        pad=18,
        color=TEXT,
    )
    ax.text(
        0.0,
        -0.06,
        "Same 80/20 stratified split, Optuna-tuned XGBoost parameters, SMOTE on training data only.",
        transform=ax.transAxes,
        fontsize=9.5,
        color=MUTED,
    )
    fig.savefig(RESULTS_TABLE_PNG, dpi=220, bbox_inches="tight", facecolor=BG)
    plt.close(fig)


def save_shap_comparison(results: list[dict[str, Any]], class_names: np.ndarray) -> None:
    class_idx = tier4_index(class_names)
    fig, axes = plt.subplots(1, 2, figsize=(16.5, 6.8), facecolor=BG)

    for ax, result in zip(axes, results):
        plt.sca(ax)
        shap_values = shap_values_for_class(result["model"], result["X_test"], class_idx)
        shap.summary_plot(
            shap_values,
            result["X_test"],
            max_display=len(result["features"]),
            plot_type="dot",
            show=False,
            plot_size=None,
            color_bar=False,
        )
        ax.set_title(result["name"], loc="left", fontsize=13, fontweight="bold", color=TEXT, pad=10)
        ax.tick_params(axis="both", colors=TEXT, labelsize=9)
        ax.xaxis.label.set_color(TEXT)
        ax.yaxis.label.set_color(TEXT)
        ax.grid(axis="x", color=MUTED, alpha=0.22, linewidth=0.8)

    fig.suptitle(
        "SHAP Summary for Tier 4 Detection",
        x=0.05,
        y=1.02,
        ha="left",
        fontsize=16,
        fontweight="bold",
        color=TEXT,
    )
    fig.tight_layout(w_pad=3.2)
    fig.savefig(SHAP_COMPARISON_PNG, dpi=220, bbox_inches="tight", facecolor=BG)
    plt.close(fig)


def main() -> None:
    missing = [feature for feature in ARQUIVO_FEATURES if feature not in FEATURES]
    if missing:
        raise ValueError(f"Requested Arquivo.pt features missing from model FEATURES: {missing}")

    full_features = list(FEATURES)
    no_arquivo_features = [feature for feature in FEATURES if feature not in set(ARQUIVO_FEATURES)]
    removed = [feature for feature in FEATURES if feature not in no_arquivo_features]
    if set(removed) != set(ARQUIVO_FEATURES) or len(removed) != len(ARQUIVO_FEATURES):
        raise ValueError(f"Ablation must remove exactly {ARQUIVO_FEATURES}; got {removed}")

    df = load_training_data()
    df = df[df[TARGET_COL] != INDETERMINATE_TIER].copy().reset_index(drop=True)

    encoder = LabelEncoder()
    y = encoder.fit_transform(df[TARGET_COL])
    row_idx = np.arange(len(df))
    train_idx, test_idx = train_test_split(
        row_idx,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,
    )

    model_params = {**load_optuna_params(), **XGB_FIXED_PARAMS}
    full = fit_and_evaluate(
        "Experiment A - With Arquivo.pt",
        df,
        full_features,
        y,
        train_idx,
        test_idx,
        encoder,
        model_params,
    )
    ablated = fit_and_evaluate(
        "Experiment B - Without Arquivo.pt",
        df,
        no_arquivo_features,
        y,
        train_idx,
        test_idx,
        encoder,
        model_params,
    )

    table = build_comparison_rows(full, ablated)
    save_results_table(table)
    save_shap_comparison([full, ablated], encoder.classes_)

    json_payload = {
        "method": {
            "test_size": TEST_SIZE,
            "random_state": RANDOM_STATE,
            "training_resampling": "SMOTE on training split only",
            "optuna_params": load_optuna_params(),
            "removed_features": ARQUIVO_FEATURES,
        },
        "experiments": {
            "with_arquivo_pt": {
                "accuracy": full["accuracy"],
                "f1_weighted": full["f1_weighted"],
                "per_tier": full["per_tier"],
                "features": full["features"],
            },
            "without_arquivo_pt": {
                "accuracy": ablated["accuracy"],
                "f1_weighted": ablated["f1_weighted"],
                "per_tier": ablated["per_tier"],
                "features": ablated["features"],
            },
        },
    }
    RESULTS_JSON.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(table.to_string(index=False))
    print(f"\nSaved {RESULTS_TABLE_PNG}")
    print(f"Saved {SHAP_COMPARISON_PNG}")
    print(f"Saved {RESULTS_JSON}")


if __name__ == "__main__":
    main()
