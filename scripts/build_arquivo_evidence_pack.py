#!/usr/bin/env python3
"""
build_arquivo_evidence_pack.py

Generates the Arquivo.pt Evidence Pack from local source artifacts.
The generated files are audit aids; this script does not query Arquivo.pt
or verify replay URLs.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)

CHECKPOINT_LIMIT_PER_DOMAIN = 5000
VALID_CHECKPOINT_STATUSES = {"200", "301", "302", "304"}
MEDIAN_IMPUTED = 628

CAPTURE_DENSITY_FORMULA = "Total_Arquivo_Captures / Pop. 2021"
DIGITAL_DECAY_SOURCE = "metricas_iei_completo.csv:Media_Dias_Entre_Capturas"
DIGITAL_DECAY_NOTE = (
    "VARIAVEL_TEMPORAL_LEGADA - importada de metricas_iei_completo.csv:"
    "Media_Dias_Entre_Capturas; fórmula de derivação original não totalmente "
    "recuperável no repositório actual"
)
CONFIRMED_METRICS_JSON = ROOT / "reports" / "confirmed_model_metrics.json"
ABLATION_SUMMARY_JSON = DATA / "arquivo_ablation_summary.json"
LEGACY_MODEL_METRICS_JSON = ROOT / "reports" / "model_metrics.json"

TIER_LABELS = {
    "TIER 1 - Resiliência": "Tier 1 — Resiliência",
    "TIER 2 - Estagnação": "Tier 2 — Estagnação",
    "TIER 3 - Risco de Fuga": "Tier 3 — Risco de Fuga",
    "TIER 4 - Profecia CASSANDRA": "Tier 4 — Risco Crítico",
}


def public_tier(raw: str) -> str:
    return TIER_LABELS.get(raw, raw)


def stable_id(name: str) -> str:
    return "MUN_" + hashlib.md5(name.encode()).hexdigest()[:8].upper()


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return text.strip().lower()


def normalize_label(value: object) -> str:
    text = normalize_text(value)
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text)
    return " ".join(cleaned.split())


def find_municipio_col(columns: list[str]) -> str:
    for col in columns:
        if "munic" in normalize_label(col):
            return col
    raise KeyError(f"Cannot find municipality column in {columns}")


def find_col(columns: list[str], candidates: list[str]) -> str:
    normalized = {col: normalize_label(col) for col in columns}
    for candidate in candidates:
        candidate_norm = normalize_label(candidate)
        for col, col_norm in normalized.items():
            if candidate_norm in col_norm:
                return col
    raise KeyError(f"None of {candidates} found in {columns}")


def load_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def keyed_rows(rows: list[dict[str, str]], municipio_col: str = "Município") -> dict[str, dict[str, str]]:
    return {
        normalize_text(row.get(municipio_col, "")): row
        for row in rows
        if row.get(municipio_col)
    }


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text or text.lower() in {"nan", "none"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fmt_num(value: float | int | str | None, precision: int = 12) -> str:
    number = to_float(value)
    if number is None:
        return ""
    return f"{number:.{precision}g}"


def ts_to_year(ts: str) -> str:
    if ts and len(ts) >= 4:
        return ts[:4]
    return ""


def generated_replay_url(timestamp: str, url: str) -> str:
    if timestamp and url:
        return f"https://arquivo.pt/wayback/{timestamp}/{url}"
    return ""


def load_pop_2021() -> tuple[dict[str, float], str, int]:
    dem_path = ROOT / "dados_demograficos.csv"
    df_dem = pd.read_excel(dem_path, header=1)
    mun_col = find_municipio_col(list(df_dem.columns))
    pop_col = find_col(
        list(df_dem.columns),
        ["Pop. 2021", "Pop_2021", "Pop2021", "População 2021"],
    )
    pop_by_key: dict[str, float] = {}
    for _, row in df_dem.iterrows():
        key = normalize_text(row.get(mun_col, ""))
        pop = to_float(row.get(pop_col))
        if key and pop is not None:
            pop_by_key[key] = pop
    return pop_by_key, pop_col, len(df_dem)


def find_ablation_artifacts() -> list[Path]:
    return sorted(
        p
        for p in ROOT.rglob("arquivo_ablation_results.json")
        if ".git" not in p.parts
    )


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


print("[1/6] Loading source files...")
mun_dom_rows = load_csv(ROOT / "municipios_dominios.csv")
fase2_rows = load_csv(ROOT / "metricas_fase2_completo.csv")
cassandra_rows = load_csv(ROOT / "relatorio_produto_cassandra.csv")
iei_rows = load_csv(ROOT / "metricas_iei_completo.csv")
temporal_rows = load_csv(DATA / "arquivo_temporal_features.csv")

mun_dom = {r["Município"]: r["Domain"] for r in mun_dom_rows if r.get("Município")}
mun_dom_keyed = keyed_rows(mun_dom_rows)
fase2 = keyed_rows(fase2_rows)
cassandra = keyed_rows(cassandra_rows)
iei = keyed_rows(iei_rows)
temporal = keyed_rows(temporal_rows)
pop_2021_by_key, pop_2021_col, demographic_rows = load_pop_2021()

print(f"  municipios_dominios: {len(mun_dom_rows)} rows")
print(f"  metricas_fase2_completo: {len(fase2_rows)} rows")
print(f"  relatorio_produto_cassandra: {len(cassandra_rows)} rows")
print(f"  metricas_iei_completo: {len(iei_rows)} rows")
print(f"  arquivo_temporal_features: {len(temporal_rows)} rows")
print(f"  dados_demograficos.csv: {demographic_rows} rows; population column '{pop_2021_col}'")

print("[2/6] Loading cdx_checkpoint.json...")
CDX_PATH = ROOT / "cdx_checkpoint.json"
with open(CDX_PATH, encoding="utf-8") as f:
    cdx_data = json.load(f)
print(f"  Domains in local checkpoint: {len(cdx_data)}")
total_checkpoint_cdx_records = sum(len(v) for v in cdx_data.values())
domains_at_checkpoint_limit = sum(1 for v in cdx_data.values() if len(v) == CHECKPOINT_LIMIT_PER_DOMAIN)
print(f"  Local checkpoint CDX records: {total_checkpoint_cdx_records}")
print(f"  Domains at {CHECKPOINT_LIMIT_PER_DOMAIN}-record cap: {domains_at_checkpoint_limit}/{len(cdx_data)}")

print("[3/6] Building per-domain checkpoint statistics...")
cdx_stats: dict[str, dict[str, Any]] = {}
for domain, records in cdx_data.items():
    if not records:
        cdx_stats[domain] = {}
        continue
    timestamps = [r.get("timestamp", "") for r in records if r.get("timestamp")]
    timestamps_sorted = sorted(timestamps)
    years = [ts[:4] for ts in timestamps_sorted if len(ts) >= 4]
    statuses = [str(r.get("status", "")) for r in records]
    mimes = [str(r.get("mime", "")) for r in records]
    digests = {r.get("digest", "") for r in records if r.get("digest")}
    valid_captures = [
        r for r in records if str(r.get("status", "")) in VALID_CHECKPOINT_STATUSES
    ]
    cdx_stats[domain] = {
        "checkpoint_count": len(records),
        "checkpoint_valid_count": len(valid_captures),
        "first_ts": timestamps_sorted[0] if timestamps_sorted else "",
        "last_ts": timestamps_sorted[-1] if timestamps_sorted else "",
        "first_year": years[0] if years else "",
        "last_year": years[-1] if years else "",
        "active_years": len(set(years)),
        "unique_digests": len(digests),
        "s200": sum(1 for s in statuses if s == "200"),
        "s3xx": sum(1 for s in statuses if s.startswith("3")),
        "s4xx": sum(1 for s in statuses if s.startswith("4")),
        "s5xx": sum(1 for s in statuses if s.startswith("5")),
        "html": sum(1 for m in mimes if "html" in m),
        "pdf": sum(1 for m in mimes if "pdf" in m),
        "image": sum(1 for m in mimes if m.startswith("image")),
        "records": records,
    }
print(f"  Checkpoint stats built for {len(cdx_stats)} domains")

print("[4/6] Building evidence summary CSV...")
SUMMARY_COLS = [
    "municipality_id",
    "municipality_name",
    "domain",
    "tier_public_label",
    "checkpoint_cdx_record_count",
    "checkpoint_valid_capture_count",
    "model_total_arquivo_captures",
    "capture_count_imputed",
    "imputation_note",
    "first_capture_timestamp",
    "last_capture_timestamp",
    "first_capture_year",
    "last_capture_year",
    "active_years_count",
    "unique_digest_count",
    "status_200_count",
    "status_3xx_count",
    "status_4xx_count",
    "status_5xx_count",
    "mime_html_count",
    "mime_pdf_count",
    "mime_image_count",
    "checkpoint_capture_source",
    "model_capture_source",
    "capture_density",
    "digital_decay_rate",
    "digital_decay_rate_source",
    "digital_decay_rate_formula_status",
    "risk_score",
    "evidence_quality_flag",
]

all_municipalities = sorted(
    {
        *[r["Município"] for r in mun_dom_rows if r.get("Município")],
        *[r["Município"] for r in cassandra_rows if r.get("Município")],
        *[r["Município"] for r in iei_rows if r.get("Município")],
    },
    key=normalize_text,
)

summary_rows: list[dict[str, Any]] = []
imputed_count = 0
needs_review_count = 0

for mun in all_municipalities:
    mun_key = normalize_text(mun)
    dom_row = mun_dom_keyed.get(mun_key, {})
    domain = dom_row.get("Domain", mun_dom.get(mun, ""))
    cas = cassandra.get(mun_key, {})
    f2 = fase2.get(mun_key, {})
    iei_row = iei.get(mun_key, {})
    cdx = cdx_stats.get(domain, {}) if domain else {}

    mun_id = stable_id(mun)
    tier_label = public_tier(cas.get("CASSANDRA_Risk_Tier", ""))
    risk_score = cas.get("CASSANDRA_Risk_Score", "")

    checkpoint_count = cdx.get("checkpoint_count", 0)
    checkpoint_valid_count = cdx.get("checkpoint_valid_count", 0)

    model_val = to_float(cas.get("Total_Arquivo_Captures", ""))
    f2_val = to_float(f2.get("Total_Arquivo_Captures", ""))
    pop_2021 = pop_2021_by_key.get(mun_key)

    imputed = False
    imputation_note = ""
    if model_val is not None and f2_val is not None:
        if f2_val == 0 and model_val == MEDIAN_IMPUTED:
            imputed = True
            imputation_note = f"fase2 raw=0; model used median imputed value={MEDIAN_IMPUTED}"
            imputed_count += 1
        elif f2_val > 0 and model_val != f2_val:
            imputation_note = f"fase2 raw={fmt_num(f2_val)}; model value={fmt_num(model_val)}"
        else:
            imputation_note = "raw value used directly"
    elif model_val == MEDIAN_IMPUTED:
        imputed = True
        imputation_note = f"model value={MEDIAN_IMPUTED} matches known imputed median"
        imputed_count += 1

    capture_density = ""
    if model_val is not None and pop_2021 not in (None, 0):
        capture_density = fmt_num(model_val / pop_2021)

    digital_decay_rate = fmt_num(iei_row.get("Media_Dias_Entre_Capturas", ""))

    quality_flag = "ok"
    if not domain:
        quality_flag = "needs_manual_review"
        needs_review_count += 1
    elif not cdx:
        quality_flag = "no_checkpoint_cdx_data"
    elif imputed:
        quality_flag = "imputed"

    summary_rows.append(
        {
            "municipality_id": mun_id,
            "municipality_name": mun,
            "domain": domain,
            "tier_public_label": tier_label,
            "checkpoint_cdx_record_count": checkpoint_count,
            "checkpoint_valid_capture_count": checkpoint_valid_count,
            "model_total_arquivo_captures": model_val if model_val is not None else "",
            "capture_count_imputed": "yes" if imputed else "no",
            "imputation_note": imputation_note,
            "first_capture_timestamp": cdx.get("first_ts", ""),
            "last_capture_timestamp": cdx.get("last_ts", ""),
            "first_capture_year": cdx.get("first_year", ""),
            "last_capture_year": cdx.get("last_year", ""),
            "active_years_count": cdx.get("active_years", ""),
            "unique_digest_count": cdx.get("unique_digests", ""),
            "status_200_count": cdx.get("s200", ""),
            "status_3xx_count": cdx.get("s3xx", ""),
            "status_4xx_count": cdx.get("s4xx", ""),
            "status_5xx_count": cdx.get("s5xx", ""),
            "mime_html_count": cdx.get("html", ""),
            "mime_pdf_count": cdx.get("pdf", ""),
            "mime_image_count": cdx.get("image", ""),
            "checkpoint_capture_source": "cdx_checkpoint.json (local capped checkpoint)" if cdx else "",
            "model_capture_source": "relatorio_produto_cassandra.csv",
            "capture_density": capture_density,
            "digital_decay_rate": digital_decay_rate,
            "digital_decay_rate_source": DIGITAL_DECAY_SOURCE if digital_decay_rate else "",
            "digital_decay_rate_formula_status": DIGITAL_DECAY_NOTE if digital_decay_rate else "",
            "risk_score": risk_score,
            "evidence_quality_flag": quality_flag,
        }
    )

out_summary = DATA / "arquivo_evidence_summary.csv"
with open(out_summary, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=SUMMARY_COLS)
    writer.writeheader()
    writer.writerows(summary_rows)
print(f"  Wrote {len(summary_rows)} rows -> {out_summary.name}")
print(f"  Imputed: {imputed_count}; needs review: {needs_review_count}")

print("[5/6] Building capture samples CSV...")
SAMPLE_COLS = [
    "municipality_id",
    "municipality_name",
    "domain",
    "sample_type",
    "url",
    "timestamp",
    "year",
    "mime",
    "status",
    "digest",
    "filename",
    "collection",
    "source",
    "generated_arquivo_replay_url",
    "replay_url_verified",
]

sample_rows: list[dict[str, Any]] = []
for row in summary_rows:
    mun = row["municipality_name"]
    domain = row["domain"]
    mun_id = row["municipality_id"]
    records = cdx_stats.get(domain, {}).get("records", [])
    if not records:
        continue
    sorted_recs = sorted(records, key=lambda r: r.get("timestamp", ""))
    n = len(sorted_recs)
    indices = set()
    for i in range(min(3, n)):
        indices.add(i)
    for i in range(max(0, n - 3), n):
        indices.add(i)
    if n > 6:
        step = n // 5
        for k in range(1, 5):
            indices.add(min(k * step, n - 1))
    for idx in sorted(indices):
        record = sorted_recs[idx]
        ts = record.get("timestamp", "")
        url = record.get("url", "")
        if idx < 3:
            sample_type = "earliest"
        elif idx >= n - 3:
            sample_type = "latest"
        else:
            sample_type = "spread"
        sample_rows.append(
            {
                "municipality_id": mun_id,
                "municipality_name": mun,
                "domain": domain,
                "sample_type": sample_type,
                "url": url,
                "timestamp": ts,
                "year": ts_to_year(ts),
                "mime": record.get("mime", ""),
                "status": record.get("status", ""),
                "digest": record.get("digest", ""),
                "filename": record.get("filename", ""),
                "collection": record.get("collection", ""),
                "source": record.get("source", ""),
                "generated_arquivo_replay_url": generated_replay_url(ts, url),
                "replay_url_verified": "false",
            }
        )

out_samples = DATA / "arquivo_capture_samples.csv"
with open(out_samples, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=SAMPLE_COLS)
    writer.writeheader()
    writer.writerows(sample_rows)
print(f"  Wrote {len(sample_rows)} sample rows -> {out_samples.name}")

print("[6/6] Building feature audit CSV, JSON, and docs...")
AUDIT_COLS = [
    "municipality_id",
    "municipality_name",
    "domain",
    "raw_total_arquivo_captures",
    "model_total_arquivo_captures",
    "capture_count_imputed",
    "capture_density",
    "capture_density_formula",
    "digital_decay_rate",
    "digital_decay_rate_source",
    "digital_decay_rate_formula_status",
    "total_arquivo_captures_enters_model",
    "capture_density_enters_model",
    "digital_decay_rate_enters_model",
    "tier_public_label",
    "notes",
]

audit_rows: list[dict[str, Any]] = []
for row in summary_rows:
    mun = row["municipality_name"]
    mun_key = normalize_text(mun)
    domain = row["domain"]
    f2 = fase2.get(mun_key, {})
    notes = []
    if row["capture_count_imputed"] == "yes":
        notes.append("Capture count imputed with median value.")
    if not domain:
        notes.append("Domain unknown; municipality_id is hash-generated.")
    if not cdx_stats.get(domain):
        notes.append("No local checkpoint CDX records found for domain.")
    if not row["capture_density"]:
        notes.append("capture_density unavailable because model count or Pop. 2021 is missing.")
    audit_rows.append(
        {
            "municipality_id": row["municipality_id"],
            "municipality_name": mun,
            "domain": domain,
            "raw_total_arquivo_captures": f2.get("Total_Arquivo_Captures", ""),
            "model_total_arquivo_captures": row["model_total_arquivo_captures"],
            "capture_count_imputed": row["capture_count_imputed"],
            "capture_density": row["capture_density"],
            "capture_density_formula": CAPTURE_DENSITY_FORMULA,
            "digital_decay_rate": row["digital_decay_rate"],
            "digital_decay_rate_source": row["digital_decay_rate_source"],
            "digital_decay_rate_formula_status": row["digital_decay_rate_formula_status"],
            "total_arquivo_captures_enters_model": "yes",
            "capture_density_enters_model": "yes" if row["capture_density"] else "unknown",
            "digital_decay_rate_enters_model": "yes" if row["digital_decay_rate"] else "unknown",
            "tier_public_label": row["tier_public_label"],
            "notes": " | ".join(notes) if notes else "ok",
        }
    )

out_audit = DATA / "arquivo_feature_audit.csv"
with open(out_audit, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=AUDIT_COLS)
    writer.writeheader()
    writer.writerows(audit_rows)
print(f"  Wrote {len(audit_rows)} rows -> {out_audit.name}")

confirmed_metrics = load_json(CONFIRMED_METRICS_JSON)
arquivo_ablation_summary = load_json(ABLATION_SUMMARY_JSON)

featured_names = ["Alcácer do Sal", "Torres Vedras", "Proença-a-Nova"]
featured_cases: dict[str, dict[str, Any]] = {}
for name in featured_names:
    sr = next((r for r in summary_rows if r["municipality_name"] == name), {})
    domain = sr.get("domain", "")
    cdx = cdx_stats.get(domain, {})
    featured_cases[name] = {
        "municipality_id": sr.get("municipality_id", ""),
        "domain": domain,
        "tier_public_label": sr.get("tier_public_label", ""),
        "risk_score": sr.get("risk_score", ""),
        "checkpoint_cdx_record_count": cdx.get("checkpoint_count", ""),
        "checkpoint_valid_capture_count": cdx.get("checkpoint_valid_count", ""),
        "model_total_arquivo_captures": sr.get("model_total_arquivo_captures", ""),
        "capture_count_imputed": sr.get("capture_count_imputed", ""),
        "imputation_note": sr.get("imputation_note", ""),
        "first_capture_year": cdx.get("first_year", ""),
        "last_capture_year": cdx.get("last_year", ""),
        "active_years_count": cdx.get("active_years", ""),
        "capture_density": sr.get("capture_density", ""),
        "digital_decay_rate": sr.get("digital_decay_rate", ""),
        "digital_decay_rate_source": sr.get("digital_decay_rate_source", ""),
        "evidence_quality_flag": sr.get("evidence_quality_flag", ""),
    }

ablation_artifacts = find_ablation_artifacts()
ablation_summary = {
    "arquivo_ablation_results_json": (
        [str(p.relative_to(ROOT)) for p in ablation_artifacts]
        if ablation_artifacts
        else "NOT_FOUND"
    ),
    "summary_json": str(ABLATION_SUMMARY_JSON.relative_to(ROOT)),
    "validated": bool(arquivo_ablation_summary.get("validated", False)),
    "note": (
        "Confirmed public ablation metrics are loaded from "
        "reports/confirmed_model_metrics.json and data/arquivo_ablation_summary.json; "
        "raw restored ablation values live in arquivo_ablation_results.json when present."
    ),
    "with_arquivo": arquivo_ablation_summary.get("with_arquivo", confirmed_metrics.get("with_arquivo")),
    "without_arquivo": arquivo_ablation_summary.get("without_arquivo", confirmed_metrics.get("without_arquivo")),
    "delta": arquivo_ablation_summary.get("delta", confirmed_metrics.get("delta")),
    "source": (
        "reports/confirmed_model_metrics.json and data/arquivo_ablation_summary.json"
    ),
}

pack = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "source_files": {
        "local_cdx_checkpoint": (
            "cdx_checkpoint.json (local capped checkpoint; not exposed publicly)"
        ),
        "municipios_dominios": "municipios_dominios.csv",
        "metricas_fase2_completo": "metricas_fase2_completo.csv",
        "metricas_iei_completo": "metricas_iei_completo.csv",
        "dados_demograficos": "dados_demograficos.csv",
        "relatorio_produto_cassandra": "relatorio_produto_cassandra.csv",
        "arquivo_temporal_features": "data/arquivo_temporal_features.csv",
        "legacy_internal_model_metrics": str(LEGACY_MODEL_METRICS_JSON.relative_to(ROOT)),
        "confirmed_public_model_metrics": str(CONFIRMED_METRICS_JSON.relative_to(ROOT)),
        "arquivo_ablation_summary": str(ABLATION_SUMMARY_JSON.relative_to(ROOT)),
        "arquivo_ablation_results": "arquivo_ablation_results.json",
    },
    "field_notes": {
        "checkpoint_cdx_record_count": (
            "checkpoint_cdx_record_count reflects records available in the local capped "
            "checkpoint, not a complete historical total of all Arquivo.pt captures."
        ),
        "checkpoint_valid_capture_count": (
            "checkpoint_valid_capture_count conta registos do checkpoint com status 200, "
            "301, 302 ou 304."
        ),
        "generated_arquivo_replay_url": (
            "Gerado sintaticamente a partir do timestamp e do URL; replay_url_verified "
            "fica false enquanto não existir verificação por script dedicado."
        ),
    },
    "model_feature_formulas": {
        "capture_density": CAPTURE_DENSITY_FORMULA,
        "digital_decay_rate": DIGITAL_DECAY_SOURCE,
        "digital_decay_rate_limit": (
            "A fórmula de derivação original não é totalmente recuperável no repositório actual."
        ),
    },
    "metrics_source": {
        "status": "CONFIRMED_PUBLIC_METRICS",
        "source_files": [
            str(CONFIRMED_METRICS_JSON.relative_to(ROOT)),
            str(ABLATION_SUMMARY_JSON.relative_to(ROOT)),
            "arquivo_ablation_results.json",
        ],
        "with_arquivo": confirmed_metrics["with_arquivo"],
        "without_arquivo": confirmed_metrics["without_arquivo"],
        "delta": confirmed_metrics["delta"],
        "public_framing": confirmed_metrics.get("public_framing", ""),
        "legacy_internal_note": (
            "reports/model_metrics.json is retained only as an internal macro-F1/"
            "per-tier artifact and is not the public metric source."
        ),
    },
    "total_municipalities": len(summary_rows),
    "total_checkpoint_cdx_records": total_checkpoint_cdx_records,
    "checkpoint_domains": len(cdx_data),
    "checkpoint_record_cap_per_domain": CHECKPOINT_LIMIT_PER_DOMAIN,
    "checkpoint_domains_at_record_cap": domains_at_checkpoint_limit,
    "total_sample_records": len(sample_rows),
    "imputed_capture_count_municipalities": imputed_count,
    "municipalities_needing_manual_review": needs_review_count,
    "formula_warnings": [
        "Os contadores do checkpoint CDX são evidência local limitada, não valores de entrada do modelo.",
        f"capture_density = {CAPTURE_DENSITY_FORMULA}",
        (
            "digital_decay_rate é importada como variável temporal legada a partir de "
            "metricas_iei_completo.csv:Media_Dias_Entre_Capturas. A fórmula original "
            "não é totalmente recuperável no repositório actual."
        ),
        (
            f"Imputation marker: model values equal to {MEDIAN_IMPUTED}.0 when fase2 raw=0 "
            "are treated as median-imputed."
        ),
    ],
    "featured_cases": featured_cases,
    "ablation_summary": ablation_summary,
}

out_json = DATA / "arquivo_evidence_pack.json"
with open(out_json, "w", encoding="utf-8") as f:
    json.dump(pack, f, ensure_ascii=False, indent=2)
print(f"  Wrote -> {out_json.name}")

alcacer = featured_cases["Alcácer do Sal"]
md = """# Pacote de Evidências Arquivo.pt — CASSANDRA
## Documento para Auditoria por Júri

**Gerado em:** {generated_at}
**Fonte de métricas públicas confirmadas:** `reports/confirmed_model_metrics.json` e `data/arquivo_ablation_summary.json`

---

## 1. O que contém o checkpoint CDX local?

O checkpoint CDX local não publicado contém registos CDX extraídos da API pública do Arquivo.pt para domínios municipais portugueses. Cada registo inclui URL, timestamp, MIME type, HTTP status, digest, filename, collection e source.

Este checkpoint não é copiado para a documentação nem publicado como anexo. O checkpoint tem {total_checkpoint_cdx_records:,} registos para {checkpoint_domains} domínios; {domains_at_checkpoint_limit}/{checkpoint_domains} domínios estão exatamente no limite local de {checkpoint_limit} registos definido por `cassandra_opcao_a.py`.

**Definição crítica:** `checkpoint_cdx_record_count` reflecte os registos disponíveis no checkpoint local limitado; não é um total histórico completo de todas as capturas Arquivo.pt.

**Definição de validade:** `checkpoint_valid_capture_count` conta registos do checkpoint com status 200, 301, 302 ou 304.

---

## 2. Diferença entre checkpoint e variáveis do modelo

| Conceito | Fonte | Significado |
|---|---|---|
| `checkpoint_cdx_record_count` | checkpoint CDX local não publicado | Número de registos disponíveis no checkpoint local limitado; não é total histórico completo |
| `checkpoint_valid_capture_count` | checkpoint CDX local não publicado | Registos do checkpoint com status 200, 301, 302 ou 304 |
| `model_total_arquivo_captures` | `relatorio_produto_cassandra.csv` | Valor de `Total_Arquivo_Captures` usado pelo modelo |
| `capture_count_imputed` | derivado | `yes` quando o modelo usou o valor mediano ({median_imputed}) em vez do valor bruto da fase 2 |

Os campos do checkpoint são evidência de proveniência local. Não são apresentados como valores de entrada do modelo.

---

## 3. Como é calculado `Total_Arquivo_Captures`?

O valor de fase 2 vem de `extrator_fase2_avancado.py`, que consulta `https://arquivo.pt/wayback/cdx` com `url=domain`, `from=20110101`, `to=20211231`, `output=json` e `fl=timestamp`, e conta as linhas de timestamp devolvidas. O valor no modelo (`relatorio_produto_cassandra.csv`) reflete este valor ou, quando o valor bruto de fase 2 é zero, a imputação mediana usada pelo pipeline.

---

## 4. `capture_density`

Fórmula do modelo:

`capture_density = Total_Arquivo_Captures / Pop. 2021`

No Evidence Pack, `capture_density` é calculada com `model_total_arquivo_captures` e a coluna demográfica `Pop. 2021`, seguindo `modelo_preditivo_real.py` e `scripts/generate_charts.py`.

---

## 5. `digital_decay_rate`

`digital_decay_rate` é importada como variável temporal legada a partir de `metricas_iei_completo.csv:Media_Dias_Entre_Capturas`. A fórmula de derivação original não é totalmente recuperável no repositório actual.

Por isso, este campo é auditável ao nível de coluna-fonte, mas não deve ser descrito como fórmula plenamente recuperada.

---

## Robustez metodológica: variáveis Arquivo Core

As variáveis Arquivo Core totalmente auditáveis são `Total_Arquivo_Captures` e `capture_density`. A primeira corresponde ao valor de entrada do modelo, com distinção explícita face aos contadores de checkpoint. A segunda é calculada por fórmula directa:

`capture_density = Total_Arquivo_Captures / Pop. 2021`

`digital_decay_rate` mantém proveniência de coluna documentada, mas tem limitação assumida quanto à fórmula original. Por esse motivo, o argumento central da candidatura não deve depender exclusivamente desta variável temporal legada.

O projecto inclui agora o `Arquivo Core Robustness Check`, com resumo em `data/arquivo_core_robustness_summary.json`, para testar a contribuição funcional mensurável das variáveis Arquivo.pt sem reforçar artificialmente a variável legada. Quando o resultado for fraco ou conservador, deve ser comunicado como limitação metodológica e não como substituto da ablação pública validada.

---

## 6. Porque os contadores do checkpoint diferem de `Total_Arquivo_Captures`

Exemplo: Alcácer do Sal

- `checkpoint_cdx_record_count`: {alcacer_checkpoint}
- `checkpoint_valid_capture_count`: {alcacer_valid}
- `model_total_arquivo_captures`: {alcacer_model_total}

A diferença é esperada:

- o checkpoint CDX usa `domain/*`, não a mesma janela temporal, e está limitado a {checkpoint_limit} registos;
- a extração de fase 2/modelo usa `from=20110101`, `to=20211231`, `url=domain`, e conta linhas de timestamp devolvidas;
- portanto, os contadores do checkpoint são evidência de proveniência, não a mesma métrica de `Total_Arquivo_Captures`.

---

## 7. Ligações de replay

O campo `generated_arquivo_replay_url` é gerado sintaticamente como:

`https://arquivo.pt/wayback/{{timestamp}}/{{url}}`

Estas ligações não são verificadas por este script. O campo `replay_url_verified` fica `false` em todas as linhas geradas.

---

## 8. Estado da ablação

As métricas públicas confirmadas são:

- **Com Arquivo.pt:** exatidão global {with_accuracy:.2f}%; F1 ponderado {with_weighted_f1:.2f}%
- **Sem Arquivo.pt:** exatidão global {without_accuracy:.2f}%; F1 ponderado {without_weighted_f1:.2f}%

Estas métricas vêm de `reports/confirmed_model_metrics.json` e `data/arquivo_ablation_summary.json`, com valores brutos restaurados em `arquivo_ablation_results.json` quando presente. `reports/model_metrics.json` é um artefacto interno legado de macro-F1/per-tier e não é a fonte das métricas públicas.

**Nota conservadora:** A remoção das variáveis derivadas do Arquivo.pt corresponde a {accuracy_delta:.2f} pp de exatidão e {weighted_f1_delta:.2f} pp de F1 ponderado. Isto suporta evidência por ablação e enquadramento de sistema de apoio à decisão.

---

## 9. Limitações restantes

- O checkpoint CDX é limitado localmente e não representa totais históricos completos.
- `digital_decay_rate` tem proveniência de coluna, mas a fórmula original não está totalmente recuperável no repositório atual.
- O `Arquivo Core Robustness Check` é uma verificação secundária e não substitui as métricas públicas confirmadas.
- As ligações `generated_arquivo_replay_url` são geradas, não verificadas.
- Valores SHAP, probabilidades individuais, métricas de ablação e fórmulas ausentes no repositório não foram inventados.
- O checkpoint CDX local não está incluído nem ligado como download público.

---

## Ficheiros gerados

| Ficheiro | Descrição |
|---|---|
| `data/arquivo_evidence_summary.csv` | Resumo por município/domínio |
| `data/arquivo_capture_samples.csv` | Amostras de capturas CDX por município |
| `data/arquivo_feature_audit.csv` | Auditoria de variáveis de modelo |
| `data/arquivo_evidence_pack.json` | Pacote JSON compacto para auditoria |
| `data/arquivo_core_robustness_summary.json` | Verificação secundária de robustez das variáveis Arquivo Core |
| `docs/DIGITAL_DECAY_RATE_PROVENANCE.md` | Nota de proveniência e limitação de `digital_decay_rate` |
| `docs/ARQUIVO_EVIDENCE_PACK.md` | Este documento |
""".format(
    generated_at=pack["generated_at"],
    total_checkpoint_cdx_records=total_checkpoint_cdx_records,
    checkpoint_domains=len(cdx_data),
    domains_at_checkpoint_limit=domains_at_checkpoint_limit,
    checkpoint_limit=CHECKPOINT_LIMIT_PER_DOMAIN,
    median_imputed=MEDIAN_IMPUTED,
    alcacer_checkpoint=alcacer["checkpoint_cdx_record_count"],
    alcacer_valid=alcacer["checkpoint_valid_capture_count"],
    alcacer_model_total=fmt_num(alcacer["model_total_arquivo_captures"]),
    with_accuracy=confirmed_metrics["with_arquivo"]["accuracy"] * 100,
    with_weighted_f1=confirmed_metrics["with_arquivo"]["weighted_f1"] * 100,
    without_accuracy=confirmed_metrics["without_arquivo"]["accuracy"] * 100,
    without_weighted_f1=confirmed_metrics["without_arquivo"]["weighted_f1"] * 100,
    accuracy_delta=confirmed_metrics["delta"]["accuracy_pp"],
    weighted_f1_delta=confirmed_metrics["delta"]["weighted_f1_pp"],
)

out_md = DOCS / "ARQUIVO_EVIDENCE_PACK.md"
with open(out_md, "w", encoding="utf-8") as f:
    f.write(md)
print(f"  Wrote -> {out_md.name}")

print("\n=== VALIDATION REPORT ===")
validation_errors: list[str] = []

if len(summary_rows) != 308:
    validation_errors.append(f"Expected 308 municipalities, found {len(summary_rows)}")

summary_header = list(csv.DictReader(open(out_summary, encoding="utf-8")).fieldnames or [])
sample_header = list(csv.DictReader(open(out_samples, encoding="utf-8")).fieldnames or [])
audit_header = list(csv.DictReader(open(out_audit, encoding="utf-8")).fieldnames or [])

for old_name in ["raw_cdx_record_count", "raw_valid_capture_count", "arquivo_replay_url"]:
    if old_name in summary_header or old_name in sample_header or old_name in audit_header:
        validation_errors.append(f"Deprecated field still present: {old_name}")

for required_name in [
    "checkpoint_cdx_record_count",
    "checkpoint_valid_capture_count",
    "generated_arquivo_replay_url",
    "replay_url_verified",
]:
    if required_name not in summary_header + sample_header:
        validation_errors.append(f"Required field missing: {required_name}")

json.loads(out_json.read_text(encoding="utf-8"))

density_mismatches = []
ddr_mismatches = []
for row in summary_rows:
    mun_key = normalize_text(row["municipality_name"])
    model_val = to_float(row["model_total_arquivo_captures"])
    pop_2021 = pop_2021_by_key.get(mun_key)
    density = to_float(row["capture_density"])
    if model_val is not None and pop_2021 not in (None, 0):
        expected = model_val / pop_2021
        if density is None or abs(density - expected) > 1e-10:
            density_mismatches.append(row["municipality_name"])
    expected_ddr = to_float(iei.get(mun_key, {}).get("Media_Dias_Entre_Capturas", ""))
    actual_ddr = to_float(row["digital_decay_rate"])
    if expected_ddr is not None and (actual_ddr is None or abs(actual_ddr - expected_ddr) > 1e-12):
        ddr_mismatches.append(row["municipality_name"])

if density_mismatches:
    validation_errors.append(f"capture_density mismatches: {density_mismatches[:5]}")
if ddr_mismatches:
    validation_errors.append(f"digital_decay_rate mismatches: {ddr_mismatches[:5]}")

bad_generated_links = [
    row for row in sample_rows
    if row["generated_arquivo_replay_url"]
    and not row["generated_arquivo_replay_url"].startswith("https://arquivo.pt/wayback/")
]
if bad_generated_links:
    validation_errors.append(f"Unexpected generated Arquivo.pt link format: {len(bad_generated_links)}")

verified_links = [row for row in sample_rows if row["replay_url_verified"] != "false"]
if verified_links:
    validation_errors.append(f"Replay URLs unexpectedly marked verified: {len(verified_links)}")

md_text = out_md.read_text(encoding="utf-8")
if re.search(r"\[[^\]]*cdx_checkpoint\.json[^\]]*\]\(", md_text):
    validation_errors.append("docs contain a public markdown link to cdx_checkpoint.json")
if "checkpoint_cdx_record_count reflects records available in the local capped checkpoint" not in md_text:
    validation_errors.append("checkpoint cap note missing from docs")
if "checkpoint_valid_capture_count counts checkpoint records with status 200, 301, 302, or 304" not in md_text:
    validation_errors.append("valid capture logic note missing from docs")
if "demonstra o contributo" in md_text or "prova sinal" in md_text:
    validation_errors.append("unsupported ablation claim remains in docs")

print(f"Municipalities in summary: {len(summary_rows)}")
print(f"Summary headers: OK")
print(f"Capture sample headers: OK")
print(f"Feature audit headers: OK")
print("JSON validates: OK")
print(f"Generated replay links with unexpected format: {len(bad_generated_links)}")
print(f"Replay URLs marked verified: {len(verified_links)}")
print(f"capture_density mismatches: {len(density_mismatches)}")
print(f"digital_decay_rate mismatches: {len(ddr_mismatches)}")
print("No markdown link to cdx_checkpoint.json in docs: OK")
print(f"arquivo_ablation_results.json present: {'yes' if ablation_artifacts else 'no'}")

print("\n--- Featured municipalities ---")
for name in featured_names:
    print(f"\n  {name}:")
    for key, value in featured_cases[name].items():
        print(f"    {key}: {value}")

print("\n--- Files written ---")
for path in [out_summary, out_samples, out_audit, out_json, out_md]:
    print(f"  {path.relative_to(ROOT)}: {path.stat().st_size:,} bytes")

if validation_errors:
    print("\nVALIDATION FAILED")
    for error in validation_errors:
        print(f"  - {error}")
    raise SystemExit(1)

print("\nVALIDATION PASSED")
print("Done.")
