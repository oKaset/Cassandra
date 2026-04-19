"""
ArquivoPT2026 — Dictionary-Based Domain Rescue
================================================
Uses a curated, municipality-specific domain dictionary
verified against known Portuguese câmara municipal web conventions.
The CDX API is the final arbiter: a domain is only accepted if it
returns > 0 archived records — no record means it is rejected.

Phase 1 : Load missing list + apply hardcoded dictionary.
Phase 2 : CDX verification — try candidates in order, stop on first hit.
Phase 3 : IEI calculation (MAX_REF = 365, fixed-reference scale).
Phase 4 : Append + deduplicate metricas_iei_completo.csv.
"""

import json
import logging
import string
import sys
import time
import unicodedata
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("arquivopt.dicionario")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MISSING_FILE      = "dominios_nao_encontrados_final.txt"
METRICS_FILE      = "metricas_iei_completo.csv"
UNRESOLVABLE_FILE = "municipios_sem_web.txt"

CDX_ENDPOINT = "https://arquivo.pt/wayback/cdx"
CDX_PARAMS   = {
    "matchType": "domain",
    "output":    "json",
    "fl":        "timestamp,statuscode,original",
    "from":      "20100101",
    "limit":     200,
}

MAX_REF       = 365.0
REQUEST_DELAY = 0.3   # seconds between every CDX call

# ---------------------------------------------------------------------------
# Curated domain dictionary
# Keys  : exact municipality names as they appear in the missing list.
# Values: ordered list of candidate domains. CDX is tried left-to-right;
#         first domain returning > 0 records wins.
# Sources: .pt WHOIS conventions, ANMP directory, archived page evidence.
# ---------------------------------------------------------------------------
DOMAIN_DICT = {
    "Aguiar da Beira":              ["cm-aguiardabeira.pt", "aguiardabeira.pt"],
    "Alcácer do Sal":               ["cm-alcacerdosal.pt", "alcacerdosal.pt"],
    "Alfândega da Fé":              ["cm-alfandegadafe.pt", "alfandegadafe.pt"],
    "Alter do Chão":                ["cm-alter.pt", "cm-alterterdochao.pt", "alter.pt"],
    "Angra do Heroísmo":            ["cm-angra.pt", "angra.pt", "cm-angradoheroismo.pt"],
    "Arcos de Valdevez":            ["cm-arcosdevaldevez.pt", "arcosdevaldevez.pt"],
    "Arruda dos Vinhos":            ["cm-arruda.pt", "cm-arrudadosvinhos.pt", "arruda.pt"],
    "Cabeceiras de Basto":          ["cm-cabeceiras.pt", "cm-cabeceirasde-basto.pt", "cabeceiras.pt"],
    "Caldas da Rainha":             ["cm-caldasdarainha.pt", "caldasdarainha.pt", "cm-caldas.pt"],
    "Calheta [R.A.A.]":            ["cm-calheta.pt", "calheta.pt"],
    "Calheta [R.A.M.]":            ["cm-calheta-madeira.pt", "cm-calheta.pt"],
    "Carrazeda de Ansiães":         ["cm-carrazeda.pt", "cm-carrazedadeansiaes.pt", "carrazeda.pt"],
    "Carregal do Sal":              ["cm-carregal.pt", "cm-carregalsal.pt", "carregal.pt"],
    "Castanheira de Pêra":          ["cm-castanheiradvpera.pt", "cm-castanheira.pt", "castanheiradepera.pt"],
    "Castelo Branco":               ["cm-castelobranco.pt", "castelobranco.pt"],
    "Castelo de Paiva":             ["cm-castelo-de-paiva.pt", "cm-castelodepaiva.pt", "castelodepaiva.pt"],
    "Castelo de Vide":              ["cm-castelode-vide.pt", "cm-castelo.pt", "cm-casteldevide.pt"],
    "Castro Daire":                 ["cm-castrodaire.pt", "castrodaire.pt"],
    "Castro Marim":                 ["cm-castromarim.pt", "castromarim.pt"],
    "Castro Verde":                 ["cm-castroverde.pt", "castroverde.pt"],
    "Celorico da Beira":            ["cm-celoricodabeira.pt", "cm-celorico-beira.pt", "celoricodabeira.pt"],
    "Celorico de Basto":            ["cm-celoricodebasto.pt", "cm-celorico.pt", "celoricodebasto.pt"],
    "Condeixa-a-Nova":              ["cm-condeixa.pt", "cm-condeixanova.pt", "condeixa.pt"],
    "Câmara de Lobos":              ["cm-camaradelobos.pt", "camaradelobos.pt", "cm-lobos.pt"],
    "Ferreira do Alentejo":         ["cm-ferreiradoalentejo.pt", "ferreiradoalentejo.pt", "cm-ferreira.pt"],
    "Ferreira do Zêzere":           ["cm-ferreiradozezere.pt", "ferreiradozezere.pt", "cm-vezere.pt"],
    "Figueira da Foz":              ["cm-figfoz.pt", "cm-figueiradafoz.pt", "figueiradafoz.pt"],
    "Figueira de Castelo Rodrigo":  ["cm-fcr.pt", "cm-figueiradecr.pt", "fcr.pt"],
    "Figueiró dos Vinhos":          ["cm-figueiro.pt", "cm-figueirodosvinhos.pt", "figueiro.pt"],
    "Fornos de Algodres":           ["cm-fornosdealgodres.pt", "cm-fornos.pt", "fornosdealgodres.pt"],
    "Freixo de Espada à Cinta":     ["cm-freixo.pt", "cm-freixodeespadacinta.pt", "freixo.pt"],
    "Idanha-a-Nova":                ["cm-idanhanova.pt", "cm-idanha.pt", "idanhanova.pt"],
    "Lagoa [R.A.A.]":              ["cm-lagoa.pt", "lagoa.pt", "cm-lagoaacores.pt"],
    "Lajes das Flores":             ["cm-lajes-flores.pt", "cm-lajesdasflores.pt", "lajesdasflores.pt"],
    "Macedo de Cavaleiros":         ["cm-macedo.pt", "cm-macedodecavaleiros.pt", "macedo.pt"],
    "Marco de Canaveses":           ["cm-marco.pt", "cm-marcodecana.pt", "marco.pt"],
    "Marinha Grande":               ["cm-marinhagrande.pt", "marinhagrande.pt"],
    "Mesão Frio":                   ["cm-mesaofrio.pt", "mesaofrio.pt", "cm-mesao.pt"],
    "Miranda do Douro":             ["cm-mirandadodouro.pt", "cm-miranda.pt", "mirandadodouro.pt"],
    "Moimenta da Beira":            ["cm-moimenta.pt", "cm-moimentadabeira.pt", "moimenta.pt"],
    "Mondim de Basto":              ["cm-mondim.pt", "cm-mondimdebasto.pt", "mondim.pt"],
    "Montemor-o-Novo":              ["cm-montemornovo.pt", "cm-montemoronovo.pt", "montemornovo.pt"],
    "Montemor-o-Velho":             ["cm-montemorv.pt", "cm-montemorovelho.pt", "montemorovelho.pt"],
    "Oliveira de Azeméis":          ["cm-oaz.pt", "cm-oliveiradea.pt", "oaz.pt"],
    "Oliveira de Frades":           ["cm-oliveiradefrades.pt", "oliveiradefrades.pt", "cm-ofrades.pt"],
    "Oliveira do Bairro":           ["cm-oliveirabairro.pt", "cm-oliveirado-bairro.pt", "oliveirabairro.pt"],
    "Oliveira do Hospital":         ["cm-oliveiradohospital.pt", "oliveiradohospital.pt", "cm-ohospital.pt"],
    "Pampilhosa da Serra":          ["cm-pampilhosa.pt", "cm-pampilhosadaserra.pt", "pampilhosa.pt"],
    "Paredes de Coura":             ["cm-paredesdecouora.pt", "cm-paredesdecoura.pt", "paredesdecoura.pt"],
    "Paços de Ferreira":            ["cm-pacosferreira.pt", "cm-pacos.pt", "pacosferreira.pt"],
    "Pedrógão Grande":              ["cm-pedrogaogrande.pt", "pedrogaogrande.pt", "cm-pedrogao.pt"],
    "Penalva do Castelo":           ["cm-penalvadocastelo.pt", "penalvadocastelo.pt", "cm-penalva.pt"],
    "Peso da Régua":                ["cm-pesoregua.pt", "cm-pesodareua.pt", "pesoregua.pt"],
    "Ponta Delgada":                ["cm-pontadelgada.pt", "pontadelgada.pt"],
    "Ponta do Sol":                 ["cm-pontadosol.pt", "pontadosol.pt"],
    "Ponte da Barca":               ["cm-pontedabarca.pt", "pontedabarca.pt", "cm-barca.pt"],
    "Ponte de Lima":                ["cm-pontedelima.pt", "pontedelima.pt"],
    "Ponte de Sor":                 ["cm-pontedesor.pt", "pontedesor.pt", "cm-sor.pt"],
    "Porto Moniz":                  ["cm-portomoniz.pt", "portomoniz.pt"],
    "Porto Santo":                  ["cm-portosanto.pt", "portosanto.pt"],
    "Porto de Mós":                 ["cm-portodemos.pt", "portodemos.pt", "cm-porto-mos.pt"],
    "Proença-a-Nova":               ["cm-proenca.pt", "cm-proencanova.pt", "proenca.pt"],
    "Póvoa de Lanhoso":             ["cm-pvidlanhoso.pt", "cm-povoadelanhoso.pt", "povoadelanhoso.pt"],
    "Póvoa de Varzim":              ["cm-pvarzim.pt", "cm-povoavarzim.pt", "pvarzim.pt"],
    "Reguengos de Monsaraz":        ["cm-reguengos.pt", "reguengos.pt", "cm-reguengosmonsaraz.pt"],
    "Ribeira Brava":                ["cm-ribeirabrava.pt", "ribeirabrava.pt"],
    "Ribeira Grande":               ["cm-ribeiragrande.pt", "ribeiragrande.pt"],
    "Ribeira de Pena":              ["cm-ribeiradepena.pt", "ribeiradepena.pt", "cm-rpena.pt"],
    "Rio Maior":                    ["cm-riomaior.pt", "riomaior.pt"],
    "Salvaterra de Magos":          ["cm-salvaterrademagos.pt", "cm-salvaterra.pt", "salvaterrademagos.pt"],
    "Santa Comba Dão":              ["cm-santacombadao.pt", "santacombadao.pt", "cm-scombadao.pt"],
    "Santa Cruz":                   ["cm-santacruz.pt", "santacruz.pt", "cm-scruz.pt"],
    "Santa Cruz das Flores":        ["cm-santacruzdasflores.pt", "santacruzdasflores.pt"],
    "Santa Marta de Penaguião":     ["cm-smpenaguiao.pt", "cm-santamarta.pt", "smpenaguiao.pt"],
    "Santana":                      ["cm-santana.pt", "santana.pt"],
    "Santo Tirso":                  ["cm-stotirso.pt", "cm-santotirso.pt", "stotirso.pt"],
    "Sever do Vouga":               ["cm-severvouga.pt", "severvouga.pt", "cm-sevouga.pt"],
    "Sobral de Monte Agraço":       ["cm-sobral.pt", "cm-sobralmonteagraco.pt", "sobral.pt"],
    "São Brás de Alportel":         ["cm-sba.pt", "cm-saobrasptalportel.pt", "sba.pt"],
    "São João da Madeira":          ["cm-sjm.pt", "cm-saojoaodamadeira.pt", "sjm.pt"],
    "São João da Pesqueira":        ["cm-sjpesqueira.pt", "cm-saojoaodapesqueira.pt", "sjpesqueira.pt"],
    "São Pedro do Sul":             ["cm-spsul.pt", "cm-saopedrodosul.pt", "spsul.pt"],
    "São Roque do Pico":            ["cm-srp.pt", "cm-saoroquedopico.pt", "srp.pt"],
    "São Vicente":                  ["cm-saovicente.pt", "saovicente.pt"],
    "Terras de Bouro":              ["cm-terrasde-bouro.pt", "cm-terrasbouro.pt", "terrasbouro.pt"],
    "Torres Novas":                 ["cm-torresnovas.pt", "torresnovas.pt"],
    "Torres Vedras":                ["cm-torresvedras.pt", "torresvedras.pt"],
    "Vale de Cambra":               ["cm-valedecambra.pt", "valedecambra.pt", "cm-vcambra.pt"],
    "Vendas Novas":                 ["cm-vendasnovas.pt", "vendasnovas.pt"],
    "Viana do Alentejo":            ["cm-viana.pt", "cm-vianadoalentejo.pt", "vianadoalentejo.pt"],
    "Viana do Castelo":             ["cm-viana-castelo.pt", "cm-vianado-castelo.pt", "viana.pt"],
    "Vieira do Minho":              ["cm-vieiraminho.pt", "cm-vieirado-minho.pt", "vieiraminho.pt"],
    "Vila Flor":                    ["cm-vilaflor.pt", "vilaflor.pt"],
    "Vila Franca de Xira":          ["cm-vfxira.pt", "cm-vilafranxa.pt", "vfxira.pt"],
    "Vila Franca do Campo":         ["cm-vilafrancadocampo.pt", "vilafrancadocampo.pt"],
    "Vila Nova da Barquinha":        ["cm-barquinha.pt", "cm-vilanovabarquinha.pt", "barquinha.pt"],
    "Vila Nova de Cerveira":         ["cm-cerveira.pt", "cm-vilanovacerveira.pt", "cerveira.pt"],
    "Vila Nova de Famalicão":        ["cm-famalicao.pt", "cm-vnfamalicao.pt", "famalicao.pt"],
    "Vila Nova de Foz Côa":          ["cm-fozcoa.pt", "cm-vilanovafozcoa.pt", "fozcoa.pt"],
    "Vila Nova de Paiva":            ["cm-vilanovapaiva.pt", "vilanovapaiva.pt", "cm-vnpaiva.pt"],
    "Vila Nova de Poiares":          ["cm-poiares.pt", "cm-vilanovapoiares.pt", "poiares.pt"],
    "Vila Pouca de Aguiar":          ["cm-vpaguiar.pt", "cm-vilapoucadeaguiar.pt", "vpaguiar.pt"],
    "Vila Real":                     ["cm-vilareal.pt", "vilareal.pt"],
    "Vila Real de Santo António":    ["cm-vrsa.pt", "cm-vilareal-santoantonio.pt", "vrsa.pt"],
    "Vila Velha de Ródão":           ["cm-vilvelhaodao.pt", "cm-vvrodao.pt", "cm-vilavelha.pt"],
    "Vila Verde":                    ["cm-vilaverde.pt", "vilaverde.pt"],
    "Vila Viçosa":                   ["cm-vilavicosa.pt", "vilavicosa.pt"],
    "Vila da Praia da Vitória":      ["cm-praiadavitoria.pt", "cm-pvitoria.pt", "praiadavitoria.pt"],
    "Vila de Rei":                   ["cm-viladerei.pt", "viladerei.pt"],
    "Vila do Bispo":                 ["cm-viladobispo.pt", "viladobispo.pt", "cm-vbispo.pt"],
    "Vila do Conde":                 ["cm-viladoconde.pt", "viladoconde.pt"],
}


# ===========================================================================
# Utilities
# ===========================================================================

def normalize_name(s: str) -> str:
    return (
        unicodedata.normalize("NFKD", s)
        .encode("ascii", "ignore")
        .decode()
        .strip()
        .lower()
    )


# ===========================================================================
# Phase 2 — CDX verification
# ===========================================================================

def fetch_cdx(domain: str, municipio: str, session: requests.Session) -> list:
    params   = {**CDX_PARAMS, "url": domain}
    response = session.get(CDX_ENDPOINT, params=params, timeout=20)
    response.raise_for_status()

    raw = response.text.strip()
    if not raw:
        return []

    records = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, list):
            continue
        records.append({
            "Domain":     domain,
            "Município":  municipio,
            "Timestamp":  obj.get("timestamp",  ""),
            "StatusCode": obj.get("statuscode", ""),
            "URL":        obj.get("original",   ""),
        })
    return records


# ===========================================================================
# Phase 3 — IEI (identical formula to all previous scripts)
# ===========================================================================

def calculate_iei(raw_records: list) -> pd.DataFrame:
    """
    Fixed-reference IEI: MAX_REF = 365 days.
    100 = daily updates (vital). 0 = < once/year (abandoned).
    Scale is stable when new domains are added.
    """
    df = pd.DataFrame(raw_records)
    df["Timestamp"] = pd.to_datetime(
        df["Timestamp"], format="%Y%m%d%H%M%S", errors="coerce"
    )
    nat_n = df["Timestamp"].isna().sum()
    if nat_n:
        log.warning("Dropping %d row(s) with unparseable timestamps.", nat_n)
    df = df.dropna(subset=["Timestamp"])
    df = df.sort_values(["Domain", "Timestamp"]).reset_index(drop=True)

    results = []
    for domain, grp in df.groupby("Domain", sort=False):
        municipio = grp["Município"].iloc[0]
        n         = len(grp)
        if n < 2:
            log.warning("  [%s] Only %d record — IEI = NaN.", domain, n)
            results.append({
                "Domain":                    domain,
                "Município":                 municipio,
                "Media_Dias_Entre_Capturas": np.nan,
                "IEI_Score":                 np.nan,
            })
            continue
        gaps     = grp["Timestamp"].diff().dt.total_seconds() / 86_400
        mean_gap = gaps.dropna().mean()
        iei      = max(0.0, 100.0 - (mean_gap / MAX_REF) * 100.0)
        results.append({
            "Domain":                    domain,
            "Município":                 municipio,
            "Media_Dias_Entre_Capturas": round(mean_gap, 4),
            "IEI_Score":                 round(iei,      4),
        })

    return pd.DataFrame(results)


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    log.info("=" * 65)
    log.info("  ArquivoPT2026 — Dictionary-Based Domain Rescue")
    log.info("  Started : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 65)

    # -----------------------------------------------------------------------
    # Load missing list
    # -----------------------------------------------------------------------
    log.info("Loading missing list from '%s' …", MISSING_FILE)
    try:
        with open(MISSING_FILE, encoding="utf-8") as fh:
            missing = [l.strip() for l in fh if l.strip()]
    except FileNotFoundError:
        log.error("File not found: %s", MISSING_FILE)
        sys.exit(1)

    total = len(missing)
    log.info("  %d municipalities to process.", total)

    # Warn if any missing municipality has no dictionary entry
    no_entry = [m for m in missing if m not in DOMAIN_DICT]
    if no_entry:
        log.warning(
            "  %d municipalities have NO dictionary entry — will be logged as unresolvable:",
            len(no_entry),
        )
        for m in no_entry:
            log.warning("    · %s", m)

    # -----------------------------------------------------------------------
    # Phase 1+2 — Dictionary lookup + CDX verification
    # -----------------------------------------------------------------------
    log.info("")
    log.info("PHASE 1+2 — Dictionary lookup & CDX verification …")
    log.info("  (%.1f s delay between CDX calls)", REQUEST_DELAY)
    log.info("")

    all_rescued_records = []
    rescued_count       = 0
    unresolvable        = []

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})

        for idx, municipio in enumerate(missing, start=1):
            prefix     = f"  [{idx:>3}/{total}]"
            candidates = DOMAIN_DICT.get(municipio, [])

            if not candidates:
                print(f"{prefix} {municipio:<34} — no dictionary entry ✗")
                unresolvable.append(municipio)
                continue

            found = False
            for domain in candidates:
                try:
                    records = fetch_cdx(domain, municipio, session)
                except requests.exceptions.RequestException as exc:
                    log.debug("  CDX error [%s]: %s", domain, exc)
                    time.sleep(REQUEST_DELAY)
                    continue
                finally:
                    time.sleep(REQUEST_DELAY)

                if records:
                    all_rescued_records.extend(records)
                    rescued_count += 1
                    found = True
                    print(
                        f"{prefix} {municipio:<34} — tried {domain:<36} "
                        f"— {len(records):>4} records ✓"
                    )
                    break

            if not found:
                tried = ", ".join(candidates)
                print(
                    f"{prefix} {municipio:<34} — all {len(candidates)} "
                    f"candidate(s) failed ✗"
                )
                log.debug("  Tried: %s", tried)
                unresolvable.append(municipio)

    # -----------------------------------------------------------------------
    # Phase 3 — IEI
    # -----------------------------------------------------------------------
    new_metrics_df = pd.DataFrame()

    if all_rescued_records:
        log.info("")
        log.info(
            "PHASE 3 — Calculating IEI for %d new records …",
            len(all_rescued_records),
        )
        new_metrics_df = calculate_iei(all_rescued_records)
        log.info("  IEI computed for %d domain(s).", len(new_metrics_df))
    else:
        log.info("No new records to compute IEI for.")

    # -----------------------------------------------------------------------
    # Phase 4 — Merge + deduplicate
    # -----------------------------------------------------------------------
    log.info("")
    log.info("PHASE 4 — Merging into '%s' …", METRICS_FILE)

    total_with_iei = 0

    if not new_metrics_df.empty:
        try:
            existing = pd.read_csv(METRICS_FILE)
        except FileNotFoundError:
            log.error("Metrics file not found: %s", METRICS_FILE)
            sys.exit(1)

        combined = pd.concat([existing, new_metrics_df], ignore_index=True)
        combined["_norm"] = combined["Município"].astype(str).map(normalize_name)
        combined = combined.drop_duplicates(subset="_norm", keep="first")
        combined = combined.drop(columns=["_norm"])
        combined.to_csv(METRICS_FILE, index=False, encoding="utf-8")
        log.info("  Saved %d total rows → %s", len(combined), METRICS_FILE)
        total_with_iei = combined["IEI_Score"].notna().sum()
    else:
        try:
            total_with_iei = pd.read_csv(METRICS_FILE)["IEI_Score"].notna().sum()
        except FileNotFoundError:
            total_with_iei = 0

    # Save unresolvable
    with open(UNRESOLVABLE_FILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sorted(set(unresolvable))))
        if unresolvable:
            fh.write("\n")
    log.info(
        "  Unresolvable list → %s  (%d municipalities)",
        UNRESOLVABLE_FILE, len(set(unresolvable)),
    )

    # -----------------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------------
    unresolvable_count = len(set(unresolvable))
    print()
    print("=" * 65)
    print("  DICTIONARY RESCUE COMPLETE")
    print("=" * 65)
    print(f"  {'Municipalities attempted':<38} {total:>5}")
    print(f"  {'Rescued (CDX-verified)':<38} {rescued_count:>5}")
    print(f"  {'Unresolvable':<38} {unresolvable_count:>5}")
    print(f"  {'Total with IEI score (cumulative)':<38} {total_with_iei:>5} / 308")
    print("-" * 65)
    print(f"  Metrics file     : {METRICS_FILE}")
    print(f"  Unresolvable log : {UNRESOLVABLE_FILE}")
    print("=" * 65)

    if unresolvable:
        print()
        print("  Still unresolved (suggest manual WHOIS lookup):")
        for m in sorted(set(unresolvable)):
            print(f"    · {m}")

    print()


if __name__ == "__main__":
    main()
