"""
mapa_cassandra.py
CASSANDRA Oracle Engine — Demographic Risk & Digital Lethargy Map
Visualises population change (2011→2021) overlaid with municipal website
health status for all 308 Portuguese municipalities.
"""

import re
import unicodedata

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.colors import LinearSegmentedColormap
import pandas as pd



# ---------------------------------------------------------------------------
# Name normalisation — applied uniformly to CSV, Excel, and GeoJSON sources
# ---------------------------------------------------------------------------

MAPPING_DICT = {
    'aguiardabeira': 'aguiar da beira',
    'alcacerdosal': 'alcacer do sal',
    'alfandegadafe': 'alfandega da fe',
    'alterdochao': 'alter do chao',
    'angradoheroismo': 'angra do heroismo',
    'arcosdevaldevez': 'arcos de valdevez',
    'arrudadosvinhos': 'arruda dos vinhos',
    'azores calheta': 'azores calheta',
    'azores lagoa': 'azores lagoa',
    'cabeceirasdebasto': 'cabeceiras de basto',
    'caldasdarainha': 'caldas da rainha',
    'calheta [r.a.a.]': 'azores calheta',
    'calheta [r.a.m.]': 'madeira calheta',
    'camaradelobos': 'camara de lobos',
    'campomaior': 'campo maior',
    'carrazedadeansiaes': 'carrazeda de ansiaes',
    'carregaldosal': 'carregal do sal',
    'castanheiradepera': 'castanheira de pera',
    'castelobranco': 'castelo branco',
    'castelodepaiva': 'castelo de paiva',
    'castelodevide': 'castelo de vide',
    'castrodaire': 'castro daire',
    'castromarim': 'castro marim',
    'castroverde': 'castro verde',
    'celoricodabeira': 'celorico da beira',
    'celoricodebasto': 'celorico de basto',
    'faro lagoa': 'faro lagoa',
    'ferreiradoalentejo': 'ferreira do alentejo',
    'ferreiradozezere': 'ferreira do zezere',
    'figueiradafoz': 'figueira da foz',
    'figueiradecastelorodrigo': 'figueira de castelo rodrigo',
    'figueirodosvinhos': 'figueiro dos vinhos',
    'fornosdealgodres': 'fornos de algodres',
    'freixodeespadaacinta': 'freixo de espada a cinta',
    'lagoa': 'faro lagoa',
    'lagoa [r.a.a.]': 'azores lagoa',
    'lajesdasflores': 'lajes das flores',
    'lajesdopico': 'lajes do pico',
    'macedodecavaleiros': 'macedo de cavaleiros',
    'madeira calheta': 'madeira calheta',
    'marcodecanaveses': 'marco de canaveses',
    'marinhagrande': 'marinha grande',
    'mesaofrio': 'mesao frio',
    'mirandadocorvo': 'miranda do corvo',
    'mirandadodouro': 'miranda do douro',
    'moimentadabeira': 'moimenta da beira',
    'mondimdebasto': 'mondim de basto',
    'oliveiradeazemeis': 'oliveira de azemeis',
    'oliveiradefrades': 'oliveira de frades',
    'oliveiradobairro': 'oliveira do bairro',
    'oliveiradohospital': 'oliveira do hospital',
    'pacosdeferreira': 'pacos de ferreira',
    'pampilhosadaserra': 'pampilhosa da serra',
    'paredesdecoura': 'paredes de coura',
    'pedrogaogrande': 'pedrogao grande',
    'penalvadocastelo': 'penalva do castelo',
    'pesodaregua': 'peso da regua',
    'pontadelgada': 'ponta delgada',
    'pontadosol': 'ponta do sol',
    'pontedabarca': 'ponte da barca',
    'pontedelima': 'ponte de lima',
    'pontedesor': 'ponte de sor',
    'portodemos': 'porto de mos',
    'portomoniz': 'porto moniz',
    'portosanto': 'porto santo',
    'povoadelanhoso': 'povoa de lanhoso',
    'povoadevarzim': 'povoa de varzim',
    'praiadavitoria': 'praia da vitoria',
    'reguengosdemonsaraz': 'reguengos de monsaraz',
    'ribeirabrava': 'ribeira brava',
    'ribeiradepena': 'ribeira de pena',
    'ribeiragrande': 'ribeira grande',
    'riomaior': 'rio maior',
    'salvaterrademagos': 'salvaterra de magos',
    'santacombadao': 'santa comba dao',
    'santacruz': 'santa cruz',
    'santacruzdagraciosa': 'santa cruz da graciosa',
    'santacruzdasflores': 'santa cruz das flores',
    'santamariadafeira': 'santa maria da feira',
    'santamartadepenaguiao': 'santa marta de penaguiao',
    'santiagodocacem': 'santiago do cacem',
    'santotirso': 'santo tirso',
    'saobrasdealportel': 'sao bras de alportel',
    'saojoaodamadeira': 'sao joao da madeira',
    'saojoaodapesqueira': 'sao joao da pesqueira',
    'saopedrodosul': 'sao pedro do sul',
    'saoroquedopico': 'sao roque do pico',
    'saovicente': 'sao vicente',
    'severdovouga': 'sever do vouga',
    'sobraldemonteagraco': 'sobral de monte agraco',
    'terrasdebouro': 'terras de bouro',
    'torredemoncorvo': 'torre de moncorvo',
    'torresnovas': 'torres novas',
    'torresvedras': 'torres vedras',
    'valedecambra': 'vale de cambra',
    'vendasnovas': 'vendas novas',
    'vianadoalentejo': 'viana do alentejo',
    'vianadocastelo': 'viana do castelo',
    'vieiradominho': 'vieira do minho',
    'vila da praia da vitoria': 'praia da vitoria',
    'viladerei': 'vila de rei',
    'viladobispo': 'vila do bispo',
    'viladoconde': 'vila do conde',
    'viladoporto': 'vila do porto',
    'vilaflor': 'vila flor',
    'vilafrancadexira': 'vila franca de xira',
    'vilafrancadocampo': 'vila franca do campo',
    'vilanovadabarquinha': 'vila nova da barquinha',
    'vilanovadecerveira': 'vila nova de cerveira',
    'vilanovadefamalicao': 'vila nova de famalicao',
    'vilanovadefozcoa': 'vila nova de foz coa',
    'vilanovadegaia': 'vila nova de gaia',
    'vilanovadepaiva': 'vila nova de paiva',
    'vilanovadepoiares': 'vila nova de poiares',
    'vilapoucadeaguiar': 'vila pouca de aguiar',
    'vilareal': 'vila real',
    'vilarealdesantoantonio': 'vila real de santo antonio',
    'vilavelhaderodao': 'vila velha de rodao',
    'vilaverde': 'vila verde',
    'vilavicosa': 'vila vicosa',
}


def strip_accents(value: str) -> str:
    return ''.join(
        char for char in unicodedata.normalize('NFKD', value)
        if not unicodedata.combining(char)
    )


def normalize_name(name: str) -> str:
    if not isinstance(name, str):
        return ''
    name = name.strip().lower()
    lookup_key = strip_accents(name)
    name = MAPPING_DICT.get(lookup_key, name)
    name = strip_accents(name.lower().strip())
    return re.sub(r'\s+', ' ', name).strip()


# ---------------------------------------------------------------------------
# 1. Load metrics CSV
# ---------------------------------------------------------------------------

df_metrics = pd.read_csv('metricas_fase2_avancadas.csv', encoding='utf-8-sig')
# Validate required columns early so failures are explicit
assert 'Município' in df_metrics.columns, "metricas_fase2_avancadas.csv missing 'Município'"
assert 'Live_StatusCode' in df_metrics.columns, "metricas_fase2_avancadas.csv missing 'Live_StatusCode'"

# ---------------------------------------------------------------------------
# 2. Load demographics Excel (header on row 2 → header=1)
# ---------------------------------------------------------------------------

df_demo = pd.read_excel('dados_demograficos.csv', header=1)
print("Demographics columns detected:", df_demo.columns.tolist())

assert 'Município' in df_demo.columns, "dados_demograficos.csv missing 'Município'"

# Dynamically locate the population-change column (contains both '2011' and '2021')
pop_col = [c for c in df_demo.columns if '2011' in str(c) and '2021' in str(c)][0]
df_demo = df_demo.rename(columns={pop_col: 'Var_Pop'})
print(f"Population change column '{pop_col}' → renamed to 'Var_Pop'")

# ---------------------------------------------------------------------------
# 3. Build merge keys and join CSV sources
# ---------------------------------------------------------------------------

df_metrics['mun_key'] = df_metrics['Município'].apply(normalize_name)
df_demo['mun_key'] = df_demo['Município'].apply(normalize_name)

# Left join from metrics; keep display label from metrics
df_merged = df_metrics.merge(
    df_demo[['mun_key', 'Var_Pop']],
    on='mun_key',
    how='left'
)

# ---------------------------------------------------------------------------
# 4. Load GeoJSON from local file
# ---------------------------------------------------------------------------

GEOJSON_PATH = 'municipios.geojson'
gdf = gpd.read_file(GEOJSON_PATH)
print(f"GeoJSON loaded from local file: {GEOJSON_PATH}")

# Enforce WGS84 immediately to prevent distorted maps (source may be EPSG:3763)
gdf = gdf.to_crs(epsg=4326)

# Prefer the municipality column explicitly when present; otherwise fall back
# to the highest-cardinality column that contains the municipality 'lisboa'.
if 'NAME_2' in gdf.columns:
    name_col = 'NAME_2'
else:
    candidate_cols = [
        col for col in gdf.columns
        if gdf[col].astype(str).str.lower().str.strip().eq('lisboa').any()
    ]
    if not candidate_cols:
        raise ValueError(
            f"Could not detect municipality name column in GeoJSON. "
            f"Available columns: {gdf.columns.tolist()}"
        )
    name_col = max(candidate_cols, key=lambda col: gdf[col].astype(str).nunique())

print(f"GeoJSON municipality name column: '{name_col}'")

# Normalise GeoJSON municipality names and disambiguate duplicated
# municipality labels that exist in different autonomous regions.
geo_name_counts = gdf[name_col].astype(str).str.strip().value_counts()
gdf['mun_key'] = gdf.apply(
    lambda row: normalize_name(
        f"{row['NAME_1']} {row[name_col]}"
        if geo_name_counts.get(str(row[name_col]).strip(), 0) > 1 and 'NAME_1' in gdf.columns
        else row[name_col]
    ),
    axis=1,
)

# ---------------------------------------------------------------------------
# 5. Merge GeoJSON ↔ combined data
# ---------------------------------------------------------------------------

gdf = gdf.merge(
    df_merged[['mun_key', 'Município', 'Live_StatusCode', 'Var_Pop']],
    on='mun_key',
    how='left'
)

n_geojson = len(gdf)
n_data = df_merged['mun_key'].nunique()
n_matched = gdf['Var_Pop'].notna().sum()
match_pct = 100 * n_matched / n_data if n_data else 0

# Identify unmatched data municipalities for diagnostics
matched_keys = set(gdf.loc[gdf['Var_Pop'].notna(), 'mun_key'])
unmatched_names = df_merged.loc[
    ~df_merged['mun_key'].isin(matched_keys), 'Município'
].dropna().unique().tolist()

print(f"\nMerge diagnostics:")
print(f"  GeoJSON municipalities : {n_geojson}")
print(f"  Data municipalities    : {n_data}")
print(f"  Matched                : {n_matched} ({match_pct:.1f}% success rate)")
print(f"  Unmatched from data    : {unmatched_names}\n")

if n_matched != n_data or n_matched != n_geojson:
    raise ValueError(
        f"Municipality merge incomplete: {n_matched}/{n_data} matched. "
        f"Unmatched data municipalities: {unmatched_names}"
    )

# ---------------------------------------------------------------------------
# 6. Visualisation — CASSANDRA identity
# ---------------------------------------------------------------------------

fig, ax = plt.subplots(1, 1, figsize=(14, 16), dpi=300)
fig.patch.set_facecolor('#1B2A4A')
ax.set_facecolor('#1B2A4A')

# Diverging colour scale anchored at zero; computed only from matched rows
matched_vals = gdf.loc[gdf['Var_Pop'].notna(), 'Var_Pop']
data_min = float(matched_vals.min())
data_max = float(matched_vals.max())

norm = mcolors.TwoSlopeNorm(vmin=data_min, vcenter=0, vmax=data_max)

cmap = LinearSegmentedColormap.from_list(
    'cassandra', ['#FF3366', '#FFFFFF', '#00E5FF']
)

# --- Layer 1: unmatched municipalities (no demographic data) ---
gdf_unmatched = gdf[gdf['Var_Pop'].isna()]
if not gdf_unmatched.empty:
    gdf_unmatched.plot(
        ax=ax,
        facecolor='#2E4A6E',
        edgecolor='#1B2A4A',
        linewidth=0.3,
    )

# --- Layer 2a: matched, active sites ---
dead_statuses = {'Dead', 'Timeout'}
gdf_matched = gdf[gdf['Var_Pop'].notna()].copy()

mask_active = ~gdf_matched['Live_StatusCode'].isin(dead_statuses)
gdf_active = gdf_matched[mask_active]

if not gdf_active.empty:
    gdf_active.plot(
        ax=ax,
        column='Var_Pop',
        cmap=cmap,
        norm=norm,
        edgecolor='none',
        linewidth=0,
    )

# --- Layer 2b: matched, dead/timeout sites (hatched on top) ---
gdf_dead = gdf_matched[~mask_active]

if not gdf_dead.empty:
    gdf_dead.plot(
        ax=ax,
        column='Var_Pop',
        cmap=cmap,
        norm=norm,
        edgecolor='none',
        linewidth=0,
    )
    # Hatch layer painted on top — edgecolor here controls hatch line colour
    gdf_dead.plot(
        ax=ax,
        facecolor='none',
        hatch='////',
        edgecolor='#FFAA00',
        linewidth=1.5,
    )

# --- Colorbar ---
sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])
cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, aspect=30)
cbar.set_label('Variação Populacional 2011→2021 (%)', color='white', fontsize=10)
cbar.ax.yaxis.set_tick_params(color='white')
plt.setp(cbar.ax.yaxis.get_ticklabels(), color='white')
cbar.outline.set_edgecolor('#3A5A8A')

ax.set_axis_off()

# ---------------------------------------------------------------------------
# 7. Branding
# ---------------------------------------------------------------------------

ax.set_title(
    'CASSANDRA — Mapa de Risco Demográfico e Letargia Digital',
    color='white', fontsize=18, fontweight='bold', pad=20,
    fontfamily='DejaVu Sans',
)

n_municipios = len(gdf)
fig.text(
    0.5, 0.93,
    f'{n_municipios} municípios · Cor = Demografia | Padrão Riscado = Site Autárquico Morto/Inativo',
    ha='center', color='#7FB3D3', fontsize=11,
    fontfamily='DejaVu Sans',
)

fig.text(
    0.98, 0.01,
    'Powered by CASSANDRA Oracle Engine',
    ha='right', color='#3A5A8A', fontsize=9, style='italic',
    fontfamily='DejaVu Sans',
)

# ---------------------------------------------------------------------------
# 8. Output
# ---------------------------------------------------------------------------

plt.savefig(
    'mapa_risco_cassandra.png',
    bbox_inches='tight',
    facecolor='#1B2A4A',
    dpi=300,
)
plt.close()

print("Saved: mapa_risco_cassandra.png")
print(f"Final match rate: {n_matched}/{n_data} ({match_pct:.1f}%)")
print(f"Unmatched municipalities: {unmatched_names}")
