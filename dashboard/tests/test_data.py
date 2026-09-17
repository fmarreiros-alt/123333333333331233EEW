import json
import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data import ATTRIBUTES, aggregate, category_metrics, filter_products, list_runs, load_raw, load_run, product_frame, run_signature, valid_product
from cosmos_export import import_cosmos_export
from cosmos_meli_export import import_cosmos_meli_export


def product(ean="0001234567890", category="Alimentos", status="FOUND", image=True):
    found = status == "FOUND"
    return {
        "ean": ean, "category": category, "status": status, "found": found,
        "attributes": {key: (found and (image if key == "image" else True)) for key in ATTRIBUTES},
        "marketplace": {"ean": ean, "category": category, "description": "Produto marketplace"},
        "cosmos": {"ean": ean, "description": "Produto Cosmos"} if found else None,
        "accuracy": {"ean": True if found else None, "brand": None},
    }


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.products = [
            product(), product("0001234567891", image=False),
            product("0001234567892", status="NOT_FOUND"),
            product("0001234567893", category="Higiene", status="ERROR"),
        ]
        self.frame = product_frame(self.products)

    def test_denominators_include_errors_in_total_and_only_found_in_attributes(self):
        result = aggregate(self.frame)
        self.assertEqual((result["total"], result["found"], result["notFound"], result["errors"]), (4, 2, 1, 1))
        self.assertEqual(result["coverage"], 50)
        self.assertEqual(result["attributeCoverage"]["image"], 50)
        self.assertEqual(result["attributeCoverage"]["description"], 100)

    def test_filters_recalculate_denominators_and_preserve_string_eans(self):
        filtered = filter_products(self.frame, categories=["Alimentos"], attributes={"image": True})
        self.assertEqual(filtered["ean"].tolist(), ["0001234567890"])
        self.assertEqual(aggregate(filtered)["coverage"], 100)
        self.assertEqual(len(filter_products(self.frame, statuses=["ERROR"])), 1)
        self.assertEqual(len(filter_products(self.frame, attributes={"weight": False})), 2)

    def test_empty_filters_and_no_found_are_finite(self):
        for frame in [filter_products(self.frame, categories=[]), product_frame([]), filter_products(self.frame, statuses=["ERROR"])]:
            metrics = aggregate(frame)
            self.assertTrue(math.isfinite(metrics["coverage"]))
            self.assertEqual(set(metrics["attributeCoverage"].values()), {0})

    def test_category_denominators_are_local(self):
        categories = category_metrics(self.frame).set_index("category")
        self.assertAlmostEqual(categories.loc["Alimentos", "coverage"], 200 / 3)
        self.assertEqual(categories.loc["Alimentos", "image"], 50)
        self.assertEqual(categories.loc["Higiene", "errors"], 1)
        self.assertEqual(categories.loc["Higiene", "coverage"], 0)


class LoaderTests(unittest.TestCase):
    def test_import_cosmos_meli_export_preserves_comparison_and_raw_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "cosmos-meli.csv"
            pd.DataFrame([
                {
                    "ean": "0012345678901", "entity": "Air Fryer", "cosmos_api_status": "",
                    "cosmos_description": "Fritadeira", "cosmos_brand.name": "Marca", "cosmos_thumbnail": "https://example.test/a.png",
                    "meli_matched": "TRUE", "meli_n_results": "2", "meli_status": "active", "meli_name": "Fritadeira Meli",
                    "meli_gtin_matches_source": "", "meli_n_attributes": "4", "meli_n_pictures": "1", "meli_attributes": '{"BRAND":"Marca"}',
                },
            ]).to_csv(source, index=False)
            run_path = import_cosmos_meli_export(source, root / "runs", "meli-import")
            loaded = load_run(run_path)
            product_data = loaded.products[0]
            summary = json.loads((run_path / "summary.json").read_text())
            raw = json.loads((run_path / "raw" / "0012345678901.json").read_text())
            self.assertTrue(product_data["comparison"]["meliMatched"])
            self.assertTrue(product_data["comparison"]["meliMultipleResults"])
            self.assertIsNone(product_data["comparison"]["meliGtinMatch"])
            self.assertEqual(summary["comparison"]["gtinMatchInformed"], 0)
            self.assertEqual(raw["response"]["body"]["meli_attributes"], '{"BRAND":"Marca"}')

    def test_import_cosmos_export_creates_dashboard_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "cosmos.csv"
            pd.DataFrame([
                {"entity": "Air Fryer", "ean": "0618231568338", "description": "Fritadeira", "api_status": "", "thumbnail": "https://example.test/a.png", "brand.name": "Marca", "net_weight": "500", "gross_weight": "", "width": "10", "height": "20", "length": "5", "ncm.code": "85167920", "gpc.code": ""},
                {"entity": "Air Fryer", "ean": "0618231568550", "description": "", "api_status": "Não encontrado", "thumbnail": "", "brand.name": "", "net_weight": "", "gross_weight": "", "width": "", "height": "", "length": "", "ncm.code": "", "gpc.code": ""},
            ]).to_csv(source, index=False)
            run_path = import_cosmos_export(source, root / "runs", "test-import")
            loaded = load_run(run_path)
            self.assertEqual(len(loaded.products), 2)
            self.assertEqual(loaded.products[0]["status"], "FOUND")
            self.assertEqual(loaded.products[1]["status"], "NOT_FOUND")
            self.assertEqual(json.loads((run_path / "summary.json").read_text())["found"], 1)

    def test_missing_invalid_duplicate_and_partial_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.assertEqual(load_run(path).products, [])
            (path / "products.json").write_text("{invalid", encoding="utf-8")
            self.assertTrue(load_run(path).warnings)
            (path / "metadata.json").write_text(json.dumps({"status": "interrupted", "total": 10}), encoding="utf-8")
            (path / "products.json").write_text(json.dumps([product(), product(), {"ean": "bad"}]), encoding="utf-8")
            run = load_run(path)
            self.assertEqual(len(run.products), 1)
            self.assertTrue(any("2 registro(s)" in message for message in run.warnings))
            self.assertEqual(run.metadata["status"], "interrupted")

    def test_invalid_shapes_are_rejected_without_exception(self):
        for invalid in ([], None, {"status": []}, {**product(), "status": []}, {**product(), "ean": 1234567890}):
            self.assertFalse(valid_product(invalid))

    def test_running_execution_does_not_read_a_stale_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "metadata.json").write_text('{"status":"running"}', encoding="utf-8")
            (path / "products.json").write_text(json.dumps([product()]), encoding="utf-8")
            self.assertEqual(load_run(path).products, [])

    def test_signature_changes_when_collector_updates_a_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            before = run_signature(path)
            (path / "products.json").write_text("[]", encoding="utf-8")
            self.assertNotEqual(before, run_signature(path))
            before = run_signature(path)
            (path / "products.json").write_text(json.dumps([product()]), encoding="utf-8")
            self.assertNotEqual(before, run_signature(path))

    def test_run_discovery_and_safe_raw_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(list_runs(root / "missing"), [])
            run = root / "run-a"
            (run / "raw").mkdir(parents=True)
            self.assertEqual(list_runs(root), [run])
            self.assertIsNotNone(load_raw(run, "../../metadata")[1])
            self.assertIsNotNone(load_raw(run, "0001234567890")[1])
            raw = {"request": {"ean": "0001234567890"}, "response": {"status": 200, "body": {"description": "Exemplo"}}}
            (run / "raw" / "0001234567890.json").write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(load_raw(run, "0001234567890"), (raw, None))


if __name__ == "__main__":
    unittest.main()
