#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JSON = PROJECT_ROOT / "data" / "arquivo_core_robustness_summary.json"
OPTUNA_REPORT = PROJECT_ROOT / "model_smote_report.txt"

RANDOM_STATE = 42
N_SPLITS = 5
TARGET_COL = "CASSANDRA_Risk_Tier"
INDETERMINATE_TIER = "TIER - Indeterminado"
ARQUIVO_CORE_FEATURES = ["Total_Arquivo_Captures", "capture_density"]
LEGACY_TEMPORAL_FEATURE = "digital_decay_rate"

XGB_FIXED_PARAMS: dict[str, Any] = {
    "random_state": RANDOM_STATE,
    "verbosity": 0,
    "eval_metric": "mlogloss",
    "n_jobs": -1,
}


def base_summary(validated: bool = False) -> dict[str, Any]:
    return {
        "validated": validated,
        "purpose": "Robustness check isolating fully auditable Arquivo.pt variables.",
        "features_tested": {
            "arquivo_core": ARQUIVO_CORE_FEATURES,
            "legacy_temporal_feature": LEGACY_TEMPORAL_FEATURE,
        },
        "experiments": {
            "full_model": {
                "accuracy": None,
                "weighted_f1": None,
            },
            "without_all_arquivo": {
                "accuracy": None,
                "weighted_f1": None,
            },
            "without_arquivo_core_only": {
                "accuracy": None,
                "weighted_f1": None,
            },
        },
        "deltas": {
            "without_all_arquivo_accuracy_pp": None,
            "without_all_arquivo_weighted_f1_pp": None,
            "without_arquivo_core_accuracy_pp": None,
            "without_arquivo_core_weighted_f1_pp": None,
        },
        "interpretation": "",
        "limitations": [],
    }


def write_summary(payload: dict[str, Any]) -> None:
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_optuna_params() -> dict[str, Any]:
    if not OPTUNA_REPORT.exists():
        raise FileNotFoundError(f"Missing confirmed Optuna report: {OPTUNA_REPORT}")

    text = OPTUNA_REPORT.read_text(encoding="utf-8")
    match = re.search(r"Best Optuna params:\s*(\{.*?\})", text)
    if not match:
        raise ValueError("Could not recover confirmed Optuna parameters from model_smote_report.txt")
    return json.loads(match.group(1))


def rounded_metric(value: float) -> float:
    return round(float(value), 6)


def rounded_delta(without_value: float, full_value: float) -> float:
    return round((float(without_value) - float(full_value)) * 100, 4)


def evaluate_cv(
    df: Any,
    feature_cols: list[str],
    y: Any,
    model_params: dict[str, Any],
    sklearn_modules: dict[str, Any],
) -> dict[str, float]:
    np = sklearn_modules["np"]
    pd = sklearn_modules["pd"]
    xgb = sklearn_modules["xgb"]
    SMOTE = sklearn_modules["SMOTE"]
    StratifiedKFold = sklearn_modules["StratifiedKFold"]
    accuracy_score = sklearn_modules["accuracy_score"]
    f1_score = sklearn_modules["f1_score"]
    compute_sample_weight = sklearn_modules["compute_sample_weight"]

    X = df[feature_cols].copy()
    splitter = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    fold_accuracies: list[float] = []
    fold_weighted_f1: list[float] = []

    for train_idx, test_idx in splitter.split(X, y):
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
        fold_accuracies.append(float(accuracy_score(y_test, y_pred)))
        fold_weighted_f1.append(float(f1_score(y_test, y_pred, average="weighted", zero_division=0)))

    return {
        "accuracy": rounded_metric(np.mean(fold_accuracies)),
        "weighted_f1": rounded_metric(np.mean(fold_weighted_f1)),
    }


def build_interpretation(deltas: dict[str, float]) -> str:
    all_accuracy = deltas["without_all_arquivo_accuracy_pp"]
    all_f1 = deltas["without_all_arquivo_weighted_f1_pp"]
    core_accuracy = deltas["without_arquivo_core_accuracy_pp"]
    core_f1 = deltas["without_arquivo_core_weighted_f1_pp"]

    return (
        "No protocolo secundário de 5 folds, a remoção de todas as variáveis Arquivo.pt "
        f"altera a exatidão em {all_accuracy:+.4f} pp e o F1 ponderado em {all_f1:+.4f} pp. "
        "A remoção apenas das variáveis Arquivo Core, mantendo digital_decay_rate como variável "
        f"temporal legada, altera a exatidão em {core_accuracy:+.4f} pp e o F1 ponderado "
        f"em {core_f1:+.4f} pp. Este resultado deve ser lido como teste de robustez conservador: "
        "documenta a limitação e não substitui a ablação pública validada."
    )


def main() -> int:
    summary = base_summary(validated=False)

    try:
        import numpy as np
        import pandas as pd
        import xgboost as xgb
        from imblearn.over_sampling import SMOTE
        from sklearn.metrics import accuracy_score, f1_score
        from sklearn.model_selection import StratifiedKFold
        from sklearn.preprocessing import LabelEncoder
        from sklearn.utils.class_weight import compute_sample_weight

        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from scripts.generate_charts import FEATURES, load_training_data

        full_features = list(FEATURES)
        required = [*ARQUIVO_CORE_FEATURES, LEGACY_TEMPORAL_FEATURE]
        missing = [feature for feature in required if feature not in full_features]
        if missing:
            summary["limitations"].append(f"Variáveis exigidas ausentes do feature set: {missing}")
            summary["interpretation"] = (
                "O teste de robustez não foi executado porque o conjunto de variáveis "
                "não contém todos os campos Arquivo.pt necessários."
            )
            write_summary(summary)
            return 1

        without_all_arquivo = [
            feature for feature in full_features
            if feature not in {*ARQUIVO_CORE_FEATURES, LEGACY_TEMPORAL_FEATURE}
        ]
        without_arquivo_core = [
            feature for feature in full_features
            if feature not in set(ARQUIVO_CORE_FEATURES)
        ]

        df = load_training_data()
        df = df[df[TARGET_COL] != INDETERMINATE_TIER].copy().reset_index(drop=True)

        encoder = LabelEncoder()
        y = encoder.fit_transform(df[TARGET_COL])
        model_params = {**load_optuna_params(), **XGB_FIXED_PARAMS}
        sklearn_modules = {
            "np": np,
            "pd": pd,
            "xgb": xgb,
            "SMOTE": SMOTE,
            "StratifiedKFold": StratifiedKFold,
            "accuracy_score": accuracy_score,
            "f1_score": f1_score,
            "compute_sample_weight": compute_sample_weight,
        }

        full = evaluate_cv(df, full_features, y, model_params, sklearn_modules)
        no_all = evaluate_cv(df, without_all_arquivo, y, model_params, sklearn_modules)
        no_core = evaluate_cv(df, without_arquivo_core, y, model_params, sklearn_modules)

        summary["validated"] = True
        summary["experiments"]["full_model"] = full
        summary["experiments"]["without_all_arquivo"] = no_all
        summary["experiments"]["without_arquivo_core_only"] = no_core
        deltas = {
            "without_all_arquivo_accuracy_pp": rounded_delta(no_all["accuracy"], full["accuracy"]),
            "without_all_arquivo_weighted_f1_pp": rounded_delta(no_all["weighted_f1"], full["weighted_f1"]),
            "without_arquivo_core_accuracy_pp": rounded_delta(no_core["accuracy"], full["accuracy"]),
            "without_arquivo_core_weighted_f1_pp": rounded_delta(no_core["weighted_f1"], full["weighted_f1"]),
        }
        summary["deltas"] = deltas
        summary["interpretation"] = build_interpretation(deltas)
        summary["limitations"] = [
            "Este teste é uma verificação secundária e não substitui as métricas públicas confirmadas.",
            "digital_decay_rate é mantida apenas como variável temporal legada com proveniência de coluna documentada.",
            "Neste protocolo, o resultado das variáveis Arquivo Core deve ser comunicado sem reforço artificial da alegação.",
            "Os deltas são calculados como experiência sem variáveis menos modelo completo, em pontos percentuais.",
        ]
        write_summary(summary)
        print(f"Wrote {OUTPUT_JSON}")
        return 0
    except Exception as exc:
        summary["validated"] = False
        summary["interpretation"] = (
            "O teste de robustez não pôde ser validado nesta execução; não foram fabricadas métricas."
        )
        summary["limitations"].append(str(exc))
        write_summary(summary)
        print(f"Wrote non-validated summary to {OUTPUT_JSON}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
