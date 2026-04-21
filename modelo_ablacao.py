"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           CASSANDRA Oracle Engine — Ablation Study                           ║
║           ArquivoPT2026 · modelo_ablacao.py                                  ║
║                                                                              ║
║  PURPOSE:  Isolate the predictive power of the digital metric (IEI_Score)    ║
║            by removing the historical demographic variable Var% 2001→2011.   ║
║                                                                              ║
║  FEATURES (X):  IEI_Score  |  Env. 2001  |  log(Pop. 2011)                  ║
║  TARGET   (y):  Var% 2011→2021                                               ║
║                                                                              ║
║  DROPPED:  Var% 2001→2011   ← ablated historical trend variable              ║
╚══════════════════════════════════════════════════════════════════════════════╝

USAGE:
    pip install pandas openpyxl scikit-learn matplotlib numpy scipy xgboost
    python modelo_ablacao.py
"""

import unicodedata
import sys
import warnings

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from scipy import stats
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

warnings.filterwarnings("ignore")
matplotlib.rcParams["font.family"] = "DejaVu Sans"

# ──────────────────────────────────────────────────────────────────────────────
# BRAND CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────
BG_COLOR    = "#1B2A4A"       # Dark navy blue background
POINT_COLOR = "#00E5FF"       # Vibrant cyan data points
TREND_COLOR = "#C0C0C0"       # Subtle trendline
ANNOT_COLOR = "#FFFFFF"       # Annotation text
GRID_COLOR  = "#253A5E"       # Subtle grid lines
SPINE_COLOR = "#3A4F78"       # Axis spine colour
WATERMARK   = "Powered by CASSANDRA Oracle Engine"
OUTPUT_PNG  = "ablacao_validacao.png"


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def normalize_municipio(s: str) -> str:
    """Strip accents, lowercase, strip whitespace."""
    if not isinstance(s, str):
        s = str(s)
    return (
        unicodedata.normalize("NFKD", s)
        .encode("ascii", "ignore")
        .decode()
        .strip()
        .lower()
    )


def safe_float(series: pd.Series) -> pd.Series:
    """Coerce to numeric, replace commas if needed."""
    cleaned = series.astype(str).str.replace(",", ".", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")


def find_municipio_col(df: pd.DataFrame) -> str:
    """Return the first column whose name contains 'munic' (case-insensitive)."""
    for col in df.columns:
        if "munic" in str(col).lower():
            return col
    for col in df.columns:
        if df[col].dtype == object:
            return col
    raise ValueError(f"Cannot find municipality column in: {df.columns.tolist()}")


def find_col(df: pd.DataFrame, candidates: list) -> str:
    """Return the first column matching any candidate (case-insensitive partial)."""
    for cand in candidates:
        for col in df.columns:
            if cand.lower() in str(col).lower():
                return col
    raise KeyError(f"None of {candidates} found in columns: {df.columns.tolist()}")


def apply_dark_theme(ax, fig):
    """Apply CASSANDRA premium dark theme to a matplotlib axes."""
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    for spine in ax.spines.values():
        spine.set_edgecolor(SPINE_COLOR)
    ax.tick_params(colors=ANNOT_COLOR, labelsize=9)
    ax.xaxis.label.set_color(ANNOT_COLOR)
    ax.yaxis.label.set_color(ANNOT_COLOR)
    ax.title.set_color(ANNOT_COLOR)
    ax.grid(True, color=GRID_COLOR, linewidth=0.5, linestyle="--", alpha=0.6)


def add_watermark(ax):
    """Place the CASSANDRA watermark in the bottom-right corner."""
    ax.text(
        0.99, 0.01, WATERMARK,
        transform=ax.transAxes,
        fontsize=7.5, color="#5A7AAF",
        ha="right", va="bottom",
        fontstyle="italic",
        alpha=0.85,
    )


def annotate_outliers(ax, xs, ys, labels, color=ANNOT_COLOR):
    """Draw leader-line annotations on selected points."""
    for x, y_val, label in zip(xs, ys, labels):
        ax.annotate(
            label,
            xy=(x, y_val),
            xytext=(12, 8),
            textcoords="offset points",
            fontsize=7.5,
            color=color,
            arrowprops=dict(
                arrowstyle="-",
                color=color,
                lw=0.7,
                alpha=0.7,
            ),
            path_effects=[pe.withStroke(linewidth=2, foreground=BG_COLOR)],
        )


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 1 — DATA INTEGRATION
# ──────────────────────────────────────────────────────────────────────────────
_SEP = "═" * 70

print(f"\n{_SEP}")
print("  CASSANDRA ABLATION STUDY: Model trained WITHOUT historical demographic trend.")
print(f"{_SEP}")
print("\n  PHASE 1 — DATA INTEGRATION")
print(_SEP)

# --- Load IEI metrics ---
try:
    df_iei = pd.read_csv("metricas_iei_completo.csv")
    print(f"[IEI]  Loaded {len(df_iei)} rows from metricas_iei_completo.csv")
except FileNotFoundError:
    sys.exit("[ERROR] metricas_iei_completo.csv not found. Run from project root.")

# --- Load demographic data (Excel file, header on row index 1) ---
try:
    df_dem = pd.read_excel("dados_demograficos.csv", header=1)
    print(f"[DEM]  Loaded {len(df_dem)} rows from dados_demograficos.csv")
except FileNotFoundError:
    sys.exit("[ERROR] dados_demograficos.csv not found. Run from project root.")

# --- Locate municipality columns ---
iei_mun_col = find_municipio_col(df_iei)
dem_mun_col = find_municipio_col(df_dem)
print(f"[IEI]  Municipality column : '{iei_mun_col}'")
print(f"[DEM]  Municipality column : '{dem_mun_col}'")

# --- Normalise keys ---
df_iei["_key"] = df_iei[iei_mun_col].apply(normalize_municipio)
df_dem["_key"] = df_dem[dem_mun_col].apply(normalize_municipio)

# --- Inner merge on normalised key ---
df = pd.merge(df_iei, df_dem, on="_key", how="inner", suffixes=("_iei", "_dem"))
n_matched = len(df)
print(f"\n  Merge result: {n_matched}/308 municipalities matched")

if n_matched < 280:
    unmatched_iei = sorted(set(df_iei["_key"]) - set(df["_key"]))[:20]
    unmatched_dem = sorted(set(df_dem["_key"]) - set(df["_key"]))[:20]
    raise ValueError(
        f"Merge produced only {n_matched}/308 matches (threshold: 280).\n"
        f"  IEI unmatched ({len(unmatched_iei)}): {unmatched_iei}\n"
        f"  DEM unmatched ({len(unmatched_dem)}): {unmatched_dem}"
    )

print("  ✔  Merge threshold OK (≥280)\n")


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 2 — FEATURE ENGINEERING  (ABLATION: Var% 2001→2011 DROPPED)
# ──────────────────────────────────────────────────────────────────────────────
print(_SEP)
print("  PHASE 2 — FEATURE ENGINEERING  [ABLATION MODE]")
print(_SEP)
print("  ⚡ Historical variable 'Var% 2001→2011' has been DROPPED.")
print("  ⚡ Model will rely solely on digital signal (IEI_Score) + static demos.\n")

# Locate each required column dynamically (robust to merge suffixes)
col_iei    = find_col(df, ["IEI_Score", "IEI Score", "IEI"])
col_env01  = find_col(df, ["Env. 2001", "Env_2001", "Envelhecimento 2001"])
col_pop11  = find_col(df, ["Pop. 2011", "Pop_2011", "Pop2011", "População 2011"])
col_target = find_col(df, ["Var% 2011→2021", "Var% 2011", "2011→2021", "2011-2021", "Var%_2011"])

print(f"  FEATURE  IEI_Score  → '{col_iei}'")
print(f"  FEATURE  Env. 2001  → '{col_env01}'")
print(f"  FEATURE  Pop. 2011  → '{col_pop11}'   [log-transformed]")
print(f"  TARGET               → '{col_target}'")
print(f"  DROPPED              → Var% 2001→2011  (ablated)")

# Determine the display municipality name column
name_col = iei_mun_col
for candidate in [iei_mun_col, iei_mun_col + "_iei", dem_mun_col, dem_mun_col + "_dem"]:
    if candidate in df.columns:
        name_col = candidate
        break

# Coerce features and target to float
for col in [col_iei, col_env01, col_pop11, col_target]:
    df[col] = safe_float(df[col])

# Log-transform population (absorbs skew; shift ensures all values ≥ 1)
pop_raw = df[col_pop11]
shift   = max(0.0, 1.0 - float(pop_raw.min()))
df["log_pop_2011"] = np.log(pop_raw + shift)

# ── ABLATION FEATURE SET (3 features only) ──────────────────────────────────
feature_cols = [col_iei, col_env01, "log_pop_2011"]
target_col   = col_target

df_model = df[[name_col] + feature_cols + [target_col]].copy()
df_model = df_model.dropna(subset=feature_cols + [target_col])

n_final = len(df_model)
print(f"\n  Final modelling sample: {n_final} municipalities (after dropping NaNs)")

X     = df_model[feature_cols].values
y     = df_model[target_col].values
names = df_model[name_col].values


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 3 — MODEL  (XGBoost → RandomForest fallback)
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{_SEP}")

X_train, X_test, y_train, y_test, names_train, names_test = train_test_split(
    X, y, names, test_size=0.2, random_state=42
)

# Try XGBoost first; fall back gracefully to RandomForest
try:
    import xgboost as xgb
    model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
    )
    model_name = "XGBRegressor"
    print(f"  PHASE 3 — MODEL  ({model_name})")
    print(_SEP)
except Exception as e:
    from sklearn.ensemble import RandomForestRegressor
    print(f"  [WARN] XGBoost unavailable ({e}). Falling back to RandomForestRegressor.")
    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=4,
        random_state=42,
        n_jobs=-1,
    )
    model_name = "RandomForestRegressor"
    print(f"  PHASE 3 — MODEL  ({model_name})")
    print(_SEP)

model.fit(X_train, y_train)
y_pred = model.predict(X_test)

mae = mean_absolute_error(y_test, y_pred)
r2  = r2_score(y_test, y_pred)

# ── HEAVILY EMPHASISED METRICS ────────────────────────────────────────────────
print()
print("  " + "▓" * 50)
print(f"  ▓{'ABLATION STUDY — PERFORMANCE METRICS':^48}▓")
print("  " + "▓" * 50)
print(f"  ▓  {'R² (Coefficient of Determination)':35s}  {r2:+.6f}  ▓")
print(f"  ▓  {'MAE (Mean Absolute Error)':35s}  {mae:.6f}  ▓")
print(f"  ▓  {'Model':35s}  {model_name:<10}  ▓")
print(f"  ▓  {'Train / Test split':35s}  80 / 20        ▓")
print(f"  ▓  {'Test set size (n)':35s}  {len(y_test):<10}     ▓")
print("  " + "▓" * 50)
print()

if r2 < 0:
    print("  ⚠  WARNING: R² < 0 — model worse than mean baseline without historical trend.")
elif r2 < 0.3:
    print("  📉 Low R²: Digital signal alone explains limited variance without Var% 2001→2011.")
elif r2 >= 0.5:
    print("  📈 Strong signal: IEI_Score retains meaningful predictive power in isolation.")

# Feature importances
print("\n  Feature Importances (ranked):")
if hasattr(model, "feature_importances_"):
    feat_labels = [col_iei, col_env01, "log_pop_2011"]
    ranked = sorted(zip(feat_labels, model.feature_importances_), key=lambda x: x[1], reverse=True)
    for rank, (feat, imp) in enumerate(ranked, 1):
        bar = "█" * int(imp * 40)
        print(f"    {rank}. {feat:42s}  {imp:.4f}  {bar}")


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 4 — PREMIUM VISUALISATION: ablacao_validacao.png
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{_SEP}")
print(f"  PHASE 4 — Generating {OUTPUT_PNG}")
print(_SEP)

fig, ax = plt.subplots(figsize=(13, 8))
apply_dark_theme(ax, fig)

# ── Scatter: actual vs predicted ──────────────────────────────────────────────
sc = ax.scatter(
    y_test, y_pred,
    c=POINT_COLOR,
    alpha=0.75,
    s=65,
    edgecolors="none",
    zorder=3,
    label="Municípios (test set)"
)

# ── Perfect-prediction diagonal line ─────────────────────────────────────────
margin = 0.08
y_all_vals = np.concatenate([y_test, y_pred])
lo = y_all_vals.min() - abs(y_all_vals.min()) * margin
hi = y_all_vals.max() + abs(y_all_vals.max()) * margin
ax.plot(
    [lo, hi], [lo, hi],
    color=TREND_COLOR, linestyle="--", linewidth=1.5,
    alpha=0.8, label="Previsão perfeita (y = x)", zorder=4
)

# ── OLS regression line through scatter ──────────────────────────────────────
slope_v, intercept_v, r_val_v, _, _ = stats.linregress(y_test, y_pred)
x_fit = np.linspace(lo, hi, 300)
ax.plot(
    x_fit, slope_v * x_fit + intercept_v,
    color="#FF6B35", linestyle="-", linewidth=1.2,
    alpha=0.6, label=f"Tendência (r={r_val_v:.3f})", zorder=4
)

# ── Annotate 5 best and 5 worst predictions ───────────────────────────────────
residuals = np.abs(y_pred - y_test)
df_val = pd.DataFrame({
    "y_test":   y_test,
    "y_pred":   y_pred,
    "residual": residuals,
    "name":     names_test,
})
best5  = df_val.nsmallest(5, "residual")
worst5 = df_val.nlargest(5, "residual")

ax.scatter(best5["y_test"], best5["y_pred"],
           c="#69FF47", s=95, zorder=5, edgecolors="#FFFFFF", linewidths=0.6,
           label="Top 5 previsões")
annotate_outliers(ax, best5["y_test"], best5["y_pred"], best5["name"], color="#69FF47")

ax.scatter(worst5["y_test"], worst5["y_pred"],
           c="#FF4081", s=95, zorder=5, edgecolors="#FFFFFF", linewidths=0.6,
           label="5 maiores erros")
annotate_outliers(ax, worst5["y_test"], worst5["y_pred"], worst5["name"], color="#FF4081")

# ── Labels & title ────────────────────────────────────────────────────────────
ax.set_xlabel("Variação Demográfica Real 2011→2021 (%)", fontsize=11, labelpad=8)
ax.set_ylabel("Variação Demográfica Prevista (%)", fontsize=11, labelpad=8)
ax.set_title(
    "CASSANDRA - Estudo de Ablação: Sinal Digital Isolado",
    fontsize=15, fontweight="bold", pad=16, color=ANNOT_COLOR,
)

# ── Subtitle / annotation strip ───────────────────────────────────────────────
ax.text(
    0.50, 1.008,
    f"Ablação: 'Var% 2001→2011' removida · apenas IEI_Score + Env. 2001 + Pop. 2011",
    transform=ax.transAxes,
    fontsize=8, color="#8AB4D4", ha="center", va="bottom", fontstyle="italic",
)

# ── Legend ────────────────────────────────────────────────────────────────────
legend = ax.legend(
    facecolor="#253A5E", labelcolor=ANNOT_COLOR,
    fontsize=9, edgecolor=SPINE_COLOR, framealpha=0.9,
)

# ── Metrics text box (top-left) ───────────────────────────────────────────────
metrics_txt = (
    f"ABLATION METRICS\n"
    f"────────────────\n"
    f"R²   = {r2:+.4f}\n"
    f"MAE  = {mae:.4f}\n"
    f"────────────────\n"
    f"Model  : {model_name}\n"
    f"n test : {len(y_test)}\n"
    f"Features:\n"
    f"  • IEI_Score\n"
    f"  • Env. 2001\n"
    f"  • log(Pop.2011)\n"
    f"DROPPED:\n"
    f"  ✗ Var% 2001→2011"
)
props = dict(boxstyle="round,pad=0.6", facecolor="#0D1E38", edgecolor=SPINE_COLOR, alpha=0.92)
ax.text(
    0.02, 0.98, metrics_txt,
    transform=ax.transAxes,
    fontsize=8, verticalalignment="top",
    color=ANNOT_COLOR, bbox=props, family="monospace",
)

# ── Watermark ─────────────────────────────────────────────────────────────────
add_watermark(ax)

# ── Save ──────────────────────────────────────────────────────────────────────
fig.tight_layout()
fig.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor=BG_COLOR)
plt.close(fig)
print(f"  ✔  Saved: {OUTPUT_PNG}")

# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{_SEP}")
print("  CASSANDRA ABLATION STUDY — Complete.")
print(f"  Output  → {OUTPUT_PNG}")
print(f"\n  ┌─ ABLATION RESULT ────────────────────────────────────┐")
print(f"  │  R²  (test) : {r2:+.6f}                              │")
print(f"  │  MAE (test) : {mae:.6f}                              │")
print(f"  │  Δ feature  : Var% 2001→2011 REMOVED                 │")
print(f"  └───────────────────────────────────────────────────────┘")
print(f"{_SEP}\n")
