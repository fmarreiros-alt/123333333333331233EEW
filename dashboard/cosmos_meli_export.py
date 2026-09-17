"""Import a flattened Cosmos and Mercado Livre comparison CSV."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from data import ATTRIBUTES, aggregate, category_metrics, product_frame


REQUIRED_COLUMNS = {"ean", "entity", "cosmos_api_status", "meli_matched"}
MELI_COLUMNS = (
    "meli_product_id", "meli_domain_id", "meli_status", "meli_name", "meli_permalink",
    "meli_short_description_content",
    "meli_gtin_matches_source", "meli_n_results", "meli_n_attributes", "meli_n_description_pictures",
    "meli_n_pictures", "meli_first_picture_url", "meli_attributes",
)


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
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _boolean(value: Any) -> bool | None:
    text = (_text(value) or "").casefold()
    if text in {"true", "1", "sim", "yes"}:
        return True
    if text in {"false", "0", "não", "nao", "no"}:
        return False
    return None


def _found(status: Any) -> bool:
    return (_text(status) or "").casefold() in {"", "encontrado", "found", "200"}


def _cosmos_product(row: dict[str, Any]) -> dict[str, Any] | None:
    if not _found(row.get("cosmos_api_status")):
        return None
    return {
        "ean": _text(row.get("ean")), "description": _text(row.get("cosmos_description")),
        "brand": _text(row.get("cosmos_brand.name")), "imageUrl": _text(row.get("cosmos_thumbnail")),
        "category": _text(row.get("cosmos_category.description")), "netWeight": _number(row.get("cosmos_net_weight")),
        "grossWeight": _number(row.get("cosmos_gross_weight")), "width": _number(row.get("cosmos_width")),
        "height": _number(row.get("cosmos_height")), "length": _number(row.get("cosmos_length")),
        "ncm": _text(row.get("cosmos_ncm.code")), "ncmDescription": _text(row.get("cosmos_ncm.description")),
        "ncmFullDescription": _text(row.get("cosmos_ncm.full_description")), "cest": _text(row.get("cosmos_cest.code")),
    }


def _meli_product(row: dict[str, Any]) -> dict[str, Any]:
    return {key.removeprefix("meli_"): _text(row.get(key)) for key in MELI_COLUMNS if key in row}


def _attributes(product: dict[str, Any] | None) -> dict[str, bool]:
    if product is None:
        return {key: False for key in ATTRIBUTES}
    image = _text(product.get("imageUrl"))
    return {
        "description": bool(_text(product.get("description"))), "image": bool(image and re.match(r"^https?://", image)),
        "brand": bool(_text(product.get("brand"))), "commercialCategory": bool(_text(product.get("category"))),
        "cest": bool(re.fullmatch(r"\d{7}", _text(product.get("cest")) or "")),
        "netWeight": (_number(product.get("netWeight")) or 0) > 0,
        "grossWeight": (_number(product.get("grossWeight")) or 0) > 0,
        "dimensions": all((_number(product.get(key)) or 0) > 0 for key in ("width", "height", "length")),
        "ncm": all(bool(_text(product.get(key))) for key in ("ncm", "ncmDescription", "ncmFullDescription")),
    }


def _product(row: dict[str, Any]) -> dict[str, Any]:
    cosmos = _cosmos_product(row)
    ean = _text(row.get("ean")) or ""
    category = _text(row.get("entity")) or "Sem categoria"
    found = cosmos is not None
    results = (_number(row.get("meli_n_results")) or 0)
    return {
        "ean": ean, "category": category, "status": "FOUND" if found else "NOT_FOUND", "httpStatus": 200 if found else 404,
        "found": found, "attributes": _attributes(cosmos), "marketplace": {"ean": ean, "category": category},
        "cosmos": cosmos, "meli": _meli_product(row),
        "comparison": {
            "meliMatched": _boolean(row.get("meli_matched")), "meliHasResult": results > 0, "meliMultipleResults": results > 1,
            "meliGtinMatch": _boolean(row.get("meli_gtin_matches_source")),
            "meliActive": (_text(row.get("meli_status")) or "").casefold() == "active",
            "meliHasName": bool(_text(row.get("meli_name"))),
            "meliHasShortDescription": bool(_text(row.get("meli_short_description_content"))),
            "meliHasAttributes": (_number(row.get("meli_n_attributes")) or 0) > 0,
            "meliHasImage": (_number(row.get("meli_n_pictures")) or 0) > 0,
            "meliHasLink": bool(_text(row.get("meli_permalink"))),
        },
        "accuracy": {"ean": None, "brand": None, "netWeight": None, "grossWeight": None, "ncm": None},
    }


def _raw_body(row: dict[str, Any]) -> dict[str, Any]:
    return {key: (_text(value) if value != "" else None) for key, value in row.items()}


def import_cosmos_meli_export(input_path: Path, runs_dir: Path, run_name: str | None = None) -> Path:
    """Import the consolidated CSV and return the generated dashboard run."""
    frame = pd.read_csv(input_path, dtype="string", keep_default_na=False)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"CSV Cosmos x Meli sem colunas obrigatórias: {', '.join(sorted(missing))}.")
    if frame["ean"].duplicated().any() or frame["ean"].str.fullmatch(r"[0-9]{1,14}").eq(False).any():
        raise ValueError("CSV Cosmos x Meli contém EAN duplicado ou inválido.")

    rows = frame.to_dict(orient="records")
    products = [_product(row) for row in rows]
    run_id = run_name or datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ-cosmos-meli")
    run_path = runs_dir / run_id
    raw_path = run_path / "raw"
    raw_path.mkdir(parents=True, exist_ok=False)
    for row in rows:
        ean = _text(row["ean"]) or ""
        payload = {"request": {"ean": ean, "source": "cosmos-meli-consolidated"}, "response": {"status": 200 if _found(row["cosmos_api_status"]) else 404, "body": _raw_body(row)}}
        (raw_path / f"{ean}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    frame_products = product_frame(products)
    metrics = aggregate(frame_products)
    metrics["byCategory"] = category_metrics(frame_products).to_dict(orient="records")
    comparison = [product["comparison"] for product in products]
    metrics["comparison"] = {
        "universe": len(products), "matched": sum(item["meliMatched"] is True for item in comparison),
        "hasResult": sum(item["meliHasResult"] for item in comparison), "multipleResults": sum(item["meliMultipleResults"] for item in comparison),
        "gtinMatch": sum(item["meliGtinMatch"] is True for item in comparison), "gtinMatchInformed": sum(item["meliGtinMatch"] is not None for item in comparison),
        "active": sum(item["meliActive"] for item in comparison), "withName": sum(item["meliHasName"] for item in comparison),
        "withAttributes": sum(item["meliHasAttributes"] for item in comparison), "withImage": sum(item["meliHasImage"] for item in comparison),
    }
    metadata = {
        "status": "completed", "mode": "imported-cosmos-meli-csv", "source_type": "cosmos_meli_consolidated",
        "source": str(input_path), "universe": "consolidated_csv", "total": len(products), "processed": len(products),
        "units": {"weight": "export original", "dimensions": "export original"},
    }
    (run_path / "products.json").write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_path / "summary.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_path / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_path / "requests.jsonl").write_text("", encoding="utf-8")
    (run_path / "errors.jsonl").write_text("", encoding="utf-8")
    return run_path