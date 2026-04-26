from __future__ import annotations

import html
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(layout="wide", page_title="CASSANDRA Oracle", page_icon="👁️")


BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "relatorio_produto_cassandra.csv"
GEOJSON_PATH = BASE_DIR / "municipios.geojson"

REQUIRED_COLUMNS = [
    "Município",
    "Var_Pop",
    "IEI_Score",
    "Total_Arquivo_Captures",
    "Live_StatusCode",
    "CASSANDRA_Risk_Tier",
]

CORE_TIERS = [
    "TIER 4 - Profecia CASSANDRA",
    "TIER 3 - Risco de Fuga",
    "TIER 2 - Estagnação",
    "TIER 1 - Resiliência",
]

INDETERMINATE_TIER = "TIER - Indeterminado"
MAP_TIER_ORDER = CORE_TIERS + [INDETERMINATE_TIER]
MAP_TIER_COLORS = {
    "TIER 4 - Profecia CASSANDRA": "#FF3366",
    "TIER 3 - Risco de Fuga": "#FFAA00",
    "TIER 2 - Estagnação": "#FFEA00",
    "TIER 1 - Resiliência": "#00E5FF",
    "TIER - Indeterminado": "#555555",
}
PLOTLY_MAP_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": True,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
}

TIER_STYLE = {
    "TIER 4 - Profecia CASSANDRA": {
        "accent": "#FF3366",
        "soft": "rgba(255, 51, 102, 0.14)",
        "glow": "rgba(255, 51, 102, 0.22)",
        "label": "Profecia CASSANDRA",
    },
    "TIER 3 - Risco de Fuga": {
        "accent": "#FF9F1C",
        "soft": "rgba(255, 159, 28, 0.14)",
        "glow": "rgba(255, 159, 28, 0.20)",
        "label": "Risco de Fuga",
    },
    "TIER 2 - Estagnação": {
        "accent": "#FFD166",
        "soft": "rgba(255, 209, 102, 0.14)",
        "glow": "rgba(255, 209, 102, 0.18)",
        "label": "Estagnação",
    },
    "TIER 1 - Resiliência": {
        "accent": "#00E5FF",
        "soft": "rgba(0, 229, 255, 0.14)",
        "glow": "rgba(0, 229, 255, 0.20)",
        "label": "Resiliência",
    },
    "TIER - Indeterminado": {
        "accent": "#8A93A6",
        "soft": "rgba(138, 147, 166, 0.16)",
        "glow": "rgba(138, 147, 166, 0.18)",
        "label": "Indeterminado",
    },
}

DISPLAY_LABELS: dict[str, str] = {
    "CASSANDRA_Risk_Tier": "Nível de Ameaça",
    "Var_Pop": "Fuga Demográfica",
    "IEI_Score": "Saúde Digital (IEI)",
    "Live_StatusCode": "Estado Atual do Portal",
    "Total_Arquivo_Captures": "Pegada no Arquivo.pt",
    "Município": "Município",
}
DISPLAY_HELP: dict[str, str] = {
    "Var_Pop": "Variação populacional entre 2011 e 2021. Valores negativos indicam desertificação.",
    "IEI_Score": "Índice de 0 a 100 baseado no histórico de 20 anos de capturas. Valores baixos indicam abandono e letargia digital.",
    "Live_StatusCode": "Diagnóstico em tempo real. 'Dead' ou 'Timeout' significa que a autarquia está digitalmente incontactável.",
    "Total_Arquivo_Captures": "Volume total de preservação digital ao longo das décadas no Arquivo.pt.",
    "CASSANDRA_Risk_Tier": "Classificação final do Oracle Engine baseada na combinação dos sinais demográficos e digitais.",
}

# Name normalisation — ported from mapa_cassandra.py
MAPPING_DICT = {
    "aguiardabeira": "aguiar da beira",
    "alcacerdosal": "alcacer do sal",
    "alfandegadafe": "alfandega da fe",
    "alterdochao": "alter do chao",
    "angradoheroismo": "angra do heroismo",
    "arcosdevaldevez": "arcos de valdevez",
    "arrudadosvinhos": "arruda dos vinhos",
    "azores calheta": "azores calheta",
    "azores lagoa": "azores lagoa",
    "cabeceirasdebasto": "cabeceiras de basto",
    "caldasdarainha": "caldas da rainha",
    "calheta [r.a.a.]": "azores calheta",
    "calheta [r.a.m.]": "madeira calheta",
    "camaradelobos": "camara de lobos",
    "campomaior": "campo maior",
    "carrazedadeansiaes": "carrazeda de ansiaes",
    "carregaldosal": "carregal do sal",
    "castanheiradepera": "castanheira de pera",
    "castelobranco": "castelo branco",
    "castelodepaiva": "castelo de paiva",
    "castelodevide": "castelo de vide",
    "castrodaire": "castro daire",
    "castromarim": "castro marim",
    "castroverde": "castro verde",
    "celoricodabeira": "celorico da beira",
    "celoricodebasto": "celorico de basto",
    "faro lagoa": "faro lagoa",
    "ferreiradoalentejo": "ferreira do alentejo",
    "ferreiradozezere": "ferreira do zezere",
    "figueiradafoz": "figueira da foz",
    "figueiradecastelorodrigo": "figueira de castelo rodrigo",
    "figueirodosvinhos": "figueiro dos vinhos",
    "fornosdealgodres": "fornos de algodres",
    "freixodeespadaacinta": "freixo de espada a cinta",
    "lagoa": "faro lagoa",
    "lagoa [r.a.a.]": "azores lagoa",
    "lajesdasflores": "lajes das flores",
    "lajesdopico": "lajes do pico",
    "macedodecavaleiros": "macedo de cavaleiros",
    "madeira calheta": "madeira calheta",
    "marcodecanaveses": "marco de canaveses",
    "marinhagrande": "marinha grande",
    "mesaofrio": "mesao frio",
    "mirandadocorvo": "miranda do corvo",
    "mirandadodouro": "miranda do douro",
    "moimentadabeira": "moimenta da beira",
    "mondimdebasto": "mondim de basto",
    "oliveiradeazemeis": "oliveira de azemeis",
    "oliveiradefrades": "oliveira de frades",
    "oliveiradobairro": "oliveira do bairro",
    "oliveiradohospital": "oliveira do hospital",
    "pacosdeferreira": "pacos de ferreira",
    "pampilhosadaserra": "pampilhosa da serra",
    "paredesdecoura": "paredes de coura",
    "pedrogaogrande": "pedrogao grande",
    "penalvadocastelo": "penalva do castelo",
    "pesodaregua": "peso da regua",
    "pontadelgada": "ponta delgada",
    "pontadosol": "ponta do sol",
    "pontedabarca": "ponte da barca",
    "pontedelima": "ponte de lima",
    "pontedesor": "ponte de sor",
    "portodemos": "porto de mos",
    "portomoniz": "porto moniz",
    "portosanto": "porto santo",
    "povoadelanhoso": "povoa de lanhoso",
    "povoadevarzim": "povoa de varzim",
    "praiadavitoria": "praia da vitoria",
    "reguengosdemonsaraz": "reguengos de monsaraz",
    "ribeirabrava": "ribeira brava",
    "ribeiradepena": "ribeira de pena",
    "ribeiragrande": "ribeira grande",
    "riomaior": "rio maior",
    "salvaterrademagos": "salvaterra de magos",
    "santacombadao": "santa comba dao",
    "santacruz": "santa cruz",
    "santacruzdagraciosa": "santa cruz da graciosa",
    "santacruzdasflores": "santa cruz das flores",
    "santamariadafeira": "santa maria da feira",
    "santamartadepenaguiao": "santa marta de penaguiao",
    "santiagodocacem": "santiago do cacem",
    "santotirso": "santo tirso",
    "saobrasdealportel": "sao bras de alportel",
    "saojoaodamadeira": "sao joao da madeira",
    "saojoaodapesqueira": "sao joao da pesqueira",
    "saopedrodosul": "sao pedro do sul",
    "saoroquedopico": "sao roque do pico",
    "saovicente": "sao vicente",
    "severdovouga": "sever do vouga",
    "sobraldemonteagraco": "sobral de monte agraco",
    "terrasdebouro": "terras de bouro",
    "torredemoncorvo": "torre de moncorvo",
    "torresnovas": "torres novas",
    "torresvedras": "torres vedras",
    "valedecambra": "vale de cambra",
    "vendasnovas": "vendas novas",
    "vianadoalentejo": "viana do alentejo",
    "vianadocastelo": "viana do castelo",
    "vieiradominho": "vieira do minho",
    "vila da praia da vitoria": "praia da vitoria",
    "viladerei": "vila de rei",
    "viladobispo": "vila do bispo",
    "viladoconde": "vila do conde",
    "viladoporto": "vila do porto",
    "vilaflor": "vila flor",
    "vilafrancadexira": "vila franca de xira",
    "vilafrancadocampo": "vila franca do campo",
    "vilanovadabarquinha": "vila nova da barquinha",
    "vilanovadecerveira": "vila nova de cerveira",
    "vilanovadefamalicao": "vila nova de famalicao",
    "vilanovadefozcoa": "vila nova de foz coa",
    "vilanovadegaia": "vila nova de gaia",
    "vilanovadepaiva": "vila nova de paiva",
    "vilanovadepoiares": "vila nova de poiares",
    "vilapoucadeaguiar": "vila pouca de aguiar",
    "vilareal": "vila real",
    "vilarealdesantoantonio": "vila real de santo antonio",
    "vilavelhaderodao": "vila velha de rodao",
    "vilaverde": "vila verde",
    "vilavicosa": "vila vicosa",
}


def inject_css() -> None:
    st.markdown(
        """
        <style>
            :root {
                --bg-main: #07111f;
                --bg-panel: rgba(12, 22, 38, 0.88);
                --bg-panel-strong: rgba(9, 18, 31, 0.96);
                --line-soft: rgba(255, 255, 255, 0.08);
                --text-main: #ecf6ff;
                --text-soft: #9db0c7;
                --cyan: #00E5FF;
                --red: #FF3366;
                --amber: #FF9F1C;
                --yellow: #FFD166;
                --neutral: #8A93A6;
                --radius-xl: 24px;
                --radius-lg: 18px;
                --shadow-soft: 0 18px 45px rgba(0, 0, 0, 0.28);
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(0, 229, 255, 0.11), transparent 28%),
                    radial-gradient(circle at top right, rgba(255, 51, 102, 0.10), transparent 22%),
                    linear-gradient(180deg, #050d18 0%, #081322 100%);
                color: var(--text-main);
            }

            [data-testid="stSidebar"] {
                background:
                    linear-gradient(180deg, rgba(6, 14, 24, 0.98) 0%, rgba(7, 17, 31, 0.94) 100%);
                border-right: 1px solid rgba(255, 255, 255, 0.06);
            }

            [data-testid="stSidebar"] .block-container {
                padding-top: 1.2rem;
            }

            [data-testid="stSidebar"] [data-testid="stMetric"] {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 18px;
                padding: 0.35rem 0.7rem;
            }

            .brand-shell {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 0.8rem;
                padding: 1.1rem 0 1.4rem 0;
            }

            .brand-orb {
                width: 116px;
                height: 116px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 2.8rem;
                background:
                    radial-gradient(circle at 50% 42%, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0.02) 38%),
                    radial-gradient(circle at 50% 50%, rgba(0, 229, 255, 0.18), transparent 62%),
                    linear-gradient(180deg, rgba(16, 33, 56, 0.96), rgba(8, 17, 30, 0.96));
                border: 1px solid rgba(0, 229, 255, 0.35);
                box-shadow:
                    0 0 0 10px rgba(0, 229, 255, 0.05),
                    0 0 48px rgba(0, 229, 255, 0.24),
                    inset 0 0 32px rgba(0, 229, 255, 0.12);
                color: var(--text-main);
            }

            .brand-caption {
                color: var(--text-soft);
                text-transform: uppercase;
                letter-spacing: 0.24rem;
                font-size: 0.68rem;
            }

            .sidebar-title {
                font-size: 1.55rem;
                font-weight: 700;
                letter-spacing: 0.10rem;
                text-align: center;
                color: var(--text-main);
                margin: 0.2rem 0 1rem 0;
            }

            .about-card,
            .hero-card,
            .premium-panel,
            .status-card,
            .detail-card,
            .mini-indicator,
            .legend-bar {
                background: var(--bg-panel);
                border: 1px solid var(--line-soft);
                border-radius: var(--radius-xl);
                box-shadow: var(--shadow-soft);
            }

            .about-card {
                padding: 1rem 1rem 0.95rem 1rem;
                margin-bottom: 1rem;
            }

            .about-card h4,
            .section-title {
                margin: 0 0 0.55rem 0;
                color: var(--text-main);
                font-size: 0.95rem;
                font-weight: 700;
                letter-spacing: 0.03rem;
            }

            .about-card p,
            .hero-subtitle,
            .caption-note,
            .status-copy,
            .empty-copy {
                color: var(--text-soft);
                line-height: 1.6;
                font-size: 0.92rem;
                margin: 0;
            }

            .sidebar-divider {
                margin: 1rem 0 0.7rem 0;
                border-top: 1px solid rgba(255, 255, 255, 0.06);
            }

            .filter-block-label {
                color: var(--text-main);
                font-size: 0.78rem;
                font-weight: 700;
                letter-spacing: 0.08rem;
                text-transform: uppercase;
                margin-bottom: 0.55rem;
            }

            .filters-state {
                margin-top: 0.9rem;
                padding: 0.85rem 0.95rem;
                border-radius: 18px;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.06);
            }

            .filters-state strong {
                display: block;
                color: var(--text-main);
                font-size: 1.05rem;
            }

            .filters-state span {
                color: var(--text-soft);
                font-size: 0.82rem;
                text-transform: uppercase;
                letter-spacing: 0.06rem;
            }

            .hero-card {
                padding: 1.55rem 1.7rem 1.45rem 1.7rem;
                margin-bottom: 1.15rem;
                background:
                    radial-gradient(circle at right top, rgba(0, 229, 255, 0.10), transparent 24%),
                    linear-gradient(180deg, rgba(8, 18, 32, 0.96), rgba(9, 17, 31, 0.92));
            }

            .hero-kicker {
                color: var(--cyan);
                font-size: 0.74rem;
                text-transform: uppercase;
                letter-spacing: 0.18rem;
                margin-bottom: 0.55rem;
                font-weight: 700;
            }

            .hero-title {
                color: var(--text-main);
                font-size: clamp(1.8rem, 3vw, 2.75rem);
                font-weight: 800;
                line-height: 1.08;
                margin: 0 0 0.55rem 0;
            }

            .metric-card {
                border-radius: 22px;
                padding: 1.1rem 1.2rem 1rem 1.2rem;
                min-height: 162px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                box-shadow: var(--shadow-soft);
                position: relative;
                overflow: hidden;
            }

            .metric-card::before {
                content: "";
                position: absolute;
                inset: 0;
                background: linear-gradient(135deg, rgba(255, 255, 255, 0.08), transparent 42%);
                pointer-events: none;
            }

            .metric-kicker {
                color: rgba(255, 255, 255, 0.78);
                font-size: 0.74rem;
                text-transform: uppercase;
                letter-spacing: 0.12rem;
                font-weight: 700;
                margin-bottom: 0.7rem;
            }

            .metric-value {
                color: #ffffff;
                font-size: 2.4rem;
                font-weight: 800;
                line-height: 1;
                margin-bottom: 0.5rem;
            }

            .metric-title {
                color: var(--text-main);
                font-size: 1.02rem;
                font-weight: 700;
                margin-bottom: 0.45rem;
            }

            .metric-subtitle {
                color: rgba(236, 246, 255, 0.72);
                font-size: 0.88rem;
                line-height: 1.45;
            }

            .mini-indicator {
                padding: 0.95rem 1.05rem;
                margin: 0.75rem 0 1.15rem 0;
            }

            .mini-indicator strong {
                color: var(--text-main);
                font-size: 1rem;
            }

            .mini-indicator span {
                color: var(--text-soft);
                font-size: 0.9rem;
                margin-left: 0.35rem;
            }

            .premium-panel {
                padding: 1.2rem 1.25rem 1.15rem 1.25rem;
                height: 100%;
                background:
                    linear-gradient(180deg, rgba(11, 23, 39, 0.94), rgba(8, 17, 30, 0.92));
            }

            .panel-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 1rem;
                margin-bottom: 0.9rem;
            }

            .panel-header h3 {
                color: var(--text-main);
                margin: 0;
                font-size: 1.12rem;
                font-weight: 700;
            }

            .panel-pill {
                padding: 0.35rem 0.7rem;
                border-radius: 999px;
                background: rgba(0, 229, 255, 0.10);
                border: 1px solid rgba(0, 229, 255, 0.22);
                color: var(--cyan);
                font-size: 0.78rem;
                font-weight: 700;
                white-space: nowrap;
            }

            .caption-box {
                margin-top: 0.85rem;
                padding: 0.9rem 1rem;
                border-radius: 18px;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.06);
            }

            .status-card {
                padding: 1rem 1.05rem;
                margin: 0.25rem 0 0.75rem 0;
            }

            .status-card strong {
                display: block;
                color: var(--text-main);
                margin-bottom: 0.35rem;
                font-size: 1rem;
            }

            .status-card.warning {
                border-color: rgba(255, 209, 102, 0.18);
                background: linear-gradient(180deg, rgba(38, 28, 5, 0.55), rgba(22, 18, 7, 0.48));
            }

            .status-card.error {
                border-color: rgba(255, 51, 102, 0.22);
                background: linear-gradient(180deg, rgba(48, 7, 20, 0.62), rgba(26, 11, 18, 0.52));
            }

            .status-card.info {
                border-color: rgba(0, 229, 255, 0.18);
                background: linear-gradient(180deg, rgba(8, 27, 42, 0.72), rgba(8, 18, 31, 0.48));
            }

            .detail-card {
                padding: 1rem 1rem 0.95rem 1rem;
                margin-top: 0.85rem;
            }

            .detail-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 0.8rem;
                margin-top: 0.95rem;
            }

            .detail-item {
                padding: 0.85rem 0.9rem;
                border-radius: 16px;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.05);
            }

            .detail-item span {
                display: block;
                color: var(--text-soft);
                font-size: 0.76rem;
                text-transform: uppercase;
                letter-spacing: 0.06rem;
                margin-bottom: 0.35rem;
            }

            .detail-item strong {
                color: var(--text-main);
                font-size: 1rem;
                line-height: 1.35;
            }

            .tier-badge {
                display: inline-flex;
                align-items: center;
                gap: 0.45rem;
                padding: 0.45rem 0.8rem;
                border-radius: 999px;
                font-size: 0.84rem;
                font-weight: 700;
                margin-top: 0.25rem;
                border: 1px solid transparent;
            }

            .legend-bar {
                display: flex;
                flex-wrap: wrap;
                gap: 0.6rem;
                padding: 0.85rem 1rem;
                margin: 0.45rem 0 0.95rem 0;
            }

            .legend-chip {
                display: inline-flex;
                align-items: center;
                gap: 0.45rem;
                padding: 0.42rem 0.72rem;
                border-radius: 999px;
                font-size: 0.8rem;
                color: var(--text-main);
                border: 1px solid rgba(255, 255, 255, 0.06);
                background: rgba(255, 255, 255, 0.03);
            }

            .legend-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                flex: 0 0 auto;
            }

            .empty-card {
                padding: 1rem 1.05rem;
                border-radius: 18px;
                border: 1px dashed rgba(255, 255, 255, 0.12);
                background: rgba(255, 255, 255, 0.02);
                margin-top: 0.85rem;
            }

            .empty-card strong {
                display: block;
                color: var(--text-main);
                margin-bottom: 0.35rem;
            }

            [data-testid="stDataFrame"] {
                border-radius: 22px;
                overflow: hidden;
                border: 1px solid rgba(255, 255, 255, 0.06);
                background: rgba(7, 15, 26, 0.85);
            }

            @media (max-width: 980px) {
                .detail-grid {
                    grid-template-columns: 1fr;
                }
            }

            /* KPI row glassmorphism upgrade */
            .metric-card {
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                border: 1px solid rgba(255, 255, 255, 0.09);
                box-shadow:
                    0 20px 48px rgba(0, 0, 0, 0.32),
                    inset 0 1px 0 rgba(255, 255, 255, 0.07);
            }

            /* Premium panel upgrade */
            .premium-panel {
                backdrop-filter: blur(10px);
                -webkit-backdrop-filter: blur(10px);
            }

            /* Typography refinements */
            .hero-title {
                background: linear-gradient(135deg, #ffffff 0%, #b0d4f1 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }

            /* Detail card glassmorphism upgrade */
            .detail-card {
                backdrop-filter: blur(14px);
                -webkit-backdrop-filter: blur(14px);
                background: linear-gradient(
                    135deg,
                    rgba(11, 26, 45, 0.92),
                    rgba(7, 15, 26, 0.88)
                );
                border: 1px solid rgba(255, 255, 255, 0.09);
                box-shadow:
                    0 24px 52px rgba(0, 0, 0, 0.36),
                    inset 0 1px 0 rgba(255, 255, 255, 0.06);
            }

            /* Detail grid — 1-column for breathing room */
            .detail-grid {
                grid-template-columns: 1fr;
            }

            /* Help text below each metric value */
            .detail-help {
                color: var(--text-soft);
                font-size: 0.74rem;
                line-height: 1.5;
                margin-top: 0.28rem;
                opacity: 0.85;
            }

            /* ── CHANGE 1 additions ── */
            @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap');

            html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif !important; }

            [data-testid="stToolbar"] { display: none !important; }
            [data-testid="stHeader"]  { display: none !important; }
            #MainMenu                  { display: none !important; }
            footer                     { display: none !important; }
            .block-container           { padding: 1.5rem 2rem 2rem 2rem !important; max-width: 100% !important; }

            .stApp { background: radial-gradient(ellipse at top left, #0d1117 0%, #060a0f 100%) !important; }

            .kpi-card {
                background: linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%);
                backdrop-filter: blur(10px);
                -webkit-backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 12px;
                padding: 1.4rem 1.6rem;
                transition: transform 0.2s ease, box-shadow 0.2s ease;
                margin-bottom: 0.5rem;
            }
            .kpi-card:hover {
                transform: translateY(-5px);
            }
            .kpi-card .kpi-value {
                font-size: 2.8rem;
                font-weight: 700;
                line-height: 1;
                margin-bottom: 0.3rem;
            }
            .kpi-card .kpi-label {
                font-size: 0.65rem;
                letter-spacing: 1.5px;
                text-transform: uppercase;
                opacity: 0.65;
                color: #ffffff;
            }
            .kpi-card .kpi-sub {
                font-size: 0.75rem;
                opacity: 0.45;
                margin-top: 0.2rem;
            }

            .cassandra-title {
                font-family: 'Space Grotesk', sans-serif;
                font-size: 2.2rem;
                font-weight: 700;
                letter-spacing: 3px;
                color: #ffffff;
                text-shadow: 0 0 20px rgba(0, 229, 255, 0.4), 0 0 60px rgba(0, 229, 255, 0.15);
                margin-bottom: 0.2rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def strip_accents(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def normalize_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    name = name.strip().lower()
    lookup_key = strip_accents(name)
    name = MAPPING_DICT.get(lookup_key, name)
    name = strip_accents(name.lower().strip())
    return re.sub(r"\s+", " ", name).strip()


def normalize_search_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.casefold().strip()


def normalize_municipality(value: Any) -> str:
    return normalize_name("" if value is None else str(value))


def validate_dataset(dataframe: pd.DataFrame) -> tuple[bool, str | None]:
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing_columns:
        formatted = ", ".join(missing_columns)
        return False, f"O CSV não contém as colunas obrigatórias: {formatted}."
    return True, None


@st.cache_data(show_spinner=False)
def load_risk_dataset(csv_path: str) -> tuple[pd.DataFrame | None, str | None]:
    path = Path(csv_path)
    if not path.exists():
        return None, f"Ficheiro não encontrado: {path.name}."

    try:
        dataframe = pd.read_csv(path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return None, "O CSV existe, mas está vazio."
    except pd.errors.ParserError:
        return None, "O CSV não pôde ser interpretado. Verifica se o artefacto final foi exportado corretamente."
    except UnicodeDecodeError:
        return None, "O CSV não pôde ser lido com codificação UTF-8."
    except Exception as exc:
        return None, f"Falha ao carregar o CSV: {exc}"

    is_valid, validation_error = validate_dataset(dataframe)
    if not is_valid:
        return None, validation_error

    prepared = dataframe.loc[:, REQUIRED_COLUMNS].copy()
    prepared["Município"] = prepared["Município"].astype(str).str.strip()
    prepared["Live_StatusCode"] = prepared["Live_StatusCode"].astype(str).str.strip()
    prepared["CASSANDRA_Risk_Tier"] = prepared["CASSANDRA_Risk_Tier"].astype(str).str.strip()
    prepared["Var_Pop"] = pd.to_numeric(prepared["Var_Pop"], errors="coerce")
    prepared["IEI_Score"] = pd.to_numeric(prepared["IEI_Score"], errors="coerce")
    prepared["Total_Arquivo_Captures"] = pd.to_numeric(
        prepared["Total_Arquivo_Captures"], errors="coerce"
    )
    prepared["__municipio_normalized"] = prepared["Município"].map(normalize_search_text)
    prepared["mun_key"] = prepared["Município"].map(normalize_municipality)

    return prepared, None


def detect_geojson_municipality_column(gdf: gpd.GeoDataFrame) -> str:
    if "NAME_2" in gdf.columns:
        return "NAME_2"

    candidate_columns: list[str] = []
    geometry_column = getattr(gdf.geometry, "name", "geometry")

    for column in gdf.columns:
        if column == geometry_column:
            continue
        try:
            normalized_values = gdf[column].astype(str).map(normalize_municipality)
        except Exception:
            continue
        if normalized_values.eq("lisboa").any():
            candidate_columns.append(column)

    if not candidate_columns:
        available_columns = ", ".join(
            str(column) for column in gdf.columns if column != geometry_column
        )
        raise ValueError(
            "Não foi possível detetar a coluna de município no GeoJSON. "
            f"Colunas disponíveis: {available_columns}."
        )

    return max(
        candidate_columns,
        key=lambda column: (
            gdf[column]
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .nunique(),
            str(column),
        ),
    )


@st.cache_data(show_spinner=False)
def load_geojson_map_contract(
    geojson_path: str,
) -> tuple[dict[str, Any] | None, str | None]:
    path = Path(geojson_path)
    if not path.exists():
        return None, f"Ficheiro não encontrado: {path.name}."

    try:
        gdf = gpd.read_file(path)
    except Exception as exc:
        return None, f"Falha ao carregar o GeoJSON: {exc}"

    if gdf.empty:
        return None, "O GeoJSON não contém geometrias utilizáveis."

    if gdf.crs is None:
        return None, "O GeoJSON não define CRS e não pode ser convertido com segurança para WGS84."

    try:
        gdf = gdf.to_crs(epsg=4326)
    except Exception as exc:
        return None, f"Não foi possível converter o GeoJSON para WGS84: {exc}"

    try:
        municipality_property = detect_geojson_municipality_column(gdf)
    except ValueError as exc:
        return None, str(exc)

    geometry_missing = gdf.geometry.isna()
    if geometry_missing.any():
        missing_count = int(geometry_missing.sum())
        return (
            None,
            "O GeoJSON contém geometrias ausentes e não pode ser usado no mapa: "
            f"{missing_count} registos sem geometria.",
        )

    name_counts = gdf[municipality_property].astype(str).str.strip().value_counts()

    try:
        gdf = gdf.copy()
        gdf["mun_key"] = gdf.apply(
            lambda row: normalize_municipality(
                f"{row['NAME_1']} {row[municipality_property]}"
                if name_counts.get(str(row[municipality_property]).strip(), 0) > 1
                and "NAME_1" in gdf.columns
                and str(row.get("NAME_1", "")).strip()
                else row[municipality_property]
            ),
            axis=1,
        )
    except Exception as exc:
        return None, f"Falha ao construir as chaves municipais do GeoJSON: {exc}"

    blank_keys = gdf["mun_key"].fillna("").eq("")
    if blank_keys.any():
        blank_names = (
            gdf.loc[blank_keys, municipality_property]
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .unique()
            .tolist()
        )
        return (
            None,
            "O GeoJSON contém municípios sem chave de reconciliação utilizável: "
            f"{summarize_names(blank_names)}.",
        )

    duplicate_keys = sorted(
        gdf.loc[gdf["mun_key"].duplicated(keep=False), municipality_property]
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )
    if duplicate_keys:
        return (
            None,
            "O GeoJSON contém chaves municipais duplicadas após reconciliação: "
            f"{summarize_names(duplicate_keys)}.",
        )

    try:
        gdf = gdf.set_index("mun_key")
    except Exception as exc:
        return None, f"Falha ao indexar o GeoJSON por município: {exc}"

    try:
        geojson_data = json.loads(gdf.to_json())
    except Exception as exc:
        return None, f"Falha ao converter o GeoJSON preparado para Plotly: {exc}"

    features = geojson_data.get("features", [])
    index_values = gdf.index.astype(str).tolist()
    if len(features) != len(index_values):
        return None, "O GeoJSON preparado não manteve uma correspondência estável entre índice e features."

    for feature, feature_id in zip(features, index_values):
        feature["id"] = str(feature_id)

    return {
        "geojson": geojson_data,
        "mun_keys": index_values,
        "municipality_property": municipality_property,
    }, None


def format_decimal(value: Any, decimals: int = 2, suffix: str = "") -> str:
    if pd.isna(value):
        return "—"
    formatted = f"{float(value):,.{decimals}f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted}{suffix}"


def format_integer(value: Any) -> str:
    if pd.isna(value):
        return "—"
    return f"{int(round(float(value))):,}".replace(",", ".")


def summarize_names(names: list[str], limit: int = 10) -> str:
    cleaned = sorted({str(name).strip() for name in names if str(name).strip()})
    if not cleaned:
        return "sem itens identificáveis"
    if len(cleaned) <= limit:
        return ", ".join(cleaned)
    remaining = len(cleaned) - limit
    return f"{', '.join(cleaned[:limit])} e mais {remaining}"


def get_unmatched_municipalities(
    dataframe: pd.DataFrame,
    geojson_keys: set[str],
) -> list[str]:
    if dataframe.empty:
        return []

    unmatched = dataframe.loc[~dataframe["mun_key"].isin(geojson_keys), "Município"]
    return sorted(unmatched.astype(str).str.strip().unique().tolist())


def prepare_map_dataframe(
    dataframe: pd.DataFrame,
    geojson_keys: set[str],
) -> tuple[pd.DataFrame, list[str]]:
    prepared = dataframe.copy()
    unmatched = sorted(
        prepared.loc[~prepared["mun_key"].isin(geojson_keys), "Município"]
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    matched = prepared.loc[prepared["mun_key"].isin(geojson_keys)].copy()
    if matched.empty:
        return matched, unmatched

    matched["mun_key"] = matched["mun_key"].astype(str)
    matched["__hover_municipio"] = matched["Município"].astype(str)
    matched["__hover_tier"] = matched["CASSANDRA_Risk_Tier"].astype(str)
    matched["__hover_var_pop"] = matched["Var_Pop"].map(
        lambda value: format_decimal(value, 2, "%")
    )
    matched["__hover_iei_score"] = matched["IEI_Score"].map(
        lambda value: format_decimal(value, 2)
    )
    matched["__hover_status_code"] = matched["Live_StatusCode"].astype(str)
    return matched, unmatched


def build_map_figure(
    dataframe: pd.DataFrame,
    geojson_contract: dict[str, Any],
):
    figure = px.choropleth_mapbox(
        dataframe,
        geojson=geojson_contract["geojson"],
        locations="mun_key",
        color="CASSANDRA_Risk_Tier",
        category_orders={"CASSANDRA_Risk_Tier": MAP_TIER_ORDER},
        color_discrete_map=MAP_TIER_COLORS,
        custom_data=[
            "__hover_municipio",
            "__hover_tier",
            "__hover_var_pop",
            "__hover_iei_score",
            "__hover_status_code",
        ],
        center={"lat": 39.5, "lon": -8.0},
        zoom=5.5,
        opacity=0.9,
    )

    # --- CASSANDRA MAP HOVER FIX: START ---
    figure.update_traces(
        marker_line_width=0.7,
        marker_line_color="rgba(236, 246, 255, 0.18)",
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Nível de Ameaça: %{customdata[1]}<br>"
            "Fuga Demográfica: %{customdata[2]}<br>"
            "Saúde Digital (IEI): %{customdata[3]}<br>"
            "Estado do Portal: %{customdata[4]}"
            "<extra></extra>"
        ),
    )
    # --- CASSANDRA MAP HOVER FIX: END ---

    figure.update_layout(
        mapbox_style="carto-darkmatter",
        mapbox_center={"lat": 39.5, "lon": -8.0},
        mapbox_zoom=5.5,
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        height=660,
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(0, 0, 0, 0)",
        font={"color": "#ECF6FF"},
        hoverlabel={
            "bgcolor": "rgba(7, 17, 31, 0.96)",
            "bordercolor": "rgba(0, 229, 255, 0.26)",
            "font": {"color": "#ECF6FF", "size": 13},
        },
        legend={
            "title": {"text": ""},
            "orientation": "v",
            "yanchor": "top",
            "y": 0.99,
            "xanchor": "left",
            "x": 0.01,
            "bgcolor": "rgba(7, 17, 31, 0.74)",
            "bordercolor": "rgba(255, 255, 255, 0.08)",
            "borderwidth": 1,
            "font": {"color": "#ECF6FF", "size": 12},
            "traceorder": "normal",
        },
        uirevision="cassandra-map",
    )
    return figure


def compute_kpis(dataframe: pd.DataFrame) -> dict[str, int]:
    counts = dataframe["CASSANDRA_Risk_Tier"].value_counts(dropna=False)
    metrics = {tier: int(counts.get(tier, 0)) for tier in CORE_TIERS}
    metrics[INDETERMINATE_TIER] = int(counts.get(INDETERMINATE_TIER, 0))
    return metrics


def apply_filters(
    dataframe: pd.DataFrame,
    selected_tiers: list[str],
    selected_status_codes: list[str],
) -> pd.DataFrame:
    filtered = dataframe.copy()
    if selected_tiers:
        filtered = filtered[filtered["CASSANDRA_Risk_Tier"].isin(selected_tiers)]
    if selected_status_codes:
        filtered = filtered[filtered["Live_StatusCode"].isin(selected_status_codes)]
    return filtered


def tier_visual(tier: str) -> dict[str, str]:
    return TIER_STYLE.get(tier, TIER_STYLE[INDETERMINATE_TIER])


def tier_badge_html(tier: str) -> str:
    visual = tier_visual(tier)
    return (
        f"<span class='tier-badge' "
        f"style='background:{visual['soft']}; border-color:{visual['glow']}; color:{visual['accent']};'>"
        f"{html.escape(tier)}</span>"
    )


def render_status_card(title: str, message: str, tone: str = "info") -> None:
    st.markdown(
        (
            f"<div class='status-card {tone}'>"
            f"<strong>{html.escape(title)}</strong>"
            f"<p class='status-copy'>{html.escape(message)}</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_brand_block() -> None:
    st.markdown(
        """
        <div class="brand-shell">
            <div class="brand-orb">👁</div>
            <div class="brand-caption">CASSANDRA ORACLE</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_about_text() -> str:
    return (
        "Painel de apoio à decisão para leitura territorial do risco municipal. "
        "A interface organiza o relatório final da CASSANDRA ao combinar sinais de declínio demográfico "
        "com sinais de saúde digital e letargia observados via Arquivo.pt, sem recomputar o pipeline."
    )


def sort_status_codes(values: list[str]) -> list[str]:
    def order_key(item: str) -> tuple[int, int | str]:
        return (0, int(item)) if item.isdigit() else (1, item)

    return sorted(values, key=order_key)


def render_sidebar(
    dataframe: pd.DataFrame | None,
    data_error: str | None,
) -> tuple[list[str], list[str]]:
    selected_tiers: list[str] = []
    selected_status_codes: list[str] = []

    with st.sidebar:
        render_brand_block()
        st.markdown("<div class='sidebar-title'>CASSANDRA ENGINE</div>", unsafe_allow_html=True)
        st.markdown(
            (
                "<div class='about-card'>"
                "<h4>Sobre</h4>"
                f"<p>{html.escape(sidebar_about_text())}</p>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        total_loaded = int(len(dataframe)) if dataframe is not None else 0
        st.metric("Municípios carregados", format_integer(total_loaded))

        st.markdown("<div class='sidebar-divider'></div>", unsafe_allow_html=True)
        st.markdown("<div class='filter-block-label'>Filtros</div>", unsafe_allow_html=True)

        if dataframe is None:
            render_status_card(
                "Dados indisponíveis",
                data_error or "O relatório final não está disponível nesta pasta.",
                tone="error",
            )
            return selected_tiers, selected_status_codes

        tier_options = [tier for tier in CORE_TIERS if tier in dataframe["CASSANDRA_Risk_Tier"].unique()]
        if INDETERMINATE_TIER in dataframe["CASSANDRA_Risk_Tier"].unique():
            tier_options.append(INDETERMINATE_TIER)

        status_options = sort_status_codes(
            [value for value in dataframe["Live_StatusCode"].dropna().astype(str).unique().tolist() if value]
        )

        selected_tiers = st.multiselect(
            "Filtrar por tier",
            options=tier_options,
            placeholder="Todos os tiers",
        )
        selected_status_codes = st.multiselect(
            "Filtrar por Estado do Portal",
            options=status_options,
            placeholder="Todos os estados",
        )

        filtered_count = len(apply_filters(dataframe, selected_tiers, selected_status_codes))
        if selected_tiers or selected_status_codes:
            st.markdown(
                (
                    "<div class='filters-state'>"
                    f"<span>Municípios carregados</span><strong>{format_integer(total_loaded)}</strong>"
                    f"<span>Municípios visíveis</span><strong>{format_integer(filtered_count)}</strong>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

    return selected_tiers, selected_status_codes


def render_header() -> None:
    st.markdown("""
<div style="padding: 1rem 0 1.5rem 0;">
    <div class="cassandra-title">&#x26A1; CASSANDRA ORACLE</div>
    <div style="font-size:0.8rem; letter-spacing:2px; text-transform:uppercase;
                opacity:0.4; color:#ffffff;">Engine de Intelig&#234;ncia Demogr&#225;fica &middot; Portugal</div>
</div>
""", unsafe_allow_html=True)


def render_metric_card(title: str, value: int, tier: str, total_visible: int) -> None:
    visual = tier_visual(tier)
    share = 0 if total_visible == 0 else (value / total_visible) * 100
    subtitle = f"{format_decimal(share, 1, '%')} dos municípios visíveis"
    st.markdown(
        (
            "<div class='metric-card' "
            f"style='background:linear-gradient(180deg, {visual['soft']}, rgba(7, 15, 26, 0.92)); "
            f"box-shadow: 0 16px 38px {visual['glow']};'>"
            f"<div class='metric-kicker' style='color:{visual['accent']};'>Risco Municipal</div>"
            f"<div class='metric-value'>{format_integer(value)}</div>"
            f"<div class='metric-title'>{html.escape(title)}</div>"
            f"<div class='metric-subtitle'>{html.escape(subtitle)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_kpi_row(kpis: dict[str, int], total_visible: int) -> None:
    columns = st.columns(4, gap="medium")
    for column, tier in zip(columns, CORE_TIERS):
        with column:
            render_metric_card(TIER_STYLE[tier]["label"], kpis.get(tier, 0), tier, total_visible)

    indeterminate_count = kpis.get(INDETERMINATE_TIER, 0)
    if indeterminate_count > 0:
        st.markdown(
            (
                "<div class='mini-indicator'>"
                f"<strong>{format_integer(indeterminate_count)}</strong>"
                "<span>municípios em TIER - Indeterminado continuam visíveis no total filtrado.</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )


def render_map_panel(
    filtered_dataframe: pd.DataFrame | None,
    full_dataframe: pd.DataFrame | None,
    geojson_contract: dict[str, Any] | None,
    geojson_error: str | None,
) -> None:
    st.markdown(
        """
        <div class="panel-header">
            <h3>Mapa de Risco</h3>
            <div class="panel-pill">Artefacto final</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if filtered_dataframe is None or full_dataframe is None:
        render_status_card(
            "Mapa indisponível",
            geojson_error or "O mapa interativo depende do relatório final carregado nesta pasta.",
            tone="warning",
        )
        return

    if geojson_contract is None:
        render_status_card(
            "Mapa indisponível",
            geojson_error or "O GeoJSON não está disponível nesta pasta.",
            tone="warning",
        )
        return

    duplicate_csv_keys = sorted(
        full_dataframe.loc[full_dataframe["mun_key"].duplicated(keep=False), "Município"]
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )
    if duplicate_csv_keys:
        render_status_card(
            "Mapa indisponível",
            "O CSV contém chaves municipais duplicadas após reconciliação: "
            f"{summarize_names(duplicate_csv_keys)}.",
            tone="warning",
        )
        return

    blank_csv_keys = sorted(
        full_dataframe.loc[full_dataframe["mun_key"].fillna("").eq(""), "Município"]
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )
    if blank_csv_keys:
        render_status_card(
            "Mapa indisponível",
            "O CSV contém municípios sem chave municipal utilizável: "
            f"{summarize_names(blank_csv_keys)}.",
            tone="warning",
        )
        return

    geojson_keys = set(geojson_contract["mun_keys"])
    unmatched_all = get_unmatched_municipalities(full_dataframe, geojson_keys)
    if unmatched_all:
        render_status_card(
            "Cobertura municipal incompleta",
            "Sem correspondência no GeoJSON após reconciliação: "
            f"{summarize_names(unmatched_all)}.",
            tone="warning",
        )

    if filtered_dataframe.empty:
        render_status_card(
            "Sem municípios visíveis",
            "Os filtros ativos eliminaram todos os registos. Ajusta os critérios para retomar a leitura espacial.",
            tone="warning",
        )
        return

    map_dataframe, unmatched_visible = prepare_map_dataframe(filtered_dataframe, geojson_keys)
    if unmatched_visible:
        render_status_card(
            "Alguns municípios visíveis ficaram fora do mapa",
            "Sem correspondência no GeoJSON após reconciliação: "
            f"{summarize_names(unmatched_visible)}.",
            tone="warning",
        )

    if map_dataframe.empty:
        render_status_card(
            "Mapa sem correspondências",
            "Nenhum município visível pôde ser associado ao GeoJSON local.",
            tone="warning",
        )
        return

    figure = build_map_figure(map_dataframe, geojson_contract)
    st.plotly_chart(
        figure,
        use_container_width=True,
        config=PLOTLY_MAP_CONFIG,
    )
    st.markdown(
        """
        <div class="caption-box">
            <p class="caption-note">
                Distribuição espacial do tier CASSANDRA por município, apresentada como suporte visual de leitura estratégica do relatório final.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def get_filtered_municipalities(dataframe: pd.DataFrame, search_query: str) -> list[str]:
    unique = (
        dataframe[["Município", "__municipio_normalized"]]
        .drop_duplicates(subset=["Município"])
        .sort_values("__municipio_normalized")
    )
    if not search_query.strip():
        return unique["Município"].tolist()

    normalized_query = normalize_search_text(search_query)
    matches = unique[unique["__municipio_normalized"].str.contains(normalized_query, na=False)]
    return matches["Município"].tolist()


def render_detail_card(row: pd.Series) -> None:
    municipality = html.escape(str(row["Município"]))
    risk_tier = str(row["CASSANDRA_Risk_Tier"])

    st.markdown(
        (
            "<div class='detail-card'>"
            "<div class='panel-header' style='margin-bottom:0.35rem;'>"
            "<h3>Ficha Municipal</h3>"
            "<div class='panel-pill'>Leitura individual</div>"
            "</div>"
            f"{tier_badge_html(risk_tier)}"
            "<div class='detail-grid'>"
            f"<div class='detail-item'>"
            f"<span>{html.escape(DISPLAY_LABELS['Município'])}</span>"
            f"<strong>{municipality}</strong>"
            f"</div>"
            f"<div class='detail-item'>"
            f"<span>{html.escape(DISPLAY_LABELS['Var_Pop'])}</span>"
            f"<strong>{html.escape(format_decimal(row['Var_Pop'], 2, '%'))}</strong>"
            f"<p class='detail-help'>{html.escape(DISPLAY_HELP['Var_Pop'])}</p>"
            f"</div>"
            f"<div class='detail-item'>"
            f"<span>{html.escape(DISPLAY_LABELS['IEI_Score'])}</span>"
            f"<strong>{html.escape(format_decimal(row['IEI_Score'], 2))}</strong>"
            f"<p class='detail-help'>{html.escape(DISPLAY_HELP['IEI_Score'])}</p>"
            f"</div>"
            f"<div class='detail-item'>"
            f"<span>{html.escape(DISPLAY_LABELS['Live_StatusCode'])}</span>"
            f"<strong>{html.escape(str(row['Live_StatusCode']))}</strong>"
            f"<p class='detail-help'>{html.escape(DISPLAY_HELP['Live_StatusCode'])}</p>"
            f"</div>"
            f"<div class='detail-item'>"
            f"<span>{html.escape(DISPLAY_LABELS['CASSANDRA_Risk_Tier'])}</span>"
            f"<strong>{html.escape(risk_tier)}</strong>"
            f"<p class='detail-help'>{html.escape(DISPLAY_HELP['CASSANDRA_Risk_Tier'])}</p>"
            f"</div>"
            f"<div class='detail-item'>"
            f"<span>{html.escape(DISPLAY_LABELS['Total_Arquivo_Captures'])}</span>"
            f"<strong>{html.escape(format_integer(row['Total_Arquivo_Captures']))}</strong>"
            f"<p class='detail-help'>{html.escape(DISPLAY_HELP['Total_Arquivo_Captures'])}</p>"
            f"</div>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_search_panel(filtered_dataframe: pd.DataFrame) -> None:
    st.markdown(
        """
        <div class="panel-header">
            <h3>Explorar Município</h3>
            <div class="panel-pill">Pesquisa sem acentos</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if filtered_dataframe.empty:
        render_status_card(
            "Sem municípios visíveis",
            "Os filtros ativos eliminaram todos os registos. Ajusta os critérios para retomar a exploração.",
            tone="warning",
        )
        return

    previous_selection = st.session_state.get("cassandra_selected_municipality", "")
    search_query = st.text_input(
        "Pesquisar município",
        placeholder="Ex.: Macao, Vila Vicosa, Sao Joao da Pesqueira",
        help="A pesquisa ignora acentos para facilitar a seleção.",
    )

    available_names = get_filtered_municipalities(filtered_dataframe, search_query)

    if previous_selection and previous_selection not in filtered_dataframe["Município"].tolist():
        render_status_card(
            "Seleção fora dos filtros",
            "O município previamente selecionado deixou de pertencer ao conjunto visível. Seleciona outro município ou ajusta os filtros.",
            tone="info",
        )

    if search_query and not available_names:
        st.markdown(
            """
            <div class="empty-card">
                <strong>Sem correspondências</strong>
                <p class="empty-copy">Não foram encontrados municípios com esse padrão dentro dos filtros ativos.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.session_state["cassandra_selected_municipality"] = ""
        return

    options = [""] + available_names
    default_value = previous_selection if previous_selection in options else ""
    selected = st.selectbox(
        "Selecionar município",
        options=options,
        index=options.index(default_value),
        format_func=lambda item: "Escolha um município visível" if item == "" else item,
    )
    st.session_state["cassandra_selected_municipality"] = selected

    if not selected:
        st.markdown(
            """
            <div class="empty-card">
                <strong>Leitura individual disponível</strong>
                <p class="empty-copy">Seleciona um município para abrir a ficha com os principais sinais do relatório final.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    selected_row = filtered_dataframe.loc[filtered_dataframe["Município"] == selected].iloc[0]
    render_detail_card(selected_row)


def style_oracle_row(row: pd.Series) -> list[str]:
    _tier_col = DISPLAY_LABELS["CASSANDRA_Risk_Tier"]
    tier = str(row.get(_tier_col, ""))
    visual = tier_visual(tier)
    background = visual["soft"]
    return [
        f"background-color: {background}; color: #eef6ff;"
        if column != _tier_col
        else ""
        for column in row.index
    ]


def style_tier_column(column: pd.Series) -> list[str]:
    styles: list[str] = []
    for tier in column:
        visual = tier_visual(str(tier))
        styles.append(
            f"background-color: {visual['soft']}; color: {visual['accent']}; "
            f"font-weight: 700; border-left: 4px solid {visual['accent']};"
        )
    return styles


def build_oracle_styler(dataframe: pd.DataFrame) -> pd.io.formats.style.Styler:
    display_df = dataframe.loc[:, REQUIRED_COLUMNS].copy()
    display_df = display_df.rename(columns=DISPLAY_LABELS)

    tier_col = DISPLAY_LABELS["CASSANDRA_Risk_Tier"]
    var_pop_col = DISPLAY_LABELS["Var_Pop"]
    iei_col = DISPLAY_LABELS["IEI_Score"]
    captures_col = DISPLAY_LABELS["Total_Arquivo_Captures"]

    styler = (
        display_df.style.apply(style_oracle_row, axis=1)
        .apply(style_tier_column, subset=[tier_col], axis=0)
        .format(
            {
                var_pop_col: lambda value: format_decimal(value, 2, "%"),
                iei_col: lambda value: format_decimal(value, 2),
                captures_col: lambda value: format_integer(value),
            }
        )
        .set_table_styles(
            [
                {
                    "selector": "th",
                    "props": [
                        ("background", "#0b1627"),
                        ("color", "#ecf6ff"),
                        ("border-bottom", "1px solid rgba(255,255,255,0.08)"),
                        ("font-size", "0.85rem"),
                        ("font-weight", "700"),
                        ("text-align", "left"),
                    ],
                },
                {
                    "selector": "td",
                    "props": [
                        ("border-bottom", "1px solid rgba(255,255,255,0.04)"),
                        ("font-size", "0.9rem"),
                    ],
                },
            ]
        )
    )
    return styler


def render_oracle_legend() -> None:
    chips = []
    for tier in CORE_TIERS + [INDETERMINATE_TIER]:
        visual = tier_visual(tier)
        chips.append(
            (
                "<span class='legend-chip'>"
                f"<span class='legend-dot' style='background:{visual['accent']};'></span>"
                f"{html.escape(tier)}"
                "</span>"
            )
        )
    st.markdown(
        f"<div class='legend-bar'>{''.join(chips)}</div>",
        unsafe_allow_html=True,
    )


def render_oracle_log(filtered_dataframe: pd.DataFrame) -> None:
    st.markdown(
        """
        <div class="panel-header" style="margin-top: 0.3rem;">
            <h3>Oracle Log</h3>
            <div class="panel-pill">Tabela filtrada</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_oracle_legend()

    styler = build_oracle_styler(filtered_dataframe)
    st.dataframe(styler, use_container_width=True, hide_index=True, height=520)


def render_data_error_state(
    data_error: str,
    geojson_contract: dict[str, Any] | None,
    geojson_error: str | None,
) -> None:
    render_status_card(
        "Relatório final indisponível",
        data_error,
        tone="error",
    )
    if geojson_contract is not None or geojson_error:
        st.markdown("<div style='margin-top:0.75rem;'></div>", unsafe_allow_html=True)
        render_map_panel(None, None, geojson_contract, geojson_error)


def main() -> None:
    inject_css()

    dataframe, data_error = load_risk_dataset(str(CSV_PATH))
    geojson_contract, geojson_error = load_geojson_map_contract(str(GEOJSON_PATH))
    selected_tiers, selected_status_codes = render_sidebar(dataframe, data_error)

    render_header()

    if dataframe is None:
        render_data_error_state(
            data_error or "Não foi possível carregar o relatório final.",
            geojson_contract,
            geojson_error,
        )
        return

    filtered_dataframe = apply_filters(dataframe, selected_tiers, selected_status_codes)
    kpis = compute_kpis(filtered_dataframe)

    # ── CHANGE 3: KPI Cards ──
    tier_config = [
        ("TIER 4 - Profecia CASSANDRA", "MUNICÍPIOS CRÍTICOS", "#FF3366"),
        ("TIER 3 - Risco de Fuga",      "AMEAÇA ELEVADA",      "#FFAA00"),
        ("TIER 2 - Estagnação",         "RISCO MODERADO",      "#FFEA00"),
        ("TIER 1 - Resiliência",        "CONTROLADOS",         "#00E5FF"),
    ]
    total = len(filtered_dataframe)
    kpi_cols = st.columns(4)
    for col, (tier_val, tier_label, tier_color) in zip(kpi_cols, tier_config):
        count = int((filtered_dataframe["CASSANDRA_Risk_Tier"] == tier_val).sum())
        pct   = (count / total * 100) if total > 0 else 0
        col.markdown(f"""
    <div class="kpi-card" style="border-top: 3px solid {tier_color};">
        <div class="kpi-value" style="color:{tier_color};
             text-shadow: 0 0 15px {tier_color}55;">{count}</div>
        <div class="kpi-label">{tier_label}</div>
        <div class="kpi-sub">{pct:.1f}% do total</div>
    </div>
    """, unsafe_allow_html=True)

    left_column, right_column = st.columns([2, 1], gap="large")

    with left_column:
        render_map_panel(filtered_dataframe, dataframe, geojson_contract, geojson_error)

    with right_column:
        render_search_panel(filtered_dataframe)

    render_oracle_log(filtered_dataframe)


if __name__ == "__main__":
    main()
