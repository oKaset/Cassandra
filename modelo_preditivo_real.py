"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           CASSANDRA Oracle Engine — Predictive Demographic Model             ║
║           ArquivoPT2026 · Phase 3: modelo_preditivo_real.py                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

USAGE:
    pip install pandas openpyxl scikit-learn matplotlib numpy scipy
    python modelo_preditivo_real.py
"""

import unicodedata
import sys
import warnings

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch
from scipy import stats
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.ensemble import RandomForestRegressor

warnings.filterwarnings("ignore")
matplotlib.rcParams["font.family"] = "DejaVu Sans"

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


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 1 — DATA INTEGRATION
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 70)
print("  PHASE 1 — DATA INTEGRATION")
print("═" * 70)

# --- Load IEI metrics ---
df_iei = pd.read_csv("metricas_iei_completo.csv")
print(f"[IEI]  Loaded {len(df_iei)} rows from metricas_iei_completo.csv")

# --- Load demographic data (header on row index 1) ---
df_dem = pd.read_excel("dados_demograficos.csv", header=1)
print(f"[DEM]  Loaded {len(df_dem)} rows from dados_demograficos.csv")

# Identify the municipality column in each dataframe
# (first column whose name contains 'munic' case-insensitively, or column 0)
def find_municipio_col(df: pd.DataFrame) -> str:
    for col in df.columns:
        if "munic" in str(col).lower():
            return col
    # fallback: first string column
    for col in df.columns:
        if df[col].dtype == object:
            return col
    raise ValueError(f"Cannot find municipality column in columns: {df.columns.tolist()}")

iei_mun_col = find_municipio_col(df_iei)
dem_mun_col = find_municipio_col(df_dem)

print(f"[IEI]  Municipality column: '{iei_mun_col}'")
print(f"[DEM]  Municipality column: '{dem_mun_col}'")

# --- Normalise keys ---
df_iei["_key"] = df_iei[iei_mun_col].apply(normalize_municipio)
df_dem["_key"] = df_dem[dem_mun_col].apply(normalize_municipio)

# --- Inner merge ---
df = pd.merge(df_iei, df_dem, on="_key", how="inner", suffixes=("_iei", "_dem"))

n_matched = len(df)
print(f"\nMerge result: {n_matched}/308 municipalities matched")

if n_matched < 280:
    unmatched_iei = set(df_iei["_key"]) - set(df["_key"])
    unmatched_dem = set(df_dem["_key"]) - set(df["_key"])
    msg = (
        f"Merge produced only {n_matched}/308 matches — below threshold of 280.\n"
        f"  IEI keys not matched ({len(unmatched_iei)}): {sorted(unmatched_iei)[:20]}\n"
        f"  DEM keys not matched ({len(unmatched_dem)}): {sorted(unmatched_dem)[:20]}"
    )
    raise ValueError(msg)

print("✔  Merge threshold OK (≥280)\n")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 2 — FEATURE ENGINEERING
# ──────────────────────────────────────────────────────────────────────────────
print("═" * 70)
print("  PHASE 2 — FEATURE ENGINEERING")
print("═" * 70)


def find_col(df: pd.DataFrame, candidates: list[str]) -> str:
    """Return the first column that matches any candidate (case-insensitive partial)."""
    for cand in candidates:
        for col in df.columns:
            if cand.lower() in str(col).lower():
                return col
    raise KeyError(f"None of {candidates} found in columns: {df.columns.tolist()}")


# Locate feature columns dynamically (handles suffix variants from merge)
col_iei    = find_col(df, ["IEI_Score", "IEI Score", "IEI"])
col_var01  = find_col(df, ["Var% 2001", "Var 2001", "2001→2011", "2001-2011", "Var%_2001"])
col_env01  = find_col(df, ["Env. 2001", "Env_2001", "Envelhecimento 2001"])
col_pop11  = find_col(df, ["Pop. 2011", "Pop_2011", "Pop2011", "População 2011"])
col_target = find_col(df, ["Var% 2011→2021", "Var% 2011", "2011→2021", "2011-2021", "Var%_2011"])

print(f"  IEI_Score     → '{col_iei}'")
print(f"  Var% 2001→11  → '{col_var01}'")
print(f"  Env. 2001     → '{col_env01}'")
print(f"  Pop. 2011     → '{col_pop11}'")
print(f"  Target        → '{col_target}'")

# Coerce all to numeric
for col in [col_iei, col_var01, col_env01, col_pop11, col_target]:
    df[col] = safe_float(df[col])

# Log-transform population (shift to avoid zero/negative)
pop_raw = df[col_pop11]
pop_min = pop_raw.min()
shift   = max(0, 1 - pop_min)          # ensures all values ≥ 1
df["log_pop_2011"] = np.log(pop_raw + shift)

# Build modelling dataframe
feature_cols = [col_iei, col_var01, col_env01, "log_pop_2011"]
target_col   = col_target

# Find municipality name column for annotations
name_col = iei_mun_col if iei_mun_col in df.columns else dem_mun_col + "_dem"
if name_col not in df.columns:
    # try suffixed versions
    for suffix in ["_iei", "_dem", ""]:
        candidate = iei_mun_col + suffix
        if candidate in df.columns:
            name_col = candidate
            break

df_model = df[[name_col] + feature_cols + [target_col]].copy()
df_model = df_model.dropna(subset=feature_cols + [target_col])

n_final = len(df_model)
print(f"\nFinal modelling sample: {n_final} municipalities (after dropping NaNs)")

X = df_model[feature_cols].values
y = df_model[target_col].values
names = df_model[name_col].values

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 3 — MODEL
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 70)
print("  PHASE 3 — MODEL (RandomForestRegressor)")
print("═" * 70)

X_train, X_test, y_train, y_test, names_train, names_test = train_test_split(
    X, y, names, test_size=0.2, random_state=42
)

model = RandomForestRegressor(
    n_estimators=100,
    max_depth=3,
    random_state=42,
    n_jobs=-1,
)
model.fit(X_train, y_train)

y_pred = model.predict(X_test)

mae = mean_absolute_error(y_test, y_pred)
r2  = r2_score(y_test, y_pred)

print(f"\n  MAE  : {mae:.4f}")
print(f"  R²   : {r2:.4f}")

if r2 < 0:
    print("\n  ⚠  WARNING: Model performs worse than mean baseline (R² < 0)")

print("\n  Feature Importances (ranked):")
importances = model.feature_importances_
feat_labels = [col_iei, col_var01, col_env01, "log_pop_2011"]
ranked = sorted(zip(feat_labels, importances), key=lambda x: x[1], reverse=True)
for rank, (feat, imp) in enumerate(ranked, 1):
    print(f"    {rank}. {feat:40s}  {imp:.4f}")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 4 — PREMIUM VISUALISATIONS
# ──────────────────────────────────────────────────────────────────────────────
BG_COLOR    = "#1B2A4A"
POINT_A     = "#00E5FF"
POINT_B     = "#FFB347"
TREND_COLOR = "#C0C0C0"
ANNOT_COLOR = "#FFFFFF"
WATERMARK   = "Powered by CASSANDRA Oracle Engine"

def apply_dark_theme(ax, fig):
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    for spine in ax.spines.values():
        spine.set_edgecolor("#3A4F78")
    ax.tick_params(colors=ANNOT_COLOR, labelsize=9)
    ax.xaxis.label.set_color(ANNOT_COLOR)
    ax.yaxis.label.set_color(ANNOT_COLOR)
    ax.title.set_color(ANNOT_COLOR)
    ax.grid(True, color="#253A5E", linewidth=0.5, linestyle="--", alpha=0.6)


def add_watermark(ax):
    ax.text(
        0.99, 0.01, WATERMARK,
        transform=ax.transAxes,
        fontsize=7, color="#5A7AAF",
        ha="right", va="bottom",
        fontstyle="italic",
        alpha=0.8,
    )


def annotate_points(ax, xs, ys, labels, color=ANNOT_COLOR, fontsize=7.5):
    """Annotate a set of (x, y, label) triples with offset arrows."""
    for x, y_val, label in zip(xs, ys, labels):
        ax.annotate(
            label,
            xy=(x, y_val),
            xytext=(12, 8),
            textcoords="offset points",
            fontsize=fontsize,
            color=color,
            arrowprops=dict(
                arrowstyle="-",
                color=color,
                lw=0.7,
                alpha=0.7,
            ),
            path_effects=[
                pe.withStroke(linewidth=2, foreground=BG_COLOR)
            ],
        )


# ── PLOT A — Correlation: IEI vs Demographic Change ──────────────────────────
print("\n" + "═" * 70)
print("  PHASE 4A — Generating plot_correlacao.png")
print("═" * 70)

x_all  = df_model[col_iei].values
y_all  = df_model[col_target].values
n_all  = df_model[name_col].values

fig_a, ax_a = plt.subplots(figsize=(12, 7))
apply_dark_theme(ax_a, fig_a)

ax_a.scatter(x_all, y_all, c=POINT_A, alpha=0.7, s=55, edgecolors="none", zorder=3)

# Regression trendline
slope, intercept, r_val, p_val, _ = stats.linregress(x_all, y_all)
x_line = np.linspace(x_all.min(), x_all.max(), 300)
y_line = slope * x_line + intercept
ax_a.plot(x_line, y_line, color=TREND_COLOR, linestyle="--", linewidth=1.5,
          alpha=0.8, label=f"Tendência  r={r_val:.3f}", zorder=4)

# ── Outlier selection ──
# 4 highest IEI with worst demographics (lowest y)
df_ann = pd.DataFrame({"x": x_all, "y": y_all, "name": n_all})
top_iei   = df_ann.nlargest(20, "x")
worst_dem = top_iei.nsmallest(4, "y")

# 4 lowest IEI with best demographics (highest y)
bot_iei   = df_ann.nsmallest(20, "x")
best_dem  = bot_iei.nlargest(4, "y")

outliers  = pd.concat([worst_dem, best_dem])

# Highlight outliers
ax_a.scatter(outliers["x"], outliers["y"], c="#FF4081", s=80, zorder=5,
             edgecolors="#FFFFFF", linewidths=0.6)

annotate_points(ax_a, outliers["x"], outliers["y"], outliers["name"],
                color="#FF4081")

ax_a.set_xlabel("IEI Score  (Índice de Envelhecimento Digital)", fontsize=11)
ax_a.set_ylabel("Var% Populacional 2011→2021", fontsize=11)
ax_a.set_title(
    "CASSANDRA — Sinal Digital vs Declínio Demográfico",
    fontsize=14, fontweight="bold", pad=14,
)
ax_a.legend(facecolor="#253A5E", labelcolor=ANNOT_COLOR, fontsize=9,
            edgecolor="#3A4F78")
add_watermark(ax_a)

# Correlation text box
txt = (
    f"r = {r_val:.3f}\n"
    f"R² = {r_val**2:.3f}\n"
    f"n = {len(x_all)}"
)
props = dict(boxstyle="round,pad=0.5", facecolor="#253A5E",
             edgecolor="#3A4F78", alpha=0.9)
ax_a.text(0.03, 0.97, txt, transform=ax_a.transAxes, fontsize=9,
          verticalalignment="top", color=ANNOT_COLOR, bbox=props)

fig_a.tight_layout()
fig_a.savefig("plot_correlacao.png", dpi=300, bbox_inches="tight",
              facecolor=BG_COLOR)
plt.close(fig_a)
print("  ✔  Saved: plot_correlacao.png")

# ── PLOT B — Model Validation: Actual vs Predicted ───────────────────────────
print("\n  PHASE 4B — Generating plot_validacao.png")

fig_b, ax_b = plt.subplots(figsize=(12, 7))
apply_dark_theme(ax_b, fig_b)

ax_b.scatter(y_test, y_pred, c=POINT_B, alpha=0.75, s=60,
             edgecolors="none", zorder=3)

# Diagonal perfect-prediction reference line
xy_min = min(y_test.min(), y_pred.min()) * 1.05
xy_max = max(y_test.max(), y_pred.max()) * 1.05
ax_b.plot([xy_min, xy_max], [xy_min, xy_max],
          color=TREND_COLOR, linestyle="--", linewidth=1.5,
          alpha=0.8, label="Previsão perfeita (y=x)", zorder=4)

# Compute residuals for annotation selection
residuals  = np.abs(y_pred - y_test)
df_val     = pd.DataFrame({
    "y_test": y_test,
    "y_pred": y_pred,
    "residual": residuals,
    "name": names_test,
})

best5  = df_val.nsmallest(5, "residual")
worst5 = df_val.nlargest(5, "residual")

# Highlight best predictions (green tint)
ax_b.scatter(best5["y_test"], best5["y_pred"], c="#69FF47", s=90, zorder=5,
             edgecolors="#FFFFFF", linewidths=0.6, label="Top 5 previsões")
annotate_points(ax_b, best5["y_test"], best5["y_pred"], best5["name"],
                color="#69FF47")

# Highlight worst predictions (red tint)
ax_b.scatter(worst5["y_test"], worst5["y_pred"], c="#FF4081", s=90, zorder=5,
             edgecolors="#FFFFFF", linewidths=0.6, label="5 maiores erros")
annotate_points(ax_b, worst5["y_test"], worst5["y_pred"], worst5["name"],
                color="#FF4081")

ax_b.set_xlabel("Variação Demográfica Real 2011→2021 (%)", fontsize=11)
ax_b.set_ylabel("Variação Demográfica Prevista (%)", fontsize=11)
ax_b.set_title(
    "CASSANDRA — Validação Retroativa: Real vs Previsto",
    fontsize=14, fontweight="bold", pad=14,
)
ax_b.legend(facecolor="#253A5E", labelcolor=ANNOT_COLOR, fontsize=9,
            edgecolor="#3A4F78")
add_watermark(ax_b)

# Metrics text box
metrics_txt = (
    f"MAE  = {mae:.4f}\n"
    f"R²   = {r2:.4f}\n"
    f"n_test = {len(y_test)}"
)
props_b = dict(boxstyle="round,pad=0.5", facecolor="#253A5E",
               edgecolor="#3A4F78", alpha=0.9)
ax_b.text(0.03, 0.97, metrics_txt, transform=ax_b.transAxes, fontsize=9,
          verticalalignment="top", color=ANNOT_COLOR, bbox=props_b)

fig_b.tight_layout()
fig_b.savefig("plot_validacao.png", dpi=300, bbox_inches="tight",
              facecolor=BG_COLOR)
plt.close(fig_b)
print("  ✔  Saved: plot_validacao.png")

# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 70)
print("  CASSANDRA — Pipeline completo. Outputs gerados:")
print("    • plot_correlacao.png")
print("    • plot_validacao.png")
print(f"\n  Final stats  →  MAE: {mae:.4f}  |  R²: {r2:.4f}  |  n: {n_final}")
print("═" * 70 + "\n")
