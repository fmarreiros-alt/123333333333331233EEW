"""Load and aggregate the Cosmos and Mercado Livre source spreadsheets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pandas.api.types import is_bool_dtype


DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "catalog"
SAMPLE_FILE = "eans-amostra.csv"
COSMOS_FILE = "cosmo.csv"
MELI_FILE = "mercado-livre.csv"


@dataclass(frozen=True)
class CatalogSources:
    """Parsed source tables and EAN-level result sets."""

    sample_eans: frozenset[str]
    cosmos: pd.DataFrame
    meli: pd.DataFrame
    cosmos_eans: frozenset[str]
    cosmos_found_eans: frozenset[str]
    meli_eans: frozenset[str]
    meli_found_eans: frozenset[str]


def _resolve_path(data_dir: Path, environment_key: str, file_name: str) -> Path:
    configured = os.getenv(environment_key, "").strip()
    return Path(configured).expanduser() if configured else data_dir / file_name


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    frame = pd.read_csv(
        path,
        dtype={"ean": "string"},
        encoding="utf-8-sig",
        keep_default_na=False,
    )
    if "ean" not in frame.columns:
        raise ValueError(f"O arquivo {path.name} não possui a coluna ean.")
    frame["ean"] = frame["ean"].astype("string").str.strip()
    return frame.loc[frame["ean"].notna() & frame["ean"].ne("")].copy()


def _cosmos_found(frame: pd.DataFrame) -> pd.Series:
    description = frame.get("description", pd.Series("", index=frame.index)).astype("string").str.strip()
    status = frame.get("api_status", pd.Series("", index=frame.index)).astype("string").str.strip().str.casefold()
    return status.eq("") & description.ne("")


def _meli_found(frame: pd.DataFrame) -> pd.Series:
    matched = frame.get("matched", pd.Series(False, index=frame.index))
    if is_bool_dtype(matched):
        return matched.fillna(False).astype(bool)
    return matched.astype("string").str.strip().str.casefold().isin({"true", "1", "sim"})


def _unique_eans(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.drop_duplicates(subset="ean", keep="first").copy()


def load_sources(data_dir: Path | None = None) -> CatalogSources:
    """Load the sample universe and both source exports as text-preserving CSVs."""
    root = data_dir or Path(os.getenv("CATALOG_DATA_DIR", DEFAULT_DATA_DIR)).expanduser()
    sample = _read_csv(_resolve_path(root, "EANS_SAMPLE_CSV_PATH", SAMPLE_FILE))
    cosmos = _read_csv(_resolve_path(root, "COSMOS_CSV_PATH", COSMOS_FILE))
    meli = _read_csv(_resolve_path(root, "MELI_CSV_PATH", MELI_FILE))
    cosmos_found = _cosmos_found(cosmos)
    meli_found = _meli_found(meli)
    return CatalogSources(
        sample_eans=frozenset(sample["ean"]),
        cosmos=_unique_eans(cosmos),
        meli=_unique_eans(meli),
        cosmos_eans=frozenset(cosmos["ean"]),
        cosmos_found_eans=frozenset(cosmos.loc[cosmos_found, "ean"]),
        meli_eans=frozenset(meli["ean"]),
        meli_found_eans=frozenset(meli.loc[meli_found, "ean"]),
    )


def catalog_metrics(sources: CatalogSources) -> dict[str, int | float]:
    """Return total, not-found, and coverage metrics for both sources."""
    total = len(sources.sample_eans)
    cosmos_found = len(sources.cosmos_found_eans & sources.sample_eans)
    meli_found = len(sources.meli_found_eans & sources.sample_eans)
    return {
        "total": total,
        "cosmos_total": total,
        "cosmos_found": cosmos_found,
        "cosmos_not_found": total - cosmos_found,
        "cosmos_coverage": round(100 * cosmos_found / total, 2) if total else 0.0,
        "meli_total": total,
        "meli_found": meli_found,
        "meli_not_found": total - meli_found,
        "meli_coverage": round(100 * meli_found / total, 2) if total else 0.0,
        "cosmos_source_eans": len(sources.cosmos_eans),
        "meli_source_eans": len(sources.meli_eans),
        "found_in_both": len(sources.cosmos_found_eans & sources.meli_found_eans),
    }


def cosmos_category_metrics(sources: CatalogSources) -> pd.DataFrame:
    """Build category totals and EAN-only Cosmos coverage."""
    frame = sources.cosmos.copy()
    frame["found"] = _cosmos_found(frame)
    category_column = "entity" if "entity" in frame else "product_type_magalu"
    if category_column not in frame:
        frame[category_column] = "Sem categoria"
    frame[category_column] = frame[category_column].replace("", "Sem categoria")
    result = frame.groupby(category_column, as_index=False).agg(
        total=("ean", "nunique"), found=("found", "sum")
    )
    result = result.rename(columns={category_column: "category"})
    result["not_found"] = result["total"] - result["found"]
    result["coverage"] = (result["found"] / result["total"] * 100).round(2)
    return result.sort_values("total", ascending=False)


def category_comparison_metrics(sources: CatalogSources) -> pd.DataFrame:
    """Compare found EANs by the canonical Cosmos category."""
    cosmos = sources.cosmos.copy()
    category_column = "entity"
    if category_column not in cosmos:
        cosmos[category_column] = "Sem categoria"
    cosmos[category_column] = cosmos[category_column].replace("", "Sem categoria")
    universe = pd.DataFrame({"ean": sorted(sources.sample_eans)})
    universe = universe.merge(cosmos[["ean", category_column]], on="ean", how="left")
    universe[category_column] = universe[category_column].fillna("Sem categoria")
    universe["cosmos_total"] = universe["ean"].isin(sources.cosmos_eans).astype(int)
    universe["cosmos_found"] = universe["ean"].isin(sources.cosmos_found_eans).astype(int)
    universe["meli_total"] = universe["ean"].isin(sources.meli_eans).astype(int)
    universe["meli_found"] = universe["ean"].isin(sources.meli_found_eans).astype(int)
    result = universe.groupby(category_column, as_index=False).agg(
        cosmos_total=("cosmos_total", "sum"),
        cosmos_found=("cosmos_found", "sum"),
        meli_total=("meli_total", "sum"),
        meli_found=("meli_found", "sum"),
    )
    result = result.rename(columns={category_column: "category"})
    for source in ("cosmos", "meli"):
        result[f"{source}_coverage"] = (
            result[f"{source}_found"] / result[f"{source}_total"] * 100
        ).round(2)
    return result.sort_values("cosmos_total", ascending=False)