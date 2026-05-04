"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           CASSANDRA Oracle Engine — Predictive Demographic Model             ║
║           ArquivoPT2026 · Phase 3: modelo_preditivo_real.py                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

USAGE:
    pip install pandas openpyxl scikit-learn matplotlib numpy scipy
    # XGBoost optional (fallback to RandomForestClassifier if unavailable):
    pip install xgboost
    python modelo_preditivo_real.py
"""

import json
from pathlib import Path
from typing import Optional
import unicodedata
import sys
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch
from scipy import stats
from sklearn.model_selection import train_test_split, GroupKFold
from sklearn.metrics import accuracy_score, classification_report, ConfusionMatrixDisplay, confusion_matrix
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

warnings.filterwarnings("ignore")
matplotlib.rcParams["font.family"] = "DejaVu Sans"

# ──────────────────────────────────────────────────────────────────────────────
# BRAND CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────
BG_COLOR    = "#1B2A4A"
POINT_A     = "#00E5FF"
POINT_B     = "#FFB347"
TREND_COLOR = "#C0C0C0"
ANNOT_COLOR = "#FFFFFF"
WATERMARK   = "Powered by CASSANDRA Oracle Engine"

TIER_PALETTE = {
    "TIER 4 - Profecia CASSANDRA": "#FF3366",
    "TIER 3 - Risco de Fuga":      "#FFAA00",
    "TIER 2 - Estagnação":         "#00E5FF",
    "TIER 1 - Resiliência":        "#69FF47",
    "TIER - Indeterminado":        "#7FB3D3",
}

TIER_ORDER = [
    "TIER 4 - Profecia CASSANDRA",
    "TIER 3 - Risco de Fuga",
    "TIER 2 - Estagnação",
    "TIER 1 - Resiliência",
    "TIER - Indeterminado",
]

TIER_SHORT_LABELS = {
    "TIER 4 - Profecia CASSANDRA": "Tier 4",
    "TIER 3 - Risco de Fuga": "Tier 3",
    "TIER 2 - Estagnação": "Tier 2",
    "TIER 1 - Resiliência": "Tier 1",
}

LEGACY_TIER_THRESHOLDS = {
    "tier4_upper": -5.0,
    "tier3_upper": 0.0,
    "tier2_upper": 2.0,
}

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

# Phase 2 enrichment file (CASSANDRA extrator_fase2_avancado.py output)
# Expected columns: Município, Total_Arquivo_Captures, Live_StatusCode
FASE2_CSV = "metricas_fase2_completo.csv"
ARQUIVO_TEMPORAL_CSV = "data/arquivo_temporal_features.csv"
ARQUIVO_TEMPORAL_FEATURE_COLS = [
    "captures_2013_2018",
    "captures_2019_2024",
    "capture_trend",
    "last_capture_year",
    "years_since_last_capture",
]

# ──────────────────────────────────────────────────────────────────────────────
# DISTRITO MAP — 308 Portuguese municipalities → 18 Distritos
# ──────────────────────────────────────────────────────────────────────────────
DISTRITO_MAP: dict[str, str] = {
    # AVEIRO (19)
    "Águeda": "Aveiro", "Albergaria-a-Velha": "Aveiro", "Anadia": "Aveiro",
    "Arouca": "Aveiro", "Aveiro": "Aveiro", "Castelo de Paiva": "Aveiro",
    "Espinho": "Aveiro", "Estarreja": "Aveiro", "Ílhavo": "Aveiro",
    "Mealhada": "Aveiro", "Murtosa": "Aveiro", "Oliveira de Azeméis": "Aveiro",
    "Oliveira do Bairro": "Aveiro", "Ovar": "Aveiro", "Santa Maria da Feira": "Aveiro",
    "São João da Madeira": "Aveiro", "Sever do Vouga": "Aveiro",
    "Vagos": "Aveiro", "Vale de Cambra": "Aveiro",
    # BEJA (14)
    "Aljustrel": "Beja", "Almodôvar": "Beja", "Alvito": "Beja",
    "Barrancos": "Beja", "Beja": "Beja", "Castro Verde": "Beja",
    "Cuba": "Beja", "Ferreira do Alentejo": "Beja", "Mértola": "Beja",
    "Moura": "Beja", "Ourique": "Beja", "Serpa": "Beja",
    "Vidigueira": "Beja", "Odemira": "Beja",
    # BRAGA (14)
    "Amares": "Braga", "Barcelos": "Braga", "Braga": "Braga",
    "Cabeceiras de Basto": "Braga", "Celorico de Basto": "Braga",
    "Esposende": "Braga", "Fafe": "Braga", "Guimarães": "Braga",
    "Póvoa de Lanhoso": "Braga", "Terras de Bouro": "Braga",
    "Vieira do Minho": "Braga", "Vila Nova de Famalicão": "Braga",
    "Vila Verde": "Braga", "Vizela": "Braga",
    # BRAGANÇA (12)
    "Alfândega da Fé": "Bragança", "Bragança": "Bragança",
    "Carrazeda de Ansiães": "Bragança", "Freixo de Espada à Cinta": "Bragança",
    "Macedo de Cavaleiros": "Bragança", "Miranda do Douro": "Bragança",
    "Mirandela": "Bragança", "Mogadouro": "Bragança",
    "Torre de Moncorvo": "Bragança", "Vila Flor": "Bragança",
    "Vimioso": "Bragança", "Vinhais": "Bragança",
    # CASTELO BRANCO (11)
    "Belmonte": "Castelo Branco", "Castelo Branco": "Castelo Branco",
    "Covilhã": "Castelo Branco", "Fundão": "Castelo Branco",
    "Idanha-a-Nova": "Castelo Branco", "Oleiros": "Castelo Branco",
    "Penamacor": "Castelo Branco", "Proença-a-Nova": "Castelo Branco",
    "Sertã": "Castelo Branco", "Vila de Rei": "Castelo Branco",
    "Vila Velha de Ródão": "Castelo Branco",
    # COIMBRA (17)
    "Arganil": "Coimbra", "Cantanhede": "Coimbra", "Coimbra": "Coimbra",
    "Condeixa-a-Nova": "Coimbra", "Figueira da Foz": "Coimbra",
    "Góis": "Coimbra", "Lousã": "Coimbra", "Mira": "Coimbra",
    "Miranda do Corvo": "Coimbra", "Montemor-o-Velho": "Coimbra",
    "Oliveira do Hospital": "Coimbra", "Pampilhosa da Serra": "Coimbra",
    "Penacova": "Coimbra", "Penela": "Coimbra", "Soure": "Coimbra",
    "Tábua": "Coimbra", "Vila Nova de Poiares": "Coimbra",
    # ÉVORA (14)
    "Alandroal": "Évora", "Arraiolos": "Évora", "Borba": "Évora",
    "Estremoz": "Évora", "Évora": "Évora", "Montemor-o-Novo": "Évora",
    "Mora": "Évora", "Mourão": "Évora", "Portel": "Évora",
    "Redondo": "Évora", "Reguengos de Monsaraz": "Évora",
    "Vendas Novas": "Évora", "Viana do Alentejo": "Évora",
    "Vila Viçosa": "Évora",
    # FARO (16)
    "Albufeira": "Faro", "Alcoutim": "Faro", "Aljezur": "Faro",
    "Castro Marim": "Faro", "Faro": "Faro", "Lagoa": "Faro",
    "Lagos": "Faro", "Loulé": "Faro", "Monchique": "Faro",
    "Olhão": "Faro", "Portimão": "Faro", "São Brás de Alportel": "Faro",
    "Silves": "Faro", "Tavira": "Faro", "Vila do Bispo": "Faro",
    "Vila Real de Santo António": "Faro",
    # GUARDA (14)
    "Aguiar da Beira": "Guarda", "Almeida": "Guarda",
    "Celorico da Beira": "Guarda", "Figueira de Castelo Rodrigo": "Guarda",
    "Fornos de Algodres": "Guarda", "Gouveia": "Guarda",
    "Guarda": "Guarda", "Manteigas": "Guarda", "Mêda": "Guarda",
    "Pinhel": "Guarda", "Sabugal": "Guarda", "Seia": "Guarda",
    "Trancoso": "Guarda", "Vila Nova de Foz Côa": "Guarda",
    # LEIRIA (16)
    "Alcobaça": "Leiria", "Alvaiázere": "Leiria", "Ansião": "Leiria",
    "Batalha": "Leiria", "Bombarral": "Leiria", "Caldas da Rainha": "Leiria",
    "Castanheira de Pêra": "Leiria", "Figueiró dos Vinhos": "Leiria",
    "Leiria": "Leiria", "Marinha Grande": "Leiria", "Nazaré": "Leiria",
    "Óbidos": "Leiria", "Pedrógão Grande": "Leiria", "Peniche": "Leiria",
    "Pombal": "Leiria", "Porto de Mós": "Leiria",
    # LISBOA (16)
    "Alenquer": "Lisboa", "Arruda dos Vinhos": "Lisboa",
    "Azambuja": "Lisboa", "Cadaval": "Lisboa", "Cascais": "Lisboa",
    "Lisboa": "Lisboa", "Loures": "Lisboa", "Lourinhã": "Lisboa",
    "Mafra": "Lisboa", "Odivelas": "Lisboa", "Oeiras": "Lisboa",
    "Sintra": "Lisboa", "Sobral de Monte Agraço": "Lisboa",
    "Torres Vedras": "Lisboa", "Vila Franca de Xira": "Lisboa",
    "Amadora": "Lisboa",
    # PORTALEGRE (15)
    "Alter do Chão": "Portalegre", "Arronches": "Portalegre",
    "Avis": "Portalegre", "Campo Maior": "Portalegre",
    "Castelo de Vide": "Portalegre", "Crato": "Portalegre",
    "Elvas": "Portalegre", "Fronteira": "Portalegre",
    "Gavião": "Portalegre", "Marvão": "Portalegre",
    "Monforte": "Portalegre", "Nisa": "Portalegre",
    "Ponte de Sor": "Portalegre", "Portalegre": "Portalegre",
    "Sousel": "Portalegre",
    # PORTO (18)
    "Amarante": "Porto", "Baião": "Porto", "Felgueiras": "Porto",
    "Gondomar": "Porto", "Lousada": "Porto", "Maia": "Porto",
    "Marco de Canaveses": "Porto", "Matosinhos": "Porto",
    "Paços de Ferreira": "Porto", "Paredes": "Porto",
    "Penafiel": "Porto", "Porto": "Porto", "Póvoa de Varzim": "Porto",
    "Santo Tirso": "Porto", "Trofa": "Porto",
    "Valongo": "Porto", "Vila do Conde": "Porto",
    "Vila Nova de Gaia": "Porto",
    # SANTARÉM (21)
    "Abrantes": "Santarém", "Alcanena": "Santarém", "Almeirim": "Santarém",
    "Alpiarça": "Santarém", "Benavente": "Santarém", "Cartaxo": "Santarém",
    "Chamusca": "Santarém", "Constância": "Santarém", "Coruche": "Santarém",
    "Entroncamento": "Santarém", "Ferreira do Zêzere": "Santarém",
    "Golegã": "Santarém", "Mação": "Santarém",
    "Ourém": "Santarém", "Rio Maior": "Santarém",
    "Salvaterra de Magos": "Santarém", "Santarém": "Santarém",
    "Sardoal": "Santarém", "Tomar": "Santarém",
    "Torres Novas": "Santarém", "Vila Nova da Barquinha": "Santarém",
    # SETÚBAL (13)
    "Alcácer do Sal": "Setúbal", "Alcochete": "Setúbal",
    "Almada": "Setúbal", "Barreiro": "Setúbal", "Grândola": "Setúbal",
    "Moita": "Setúbal", "Montijo": "Setúbal", "Palmela": "Setúbal",
    "Santiago do Cacém": "Setúbal", "Seixal": "Setúbal",
    "Sesimbra": "Setúbal", "Setúbal": "Setúbal",
    "Sines": "Setúbal",
    # VIANA DO CASTELO (10)
    "Arcos de Valdevez": "Viana do Castelo", "Caminha": "Viana do Castelo",
    "Melgaço": "Viana do Castelo", "Monção": "Viana do Castelo",
    "Paredes de Coura": "Viana do Castelo", "Ponte da Barca": "Viana do Castelo",
    "Ponte de Lima": "Viana do Castelo", "Valença": "Viana do Castelo",
    "Viana do Castelo": "Viana do Castelo", "Vila Nova de Cerveira": "Viana do Castelo",
    # VILA REAL (14)
    "Alijó": "Vila Real", "Boticas": "Vila Real", "Chaves": "Vila Real",
    "Mesão Frio": "Vila Real", "Mondim de Basto": "Vila Real",
    "Montalegre": "Vila Real", "Murça": "Vila Real",
    "Peso da Régua": "Vila Real", "Ribeira de Pena": "Vila Real",
    "Sabrosa": "Vila Real", "Santa Marta de Penaguião": "Vila Real",
    "Valpaços": "Vila Real", "Vila Pouca de Aguiar": "Vila Real",
    "Vila Real": "Vila Real",
    # VISEU (24)
    "Armamar": "Viseu", "Carregal do Sal": "Viseu", "Castro Daire": "Viseu",
    "Cinfães": "Viseu", "Lamego": "Viseu", "Mangualde": "Viseu",
    "Moimenta da Beira": "Viseu", "Mortágua": "Viseu",
    "Nelas": "Viseu", "Oliveira de Frades": "Viseu",
    "Penalva do Castelo": "Viseu", "Penedono": "Viseu",
    "Resende": "Viseu", "Santa Comba Dão": "Viseu",
    "São João da Pesqueira": "Viseu", "São Pedro do Sul": "Viseu",
    "Sátão": "Viseu", "Sernancelhe": "Viseu", "Tabuaço": "Viseu",
    "Tarouca": "Viseu", "Tondela": "Viseu", "Vila Nova de Paiva": "Viseu",
    "Viseu": "Viseu", "Vouzela": "Viseu",
}

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
    for col in df.columns:
        if "munic" in str(col).lower():
            return col
    # fallback: first string column
    for col in df.columns:
        if df[col].dtype == object:
            return col
    raise ValueError(f"Cannot find municipality column in columns: {df.columns.tolist()}")


def find_col(df: pd.DataFrame, candidates: list) -> str:
    """Return the first column that matches any candidate (case-insensitive partial)."""
    for cand in candidates:
        for col in df.columns:
            if cand.lower() in str(col).lower():
                return col
    raise KeyError(f"None of {candidates} found in columns: {df.columns.tolist()}")


def find_optional_col(df: pd.DataFrame, candidates: list) -> Optional[str]:
    try:
        return find_col(df, candidates)
    except KeyError:
        return None


def assign_tier_from_thresholds(var_pop: float, thresholds: dict[str, float]) -> str:
    if pd.isna(var_pop):
        return "TIER - Indeterminado"
    if var_pop < thresholds["tier4_upper"]:
        return "TIER 4 - Profecia CASSANDRA"
    if var_pop < thresholds["tier3_upper"]:
        return "TIER 3 - Risco de Fuga"
    if var_pop < thresholds["tier2_upper"]:
        return "TIER 2 - Estagnação"
    return "TIER 1 - Resiliência"


def describe_thresholds(thresholds: dict[str, float]) -> str:
    return (
        f"Tier 4 < {thresholds['tier4_upper']}; "
        f"Tier 3 [{thresholds['tier4_upper']}, {thresholds['tier3_upper']}); "
        f"Tier 2 [{thresholds['tier3_upper']}, {thresholds['tier2_upper']}); "
        f"Tier 1 >= {thresholds['tier2_upper']}"
    )


def print_tier_distribution(title: str, tier_series: pd.Series) -> None:
    counts = tier_series.value_counts()
    total = len(tier_series)
    print(title)
    for tier in TIER_ORDER:
        count = counts.get(tier, 0)
        pct = 100 * count / total if total > 0 else 0.0
        print(f"    {tier:45s} : {count}  ({pct:.1f}%)")


def impute_total_arquivo_captures(df: pd.DataFrame, municipio_col: str) -> pd.DataFrame:
    captures_col = "Total_Arquivo_Captures"
    if captures_col not in df.columns:
        df[captures_col] = np.nan

    captures = safe_float(df[captures_col])
    zero_count = int((captures == 0).sum())
    missing_count = int(captures.isna().sum())
    captures = captures.mask(captures == 0, np.nan)
    global_median = captures.median()

    nut_col = find_optional_col(
        df,
        ["NUT III", "NUTS III", "NUT_III", "NUTS_III", "NUTIII", "NUTSIII", "NUTS3"],
    )
    if nut_col:
        region_values = df[nut_col]
        region_source = f"NUT III column '{nut_col}'"
    else:
        region_values = pd.Series(np.nan, index=df.index)
        region_source = "global fallback (no NUT III column found)"

    before_region_missing = int(captures.isna().sum())
    regional_medians = captures.groupby(region_values).transform("median")
    captures = captures.fillna(regional_medians)
    after_region_missing = int(captures.isna().sum())
    if not pd.isna(global_median):
        captures = captures.fillna(global_median)
    after_global_missing = int(captures.isna().sum())

    df[captures_col] = captures
    print(
        f"[FASE2] {captures_col}: zeros treated as missing={zero_count}; "
        f"pre-existing missing={missing_count}; region source={region_source}; "
        f"regional imputations={before_region_missing - after_region_missing}; "
        f"global fallback imputations={after_region_missing - after_global_missing}; "
        f"global median={global_median:.1f}"
    )
    return df


def write_tier_data_js(df_source: pd.DataFrame, output_path: str = "assets/tier_data.js") -> dict[str, int]:
    tier_numbers = (
        df_source["CASSANDRA_Risk_Tier"]
        .astype(str)
        .str.extract(r"TIER\s+(\d)")[0]
    )
    if tier_numbers.isna().any():
        bad_rows = df_source.loc[tier_numbers.isna(), "Município"].head(5).tolist()
        raise ValueError(
            "Unable to derive numeric tier values for JS export. "
            f"Examples: {bad_rows}"
        )

    tier_export = {
        municipio: int(tier)
        for municipio, tier in zip(df_source["Município"].astype(str), tier_numbers.astype(int))
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "var TIER_DATA = " + json.dumps(tier_export, ensure_ascii=False) + ";",
        encoding="utf-8",
    )
    return tier_export


def validate_tier_data_sync(
    df_source: pd.DataFrame,
    output_path: str = "assets/tier_data.js",
    known_names: Optional[list[str]] = None,
) -> list[tuple[str, int, Optional[int]]]:
    expected = write_tier_data_js(df_source, output_path)
    raw = Path(output_path).read_text(encoding="utf-8").strip()
    actual = json.loads(raw.removeprefix("var TIER_DATA = ").removesuffix(";"))

    mismatches = []
    for municipio, expected_tier in expected.items():
        actual_tier = actual.get(municipio)
        if actual_tier != expected_tier:
            mismatches.append((municipio, expected_tier, actual_tier))

    if known_names:
        for municipio in known_names:
            print(
                f"   [TIER JS] {municipio}: CSV={expected.get(municipio)}  "
                f"JS={actual.get(municipio)}"
            )
    return mismatches


# ──────────────────────────────────────────────────────────────────────────────
# VISUALISATION HELPERS
# ──────────────────────────────────────────────────────────────────────────────

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


def annotate_outliers(ax, xs, ys, labels, color=ANNOT_COLOR, fontsize=7.5):
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


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 1 — DATA INTEGRATION
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 70)
print("  PHASE 1 — DATA INTEGRATION")
print("═" * 70)

# --- Load IEI metrics ---
if not pd.io.common.file_exists("metricas_iei_completo.csv"):
    print("[ERROR] metricas_iei_completo.csv not found. Aborting.")
    sys.exit(1)
df_iei = pd.read_csv("metricas_iei_completo.csv")
print(f"[IEI]  Loaded {len(df_iei)} rows from metricas_iei_completo.csv")
print(f"[IEI]  Available columns: {df_iei.columns.tolist()}")

# ── FASE 2 ENRICHMENT — optional merge (Total_Arquivo_Captures, Live_StatusCode) ──
if pd.io.common.file_exists(FASE2_CSV):
    df_fase2 = pd.read_csv(FASE2_CSV, encoding="utf-8-sig")
    _f2_mun_col = find_municipio_col(df_fase2)
    df_fase2 = impute_total_arquivo_captures(df_fase2, _f2_mun_col)
    df_fase2["_key"] = df_fase2[_f2_mun_col].apply(normalize_municipio)
    _enrich_cols = [c for c in df_fase2.columns if c not in [_f2_mun_col, "_key"]]
    print(f"[FASE2] Loaded {len(df_fase2)} rows from {FASE2_CSV} "
          f"— enrichment columns: {_enrich_cols}")
    # Drop _key from df_fase2 before merge to avoid duplicate _key in df_iei
    df_fase2 = df_fase2.drop(columns=["_key"])
    df_fase2["_key"] = df_fase2[_f2_mun_col].apply(normalize_municipio)
    # Step 1 — Deduplicate: remove from df_fase2 any column already in df_iei (except join key '_key')
    cols_to_drop = [c for c in df_fase2.columns if c in df_iei.columns and c != "_key"]
    df_fase2 = df_fase2.drop(columns=cols_to_drop)
    # Step 2 — Recompute enrichment column list post-drop (excludes Município and _key)
    _enrich_cols = [c for c in df_fase2.columns if c not in [_f2_mun_col, "_key"]]
    # Left merge — df_iei is the LEFT frame, preserving all 308 IEI rows
    df_iei["_key"] = df_iei[find_municipio_col(df_iei)].apply(normalize_municipio)
    _merge_cols = ["_key"] + [c for c in df_fase2.columns if c not in [_f2_mun_col, "_key"]]
    df_iei = df_iei.merge(
        df_fase2[["_key"] + [c for c in df_fase2.columns if c not in [_f2_mun_col, "_key"]]],
        on="_key",
        how="left",
    )
    _n_matched_f2 = df_iei[_enrich_cols[0]].notna().sum() if _enrich_cols else 0
    print(f"[FASE2] Matched {_n_matched_f2}/308 municipalities")
else:
    print(
        f"[FASE2] ⚠  {FASE2_CSV} not found — "
        "Total_Arquivo_Captures and Live_StatusCode will use defaults. "
        "Run extrator_fase2_avancado.py to enrich."
    )

# ── Arquivo.pt temporal capture features ─────────────────────────────────────
if not pd.io.common.file_exists(ARQUIVO_TEMPORAL_CSV):
    print(f"[ERROR] {ARQUIVO_TEMPORAL_CSV} not found. Run scripts/arquivo_temporal.py first.")
    sys.exit(1)

df_temporal = pd.read_csv(ARQUIVO_TEMPORAL_CSV, encoding="utf-8-sig")
_temporal_mun_col = find_municipio_col(df_temporal)
_iei_mun_col = find_municipio_col(df_iei)
_missing_temporal_cols = [
    col for col in ARQUIVO_TEMPORAL_FEATURE_COLS if col not in df_temporal.columns
]
if _missing_temporal_cols:
    raise ValueError(f"Missing temporal feature columns: {_missing_temporal_cols}")

df_iei = df_iei.merge(
    df_temporal[[_temporal_mun_col] + ARQUIVO_TEMPORAL_FEATURE_COLS],
    left_on=_iei_mun_col,
    right_on=_temporal_mun_col,
    how="left",
)
if _temporal_mun_col != _iei_mun_col:
    df_iei = df_iei.drop(columns=[_temporal_mun_col])
print(f"[ARQUIVO] Loaded temporal features from {ARQUIVO_TEMPORAL_CSV}")

# --- Load demographic data (header on row index 1) ---
if not pd.io.common.file_exists("dados_demograficos.csv"):
    print("[ERROR] dados_demograficos.csv not found. Aborting.")
    sys.exit(1)
df_dem = pd.read_excel("dados_demograficos.csv", header=1)
print(f"[DEM]  Loaded {len(df_dem)} rows from dados_demograficos.csv")

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
# PHASE 2 — FEATURE ENGINEERING & TIER LABEL CREATION
# ──────────────────────────────────────────────────────────────────────────────
print("═" * 70)
print("  PHASE 2 — FEATURE ENGINEERING & TIER LABEL CREATION")
print("═" * 70)

# Locate feature columns dynamically (handles suffix variants from merge)
col_iei    = find_col(df, ["IEI_Score", "IEI Score", "IEI"])
col_var01  = find_col(df, ["Var% 2001", "Var 2001", "2001→2011", "2001-2011", "Var%_2001"])
col_env01  = find_col(df, ["Env. 2001", "Env_2001", "Envelhecimento 2001"])
col_pop11  = find_col(df, ["Pop. 2011", "Pop_2011", "Pop2011", "População 2011"])
col_pop21  = find_col(df, ["Pop. 2021", "Pop_2021", "Pop2021", "População 2021"])
col_decay  = find_col(df, ["Media_Dias_Entre_Capturas", "Média_Dias_Entre_Capturas"])
col_caps   = find_col(df, ["Total_Arquivo_Captures", "Total_Arquivo", "Arquivo_Captures"])
col_target = find_col(df, ["Var% 2011→2021", "Var% 2011", "2011→2021", "2011-2021", "Var%_2011"])

print(f"  IEI_Score     → '{col_iei}'")
print(f"  Var% 2001→11  → '{col_var01}'")
print(f"  Env. 2001     → '{col_env01}'")
print(f"  Pop. 2011     → '{col_pop11}'")
print(f"  Pop. 2021     → '{col_pop21}'")
print(f"  Decay metric  → '{col_decay}'")
print(f"  Captures      → '{col_caps}'")
print(f"  Target        → '{col_target}'")

# Coerce all to numeric
for col in [
    col_iei,
    col_var01,
    col_env01,
    col_pop11,
    col_pop21,
    col_target,
    col_decay,
    col_caps,
    *ARQUIVO_TEMPORAL_FEATURE_COLS,
]:
    df[col] = safe_float(df[col])

# Log-transform population (shift to avoid zero/negative)
pop_raw = df[col_pop11]
pop_min = pop_raw.min()
shift   = max(0, 1 - pop_min)          # ensures all values ≥ 1
df["log_pop_2011"] = np.log(pop_raw + shift)

# ── Additional engineered features requested before training ─────────────────
df["digital_decay_rate"] = df[col_decay]
df["capture_density"] = df[col_caps] / df[col_pop21].replace(0, np.nan)
df["iei_var_pop_interaction"] = df[col_iei] * df[col_target]
df["pop_loss_acceleration"] = df[col_target] - df[col_var01]
_coastal_keys = {normalize_municipio(municipio) for municipio in COASTAL_TOURISM_MUNICIPALITIES}
df["is_coastal"] = df["_key"].isin(_coastal_keys).astype(int)

# Build modelling dataframe
candidate_feature_cols = [
    col_iei,
    "digital_decay_rate",
    col_caps,
    "capture_density",
    "is_coastal",
    col_pop11,
    col_env01,
    col_var01,
    "iei_var_pop_interaction",
    "pop_loss_acceleration",
]
target_derived_feature_cols = {
    "iei_var_pop_interaction",
    "pop_loss_acceleration",
}
leakage_feature_cols = [
    col for col in candidate_feature_cols
    if col == col_target or col in target_derived_feature_cols
]
feature_cols = [
    col for col in candidate_feature_cols
    if col not in leakage_feature_cols
]
target_col   = col_target

# Find municipality name column for annotations
name_col = iei_mun_col if iei_mun_col in df.columns else dem_mun_col + "_dem"
if name_col not in df.columns:
    for suffix in ["_iei", "_dem", ""]:
        candidate = iei_mun_col + suffix
        if candidate in df.columns:
            name_col = candidate
            break

# Build df_model
_base_feature_cols = feature_cols
df_model = df[[name_col] + _base_feature_cols + [target_col]].copy()

# Carry over additional columns if available (for final CSV)
for extra_col in ["Total_Arquivo_Captures", "Live_StatusCode"]:
    for src_col in df.columns:
        if extra_col.lower() in src_col.lower() and extra_col not in df_model.columns:
            df_model[extra_col] = df[src_col].values
            break

df_model = df_model.dropna(subset=_base_feature_cols)   # keep rows with NaN target for tier logic

# ── Tier assignment ──────────────────────────────────────────────────────────
print("\n  Tier threshold audit:")
print(f"    Previous thresholds: {describe_thresholds(LEGACY_TIER_THRESHOLDS)}")
legacy_tiers = df_model[col_target].apply(
    lambda value: assign_tier_from_thresholds(value, LEGACY_TIER_THRESHOLDS)
)
print_tier_distribution("    Previous tier distribution:", legacy_tiers)
print(f"    Adjusted thresholds: {describe_thresholds(BALANCED_TIER_THRESHOLDS)}")
df_model["CASSANDRA_Risk_Tier"] = df_model[col_target].apply(
    lambda value: assign_tier_from_thresholds(value, BALANCED_TIER_THRESHOLDS)
)
print_tier_distribution("    Adjusted tier distribution:", df_model["CASSANDRA_Risk_Tier"])

n_final = len(df_model)
print(f"\nFull modelling sample: {n_final} municipalities (after dropping feature NaNs)")

print_tier_distribution("\n  Tier distribution (raw labels):", df_model["CASSANDRA_Risk_Tier"])

# ── Training split — exclude TIER - Indeterminado ────────────────────────────
df_train = df_model[df_model["CASSANDRA_Risk_Tier"] != "TIER - Indeterminado"].copy()
print(f"\n  Leakage audit removed target-derived features: {leakage_feature_cols}")
print(f"  feature_cols at training time: {feature_cols}")
X = df_train[feature_cols].values
y_raw = df_train["CASSANDRA_Risk_Tier"].values
names = df_train[name_col].values

# XGBoost ≥2.x requires integer-encoded targets — encode here, decode after predict
encoder = LabelEncoder()
y = encoder.fit_transform(y_raw)   # str → int

print(f"\n  Training sample (excl. Indeterminado): {len(df_train)}")
print(f"  Encoder classes: {encoder.classes_.tolist()}")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 3 — CLASSIFIER
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 70)
print("  PHASE 3 — CLASSIFIER")
print("═" * 70)

try:
    import xgboost as xgb
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.05,
        subsample=0.8, min_child_weight=3, colsample_bytree=0.8,
        random_state=42, verbosity=0, eval_metric='mlogloss',
        use_label_encoder=False
    )
    model_name = "XGBClassifier"
except Exception as e:
    from sklearn.ensemble import RandomForestClassifier
    model = RandomForestClassifier(
        n_estimators=200, max_depth=4, random_state=42, n_jobs=-1
    )
    model_name = "RandomForestClassifier"

print(f"  Model selected: {model_name}")

# ── Initial split ──────────────────────────────────────────────────────────────
# feature_cols index reference:
#   0: col_iei  1: digital_decay_rate  2: col_caps  3-7: Arquivo temporal
#   8: capture_density  9: is_coastal  10: col_pop11  11: col_env01  12: col_var01
X_train, X_test, y_train, y_test, names_train, names_test = train_test_split(
    X, y, names, test_size=0.2, random_state=42, stratify=y
)

# ── Balanced sample weights for global training step ─────────────────────────
_sample_weights_train = compute_sample_weight(class_weight='balanced', y=y_train)
model.fit(X_train, y_train, sample_weight=_sample_weights_train)

# ── Post-training classification report (for tier-by-tier F1 comparison) ─────
print("\n" + "▓" * 70)
print("  ▓  Classification Report (train set — post sample_weight rebalancing):")
_report_train = classification_report(
    encoder.inverse_transform(y_train),
    encoder.inverse_transform(model.predict(X_train)),
    zero_division=0
)
for _line in _report_train.splitlines():
    print(f"  ▓    {_line}")
print("▓" * 70 + "\n")
y_pred_test_enc = model.predict(X_test)

# Decode integer predictions back to original string labels
y_pred_test = encoder.inverse_transform(y_pred_test_enc)
y_test_str   = encoder.inverse_transform(y_test)

# ── Evaluation ───────────────────────────────────────────────────────────────
acc = accuracy_score(y_test_str, y_pred_test)
metric_labels = [
    tier for tier in TIER_ORDER
    if tier != "TIER - Indeterminado" and tier in encoder.classes_
]
report = classification_report(
    y_test_str, y_pred_test, labels=metric_labels, zero_division=0
)
report_dict = classification_report(
    y_test_str, y_pred_test, labels=metric_labels, output_dict=True, zero_division=0
)
metrics_cm = confusion_matrix(y_test_str, y_pred_test, labels=metric_labels)
metrics_payload = {
    "accuracy": float(acc),
    "f1_macro": float(report_dict["macro avg"]["f1-score"]),
    "f1_per_tier": {
        TIER_SHORT_LABELS[tier]: float(report_dict.get(tier, {}).get("f1-score", 0.0))
        for tier in reversed(metric_labels)
    },
    "confusion_matrix": metrics_cm.astype(int).tolist(),
}
reports_dir = Path("reports")
reports_dir.mkdir(exist_ok=True)
(reports_dir / "model_metrics.json").write_text(
    json.dumps(metrics_payload, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("\n" + "▓" * 70)
print(f"  ▓  Model         : {model_name}")
print(f"  ▓  Train size    : {len(X_train)}   |   Test size: {len(X_test)}")
print(f"  ▓  Accuracy      : {acc * 100:.2f}%")
print("  ▓")
print("  ▓  Classification Report:")
for line in report.splitlines():
    print(f"  ▓    {line}")
print("  ▓")
print("  ▓  Metrics saved: reports/model_metrics.json")
print("▓" * 70 + "\n")

# ── Feature importances ───────────────────────────────────────────────────────
if hasattr(model, "feature_importances_"):
    importances = model.feature_importances_
    feat_labels = feature_cols
    ranked = sorted(zip(feat_labels, importances), key=lambda x: x[1], reverse=True)
    print("  Feature Importances (ranked):")
    for rank, (feat, imp) in enumerate(ranked, 1):
        print(f"    {rank}. {feat:40s}  {imp:.4f}")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 3B — SPATIAL CROSS-VALIDATION (GroupKFold, k=5)
# ──────────────────────────────────────────────────────────────────────────────
from sklearn.metrics import f1_score, precision_score, recall_score

print("\n" + "═" * 70)
print("  CASSANDRA ENGINE — SPATIAL CROSS-VALIDATION (GroupKFold, k=5)")
print(f"  Grouping variable : Distrito (18 regiões PT)")
print(f"  Folds             : 5  |  Municipalities: 308")
print("─" * 70)

# ── Build CV sample (exclude TIER - Indeterminado, same as main training) ────
_cv_df = df_model[df_model["CASSANDRA_Risk_Tier"] != "TIER - Indeterminado"].copy()

# Map each municipality to its Distrito
_cv_df["Distrito"] = _cv_df[name_col].map(DISTRITO_MAP).fillna("Desconhecido")

# Remove rows that could not be mapped (edge case)
_cv_df = _cv_df[_cv_df["Distrito"] != "Desconhecido"].copy()

_n_groups = _cv_df["Distrito"].nunique()
if _n_groups < 2:
    print("  ⚠  WARNING: fewer than 2 Distrito groups found — skipping CV block.")
    print("═" * 70 + "\n")
else:
    _X_cv     = _cv_df[feature_cols].values.copy()
    _y_cv_raw = _cv_df["CASSANDRA_Risk_Tier"].values
    _groups   = _cv_df["Distrito"].values

    _gkf = GroupKFold(n_splits=5)

    _fold_accuracies  = []
    _fold_f1w         = []
    _fold_precw       = []
    _fold_recw        = []

    for _fold_idx, (_tr_idx, _te_idx) in enumerate(
        _gkf.split(_X_cv, _y_cv_raw, groups=_groups), start=1
    ):
        _X_fold_tr, _X_fold_te = _X_cv[_tr_idx].copy(), _X_cv[_te_idx].copy()
        _y_fold_tr_raw         = _y_cv_raw[_tr_idx]
        _y_fold_te_raw         = _y_cv_raw[_te_idx]
        _test_distritos        = sorted(set(_groups[_te_idx]))

        # ── Refit a LOCAL LabelEncoder on fold training labels only ──────────
        _fold_encoder = LabelEncoder()
        _y_fold_tr    = _fold_encoder.fit_transform(_y_fold_tr_raw)

        # Map test labels through fold encoder; skip fold if unseen label
        _unseen = set(_y_fold_te_raw) - set(_fold_encoder.classes_)
        if _unseen:
            print(f"  ⚠  Fold {_fold_idx}: unseen classes {_unseen} — fold skipped.")
            continue
        _y_fold_te = _fold_encoder.transform(_y_fold_te_raw)

        # ── Instantiate and train a fold-local copy of the model ─────────────
        try:
            import xgboost as xgb
            _fold_model = xgb.XGBClassifier(
                n_estimators=200, max_depth=3, learning_rate=0.05,
                subsample=0.8, min_child_weight=3, colsample_bytree=0.8,
                random_state=42, verbosity=0, eval_metric="mlogloss",
                use_label_encoder=False,
            )
        except Exception:
            from sklearn.ensemble import RandomForestClassifier as _RFC
            _fold_model = _RFC(n_estimators=200, max_depth=4, random_state=42, n_jobs=-1)

        # ── Per-fold balanced sample weights (computed only on this fold's y_train) ──
        _fold_sample_weights = compute_sample_weight(class_weight='balanced', y=_y_fold_tr)
        _fold_model.fit(_X_fold_tr, _y_fold_tr, sample_weight=_fold_sample_weights)
        _y_fold_pred_enc = _fold_model.predict(_X_fold_te)

        # Decode back to string labels using fold encoder
        _y_fold_pred_str = _fold_encoder.inverse_transform(_y_fold_pred_enc)
        _y_fold_te_str   = _fold_encoder.inverse_transform(_y_fold_te)

        # ── Per-fold metrics ─────────────────────────────────────────────────
        _acc_f   = accuracy_score(_y_fold_te_str, _y_fold_pred_str)
        _f1w_f   = f1_score(_y_fold_te_str, _y_fold_pred_str, average="weighted", zero_division=0)
        _precw_f = precision_score(_y_fold_te_str, _y_fold_pred_str, average="weighted", zero_division=0)
        _recw_f  = recall_score(_y_fold_te_str, _y_fold_pred_str, average="weighted", zero_division=0)

        _fold_accuracies.append(_acc_f)
        _fold_f1w.append(_f1w_f)
        _fold_precw.append(_precw_f)
        _fold_recw.append(_recw_f)

        _distritos_str = ", ".join(_test_distritos)
        print(
            f"  Fold {_fold_idx}  Test distritos: [{_distritos_str}]\n"
            f"         Accuracy: {_acc_f:.4f}  F1w: {_f1w_f:.4f}  "
            f"Prec: {_precw_f:.4f}  Rec: {_recw_f:.4f}"
        )

    if _fold_accuracies:
        print("─" * 70)
        print("  AGGREGATE RESULTS")
        print(f"  Accuracy   : {np.mean(_fold_accuracies):.4f} ± {np.std(_fold_accuracies):.4f}")
        print(f"  F1 (wtd)   : {np.mean(_fold_f1w):.4f} ± {np.std(_fold_f1w):.4f}")
        print(f"  Precision  : {np.mean(_fold_precw):.4f} ± {np.std(_fold_precw):.4f}")
        print(f"  Recall     : {np.mean(_fold_recw):.4f} ± {np.std(_fold_recw):.4f}")
    else:
        print("  ⚠  No valid folds completed — check class distribution per Distrito.")

print("═" * 70 + "\n")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 4 — PROBABILITY EXTRACTION & RISK SCORE
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 70)
print("  PHASE 4 — PROBABILITY EXTRACTION & RISK SCORE")
print("═" * 70)

if not hasattr(model, "predict_proba"):
    raise AttributeError(
        f"Model '{model_name}' does not support predict_proba(). "
        "Switch to a probabilistic classifier (RandomForestClassifier or XGBClassifier)."
    )

TIER4_LABEL = "TIER 4 - Profecia CASSANDRA"
try:
    # Use encoder.classes_ (the string→int mapping) NOT model.classes_ (ints)
    tier4_idx = encoder.classes_.tolist().index(TIER4_LABEL)
except ValueError:
    raise ValueError(
        f"'{TIER4_LABEL}' not found in encoder.classes_. "
        f"Actual classes: {encoder.classes_.tolist()}"
    )

# Generate predictions for ALL municipalities (including Indeterminado)
X_all = df_model[feature_cols].values
df_model["CASSANDRA_Risk_Tier"] = encoder.inverse_transform(model.predict(X_all))
probas = model.predict_proba(X_all)
df_model["CASSANDRA_Risk_Score"] = [
    round(float(p[tier4_idx]) * 100, 1) for p in probas
]

print(f"  ✔  Predictions generated for all {len(df_model)} municipalities")
print(f"  ✔  Risk Score range: min={df_model['CASSANDRA_Risk_Score'].min():.1f}  "
      f"max={df_model['CASSANDRA_Risk_Score'].max():.1f}  "
      f"mean={df_model['CASSANDRA_Risk_Score'].mean():.1f}")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 4 — VISUALISATION
# ──────────────────────────────────────────────────────────────────────────────

# ── PLOT A — Correlation: IEI_Score vs CASSANDRA_Risk_Score ─────────────────
print("\n" + "═" * 70)
print("  PHASE 4A — Generating plot_correlacao.png")
print("═" * 70)

fig_a, ax_a = plt.subplots(figsize=(12, 7))
apply_dark_theme(ax_a, fig_a)

for tier in TIER_ORDER:
    mask = df_model["CASSANDRA_Risk_Tier"] == tier
    if mask.sum() == 0:
        continue
    color = TIER_PALETTE.get(tier, "#AAAAAA")
    ax_a.scatter(
        df_model.loc[mask, col_iei],
        df_model.loc[mask, "CASSANDRA_Risk_Score"],
        c=color, alpha=0.75, s=55, edgecolors="none", zorder=3, label=tier
    )

# Regression trendline
x_all_vals = df_model[col_iei].values
y_score_vals = df_model["CASSANDRA_Risk_Score"].values
valid_mask = ~(np.isnan(x_all_vals) | np.isnan(y_score_vals))
slope, intercept, r_val, p_val, _ = stats.linregress(x_all_vals[valid_mask], y_score_vals[valid_mask])
x_line = np.linspace(x_all_vals[valid_mask].min(), x_all_vals[valid_mask].max(), 300)
y_line = slope * x_line + intercept
ax_a.plot(x_line, y_line, color=TREND_COLOR, linestyle="--", linewidth=1.5,
          alpha=0.8, label=f"Tendência  r={r_val:.3f}", zorder=4)

# Outlier annotations: highest risk score among TIER 4
df_ann = pd.DataFrame({
    "x": x_all_vals,
    "y": y_score_vals,
    "name": df_model[name_col].values
})
top_risk = df_ann.nlargest(5, "y")
annotate_outliers(ax_a, top_risk["x"], top_risk["y"], top_risk["name"], color="#FF3366")
ax_a.scatter(top_risk["x"], top_risk["y"], c="#FF3366", s=85, zorder=5,
             edgecolors="#FFFFFF", linewidths=0.6)

ax_a.set_xlabel("IEI Score  (Índice de Envelhecimento Digital)", fontsize=11)
ax_a.set_ylabel("CASSANDRA Risk Score  (0 – 100)", fontsize=11)
ax_a.set_title(
    "CASSANDRA — Sinal Digital vs Probabilidade de Profecia",
    fontsize=14, fontweight="bold", pad=14,
)
ax_a.legend(facecolor="#253A5E", labelcolor=ANNOT_COLOR, fontsize=8,
            edgecolor="#3A4F78", loc="upper left")
add_watermark(ax_a)

txt = (
    f"r = {r_val:.3f}\n"
    f"R² = {r_val**2:.3f}\n"
    f"n = {len(df_model)}"
)
props = dict(boxstyle="round,pad=0.5", facecolor="#253A5E",
             edgecolor="#3A4F78", alpha=0.9)
ax_a.text(0.03, 0.97, txt, transform=ax_a.transAxes, fontsize=9,
          verticalalignment="top", color=ANNOT_COLOR, bbox=props)

fig_a.tight_layout()
fig_a.savefig("plot_correlacao.png", dpi=300, bbox_inches="tight", facecolor=BG_COLOR)
plt.close(fig_a)
print("  ✔  Saved: plot_correlacao.png")

# ── PLOT B — Confusion Matrix ─────────────────────────────────────────────────
print("\n  PHASE 4B — Generating plot_validacao.png")

# Use only the training-eligible rows (no Indeterminado) for the confusion matrix
# y_test and y_pred_test are already decoded string labels at this point
y_test_labels = y_test_str
y_pred_labels = y_pred_test

# Keep the same class order used by reports/model_metrics.json.
classes_in_test = metric_labels

fig_b, ax_b = plt.subplots(figsize=(10, 8))
apply_dark_theme(ax_b, fig_b)

cm = metrics_cm
disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=classes_in_test)
disp.plot(
    ax=ax_b,
    cmap="Blues",
    colorbar=False,
    xticks_rotation=30,
)

# Style the confusion matrix to match CASSANDRA dark theme
ax_b.set_facecolor(BG_COLOR)
fig_b.patch.set_facecolor(BG_COLOR)
ax_b.tick_params(colors=ANNOT_COLOR, labelsize=8)
ax_b.xaxis.label.set_color(ANNOT_COLOR)
ax_b.yaxis.label.set_color(ANNOT_COLOR)
ax_b.title.set_color(ANNOT_COLOR)
for spine in ax_b.spines.values():
    spine.set_edgecolor("#3A4F78")
for text in ax_b.texts:
    text.set_color(ANNOT_COLOR)
    text.set_fontsize(10)
if disp.im_:
    disp.im_.set_clim(0, cm.max())

ax_b.set_title(
    f"CASSANDRA — Matriz de Confusão  |  Accuracy: {acc*100:.1f}%",
    fontsize=13, fontweight="bold", pad=14, color=ANNOT_COLOR,
)
add_watermark(ax_b)

# Short tier labels for x-axis readability
short_labels = [t.replace("TIER 4 - ", "T4\n").replace("TIER 3 - ", "T3\n")
                 .replace("TIER 2 - ", "T2\n").replace("TIER 1 - ", "T1\n") for t in classes_in_test]
ax_b.set_xticklabels(short_labels, rotation=30, ha="right", color=ANNOT_COLOR, fontsize=8)
ax_b.set_yticklabels(short_labels, rotation=0, color=ANNOT_COLOR, fontsize=8)

fig_b.tight_layout()
fig_b.savefig("plot_validacao.png", dpi=300, bbox_inches="tight", facecolor=BG_COLOR)
plt.close(fig_b)
print("  ✔  Saved: plot_validacao.png")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 4C — SHAP EXPLAINABILITY
# ──────────────────────────────────────────────────────────────────────────────
if SHAP_AVAILABLE:
    print("\n" + "═" * 70)
    print("  PHASE 4C — Generating shap_summary_cassandra.png")
    print("═" * 70)

    import matplotlib
    if matplotlib.get_backend() != "Agg":
        matplotlib.use("Agg")

    # ── Explainer & SHAP values ───────────────────────────────────────────────
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_test)

    # For multiclass XGBoost shap_values has shape (n_samples, n_features, n_classes)
    # Extract the slice corresponding to TIER 4 - Profecia CASSANDRA
    TIER4_LABEL = "TIER 4 - Profecia CASSANDRA"
    tier4_class_idx = encoder.classes_.tolist().index(TIER4_LABEL)
    shap_vals_tier4 = shap_values[:, :, tier4_class_idx]

    feat_names = feature_cols  # already a list of column name strings

    # ── Figure scaffold ───────────────────────────────────────────────────────
    fig_shap, ax_shap = plt.subplots(figsize=(12, 7))
    fig_shap.patch.set_facecolor(BG_COLOR)
    ax_shap.set_facecolor(BG_COLOR)

    # ── Beeswarm summary plot ─────────────────────────────────────────────────
    shap.summary_plot(
        shap_vals_tier4,
        X_test,
        feature_names=feat_names,
        plot_type="dot",       # beeswarm: shows direction + magnitude
        show=False,
        plot_size=None,        # suppress shap auto-sizing; we control the figure
        color_bar=True,
    )

    # ── Dark-theme styling (mirrors apply_dark_theme) ─────────────────────────
    for spine in ax_shap.spines.values():
        spine.set_edgecolor("#3A4F78")
    ax_shap.tick_params(colors=ANNOT_COLOR, labelsize=9)
    ax_shap.xaxis.label.set_color(ANNOT_COLOR)
    ax_shap.yaxis.label.set_color(ANNOT_COLOR)
    ax_shap.title.set_color(ANNOT_COLOR)
    ax_shap.grid(True, color="#253A5E", linewidth=0.5, linestyle="--", alpha=0.6)

    # ── Title & watermark ─────────────────────────────────────────────────────
    ax_shap.set_title(
        "CASSANDRA — SHAP Feature Impact  |  TIER 4: Profecia CASSANDRA",
        fontsize=13, fontweight="bold", color=ANNOT_COLOR, pad=14,
    )
    add_watermark(ax_shap)

    # ── Save ──────────────────────────────────────────────────────────────────
    fig_shap.savefig(
        "shap_summary_cassandra.png", dpi=300,
        bbox_inches="tight", facecolor=BG_COLOR,
    )
    plt.close(fig_shap)
    print("  ✔  Saved: shap_summary_cassandra.png")
else:
    print("  ⚠  shap not installed — skipping SHAP plot. Run: pip install shap")

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 5 — CSV EXPORT
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 70)
print("  PHASE 5 — CSV EXPORT")
print("═" * 70)

# Build Var_Pop from col_target
df_model["Var_Pop"] = df_model[col_target]

# ── Optional column recovery ──────────────────────────────────────────────────
# For each required metadata column, check df_model first; if absent, attempt
# to locate the source in df (the post-merge frame, which may carry suffix
# variants like '_iei' / '_dem' from the merge operation); fill typed default
# if not found anywhere.

_OPTIONAL = {
    "Total_Arquivo_Captures": {
        "candidates": ["Total_Arquivo_Captures", "Total_Arquivo", "Arquivo_Captures"],
        "default":    np.nan,     # zero means unknown capture data, not a true value
    },
    "Live_StatusCode": {
        "candidates": ["Live_StatusCode", "StatusCode", "Live_Status"],
        "default":    "N/D",      # string — matches frontend expectation
    },
}

for col_name, spec in _OPTIONAL.items():
    if col_name in df_model.columns:
        print(f"   [OPT] '{col_name}' already in df_model — keeping as-is")
    else:
        try:
            found_col = find_col(df, spec["candidates"])
            df_model[col_name] = df[found_col].values
            print(f"   [OPT] '{col_name}' recovered from df['{found_col}']")
        except KeyError:
            df_model[col_name] = spec["default"]
            print(f"   [OPT] '{col_name}' not found anywhere — filled with default: {spec['default']!r}")

# ── Build df_output with guaranteed column order ──────────────────────────────
df_output = (
    df_model[[
        name_col,
        "Var_Pop",
        col_iei,
        "Total_Arquivo_Captures",
        "Live_StatusCode",
        "CASSANDRA_Risk_Tier",
        "CASSANDRA_Risk_Score",
    ]]
    .copy()
    .rename(columns={name_col: "Município", col_iei: "IEI_Score"})
)

# ── Pre-export validation ─────────────────────────────────────────────────────
REQUIRED_COLS = [
    "Município", "Var_Pop", "IEI_Score",
    "Total_Arquivo_Captures", "Live_StatusCode",
    "CASSANDRA_Risk_Tier", "CASSANDRA_Risk_Score",
]
missing = [c for c in REQUIRED_COLS if c not in df_output.columns]
if missing:
    raise RuntimeError(f"[PHASE 5] CSV export aborted — missing: {missing}")

# ── Export ────────────────────────────────────────────────────────────────────
df_output.to_csv(
    "relatorio_produto_cassandra.csv",
    index=False,
    encoding="utf-8-sig"   # CRITICAL: preserves Portuguese diacritics in Excel
)

tier_sync_mismatches = validate_tier_data_sync(
    df_output,
    "assets/tier_data.js",
    known_names=["Montemor-o-Velho", "Vila Nova de Poiares"],
)
if tier_sync_mismatches:
    examples = tier_sync_mismatches[:6]
    raise RuntimeError(
        "assets/tier_data.js is out of sync with relatorio_produto_cassandra.csv: "
        f"{examples}"
    )

n_rows, n_cols = df_output.shape
tier_dist = df_output["CASSANDRA_Risk_Tier"].value_counts()
total_out = len(df_output)

print(f"✔  Saved: relatorio_produto_cassandra.csv")
print(f"✔  Regenerated and verified: assets/tier_data.js")
print(f"   Rows: {n_rows}  |  Columns: {n_cols}")
print(f"   Columns exported: {df_output.columns.tolist()}")
print("   Tier distribution:")
for t in TIER_ORDER:
    c = tier_dist.get(t, 0)
    pct = 100 * c / total_out if total_out > 0 else 0.0
    print(f"     {t:45s} : {c}  ({pct:.1f}%)")

score_col = df_output["CASSANDRA_Risk_Score"]
print(f"   Risk Score range: min={score_col.min():.1f}  max={score_col.max():.1f}  mean={score_col.mean():.1f}")

# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "═" * 70)
print("  CASSANDRA — Pipeline completo. Outputs gerados:")
print("    • plot_correlacao.png")
print("    • plot_validacao.png")
if SHAP_AVAILABLE:
    print("    • shap_summary_cassandra.png")
print("    • relatorio_produto_cassandra.csv")
print(f"\n  Final stats  →  Accuracy: {acc*100:.2f}%  |  Model: {model_name}  |  n: {n_final}")
print("═" * 70 + "\n")
