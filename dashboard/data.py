"""Read collector artifacts and aggregate the currently selected products.

No network access, credentials, or writes belong in this module.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"
ATTRIBUTES = {
    "description": "Descrição",
    "image": "Imagem",
    "brand": "Marca",
    "commercialCategory": "Categoria comercial",
    "cest": "CEST",
    "netWeight": "Peso líquido",
    "grossWeight": "Peso bruto",
    "dimensions": "Dimensões",
    "ncm": "NCM completo",
}
ANALYSIS_METRICS = {
    "description": "Descrição",
    "ncm": "NCM completo",
    "brand": "Marca estruturada",
    "image": "Foto do produto",
    "category": "Categoria comercial",
    "cest": "CEST",
    "descriptionBrandImage": "Descrição + marca + foto",
    "descriptionBrandImageNcm": "Descrição + marca + foto + NCM",
    "dimensions": "Três dimensões",
    "weights": "Pesos líquido e bruto",
}
STATUSES = {"FOUND": "Encontrado", "NOT_FOUND": "Não encontrado", "ERROR": "Erro"}


@dataclass
class RunData:
    products: list[dict[str, Any]]
    metadata: dict[str, Any]
    summary: dict[str, Any]
    warnings: list[str]


def list_runs(root: Path = RUNS_DIR) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        (
            path for path in root.iterdir()
            if path.is_dir() and any((path / name).exists() for name in ("metadata.json", "products.json", "raw"))
        ),
        key=lambda path: path.name,
        reverse=True,
    )


def file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def run_signature(path: Path) -> tuple:
    return tuple(file_signature(path / name) for name in ("products.json", "summary.json", "metadata.json"))


def read_json(path: Path) -> tuple[Any, str | None]:
    try:
        with path.open(encoding="utf-8-sig") as handle:
            return json.load(handle), None
    except FileNotFoundError:
        return None, f"{path.name} ainda não está disponível."
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        return None, f"Não foi possível ler {path.name}; o arquivo está inacessível ou não contém JSON válido."


def valid_product(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    attributes = value.get("attributes")
    status = value.get("status")
    return (
        isinstance(value.get("ean"), str)
        and re.fullmatch(r"[0-9]{1,14}", value["ean"]) is not None
        and isinstance(value.get("category"), str)
        and bool(value["category"].strip())
        and isinstance(status, str)
        and status in STATUSES
        and isinstance(value.get("found"), bool)
        and value["found"] == (status == "FOUND")
        and isinstance(attributes, dict)
        and all(isinstance(attributes.get(key, False), bool) for key in ATTRIBUTES)
        and isinstance(value.get("marketplace"), dict)
        and (value.get("cosmos") is None or isinstance(value.get("cosmos"), dict))
        and isinstance(value.get("accuracy", {}), dict)
    )


def load_run(path: Path) -> RunData:
    warnings: list[str] = []
    artifacts: dict[str, Any] = {}
    for name in ("metadata", "products", "summary"):
        value, error = read_json(path / f"{name}.json")
        if error:
            warnings.append(error)
        elif name != "products" and not isinstance(value, dict):
            warnings.append(f"{name}.json deve conter um objeto JSON.")
            value = None
        artifacts[name] = value
        if name == "metadata" and isinstance(value, dict) and value.get("status") == "running":
            return RunData([], value, {}, warnings)

    products: list[dict[str, Any]] = []
    source = artifacts["products"]
    if source is not None and not isinstance(source, list):
        warnings.append("products.json deve conter uma lista de produtos.")
    elif isinstance(source, list):
        seen: set[str] = set()
        skipped = 0
        for product in source:
            if not valid_product(product) or product["ean"] in seen:
                skipped += 1
                continue
            products.append(product)
            seen.add(product["ean"])
        if skipped:
            warnings.append(f"{skipped} registro(s) inválido(s) ou com EAN duplicado foram excluídos da análise.")

    metadata = artifacts["metadata"] or {}
    summary = artifacts["summary"] or {}
    if isinstance(summary.get("total"), (int, float)) and summary["total"] != len(products):
        warnings.append("summary.json e products.json têm totais diferentes. Os indicadores usam os produtos válidos disponíveis.")
    return RunData(products, metadata, summary, warnings)


def product_frame(products: list[dict[str, Any]]) -> pd.DataFrame:
    columns = ["ean", "category", "status", "found", *ATTRIBUTES]
    rows = [
        {**{key: product[key] for key in columns[:4]}, **{key: product["attributes"].get(key, False) for key in ATTRIBUTES}}
        for product in products
    ]
    frame = pd.DataFrame(rows, columns=columns)
    for key in ("found", *ATTRIBUTES):
        frame[key] = frame[key].astype(bool)
    return frame


def filter_products(
    frame: pd.DataFrame,
    *,
    categories: list[str] | None = None,
    statuses: list[str] | None = None,
    attributes: dict[str, bool | None] | None = None,
) -> pd.DataFrame:
    mask = pd.Series(True, index=frame.index)
    if categories is not None:
        mask &= frame["category"].isin(categories)
    if statuses is not None:
        mask &= frame["status"].isin(statuses)
    for attribute, expected in (attributes or {}).items():
        if expected is not None:
            available = frame["netWeight"] | frame["grossWeight"] if attribute == "weight" else frame[attribute]
            mask &= available == expected
    return frame.loc[mask].copy()


def aggregate(frame: pd.DataFrame) -> dict[str, Any]:
    total = len(frame)
    found_frame = frame.loc[frame["found"]]
    found = len(found_frame)
    return {
        "total": total,
        "found": found,
        "notFound": int((frame["status"] == "NOT_FOUND").sum()),
        "errors": int((frame["status"] == "ERROR").sum()),
        "coverage": 100 * found / total if total else 0.0,
        "attributeCoverage": {
            key: 100 * int(found_frame[key].sum()) / found if found else 0.0
            for key in ATTRIBUTES
        },
        "analysisCounts": analysis_counts(found_frame),
    }


def analysis_counts(found_frame: pd.DataFrame) -> dict[str, int]:
    if found_frame.empty:
        return {key: 0 for key in ANALYSIS_METRICS}
    return {
        "description": int(found_frame["description"].sum()),
        "ncm": int(found_frame["ncm"].sum()),
        "brand": int(found_frame["brand"].sum()),
        "image": int(found_frame["image"].sum()),
        "category": int(found_frame["commercialCategory"].sum()),
        "cest": int(found_frame["cest"].sum()),
        "descriptionBrandImage": int(found_frame[["description", "brand", "image"]].all(axis=1).sum()),
        "descriptionBrandImageNcm": int(found_frame[["description", "brand", "image", "ncm"]].all(axis=1).sum()),
        "dimensions": int(found_frame["dimensions"].sum()),
        "weights": int(found_frame[["netWeight", "grossWeight"]].all(axis=1).sum()),
    }




def category_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["category", "total", "found", "notFound", "errors", "coverage", *ATTRIBUTES]
    rows = []
    for category, group in frame.groupby("category", sort=True):
        metrics = aggregate(group)
        coverage = metrics.pop("attributeCoverage")
        rows.append({"category": category, **metrics, **coverage})
    return pd.DataFrame(rows, columns=columns)


def load_raw(path: Path, ean: str) -> tuple[Any, str | None]:
    if not re.fullmatch(r"[0-9]{1,14}", ean):
        return None, "EAN inválido para localizar o arquivo original."
    return read_json(path / "raw" / f"{ean}.json")
