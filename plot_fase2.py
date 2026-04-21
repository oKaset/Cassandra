"""
CASSANDRA Oracle Engine — Phase 2 Visualization
plot_fase2.py

Scatter plot: Historical digital capture volume (log-scaled) vs.
real population change 2011→2021, with server health coloring,
Pearson trendline, and full CASSANDRA brand identity.
"""

import sys
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy import stats

matplotlib.use("Agg")  # Non-interactive backend — safe for all environments

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────

print("[CASSANDRA] Loading Phase 2 metrics...")
df_fase2 = pd.read_csv(
    "metricas_fase2_avancadas.csv",
    encoding="utf-8-sig",
)

# dados_demograficos.csv is an Excel file disguised with a .csv extension.
# Row 0 is the title banner; true headers are on row 1 (header=1).
print("[CASSANDRA] Loading demographic data...")
df_demo = pd.read_excel(
    "dados_demograficos.csv",
    header=1,
)

# ─────────────────────────────────────────────────────────────────────────────
# 2. WHITESPACE NORMALISATION
# ─────────────────────────────────────────────────────────────────────────────

df_fase2["Município"] = df_fase2["Município"].astype(str).str.strip()
df_demo["Município"] = df_demo["Município"].astype(str).str.strip()

# ─────────────────────────────────────────────────────────────────────────────
# 3. INNER JOIN — with diagnostic error on empty result
# ─────────────────────────────────────────────────────────────────────────────

df = pd.merge(df_fase2, df_demo, on="Município", how="inner")

if len(df) == 0:
    fase2_names = df_fase2["Município"].dropna().unique()[:5].tolist()
    demo_names  = df_demo["Município"].dropna().unique()[:5].tolist()
    raise ValueError(
        "Merge produced 0 rows — no matching municipalities found.\n"
        f"  Phase-2 sample names : {fase2_names}\n"
        f"  Demographics sample  : {demo_names}\n"
        "Check encoding, whitespace, or spelling mismatches."
    )

print(f"[CASSANDRA] Merge successful: {len(df)} municipalities loaded.")

# ─────────────────────────────────────────────────────────────────────────────
# 4. DATA TRANSFORMATION
# ─────────────────────────────────────────────────────────────────────────────

df["Log_Captures"] = np.log1p(df["Total_Arquivo_Captures"])

# Identify Y-axis column
Y_COL_EXACT = "Var% 2011→2021"
if Y_COL_EXACT in df.columns:
    y_col = Y_COL_EXACT
else:
    # Fuzzy search: column whose name contains both 'Var' and '2021'
    candidates = [
        c for c in df.columns
        if "var" in c.lower() and "2021" in c.lower()
    ]
    if not candidates:
        raise ValueError(
            f"Cannot find population-variation column.\n"
            f"Available columns: {df.columns.tolist()}"
        )
    y_col = candidates[0]
    print(f"[CASSANDRA] Warning: exact column '{Y_COL_EXACT}' not found. "
          f"Using '{y_col}' instead.")

# Drop rows with NaN in the two critical columns
df = df.dropna(subset=["Log_Captures", y_col])
print(f"[CASSANDRA] Rows after NaN drop: {len(df)}")

# ─────────────────────────────────────────────────────────────────────────────
# 5. POINT COLORING LOGIC
# ─────────────────────────────────────────────────────────────────────────────

COLOR_RED  = "#FF3366"   # Digital Rot  (Dead / Timeout)
COLOR_CYAN = "#00E5FF"   # Active Signal (everything else)

def assign_color(status):
    if isinstance(status, str) and status in ("Dead", "Timeout"):
        return COLOR_RED
    return COLOR_CYAN

df["color"] = df["Live_StatusCode"].apply(assign_color)

mask_red  = df["color"] == COLOR_RED
mask_cyan = ~mask_red

# ─────────────────────────────────────────────────────────────────────────────
# 6. TRENDLINE — Pearson / Linear Regression
# ─────────────────────────────────────────────────────────────────────────────

x_vals = df["Log_Captures"].values
y_vals = df[y_col].values

slope, intercept, r_value, p_value, _ = stats.linregress(x_vals, y_vals)

x_line = np.linspace(x_vals.min(), x_vals.max(), 300)
y_line = slope * x_line + intercept

# ─────────────────────────────────────────────────────────────────────────────
# 7. FIGURE — CASSANDRA BRAND IDENTITY
# ─────────────────────────────────────────────────────────────────────────────

BG       = "#1B2A4A"
SPINE_C  = "#3A5A8A"
TICK_C   = "#AAAAAA"

fig, ax = plt.subplots(figsize=(14, 9), dpi=150)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

# ── Scatter: cyan first (bottom layer), red on top ──────────────────────────
ax.scatter(
    df.loc[mask_cyan, "Log_Captures"],
    df.loc[mask_cyan, y_col],
    c=COLOR_CYAN,
    s=60,
    alpha=0.75,
    edgecolors="none",
    zorder=2,
    label="Município Ativo",
)
ax.scatter(
    df.loc[mask_red, "Log_Captures"],
    df.loc[mask_red, y_col],
    c=COLOR_RED,
    s=60,
    alpha=0.75,
    edgecolors="none",
    zorder=3,
    label="Rot Digital (Dead/Timeout)",
)

# ── Trendline ────────────────────────────────────────────────────────────────
ax.plot(
    x_line,
    y_line,
    color="white",
    linewidth=1.5,
    linestyle="--",
    alpha=0.6,
    zorder=4,
)

# ── Pearson annotation (upper-left) ─────────────────────────────────────────
stats_text = (
    f"r = {r_value:.3f}     "
    f"R² = {r_value**2:.3f}     "
    f"p = {p_value:.4f}"
)
ax.text(
    0.03, 0.95,
    stats_text,
    transform=ax.transAxes,
    color="white",
    fontsize=11,
    va="top",
    bbox=dict(
        boxstyle="round,pad=0.4",
        facecolor=BG,
        alpha=0.7,
        edgecolor=SPINE_C,
    ),
    zorder=5,
)

# ── Axis labels ──────────────────────────────────────────────────────────────
ax.set_xlabel(
    "Volume de Atividade Digital Histórica — log(Capturas + 1)",
    color="white",
    fontsize=13,
)
ax.set_ylabel(
    "Variação Populacional Real 2011→2021 (%)",
    color="white",
    fontsize=13,
)

# ── Title ────────────────────────────────────────────────────────────────────
ax.set_title(
    "CASSANDRA Oracle Engine — Correlação Volume Digital × Declínio Populacional",
    color="white",
    fontsize=15,
    fontweight="bold",
    pad=14,
)

# ── Tick styling ─────────────────────────────────────────────────────────────
ax.tick_params(colors=TICK_C, labelsize=10)
ax.xaxis.label.set_color("white")
ax.yaxis.label.set_color("white")
for spine_name in ["top", "right"]:
    ax.spines[spine_name].set_visible(False)
for spine_name in ["bottom", "left"]:
    ax.spines[spine_name].set_color(SPINE_C)

# ── Legend ───────────────────────────────────────────────────────────────────
legend = ax.legend(
    loc="upper right",
    facecolor=BG,
    edgecolor=SPINE_C,
    labelcolor="white",
    fontsize=10,
    framealpha=0.85,
)

# ── Watermark ────────────────────────────────────────────────────────────────
ax.text(
    0.99, 0.01,
    "Powered by CASSANDRA Oracle Engine",
    transform=ax.transAxes,
    ha="right",
    va="bottom",
    fontsize=8,
    color=SPINE_C,
    alpha=0.8,
    zorder=5,
)

# ─────────────────────────────────────────────────────────────────────────────
# 8. OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

output_path = "plot_fase2_volume.png"
plt.savefig(output_path, bbox_inches="tight")
plt.close()

print(f"[CASSANDRA] Plot saved → {output_path}")
print(
    f"[CASSANDRA] Stats — r={r_value:.3f}, R²={r_value**2:.3f}, "
    f"p={p_value:.4f}, n={len(df)}"
)
