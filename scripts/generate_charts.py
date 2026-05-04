#!/usr/bin/env python3
from __future__ import annotations

import os
import pickle
import unicodedata
import warnings
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib-cache")

import joblib
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from sklearn.model_selection import train_test_split, validation_curve
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

BG = "#fdf8f8"
TEXT = "#1A1A1A"
MUTED = "#747878"
RED = "#FF3366"
AMBER = "#FFAA00"
CYAN = "#00E5FF"

FEATURES = [
    "IEI_Score",
    "digital_decay_rate",
    "Total_Arquivo_Captures",
    "capture_density",
    "is_coastal",
    "Pop. 2011",
    "Env. 2001",
    "Var% 2001→2011",
]

MODEL_PICKLE_CANDIDATES = [
    ROOT / "reports" / "validated_model.pkl",
    ROOT / "reports" / "modelo_preditivo_real.pkl",
    ROOT / "reports" / "cassandra_xgb_model.pkl",
    ROOT / "modelo_preditivo_real.pkl",
    ROOT / "cassandra_xgb_model.pkl",
]

BALANCED_TIER_THRESHOLDS = {
    "tier4_upper": -10.5,
    "tier3_upper": -5.0,
    "tier2_upper": 0.0,
}

COASTAL_TOURISM_MUNICIPALITIES = {
    "Albufeira", "Alcácer do Sal", "Alcobaça", "Alcoutim", "Aljezur", "Almada",
    "Aveiro", "Caminha", "Cascais", "Esposende", "Faro", "Figueira da Foz",
    "Grândola", "Ílhavo", "Lagoa", "Lagos", "Lisboa", "Loulé", "Lourinhã",
    "Mafra", "Marinha Grande", "Matosinhos", "Mira", "Moita", "Montijo",
    "Murtosa", "Nazaré", "Odemira", "Olhão", "Ovar", "Palmela", "Peniche",
    "Póvoa de Varzim", "Portimão", "Porto", "Santa Cruz", "Santiago do Cacém",
    "Sesimbra", "Setúbal", "Silves", "Sines", "Sintra", "Tavira",
    "Torres Vedras", "Vagos", "Viana do Castelo", "Vila do Bispo",
    "Vila do Conde", "Vila Nova de Gaia", "Vila Real de Santo António",
}

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "axes.edgecolor": TEXT,
        "axes.labelcolor": TEXT,
        "axes.linewidth": 1.0,
        "xtick.color": TEXT,
        "ytick.color": TEXT,
        "text.color": TEXT,
        "figure.facecolor": BG,
        "axes.facecolor": BG,
        "savefig.facecolor": BG,
    }
)


def normalize_municipio(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return text.strip().lower()


def normalize_label(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text.lower())
    return " ".join(cleaned.split())


def find_municipio_col(df: pd.DataFrame) -> str:
    for col in df.columns:
        if "munic" in normalize_label(col):
            return col
    raise ValueError(f"Cannot find municipality column in {df.columns.tolist()}")


def find_col(df: pd.DataFrame, candidates: list[str]) -> str:
    normalized = {col: normalize_label(col) for col in df.columns}
    for candidate in candidates:
        candidate_norm = normalize_label(candidate)
        for col, col_norm in normalized.items():
            if candidate_norm in col_norm:
                return col
    raise KeyError(f"None of {candidates} found in {df.columns.tolist()}")


def safe_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def assign_tier(var_pop: float) -> str:
    if pd.isna(var_pop):
        return "TIER - Indeterminado"
    if var_pop < BALANCED_TIER_THRESHOLDS["tier4_upper"]:
        return "TIER 4 - Profecia CASSANDRA"
    if var_pop < BALANCED_TIER_THRESHOLDS["tier3_upper"]:
        return "TIER 3 - Risco de Fuga"
    if var_pop < BALANCED_TIER_THRESHOLDS["tier2_upper"]:
        return "TIER 2 - Estagnação"
    return "TIER 1 - Resiliência"


def impute_total_arquivo_captures(df: pd.DataFrame) -> pd.DataFrame:
    captures_col = "Total_Arquivo_Captures"
    if captures_col not in df.columns:
        df[captures_col] = np.nan

    captures = safe_float(df[captures_col]).mask(lambda values: values == 0, np.nan)
    global_median = captures.median()

    nut_col = None
    for candidate in ["NUT III", "NUTS III", "NUT_III", "NUTS_III", "NUTIII", "NUTSIII"]:
        try:
            nut_col = find_col(df, [candidate])
            break
        except KeyError:
            continue

    if nut_col:
        captures = captures.fillna(captures.groupby(df[nut_col]).transform("median"))
    if not pd.isna(global_median):
        captures = captures.fillna(global_median)

    df[captures_col] = captures
    return df


def load_training_data() -> pd.DataFrame:
    df_iei = pd.read_csv(ROOT / "metricas_iei_completo.csv")

    fase2_path = ROOT / "metricas_fase2_completo.csv"
    if fase2_path.exists():
        df_fase2 = pd.read_csv(fase2_path, encoding="utf-8-sig")
        f2_mun_col = find_municipio_col(df_fase2)
        df_fase2 = impute_total_arquivo_captures(df_fase2.copy())
        df_fase2["_key"] = df_fase2[f2_mun_col].apply(normalize_municipio)

        iei_mun_col = find_municipio_col(df_iei)
        df_iei["_key"] = df_iei[iei_mun_col].apply(normalize_municipio)
        merge_cols = [
            col for col in df_fase2.columns
            if col not in {f2_mun_col, "_key"} and col not in df_iei.columns
        ]
        df_iei = df_iei.merge(df_fase2[["_key"] + merge_cols], on="_key", how="left")

    temporal_path = ROOT / "data" / "arquivo_temporal_features.csv"
    if temporal_path.exists():
        df_temporal = pd.read_csv(temporal_path, encoding="utf-8-sig")
        temporal_mun_col = find_municipio_col(df_temporal)
        iei_mun_col = find_municipio_col(df_iei)
        df_iei = df_iei.merge(
            df_temporal[[temporal_mun_col]],
            left_on=iei_mun_col,
            right_on=temporal_mun_col,
            how="left",
        )
        if temporal_mun_col != iei_mun_col and temporal_mun_col in df_iei.columns:
            df_iei = df_iei.drop(columns=[temporal_mun_col])

    df_dem = pd.read_excel(ROOT / "dados_demograficos.csv", header=1)

    iei_mun_col = find_municipio_col(df_iei)
    dem_mun_col = find_municipio_col(df_dem)
    df_iei["_key"] = df_iei[iei_mun_col].apply(normalize_municipio)
    df_dem["_key"] = df_dem[dem_mun_col].apply(normalize_municipio)

    df = df_iei.merge(df_dem, on="_key", how="inner", suffixes=("_iei", "_dem"))
    if len(df) < 280:
        raise ValueError(f"Merge produced only {len(df)}/308 municipalities")

    col_iei = find_col(df, ["IEI_Score", "IEI Score", "IEI"])
    col_decay = find_col(df, ["Media_Dias_Entre_Capturas", "Média_Dias_Entre_Capturas"])
    col_caps = find_col(df, ["Total_Arquivo_Captures", "Total_Arquivo", "Arquivo_Captures"])
    col_pop21 = find_col(df, ["Pop. 2021", "Pop_2021", "Pop2021", "População 2021"])
    col_pop11 = find_col(df, ["Pop. 2011", "Pop_2011", "Pop2011", "População 2011"])
    col_env01 = find_col(df, ["Env. 2001", "Env_2001", "Envelhecimento 2001"])
    col_var01 = find_col(df, ["Var% 2001", "Var 2001", "2001→2011", "2001-2011"])
    col_target = find_col(df, ["Var% 2011→2021", "Var% 2011", "2011→2021", "2011-2021"])

    for col in [col_iei, col_decay, col_caps, col_pop21, col_pop11, col_env01, col_var01, col_target]:
        df[col] = safe_float(df[col])

    name_col = None
    for candidate in [iei_mun_col, f"{iei_mun_col}_iei", dem_mun_col, f"{dem_mun_col}_dem"]:
        if candidate in df.columns:
            name_col = candidate
            break
    if name_col is None:
        raise ValueError(f"Cannot recover municipality name column from {df.columns.tolist()}")

    coastal_keys = {normalize_municipio(municipio) for municipio in COASTAL_TOURISM_MUNICIPALITIES}
    output = pd.DataFrame(
        {
            "Município": df[name_col],
            "IEI_Score": df[col_iei],
            "digital_decay_rate": df[col_decay],
            "Total_Arquivo_Captures": df[col_caps],
            "capture_density": df[col_caps] / df[col_pop21].replace(0, np.nan),
            "is_coastal": df["_key"].isin(coastal_keys).astype(int),
            "Pop. 2011": df[col_pop11],
            "Env. 2001": df[col_env01],
            "Var% 2001→2011": df[col_var01],
            "Var_Pop": df[col_target],
        }
    )
    output["CASSANDRA_Risk_Tier"] = output["Var_Pop"].apply(assign_tier)
    return output.dropna(subset=FEATURES)


def new_xgb_classifier(n_estimators: int = 200) -> xgb.XGBClassifier:
    return xgb.XGBClassifier(
        n_estimators=n_estimators,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        min_child_weight=3,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
        eval_metric="mlogloss",
        n_jobs=-1,
    )


def load_pickle(path: Path) -> Any:
    try:
        return joblib.load(path)
    except Exception:
        with path.open("rb") as handle:
            return pickle.load(handle)


def extract_model(payload: Any) -> Any:
    if isinstance(payload, dict):
        for key in ["model", "classifier", "estimator", "xgb_model"]:
            if key in payload:
                return payload[key]
    return payload


def load_existing_model(expected_features: int) -> Any | None:
    for path in MODEL_PICKLE_CANDIDATES:
        if not path.exists():
            continue
        model = extract_model(load_pickle(path))
        n_features = getattr(model, "n_features_in_", expected_features)
        if n_features == expected_features and hasattr(model, "predict"):
            return model
    return None


def build_model_bundle(df: pd.DataFrame) -> tuple[Any, pd.DataFrame, np.ndarray, np.ndarray]:
    train_df = df[df["CASSANDRA_Risk_Tier"] != "TIER - Indeterminado"].copy()
    X = train_df[FEATURES]

    encoder = LabelEncoder()
    y = encoder.fit_transform(train_df["CASSANDRA_Risk_Tier"])

    X_train, _, y_train, _ = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    model = load_existing_model(len(FEATURES))
    if model is None:
        model = new_xgb_classifier()
        weights = compute_sample_weight(class_weight="balanced", y=y_train)
        model.fit(X_train, y_train, sample_weight=weights)

    return model, X_train, X, y


def mean_abs_shap_values(model: Any, X: pd.DataFrame) -> np.ndarray:
    explainer = shap.TreeExplainer(model)
    values = explainer.shap_values(X)

    if isinstance(values, list):
        return np.abs(np.stack(values, axis=0)).mean(axis=(0, 1))

    values = np.asarray(values)
    if values.ndim == 2:
        return np.abs(values).mean(axis=0)
    if values.ndim == 3:
        if values.shape[1] == X.shape[1]:
            return np.abs(values).mean(axis=(0, 2))
        if values.shape[2] == X.shape[1]:
            return np.abs(values).mean(axis=(0, 1))
    raise ValueError(f"Unexpected SHAP values shape: {values.shape}")


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor(BG)
    for spine in ax.spines.values():
        spine.set_color(TEXT)
        spine.set_linewidth(1.0)
    ax.tick_params(axis="both", colors=TEXT, width=1.0, labelsize=9)
    ax.xaxis.label.set_color(TEXT)
    ax.yaxis.label.set_color(TEXT)


def set_title(ax: plt.Axes, title: str) -> None:
    ax.set_title(title.upper(), loc="left", fontsize=12, fontweight="bold", color=TEXT, pad=12)


def save_chart(fig: plt.Figure, filename: str) -> None:
    fig.savefig(ASSETS_DIR / filename, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)


def plot_shap_summary(model: Any, X_train: pd.DataFrame) -> None:
    mean_abs = mean_abs_shap_values(model, X_train)
    importance = (
        pd.DataFrame({"feature": FEATURES, "importance": mean_abs})
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )
    importance["color"] = [RED] * 3 + [AMBER] * 3 + [CYAN] * 2

    fig, ax = plt.subplots(figsize=(8.5, 5.2), facecolor=BG)
    style_axis(ax)
    ax.barh(
        importance["feature"],
        importance["importance"],
        color=importance["color"],
        edgecolor="none",
        height=0.68,
    )
    ax.invert_yaxis()
    ax.grid(axis="x", color=MUTED, alpha=0.28, linewidth=1.0)
    ax.set_xlabel("Mean absolute SHAP value", fontsize=10)
    set_title(ax, "SHAP feature importance")
    save_chart(fig, "SHAP_SUMMARY_CASSANDRA.PNG")


def plot_correlation_heatmap(df: pd.DataFrame) -> None:
    corr_cols = FEATURES + ["Var_Pop"]
    corr = df[corr_cols].corr(method="pearson")

    cmap = LinearSegmentedColormap.from_list("cassandra_diverging", [CYAN, BG, RED])
    norm = TwoSlopeNorm(vmin=-1.0, vcenter=0.0, vmax=1.0)

    fig, ax = plt.subplots(figsize=(8.2, 7.0), facecolor=BG)
    style_axis(ax)
    im = ax.imshow(corr.values, cmap=cmap, norm=norm, aspect="equal")

    ax.set_xticks(np.arange(len(corr_cols)))
    ax.set_yticks(np.arange(len(corr_cols)))
    ax.set_xticklabels(corr_cols, rotation=35, ha="right", fontsize=8)
    ax.set_yticklabels(corr_cols, fontsize=8)

    for row in range(corr.shape[0]):
        for col in range(corr.shape[1]):
            ax.text(col, row, f"{corr.iloc[row, col]:.2f}", ha="center", va="center", fontsize=7, color=TEXT)

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.035)
    cbar.outline.set_edgecolor(TEXT)
    cbar.outline.set_linewidth(1.0)
    cbar.ax.tick_params(color=TEXT, labelcolor=TEXT, width=1.0)

    set_title(ax, "Pearson correlation matrix")
    save_chart(fig, "PLOT_CORRELACAO.PNG")


def plot_validation_curve(model: Any, X: pd.DataFrame, y: np.ndarray) -> None:
    param_range = np.array([10, 25, 50, 100, 150, 200, 300, 500])
    estimator = new_xgb_classifier()
    for param in estimator.get_params():
        if param in model.get_params() and param != "n_estimators":
            estimator.set_params(**{param: model.get_params()[param]})

    weights = compute_sample_weight(class_weight="balanced", y=y)
    train_scores, cv_scores = validation_curve(
        estimator,
        X,
        y,
        param_name="n_estimators",
        param_range=param_range,
        cv=5,
        scoring="accuracy",
        n_jobs=1,
        fit_params={"sample_weight": weights},
    )

    train_mean = train_scores.mean(axis=1)
    train_std = train_scores.std(axis=1)
    cv_mean = cv_scores.mean(axis=1)
    cv_std = cv_scores.std(axis=1)
    best_idx = int(np.nanargmax(cv_mean))
    best_n = int(param_range[best_idx])

    fig, ax = plt.subplots(figsize=(8.5, 5.2), facecolor=BG)
    style_axis(ax)
    ax.plot(param_range, train_mean, color=RED, linewidth=2.0, label="Training score")
    ax.fill_between(param_range, train_mean - train_std, train_mean + train_std, color=RED, alpha=0.12)
    ax.plot(param_range, cv_mean, color=CYAN, linewidth=2.0, label="CV score")
    ax.fill_between(param_range, cv_mean - cv_std, cv_mean + cv_std, color=CYAN, alpha=0.14)
    ax.axvline(best_n, color=AMBER, linestyle="--", linewidth=1.0)
    ax.scatter([best_n], [cv_mean[best_idx]], color=AMBER, s=34, zorder=5)
    ax.set_xlabel("n_estimators", fontsize=10)
    ax.set_ylabel("Accuracy", fontsize=10)
    ax.grid(axis="both", color=MUTED, alpha=0.28, linewidth=1.0)
    ax.legend(frameon=False, fontsize=9)
    set_title(ax, "Validation curve")
    save_chart(fig, "PLOT_VALIDACAO.PNG")


def main() -> None:
    df = load_training_data()
    model, X_train, X, y = build_model_bundle(df)

    plot_shap_summary(model, X_train)
    plot_correlation_heatmap(df)
    plot_validation_curve(model, X, y)

    outputs = [
        ASSETS_DIR / "SHAP_SUMMARY_CASSANDRA.PNG",
        ASSETS_DIR / "PLOT_CORRELACAO.PNG",
        ASSETS_DIR / "PLOT_VALIDACAO.PNG",
    ]
    for output in outputs:
        if not output.exists() or output.stat().st_size <= 0:
            raise RuntimeError(f"Missing or empty output: {output}")
        print(f"{output} {output.stat().st_size}")


if __name__ == "__main__":
    main()
