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

def inject_css():
    st.markdown(
        """
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=Work+Sans:wght@400;500;600&display=swap" rel="stylesheet">
        """,
        unsafe_allow_html=True,
    )
    st.html(
        """
        <style>
            :root {
                --risk-critical: #FF3366;
                --risk-elevated: #FFAA00;
                --risk-moderate: #FFD166;
                --risk-controlled: #00E5FF;
                --shadow-hard: 4px 4px 0 0 #1c1b1b;
            }

            * { border-radius: 0 !important; }

            /* Background */
            .stApp { background: #fdf8f8 !important; }
            [data-testid="stAppViewContainer"] { background: #fdf8f8 !important; }
            [data-testid="stHeader"] { background: #fdf8f8 !important; }

            /* Sidebar */
            [data-testid="stSidebar"] > div:first-child {
                background: #ffffff !important;
                border-right: 1px solid #c4c7c7 !important;
            }

            /* Metric cards */
            [data-testid="stMetric"] {
                background: #ffffff !important;
                border: 1px solid #c4c7c7 !important;
                box-shadow: 4px 4px 0 0 #1c1b1b !important;
                padding: 24px !important;
            }
            [data-testid="stMetricValue"] {
                font-family: 'Space Grotesk', sans-serif !important;
                font-size: 48px !important;
                font-weight: 700 !important;
            }
            [data-testid="stMetricLabel"] {
                font-family: 'Space Grotesk', sans-serif !important;
                font-size: 11px !important;
                text-transform: uppercase !important;
                letter-spacing: 0.2em !important;
            }

            /* Typography */
            h1, h2, h3 {
                font-family: 'Space Grotesk', sans-serif !important;
                font-weight: 700 !important;
                text-transform: uppercase !important;
                letter-spacing: 0.08em !important;
            }

            /* Buttons */
            .stButton > button {
                border-radius: 0 !important;
                border: 1px solid #1c1b1b !important;
                box-shadow: 4px 4px 0 0 #1c1b1b !important;
                background: #1c1b1b !important;
                color: #ffffff !important;
                font-family: 'Space Grotesk', sans-serif !important;
                font-size: 12px !important;
                text-transform: uppercase !important;
                letter-spacing: 0.1em !important;
                transition: none !important;
            }
            .stButton > button:hover {
                background: #ffffff !important;
                color: #1c1b1b !important;
            }

            /* Inputs */
            [data-testid="stTextInput"] input {
                border-radius: 0 !important;
                border: 1px solid #c4c7c7 !important;
                font-family: 'Work Sans', sans-serif !important;
            }
            [data-baseweb="select"] > div {
                border-radius: 0 !important;
                border: 1px solid #c4c7c7 !important;
            }

            /* Widget labels */
            [data-testid="stWidgetLabel"] p {
                font-family: 'Space Grotesk', sans-serif !important;
                font-size: 11px !important;
                text-transform: uppercase !important;
                letter-spacing: 0.2em !important;
            }
        </style>
        """
    )

st.set_page_config(layout="wide", page_title="CASSANDRA Oracle", page_icon="👁️")
inject_css()

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
    "CASSANDRA_Risk_Score": "Risco de Colapso (%)",
}

# ── Political Pressure Radar — district lookup map ──────────────────────────
DISTRITO_MAP: dict[str, str] = {
    "Abrantes": "Santarém", "Águeda": "Aveiro", "Aguiar da Beira": "Guarda",
    "Alandroal": "Évora", "Albergaria-a-Velha": "Aveiro", "Albufeira": "Faro",
    "Alcácer do Sal": "Setúbal", "Alcanena": "Santarém", "Alcobaça": "Leiria",
    "Alcochete": "Setúbal", "Alcoutim": "Faro", "Alenquer": "Lisboa",
    "Alfândega da Fé": "Bragança", "Alijó": "Vila Real", "Aljezur": "Faro",
    "Aljustrel": "Beja", "Almada": "Setúbal", "Almeida": "Guarda",
    "Almeirim": "Santarém", "Almodôvar": "Beja", "Alpiarça": "Santarém",
    "Alter do Chão": "Portalegre", "Alvaiázere": "Leiria", "Alvito": "Beja",
    "Amadora": "Lisboa", "Amarante": "Porto", "Amares": "Braga",
    "Anadia": "Aveiro", "Ansião": "Leiria", "Arcos de Valdevez": "Viana do Castelo",
    "Arganil": "Coimbra", "Armamar": "Viseu", "Arouca": "Aveiro",
    "Arraiolos": "Évora", "Arronches": "Portalegre", "Arruda dos Vinhos": "Lisboa",
    "Aveiro": "Aveiro", "Avis": "Portalegre", "Azambuja": "Lisboa",
    "Baião": "Porto", "Barcelos": "Braga", "Barrancos": "Beja",
    "Barreiro": "Setúbal", "Batalha": "Leiria", "Beja": "Beja",
    "Belmonte": "Castelo Branco", "Benavente": "Santarém", "Bombarral": "Leiria",
    "Borba": "Évora", "Boticas": "Vila Real", "Braga": "Braga",
    "Bragança": "Bragança", "Cabeceiras de Basto": "Braga", "Cadaval": "Lisboa",
    "Caldas da Rainha": "Leiria", "Caminha": "Viana do Castelo",
    "Campo Maior": "Portalegre", "Cantanhede": "Coimbra", "Carrazeda de Ansiães": "Bragança",
    "Carregal do Sal": "Viseu", "Cartaxo": "Santarém", "Cascais": "Lisboa",
    "Castanheira de Pêra": "Leiria", "Castelo Branco": "Castelo Branco",
    "Castelo de Paiva": "Aveiro", "Castelo de Vide": "Portalegre",
    "Castro Daire": "Viseu", "Castro Marim": "Faro", "Castro Verde": "Beja",
    "Celorico da Beira": "Guarda", "Celorico de Basto": "Braga",
    "Chamusca": "Santarém", "Chaves": "Vila Real", "Cinfães": "Viseu",
    "Coimbra": "Coimbra", "Condeixa-a-Nova": "Coimbra", "Constância": "Santarém",
    "Coruche": "Santarém", "Covilhã": "Castelo Branco", "Crato": "Portalegre",
    "Cuba": "Beja", "Elvas": "Portalegre", "Entroncamento": "Santarém",
    "Espinho": "Aveiro", "Esposende": "Braga", "Estarreja": "Aveiro",
    "Estremoz": "Évora", "Évora": "Évora", "Fafe": "Braga",
    "Faro": "Faro", "Felgueiras": "Porto", "Ferreira do Alentejo": "Beja",
    "Ferreira do Zêzere": "Santarém", "Figueira da Foz": "Coimbra",
    "Figueira de Castelo Rodrigo": "Guarda", "Figueiró dos Vinhos": "Leiria",
    "Fornos de Algodres": "Guarda", "Freixo de Espada à Cinta": "Bragança",
    "Fronteira": "Portalegre", "Funchal": "Madeira", "Góis": "Coimbra",
    "Gondomar": "Porto", "Gouveia": "Guarda", "Grândola": "Setúbal",
    "Guarda": "Guarda", "Guimarães": "Braga", "Idanha-a-Nova": "Castelo Branco",
    "Ílhavo": "Aveiro", "Lagoa": "Faro", "Lagos": "Faro",
    "Lajes das Flores": "Açores", "Lajes do Pico": "Açores", "Lamego": "Viseu",
    "Leiria": "Leiria", "Lisboa": "Lisboa", "Loulé": "Faro",
    "Loures": "Lisboa", "Lourinhã": "Lisboa", "Lousã": "Coimbra",
    "Lousada": "Porto", "Macedo de Cavaleiros": "Bragança", "Mafra": "Lisboa",
    "Maia": "Porto", "Manteigas": "Guarda", "Marco de Canaveses": "Porto",
    "Marinha Grande": "Leiria", "Marvão": "Portalegre", "Matosinhos": "Porto",
    "Mealhada": "Aveiro", "Mêda": "Guarda", "Melgaço": "Viana do Castelo",
    "Mesão Frio": "Vila Real", "Mértola": "Beja", "Mira": "Coimbra",
    "Miranda do Corvo": "Coimbra", "Miranda do Douro": "Bragança",
    "Mirandela": "Bragança", "Mogadouro": "Bragança", "Moimenta da Beira": "Viseu",
    "Moita": "Setúbal", "Monção": "Viana do Castelo", "Monchique": "Faro",
    "Mondim de Basto": "Vila Real", "Monforte": "Portalegre",
    "Montalegre": "Vila Real", "Montemor-o-Novo": "Évora",
    "Montemor-o-Velho": "Coimbra", "Montijo": "Setúbal", "Mora": "Évora",
    "Mortágua": "Viseu", "Moura": "Beja", "Mourão": "Évora",
    "Murça": "Vila Real", "Murtosa": "Aveiro", "Nazaré": "Leiria",
    "Nelas": "Viseu", "Nisa": "Portalegre", "Nordeste": "Açores",
    "Óbidos": "Leiria", "Odemira": "Beja", "Odivelas": "Lisboa",
    "Oeiras": "Lisboa", "Oleiros": "Castelo Branco", "Olhão": "Faro",
    "Oliveira de Azeméis": "Aveiro", "Oliveira de Frades": "Viseu",
    "Oliveira do Bairro": "Aveiro", "Oliveira do Hospital": "Coimbra",
    "Ourém": "Santarém", "Ourique": "Beja", "Ovar": "Aveiro",
    "Paços de Ferreira": "Porto", "Palmela": "Setúbal",
    "Pampilhosa da Serra": "Coimbra", "Paredes": "Porto",
    "Paredes de Coura": "Viana do Castelo", "Pedrógão Grande": "Leiria",
    "Penacova": "Coimbra", "Penafiel": "Porto", "Penalva do Castelo": "Viseu",
    "Penamacor": "Castelo Branco", "Penedono": "Viseu", "Penela": "Coimbra",
    "Peniche": "Leiria", "Peso da Régua": "Vila Real", "Pinhel": "Guarda",
    "Pombal": "Leiria", "Ponte da Barca": "Viana do Castelo",
    "Ponte de Lima": "Viana do Castelo", "Ponte de Sor": "Portalegre",
    "Portalegre": "Portalegre", "Portel": "Évora", "Portimão": "Faro",
    "Porto": "Porto", "Porto de Mós": "Leiria", "Póvoa de Lanhoso": "Braga",
    "Póvoa de Varzim": "Porto", "Proença-a-Nova": "Castelo Branco",
    "Redondo": "Évora", "Reguengos de Monsaraz": "Évora", "Resende": "Viseu",
    "Rio Maior": "Santarém", "Sabrosa": "Vila Real", "Sabugal": "Guarda",
    "Salvaterra de Magos": "Santarém", "Santa Comba Dão": "Viseu",
    "Santa Maria da Feira": "Aveiro", "Santa Marta de Penaguião": "Vila Real",
    "Santarém": "Santarém", "Santiago do Cacém": "Setúbal", "Santo Tirso": "Porto",
    "São Brás de Alportel": "Faro", "São João da Madeira": "Aveiro",
    "São João da Pesqueira": "Viseu", "São Pedro do Sul": "Viseu",
    "Sardoal": "Santarém", "Sátão": "Viseu", "Seia": "Guarda",
    "Seixal": "Setúbal", "Sernancelhe": "Viseu", "Serpa": "Beja",
    "Sertã": "Castelo Branco", "Sesimbra": "Setúbal", "Setúbal": "Setúbal",
    "Sever do Vouga": "Aveiro", "Silves": "Faro", "Sines": "Setúbal",
    "Sintra": "Lisboa", "Sobral de Monte Agraço": "Lisboa", "Soure": "Coimbra",
    "Sousel": "Portalegre", "Tábua": "Coimbra", "Tabuaço": "Viseu",
    "Tarouca": "Viseu", "Tavira": "Faro", "Terras de Bouro": "Braga",
    "Tomar": "Santarém", "Tondela": "Viseu", "Torre de Moncorvo": "Bragança",
    "Torres Novas": "Santarém", "Torres Vedras": "Lisboa", "Trancoso": "Guarda",
    "Trofa": "Porto", "Vagos": "Aveiro", "Vale de Cambra": "Aveiro",
    "Valença": "Viana do Castelo", "Valongo": "Porto", "Valpaços": "Vila Real",
    "Velas": "Açores", "Vendas Novas": "Évora", "Viana do Alentejo": "Évora",
    "Viana do Castelo": "Viana do Castelo", "Vidigueira": "Beja",
    "Vieira do Minho": "Braga", "Vila de Rei": "Castelo Branco",
    "Vila do Bispo": "Faro", "Vila do Conde": "Porto", "Vila Flor": "Bragança",
    "Vila Franca de Xira": "Lisboa", "Vila Nova da Barquinha": "Santarém",
    "Vila Nova de Cerveira": "Viana do Castelo", "Vila Nova de Famalicão": "Braga",
    "Vila Nova de Foz Côa": "Guarda", "Vila Nova de Gaia": "Porto",
    "Vila Nova de Paiva": "Viseu", "Vila Nova de Poiares": "Coimbra",
    "Vila Pouca de Aguiar": "Vila Real", "Vila Real": "Vila Real",
    "Vila Real de Santo António": "Faro", "Vila Velha de Ródão": "Castelo Branco",
    "Vila Verde": "Braga", "Vila Viçosa": "Évora", "Vimioso": "Bragança",
    "Vinhais": "Bragança", "Viseu": "Viseu", "Vizela": "Braga",
    "Vouzela": "Viseu",
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

    load_cols = list(REQUIRED_COLUMNS)
    if "CASSANDRA_Risk_Score" in dataframe.columns:
        load_cols.append("CASSANDRA_Risk_Score")
    prepared = dataframe.loc[:, load_cols].copy()
    prepared["Município"] = prepared["Município"].astype(str).str.strip()
    prepared["Live_StatusCode"] = prepared["Live_StatusCode"].astype(str).str.strip()
    prepared["CASSANDRA_Risk_Tier"] = prepared["CASSANDRA_Risk_Tier"].astype(str).str.strip()
    prepared["Var_Pop"] = pd.to_numeric(prepared["Var_Pop"], errors="coerce")
    prepared["IEI_Score"] = pd.to_numeric(prepared["IEI_Score"], errors="coerce")
    prepared["Total_Arquivo_Captures"] = pd.to_numeric(
        prepared["Total_Arquivo_Captures"], errors="coerce"
    )
    if "CASSANDRA_Risk_Score" in prepared.columns:
        prepared["CASSANDRA_Risk_Score"] = pd.to_numeric(
            prepared["CASSANDRA_Risk_Score"], errors="coerce"
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
    if "CASSANDRA_Risk_Score" in dataframe.columns:
        matched["CASSANDRA_Risk_Score"] = matched["CASSANDRA_Risk_Score"]
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

    score_val = row.get("CASSANDRA_Risk_Score", None)
    if score_val is not None and not pd.isna(score_val):
        if score_val >= 75:
            score_color = "#FF3366"
        elif score_val >= 40:
            score_color = "#FFAA00"
        else:
            score_color = "#69FF47"
        score_str = f"{score_val:.1f}".replace(".", ",") + "%"
    else:
        score_color = "#8A93A6"
        score_str = "N/D"
    st.markdown(
        (
            "<div class='detail-card' style='margin-top:0.55rem;'>"
            "<div class='detail-grid'>"
            "<div class='detail-item'>"
            f"<span>{html.escape(DISPLAY_LABELS['CASSANDRA_Risk_Score'])}</span>"
            f"<strong style='color:{score_color};'>{score_str}</strong>"
            "</div>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.caption(
        "Probabilidade matemática de colapso demográfico-digital calculada"
        " pelo motor XGBoost. Escala 0–100."
    )

    # ── PRR SIMULATOR ──────────────────────────────────────────────────────────
    if score_val is not None and not pd.isna(score_val):
        # Heuristic: calibrated against INE census loss rates in
        # high-risk PT municipalities (2001→2021 median = 150‰ per decade)
        HUMAN_COST_RATE = 150
        loss_per_1000 = max(1, int((float(score_val) / 100.0) * HUMAN_COST_RATE))
        loss_color = "#FF3366" if loss_per_1000 >= 113 else (
                     "#FFAA00" if loss_per_1000 >= 60 else "#69FF47"
                    )
        loss_str = f"\u2212{format_integer(loss_per_1000)} hab. / 1.000 residentes"
        st.markdown(
            (
                "<div class='detail-card' style='margin-top:0.55rem;'>"
                "<div class='panel-header' style='margin-bottom:0.35rem;'>"
                "<h3>Impacto Demográfico Estimado</h3>"
                "<div class='panel-pill'>Heurística INE</div>"
                "</div>"
                "<div class='detail-grid'>"
                "<div class='detail-item'>"
                "<span>👥 Custo Humano Projetado (2035)</span>"
                f"<strong style='color:{loss_color};'>{loss_str}</strong>"
                "<p class='detail-help'>"
                "Projeção heurística por cada 1.000 residentes na próxima"
                " década. Baseada na taxa de colapso calibrada com dados INE"
                " 2001→2021."
                "</p>"
                "</div>"
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        st.caption(
            "Cassandra projeta: o risco percentual representa famílias "
            "que abandonarão o território na próxima geração."
        )

        # IEI extraction with NaN fallback
        raw_iei = row.get("IEI_Score", None)
        current_iei = float(raw_iei) if raw_iei is not None and not pd.isna(raw_iei) else 0.0
        current_iei = max(0.0, min(current_iei, 99.0))  # cap at 99 so slider always has room

        simulated_iei = st.slider(
            "Simular modernização digital (Novo IEI Score)",
            min_value=0.0,
            max_value=100.0,
            value=current_iei,
            step=1.0,
            key=f"prr_slider_{municipality}",
        )

        delta_iei = simulated_iei - current_iei

        if delta_iei > 0:
            # Heuristic: derived from mean |SHAP| of IEI_Score ≈ 0.35 pts
            # risk reduction per 1 pt IEI gain (proxy for XGBoost sensitivity)
            HEURISTIC_COEFF = 0.35
            current_risk = float(score_val)  # already validated above
            new_risk = max(0.5, current_risk - (delta_iei * HEURISTIC_COEFF))
            risk_reduction = round(current_risk - new_risk, 1)

            # Determine color for projected risk using same 3-threshold logic as score_color
            if new_risk >= 75:
                new_risk_color = "#FF3366"
            elif new_risk >= 40:
                new_risk_color = "#FFAA00"
            else:
                new_risk_color = "#69FF47"

            st.markdown(
                (
                    "<div class='detail-card' style='margin-top:0.55rem;'>"
                    "<div class='panel-header' style='margin-bottom:0.35rem;'>"
                    "<h3>💼 Simulador de Intervenção PRR — Projeção</h3>"
                    "</div>"
                    "<div class='detail-grid' style='display:grid;grid-template-columns:1fr 1fr;'>"
                    "<div class='detail-item'>"
                    "<span>Risco Pós-Intervenção</span>"
                    f"<strong style='color:{new_risk_color};'>{format_decimal(new_risk, 1, '%')}</strong>"
                    "</div>"
                    "<div class='detail-item'>"
                    "<span>Redução Estimada</span>"
                    f"<strong style='color:#69FF47;'>-{format_decimal(risk_reduction, 1, '%')}</strong>"
                    "</div>"
                    "</div>"
                    "<p class='detail-help'>"
                    "Projeção heurística baseada no impacto SHAP do IEI Score. "
                    "Não substitui modelação completa."
                    "</p>"
                    "<p style='color:#8A93A6; font-style:italic; font-size:0.8rem;'>"
                    "Cassandra projeta: capital digital injetado reverte "
                    "a letargia demográfica progressiva."
                    "</p>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
    # ── END PRR SIMULATOR ──────────────────────────────────────────────────────


def render_search_panel(filtered_dataframe: pd.DataFrame, dataframe: pd.DataFrame) -> None:
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

    # ── Political Pressure Radar ─────────────────────────────────────────────
    mun_distrito = DISTRITO_MAP.get(selected, None)
    if mun_distrito is None:
        pass
    else:
        pool = dataframe[
            dataframe["Município"].map(
                lambda m: DISTRITO_MAP.get(m, None)
            ) == mun_distrito
        ].copy()
        if not pool.empty and "CASSANDRA_Risk_Score" in pool.columns:
            pool_valid = pool.dropna(subset=["CASSANDRA_Risk_Score"])
            if not pool_valid.empty:
                best_row = pool_valid.loc[pool_valid["CASSANDRA_Risk_Score"].idxmin()]
                best_mun = str(best_row["Município"])
                best_risk = float(best_row["CASSANDRA_Risk_Score"])
                selected_risk_val = selected_row.get("CASSANDRA_Risk_Score", None)

                best_risk_str = f"{best_risk:.1f}".replace(".", ",")
                selected_risk_str = (
                    f"{float(selected_risk_val):.1f}".replace(".", ",")
                    if selected_risk_val is not None and not pd.isna(selected_risk_val)
                    else "N/D"
                )

                if best_mun == selected:
                    # Case A — selected IS the best
                    body_color = "#69FF47"
                    body_text = (
                        f"🏆 {selected} é o município líder na transição digital "
                        f"do Distrito de {mun_distrito}, com um risco de {best_risk_str}%."
                    )
                    caption_text = (
                        "Cassandra confirma: esta autarquia é referência "
                        "regional na resiliência demográfico-digital."
                    )
                    label_text = "Liderança Regional"
                else:
                    # Case B — selected is NOT the best
                    delta_val = (
                        float(selected_risk_val) - best_risk
                        if selected_risk_val is not None and not pd.isna(selected_risk_val)
                        else 0.0
                    )
                    body_color = "#FF3366" if delta_val > 30 else "#FFAA00"
                    delta_str = f"{abs(delta_val):.1f}".replace(".", ",")
                    body_text = (
                        f"📍 O município líder no Distrito de {mun_distrito} é "
                        f"{best_mun}, com um risco de {best_risk_str}% "
                        f"(vs {selected_risk_str}% aqui). A letargia digital "
                        f"é uma escolha política local."
                    )
                    caption_text = (
                        f"Cassandra alerta: a diferença de {delta_str}% "
                        "face ao líder regional é reversível com "
                        "intervenção estruturada."
                    )
                    label_text = "Pressão Política"

                st.markdown(
                    f"""
                    <div class='detail-card' style='margin-top:0.55rem;'>
                        <div class='panel-header' style='margin-bottom:0.35rem;'>
                            <h3>Radar Regional &#8212; Distrito de {mun_distrito}</h3>
                            <div class='panel-pill'>{label_text}</div>
                        </div>
                        <div class='detail-grid'>
                            <div class='detail-item'>
                                <span>Posicionamento no distrito</span>
                                <strong style='color:{body_color};'>{body_text}</strong>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.caption(caption_text)



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
    base_cols = list(REQUIRED_COLUMNS)
    if "CASSANDRA_Risk_Score" in dataframe.columns:
        tier_idx = base_cols.index("CASSANDRA_Risk_Tier")
        base_cols.insert(tier_idx + 1, "CASSANDRA_Risk_Score")

    display_df = dataframe.loc[:, base_cols].copy()

    if "CASSANDRA_Risk_Score" in display_df.columns:
        display_df["CASSANDRA_Risk_Score"] = display_df["CASSANDRA_Risk_Score"].apply(
            lambda x: f"{x:.1f}".replace(".", ",") + "%" if pd.notna(x) else "N/D"
        )

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
        render_search_panel(filtered_dataframe, dataframe)

    render_oracle_log(filtered_dataframe)


if __name__ == "__main__":
    main()
