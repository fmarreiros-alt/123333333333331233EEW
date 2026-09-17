import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from test_data import product
from ui import cached_run


APP = Path(__file__).resolve().parents[1] / "app.py"


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.patcher = patch("ui.RUNS_DIR", self.root)
        self.patcher.start()
        cached_run.clear()

    def tearDown(self):
        self.patcher.stop()
        self.temporary.cleanup()
        cached_run.clear()

    def create_run(self, name="run-a", status="completed"):
        path = self.root / name
        (path / "raw").mkdir(parents=True)
        products = [product(), product("0001234567891", category="Higiene", status="NOT_FOUND")]
        (path / "products.json").write_text(json.dumps(products), encoding="utf-8")
        (path / "metadata.json").write_text(json.dumps({"runId": name, "status": status, "mode": "demo", "qualityThreshold": 70, "weightTolerance": 0.05, "processed": 2, "total": 2}), encoding="utf-8")
        (path / "summary.json").write_text('{"total":2}', encoding="utf-8")
        (path / "raw" / products[0]["ean"]).with_suffix(".json").write_text('{"response":{"status":200,"body":{"description":"Original"}}}', encoding="utf-8")
        return path

    def test_empty_directory_and_running_execution_are_explained(self):
        app = AppTest.from_file(APP).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Nenhuma execução" in element.value for element in app.info))
        self.create_run(status="running")
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any("durante a gravação" in element.value for element in app.info))
        self.assertFalse(app.metric)

    def test_navigation_preserves_filters_and_product_raw_is_available(self):
        self.create_run()
        app = AppTest.from_file(APP, default_timeout=20).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "2")
        app.multiselect(key="filter_categories").set_value(["Alimentos"]).run()
        self.assertEqual(app.metric[0].value, "1")
        self.assertEqual(app.metric[4].value, "100.0%")
        for page in ("2_categories.py", "3_attributes.py", "4_products.py"):
            app.switch_page(f"pages/{page}").run()
            self.assertFalse(app.exception)
            self.assertEqual(app.multiselect(key="filter_categories").value, ["Alimentos"])
        app.text_input(key="product_search").set_value("000123").run()
        self.assertEqual(app.selectbox(key="product_ean").value, "0001234567890")
        app.checkbox(key="raw_run-a_0001234567890").check().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.json)
        app.text_input(key="product_search").set_value("missing").run()
        self.assertTrue(any("Nenhum EAN" in element.value for element in app.info))

    def test_no_found_and_empty_selection_render_without_exception(self):
        self.create_run(status="interrupted")
        app = AppTest.from_file(APP, default_timeout=20).run()
        app.multiselect(key="filter_statuses").set_value(["NOT_FOUND"]).run()
        self.assertEqual(app.metric[4].value, "0.0%")
        app.switch_page("pages/3_attributes.py").run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Não há produtos encontrados" in element.value for element in app.info))
        app.multiselect(key="filter_categories").set_value([]).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Nenhum produto disponível" in element.value for element in app.info))

    def test_updated_files_invalidate_cache_without_changing_run(self):
        path = self.create_run()
        app = AppTest.from_file(APP, default_timeout=20).run()
        self.assertEqual(app.metric[0].value, "2")
        (path / "products.json").write_text(json.dumps([product()]), encoding="utf-8")
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "1")
        self.assertTrue(any("totais diferentes" in element.value for element in app.warning))


if __name__ == "__main__":
    unittest.main()
