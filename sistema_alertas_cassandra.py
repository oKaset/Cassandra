#!/usr/bin/env python3
"""
Build the final business-facing CASSANDRA Risk Tier dataset for all
308 Portuguese municipalities.
"""

from __future__ import annotations

import ast
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


EXPECTED_MUNICIPALITIES = 308
OUTPUT_COLUMNS = [
    "Município",
    "Var_Pop",
    "IEI_Score",
    "Total_Arquivo_Captures",
    "Live_StatusCode",
    "CASSANDRA_Risk_Tier",
]
TIER_ORDER = {
    "TIER 4 - Profecia CASSANDRA": 0,
    "TIER 3 - Risco de Fuga": 1,
    "TIER 2 - Estagnação": 2,
    "TIER 1 - Resiliência": 3,
    "TIER - Indeterminado": 4,
}
DEAD_STATUSES = {"Dead", "Timeout"}
USE_COLOR = os.getenv("NO_COLOR") is None


class Ansi:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    WHITE = "\033[97m"
    RED = "\033[38;5;196m"
    ORANGE = "\033[38;5;208m"
    YELLOW = "\033[38;5;226m"
    CYAN = "\033[38;5;51m"
    GREY = "\033[38;5;245m"


class DataValidationError(RuntimeError):
    """Raised when the municipality pipeline fails a hard validation."""


def style(text: str, *codes: str) -> str:
    if not USE_COLOR:
        return text
    return f"{''.join(codes)}{text}{Ansi.RESET}"


def print_step(message: str) -> None:
    print(style(f"[CASSANDRA] {message}", Ansi.BOLD, Ansi.WHITE))


def print_validation(message: str) -> None:
    print(style(f"[VALIDATION] {message}", Ansi.CYAN))


def print_error(message: str) -> None:
    print(style(f"[ERROR] {message}", Ansi.BOLD, Ansi.RED), file=sys.stderr)


def load_normalization_contract(
    script_path: Path,
) -> tuple[dict[str, str], Callable[[str], str]]:
    """
    Load the exact MAPPING_DICT and normalize_name() implementation from
    mapa_cassandra.py without executing that script's top-level side effects.
    """
    if not script_path.exists():
        raise DataValidationError(
            f"Normalization source not found: {script_path.name}"
        )

    source = script_path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(script_path))

    selected_nodes: list[ast.AST] = []
    found_names: set[str] = set()

    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MAPPING_DICT":
                    selected_nodes.append(node)
                    found_names.add("MAPPING_DICT")
                    break
        elif isinstance(node, ast.FunctionDef) and node.name in {
            "strip_accents",
            "normalize_name",
        }:
            selected_nodes.append(node)
            found_names.add(node.name)

    required_names = {"MAPPING_DICT", "strip_accents", "normalize_name"}
    missing_names = required_names - found_names
    if missing_names:
        missing_str = ", ".join(sorted(missing_names))
        raise DataValidationError(
            "Could not load exact normalization contract from "
            f"{script_path.name}. Missing definitions: {missing_str}"
        )

    compiled = compile(
        ast.Module(body=selected_nodes, type_ignores=[]),
        filename=str(script_path),
        mode="exec",
    )

    namespace: dict[str, object] = {
        "re": re,
        "unicodedata": unicodedata,
    }
    exec(compiled, namespace)

    mapping_dict = namespace.get("MAPPING_DICT")
    normalize_name = namespace.get("normalize_name")

    if not isinstance(mapping_dict, dict):
        raise DataValidationError("Loaded MAPPING_DICT is not a dictionary.")
    if not callable(normalize_name):
        raise DataValidationError("Loaded normalize_name is not callable.")

    return mapping_dict, normalize_name


def ensure_required_columns(
    df: pd.DataFrame,
    required_columns: list[str],
    source_name: str,
) -> None:
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        missing_str = ", ".join(missing)
        raise DataValidationError(
            f"{source_name} is missing required columns: {missing_str}"
        )


def detect_var_pop_column(df: pd.DataFrame) -> str:
    candidates = [
        str(column)
        for column in df.columns
        if "2011" in str(column) and "2021" in str(column)
    ]

    if not candidates:
        raise DataValidationError(
            "Could not detect the population-change column containing both "
            f"'2011' and '2021'. Available columns: {df.columns.tolist()}"
        )

    if len(candidates) > 1:
        raise DataValidationError(
            "Multiple candidate population-change columns detected: "
            f"{candidates}"
        )

    return candidates[0]


def load_demographics(base_dir: Path) -> pd.DataFrame:
    file_path = base_dir / "dados_demograficos.csv"
    df = pd.read_excel(file_path, header=1)
    ensure_required_columns(df, ["Município"], file_path.name)

    var_pop_column = detect_var_pop_column(df)
    print_validation(
        f"Demographic population-change column detected: '{var_pop_column}' -> 'Var_Pop'"
    )

    return df.rename(columns={var_pop_column: "Var_Pop"})


def load_iei_metrics(base_dir: Path) -> pd.DataFrame:
    file_path = base_dir / "metricas_iei_completo.csv"
    df = pd.read_csv(file_path, encoding="utf-8-sig")
    ensure_required_columns(df, ["Município", "IEI_Score"], file_path.name)
    return df


def load_phase2_metrics(base_dir: Path) -> pd.DataFrame:
    file_path = base_dir / "metricas_fase2_avancadas.csv"
    df = pd.read_csv(file_path, encoding="utf-8-sig")
    ensure_required_columns(
        df,
        ["Município", "Live_StatusCode", "Total_Arquivo_Captures"],
        file_path.name,
    )
    return df


def prepare_source(
    df: pd.DataFrame,
    source_name: str,
    normalize_name: Callable[[str], str],
) -> pd.DataFrame:
    prepared = df.copy()
    prepared["Município"] = (
        prepared["Município"]
        .where(prepared["Município"].notna(), "")
        .astype(str)
        .str.strip()
    )
    prepared["mun_key"] = prepared["Município"].map(normalize_name)

    blank_keys = prepared["mun_key"].eq("")
    if blank_keys.any():
        rows = prepared.loc[blank_keys, ["Município"]]
        print_error(f"{source_name} contains blank municipality keys:")
        for value in rows["Município"].tolist():
            print(f"  - {value!r}", file=sys.stderr)
        raise DataValidationError(
            f"{source_name} contains blank municipality keys after normalization."
        )

    duplicate_rows = prepared.loc[
        prepared["mun_key"].duplicated(keep=False),
        ["Município", "mun_key"],
    ].sort_values(["mun_key", "Município"])
    if not duplicate_rows.empty:
        print_error(f"Duplicate municipality keys detected in {source_name}:")
        for row in duplicate_rows.itertuples(index=False):
            print(f"  - {row.Município} [{row.mun_key}]", file=sys.stderr)
        raise DataValidationError(
            f"Duplicate municipality keys detected in {source_name}."
        )

    print_validation(
        f"{source_name}: rows={len(prepared)} | unique_normalized={prepared['mun_key'].nunique()}"
    )
    return prepared


def build_label_lookup(frames: dict[str, pd.DataFrame]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for frame in frames.values():
        for row in frame[["mun_key", "Município"]].itertuples(index=False):
            lookup.setdefault(row.mun_key, row.Município)
    return lookup


def print_key_list(title: str, keys: list[str], label_lookup: dict[str, str]) -> None:
    print_error(f"{title} ({len(keys)}):")
    for key in keys:
        label = label_lookup.get(key, key)
        print(f"  - {label} [{key}]", file=sys.stderr)


def validate_key_coverage(frames: dict[str, pd.DataFrame]) -> None:
    key_sets = {
        source_name: set(frame["mun_key"])
        for source_name, frame in frames.items()
    }
    all_keys = set().union(*key_sets.values())
    common_keys = set.intersection(*key_sets.values())

    if all_keys != common_keys:
        label_lookup = build_label_lookup(frames)
        print_error("Municipality coverage mismatch across sources.")
        for source_name, keys in key_sets.items():
            missing_keys = sorted(all_keys - keys)
            extra_keys = sorted(keys - common_keys)
            if missing_keys:
                print_key_list(
                    f"Missing from {source_name}",
                    missing_keys,
                    label_lookup,
                )
            if extra_keys:
                print_key_list(
                    f"Only present in {source_name}",
                    extra_keys,
                    label_lookup,
                )
        raise DataValidationError(
            "Source municipality coverage is not perfectly aligned."
        )

    if len(all_keys) != EXPECTED_MUNICIPALITIES:
        raise DataValidationError(
            "Expected "
            f"{EXPECTED_MUNICIPALITIES} unique municipalities across sources, "
            f"but found {len(all_keys)}."
        )

    print_validation(
        f"Municipality coverage aligned across all sources: {len(all_keys)} unique keys"
    )


def build_final_dataset(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df_phase2 = frames["metricas_fase2_avancadas.csv"][
        ["mun_key", "Município", "Live_StatusCode", "Total_Arquivo_Captures"]
    ].copy()
    df_iei = frames["metricas_iei_completo.csv"][["mun_key", "IEI_Score"]].copy()
    df_demo = frames["dados_demograficos.csv"][["mun_key", "Var_Pop"]].copy()

    merged = df_phase2.merge(
        df_iei,
        on="mun_key",
        how="left",
        validate="one_to_one",
    )
    merged = merged.merge(
        df_demo,
        on="mun_key",
        how="left",
        validate="one_to_one",
    )

    print_validation(f"Final merged row count: {len(merged)}")

    duplicate_rows = merged.loc[
        merged["mun_key"].duplicated(keep=False),
        ["Município", "mun_key"],
    ]
    if not duplicate_rows.empty:
        print_error("Duplicate municipality keys detected after final merge.")
        for row in duplicate_rows.sort_values(["mun_key", "Município"]).itertuples(
            index=False
        ):
            print(f"  - {row.Município} [{row.mun_key}]", file=sys.stderr)
        raise DataValidationError(
            "Final merged dataset contains duplicate municipality keys."
        )

    print_validation("Duplicate-key check: OK")

    if len(merged) != EXPECTED_MUNICIPALITIES:
        missing_rows = merged.loc[
            merged[["IEI_Score", "Var_Pop"]].isna().any(axis=1),
            ["Município", "mun_key"],
        ]
        if not missing_rows.empty:
            print_error("Potentially unmatched municipalities after merge:")
            for row in missing_rows.itertuples(index=False):
                print(f"  - {row.Município} [{row.mun_key}]", file=sys.stderr)
        raise DataValidationError(
            "Final merged dataset must contain exactly "
            f"{EXPECTED_MUNICIPALITIES} rows, found {len(merged)}."
        )

    return merged


def coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    coerced = df.copy()
    coerced["Var_Pop"] = pd.to_numeric(coerced["Var_Pop"], errors="coerce")
    coerced["IEI_Score"] = pd.to_numeric(coerced["IEI_Score"], errors="coerce")
    coerced["Total_Arquivo_Captures"] = pd.to_numeric(
        coerced["Total_Arquivo_Captures"],
        errors="coerce",
    ).astype("Int64")
    return coerced


def bucket_live_status(value: object) -> str:
    if pd.isna(value):
        return ""
    normalized = str(value).strip()
    if not normalized:
        return ""
    if normalized in DEAD_STATUSES:
        return normalized
    return "Active"


def assign_risk_tiers(df: pd.DataFrame) -> pd.DataFrame:
    classified = coerce_numeric_columns(df)
    status_bucket = classified["Live_StatusCode"].map(bucket_live_status)

    tier4 = classified["Var_Pop"].lt(0) & status_bucket.isin(DEAD_STATUSES)
    tier3 = classified["Var_Pop"].lt(-5) | (
        classified["IEI_Score"].le(50) & status_bucket.eq("Active")
    )
    tier2 = (
        classified["Var_Pop"].ge(-5)
        & classified["Var_Pop"].lt(0)
        & classified["IEI_Score"].gt(50)
    )
    tier1 = classified["Var_Pop"].ge(0) & status_bucket.eq("Active")

    classified["CASSANDRA_Risk_Tier"] = np.select(
        [tier4, tier3, tier2, tier1],
        [
            "TIER 4 - Profecia CASSANDRA",
            "TIER 3 - Risco de Fuga",
            "TIER 2 - Estagnação",
            "TIER 1 - Resiliência",
        ],
        default="TIER - Indeterminado",
    )
    return classified


def sort_output(df: pd.DataFrame) -> pd.DataFrame:
    sorted_df = df.copy()
    sorted_df["_tier_order"] = sorted_df["CASSANDRA_Risk_Tier"].map(TIER_ORDER)
    sorted_df = sorted_df.sort_values(
        by=["_tier_order", "Var_Pop", "Município"],
        ascending=[True, True, True],
        na_position="last",
        kind="mergesort",
    )
    return sorted_df.drop(columns="_tier_order")


def export_output(df: pd.DataFrame, output_path: Path) -> None:
    final_df = df[OUTPUT_COLUMNS].copy()
    final_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print_validation(
        f"CSV exported successfully: {output_path.name} ({len(final_df)} rows)"
    )


def print_terminal_summary(df: pd.DataFrame) -> None:
    counts = df["CASSANDRA_Risk_Tier"].value_counts().reindex(TIER_ORDER.keys(), fill_value=0)
    top_tier4 = (
        df.loc[df["CASSANDRA_Risk_Tier"] == "TIER 4 - Profecia CASSANDRA"]
        .sort_values(by=["Var_Pop", "Município"], ascending=[True, True], na_position="last")
        .head(5)
    )

    divider = style("=" * 78, Ansi.DIM, Ansi.GREY)
    print()
    print(divider)
    print(
        style(
            "CASSANDRA ORACLE ENGINE | RELATÓRIO FINAL DE RISCO MUNICIPAL",
            Ansi.BOLD,
            Ansi.WHITE,
        )
    )
    print(divider)
    print(
        style("Municípios processados: ", Ansi.BOLD, Ansi.WHITE)
        + style(str(len(df)), Ansi.CYAN, Ansi.BOLD)
    )
    print()
    print(style("Contagem por tier:", Ansi.BOLD, Ansi.WHITE))
    print(
        f"  {style('Tier 4 - Profecia CASSANDRA', Ansi.RED)}: "
        f"{style(str(counts['TIER 4 - Profecia CASSANDRA']), Ansi.RED, Ansi.BOLD)}"
    )
    print(
        f"  {style('Tier 3 - Risco de Fuga', Ansi.ORANGE)}: "
        f"{style(str(counts['TIER 3 - Risco de Fuga']), Ansi.ORANGE, Ansi.BOLD)}"
    )
    print(
        f"  {style('Tier 2 - Estagnação', Ansi.YELLOW)}: "
        f"{style(str(counts['TIER 2 - Estagnação']), Ansi.YELLOW, Ansi.BOLD)}"
    )
    print(
        f"  {style('Tier 1 - Resiliência', Ansi.CYAN)}: "
        f"{style(str(counts['TIER 1 - Resiliência']), Ansi.CYAN, Ansi.BOLD)}"
    )
    if counts["TIER - Indeterminado"]:
        print(
            f"  {style('Tier - Indeterminado', Ansi.GREY)}: "
            f"{style(str(counts['TIER - Indeterminado']), Ansi.GREY, Ansi.BOLD)}"
        )

    print()
    print(style("TOP 5 MUNICÍPIOS EM RISCO CRÍTICO (TIER 4)", Ansi.BOLD, Ansi.RED))
    if top_tier4.empty:
        print(style("  Nenhum município classificado em Tier 4.", Ansi.GREY))
    else:
        for row in top_tier4.itertuples(index=False):
            var_pop = "NaN" if pd.isna(row.Var_Pop) else f"{row.Var_Pop:.2f}"
            status = "" if pd.isna(row.Live_StatusCode) else str(row.Live_StatusCode)
            print(
                "  "
                + style(f"{row.Município:<28}", Ansi.WHITE)
                + f" | Var_Pop: {style(f'{var_pop:>7}', Ansi.RED, Ansi.BOLD)}"
                + f" | Live_StatusCode: {style(status, Ansi.ORANGE)}"
            )
    print(divider)


def main() -> int:
    base_dir = Path(__file__).resolve().parent

    print_step("Loading exact municipality normalization from mapa_cassandra.py...")
    mapping_dict, normalize_name = load_normalization_contract(
        base_dir / "mapa_cassandra.py"
    )
    print_validation(
        f"Normalization contract loaded successfully ({len(mapping_dict)} aliases)"
    )

    print_step("Loading input datasets...")
    raw_frames = {
        "dados_demograficos.csv": load_demographics(base_dir),
        "metricas_iei_completo.csv": load_iei_metrics(base_dir),
        "metricas_fase2_avancadas.csv": load_phase2_metrics(base_dir),
    }

    print_step("Normalizing municipality names and validating source integrity...")
    prepared_frames = {
        source_name: prepare_source(frame, source_name, normalize_name)
        for source_name, frame in raw_frames.items()
    }

    print_step("Validating municipality coverage across all three sources...")
    validate_key_coverage(prepared_frames)

    print_step("Building final 3-way merge with zero municipality loss...")
    merged = build_final_dataset(prepared_frames)

    print_step("Applying deterministic CASSANDRA risk-tier logic...")
    classified = assign_risk_tiers(merged)
    ordered = sort_output(classified)

    if len(ordered) != EXPECTED_MUNICIPALITIES:
        raise DataValidationError(
            "Final classified dataset must contain exactly "
            f"{EXPECTED_MUNICIPALITIES} rows, found {len(ordered)}."
        )
    if ordered["mun_key"].nunique() != EXPECTED_MUNICIPALITIES:
        raise DataValidationError(
            "Final classified dataset does not contain 308 unique municipality keys."
        )

    export_output(ordered, base_dir / "relatorio_produto_cassandra.csv")
    print_terminal_summary(ordered)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DataValidationError as exc:
        print_error(str(exc))
        raise SystemExit(1)
