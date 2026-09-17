"""CLI for importing a flattened Cosmos CSV export into the dashboard."""

from __future__ import annotations

import argparse
from pathlib import Path

from cosmos_export import import_cosmos_export
from cosmos_meli_export import import_cosmos_meli_export


def main() -> None:
    """Parse arguments and create a dashboard run from a Cosmos export."""
    parser = argparse.ArgumentParser(description="Importa um CSV Cosmos ou Cosmos x Meli para o dashboard.")
    parser.add_argument("--input", type=Path, default=Path("../data/input/catalog.csv"), help="CSV exportado pelo Cosmos")
    parser.add_argument("--runs-dir", type=Path, default=Path("../data/runs"))
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--cosmos-meli", action="store_true", help="Usa o formato consolidado Cosmos x Mercado Livre")
    arguments = parser.parse_args()
    importer = import_cosmos_meli_export if arguments.cosmos_meli else import_cosmos_export
    run_path = importer(arguments.input, arguments.runs_dir, arguments.run_name)
    print(f"Execução importada: {run_path}")


if __name__ == "__main__":
    main()