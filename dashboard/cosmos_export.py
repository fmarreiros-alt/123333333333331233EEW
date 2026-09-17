"""Convert a flattened Cosmos CSV export into dashboard run artifacts."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pandas as pd

from data import ATTRIBUTES, aggregate, category_metrics, product_frame


REQUIRED_COLUMNS = {"entity", "ean", "description", "api_status"}
def _text(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    text = _text(value)
    if text is None:
        return None
    try:
        number = float(text.replace(",", "."))
    except ValueError:
        return None
    return number if pd.notna(number) else None


def _found(status: Any) -> bool:
    value = (_text(status) or "").casefold()
    return value == "" or value in {"encontrado", "found", "200"}


def _cosmos_product(row: dict[str, Any]) -> dict[str, Any] | None:
    if not _found(row.get("api_status")):
        return None
    return {
        "ean": _text(row.get("ean")),
        "description": _text(row.get("description")),
        "brand": _text(row.get("brand.name")),
        "brandPicture": _text(row.get("brand.picture")),
        "imageUrl": _text(row.get("thumbnail")),
        "category": _text(row.get("category.description")),
        "netWeight": _number(row.get("net_weight")),
        "grossWeight": _number(row.get("gross_weight")),
        "width": _number(row.get("width")),
        "height": _number(row.get("height")),
        "length": _number(row.get("length")),
        "ncm": _text(row.get("ncm.code")),
        "ncmDescription": _text(row.get("ncm.description")),
        "ncmFullDescription": _text(row.get("ncm.full_description")),
        "cest": _text(row.get("cest.code")),
    }


def _attributes(product: dict[str, Any] | None) -> dict[str, bool]:
    if product is None:
        return {key: False for key in ATTRIBUTES}
    positive = lambda key: (_number(product.get(key)) or 0) > 0
    image = _text(product.get("imageUrl"))
    image_parts = urlsplit(image) if image else None
    valid_image = bool(image_parts and image_parts.scheme in ("http", "https") and image_parts.hostname and not image_parts.username and not image_parts.password)
    valid_ncm = all(bool(_text(product.get(key))) for key in ("ncm", "ncmDescription", "ncmFullDescription"))
    return {
        "description": bool(_text(product.get("description"))),
        "image": valid_image,
        "brand": bool(_text(product.get("brand"))),
        "commercialCategory": bool(_text(product.get("category"))),
        "cest": bool(re.fullmatch(r"\d{7}", _text(product.get("cest")) or "")),
        "netWeight": positive("netWeight"),
        "grossWeight": positive("grossWeight"),
        "dimensions": all(positive(key) for key in ("width", "height", "length")),
        "ncm": valid_ncm,
    }


def _product(row: dict[str, Any]) -> dict[str, Any]:
    cosmos = _cosmos_product(row)
    attributes = _attributes(cosmos)
    found = cosmos is not None
    status = "FOUND" if found else "NOT_FOUND"
    ean = _text(row.get("ean")) or ""
    category = _text(row.get("entity")) or "Sem categoria"
    return {
        "ean": ean,
        "category": category,
        "status": status,
        "httpStatus": 200 if found else 404,
        "found": found,
        "attributes": attributes,
        "marketplace": {"ean": ean, "category": category},
        "cosmos": cosmos,
        "accuracy": {"ean": None, "brand": None, "netWeight": None, "grossWeight": None, "ncm": None},
    }


def import_cosmos_export(input_path: Path, runs_dir: Path, run_name: str | None = None) -> Path:
    """Import a Cosmos export and return the generated dashboard run path."""
    frame = pd.read_csv(input_path, dtype="string", keep_default_na=False)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"CSV Cosmos sem colunas obrigatórias: {', '.join(sorted(missing))}.")
    if frame["ean"].duplicated().any() or frame["ean"].str.fullmatch(r"[0-9]{1,14}").eq(False).any():
        raise ValueError("CSV Cosmos contém EAN duplicado ou inválido.")

    products = [_product(row) for row in frame.to_dict(orient="records")]
    run_id = run_name or datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ-cosmos-export")
    run_path = runs_dir / run_id
    raw_path = run_path / "raw"
    raw_path.mkdir(parents=True, exist_ok=False)
    for row in frame.to_dict(orient="records"):
        ean = _text(row["ean"]) or ""
        body = {key: (_text(value) if value != "" else None) for key, value in row.items()}
        status = 200 if _found(row["api_status"]) else 404
        (raw_path / f"{ean}.json").write_text(json.dumps({"request": {"ean": ean, "source": "cosmos-export"}, "response": {"status": status, "body": body}}, ensure_ascii=False), encoding="utf-8")

    metrics = aggregate(product_frame(products))
    metrics["byCategory"] = category_metrics(product_frame(products)).to_dict(orient="records")
    metadata = {
        "status": "completed", "mode": "imported-csv", "source": str(input_path),
        "total": len(products), "processed": len(products),
        "units": {"weight": "export original", "dimensions": "export original"},
    }
    (run_path / "products.json").write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_path / "summary.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_path / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_path / "requests.jsonl").write_text("", encoding="utf-8")
    (run_path / "errors.jsonl").write_text("", encoding="utf-8")
    return run_path