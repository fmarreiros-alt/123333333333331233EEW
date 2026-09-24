"""Shared controls live in the entrypoint so filters survive page navigation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
import plotly.express as px
import streamlit as st

from catalog_analysis import DEFAULT_DATA_DIR, CatalogSources, category_comparison_metrics, catalog_metrics, load_sources
from data import ATTRIBUTES, RUNS_DIR, STATUSES, filter_products, list_runs, load_raw, load_run, product_frame, run_signature


CATALOG_DATA_DIR = Path(os.getenv("CATALOG_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser()


@st.cache_data(show_spinner=False, max_entries=16)
def cached_run(path: str, signature: tuple):
    # signature deliberately participates in the cache key; files remain on disk once.
    return load_run(Path(path))


@st.cache_data(show_spinner=False)
def cached_catalog_sources(path: str) -> CatalogSources:
    """Cache the three source spreadsheets until the user refreshes them."""
    return load_sources(Path(path))


def clear_filters():
    for key in list(st.session_state):
        if key.startswith("filter_") or key in ("product_search", "product_ean"):
            del st.session_state[key]


def prepare_catalog_context() -> None:
    """Load the shared Cosmos and Mercado Livre catalog context."""
    with st.sidebar:
        st.header("Catálogo")
        st.button("Atualizar planilhas", key="refresh_catalog_files", on_click=cached_catalog_sources.clear)
        st.caption("Fontes: eans-amostra.csv, cosmo.csv e mercado-livre.csv")
    try:
        sources = cached_catalog_sources(str(CATALOG_DATA_DIR))
    except (FileNotFoundError, ValueError, pd.errors.ParserError) as error:
        st.error(str(error))
        st.info("Configure CATALOG_DATA_DIR para apontar para a pasta com as três planilhas.")
        st.stop()
    st.session_state["_catalog_context"] = sources


def catalog_context() -> CatalogSources:
    """Return the shared spreadsheet context prepared by the entrypoint."""
    return st.session_state["_catalog_context"]


def prepare_context():
    with st.sidebar:
        st.header("Cosmos Benchmark")
        st.button("Atualizar arquivos", key="refresh_files", on_click=cached_run.clear)
        try:
            runs = list_runs(RUNS_DIR)
        except OSError:
            st.error("Não foi possível acessar data/runs. Verifique as permissões da pasta.")
            st.stop()
        if not runs:
            st.info("Nenhuma execução disponível em data/runs.")
            st.code("cd collector\nnpm run benchmark -- --input ../data/input/catalog.csv", language="powershell")
            st.stop()
        if not runs:
            st.info("Nenhuma execução Cosmos disponível.")
            st.stop()
        choices = {path.name: path for path in runs}
        if st.session_state.get("selected_run") not in choices:
            st.session_state["selected_run"] = runs[0].name
            clear_filters()
        selected = st.selectbox("Execução", options=list(choices), key="selected_run", on_change=clear_filters)
        path = choices[selected]
        run = cached_run(str(path), run_signature(path))
        frame = product_frame(run.products)
        st.caption(f"{len(frame)} EANs processados disponíveis")
        st.divider()
        st.subheader("Filtros comuns")
        st.button("Limpar filtros", on_click=clear_filters, key="clear_filters")
        categories = sorted(frame["category"].unique().tolist())
        if "filter_categories" in st.session_state:
            st.session_state["filter_categories"] = [c for c in st.session_state["filter_categories"] if c in categories]
        else:
            st.session_state["filter_categories"] = categories
        selected_categories = st.multiselect("Categorias", categories, key="filter_categories")
        statuses = st.multiselect("Status", list(STATUSES), default=list(STATUSES), format_func=STATUSES.get, key="filter_statuses")
        attribute_filters = {}
        for key, label in {"image": "Tem foto", "weight": "Tem peso", "dimensions": "Tem dimensões", "ncm": "Tem NCM", "commercialCategory": "Tem categoria", "cest": "Tem CEST"}.items():
            selected_value = st.selectbox(label, ["Todos", "Sim", "Não"], key=f"filter_{key}")
            attribute_filters[key] = {"Todos": None, "Sim": True, "Não": False}[selected_value]
        st.caption("Tem peso: líquido ou bruto válido. Dimensões: largura, altura e comprimento válidos.")

    filtered = filter_products(
        frame, categories=selected_categories, statuses=statuses,
        attributes=attribute_filters,
    )
    st.session_state["_benchmark_context"] = {"path": path, "run": run, "frame": filtered}
    if run.metadata.get("mode") == "demo":
        st.warning("Demonstração com dados sintéticos. Esta execução não mede a cobertura real do Cosmos.")
    status = run.metadata.get("status")
    if not isinstance(status, str):
        status = None
    if status != "completed":
        labels = {"running": "em andamento", "interrupted": "interrompida"}
        st.info(f"Execução {labels.get(status, 'sem status de conclusão')}: os resultados podem estar parciais. Use Atualizar arquivos após o processamento.")
    for warning in run.warnings:
        st.warning(warning)
    st.caption(f"Execução: {selected} · {len(filtered)} de {len(frame)} EANs nos filtros atuais")
    processed, planned = run.metadata.get("processed"), run.metadata.get("total")
    if isinstance(processed, int) and isinstance(planned, int):
        st.caption(f"Progresso registrado: {processed} / {planned} EANs planejados. A cobertura de uma execução interrompida considera apenas os processados.")
    if status == "running":
        st.info("A análise estará disponível quando a execução terminar ou for interrompida. Isso evita misturar arquivos durante a gravação.")
        st.stop()
    st.caption("Cobertura = encontrados / EANs filtrados. Atributos usam somente os encontrados. Todos os gráficos e indicadores respeitam os filtros.")


def context():
    return st.session_state["_benchmark_context"]


def require_products():
    value = context()
    if value["frame"].empty:
        st.info("Nenhum produto disponível para estes filtros. Ajuste os filtros ou processe uma execução pelo collector.")
        st.stop()
    return value


def show_overview():
    st.title("Visão geral")
    metrics = catalog_metrics(catalog_context())
    st.caption("Indicadores calculados sobre o universo único de EANs da planilha eans-amostra.csv.")
    source_cards = [
        ("Cosmos", "cosmos_total", "cosmos_not_found", "cosmos_coverage"),
        ("Mercado Livre", "meli_total", "meli_not_found", "meli_coverage"),
    ]
    for source, total_key, not_found_key, coverage_key in source_cards:
        st.subheader(source)
        cards = [
            ("Total de EANs", metrics[total_key]),
            ("Não encontrados", metrics[not_found_key]),
            ("Cobertura", f"{metrics[coverage_key]:.2f}%"),
        ]
        for column, (label, value) in zip(st.columns(3), cards):
            column.metric(label, value)

    overview = pd.DataFrame([
        {"Fonte": "Cosmos", "Cobertura": metrics["cosmos_coverage"]},
        {"Fonte": "Mercado Livre", "Cobertura": metrics["meli_coverage"]},
    ])
    figure = px.bar(
        overview,
        x="Fonte",
        y="Cobertura",
        color="Fonte",
        text_auto=".2f",
        title="Cobertura por fonte (%)",
        labels={"Cobertura": "Cobertura (%)", "Fonte": "Fonte"},
        color_discrete_map={"Cosmos": "#5dade2", "Mercado Livre": "#f5c242"},
    )
    figure.update_yaxes(range=[0, 100])
    st.plotly_chart(figure, width="stretch")


def show_categories():
    st.title("Categorias")
    categories = category_comparison_metrics(catalog_context())
    total_eans = int(categories["cosmos_total"].sum())
    st.metric("EANs utilizados na análise", f"{total_eans:,}".replace(",", "."))
    st.caption("EANs encontrados por categoria. O Mercado Livre é agrupado pela categoria correspondente do Cosmos.")
    chart_data = categories.sort_values("cosmos_total", ascending=False).melt(
        id_vars="category",
        value_vars=["cosmos_found", "meli_found"],
        var_name="source",
        value_name="EANs encontrados",
    )
    chart_data["source"] = chart_data["source"].map({
        "cosmos_found": "Cosmos",
        "meli_found": "Mercado Livre",
    })
    figure = px.bar(
        chart_data,
        x="category",
        y="EANs encontrados",
        color="source",
        barmode="group",
        text_auto=True,
        title="EANs encontrados por categoria",
        labels={"category": "Categoria", "source": "Fonte"},
        color_discrete_map={"Cosmos": "#5dade2", "Mercado Livre": "#f5c242"},
    )
    figure.update_xaxes(tickangle=-35)
    st.plotly_chart(figure, width="stretch")

    table = categories.rename(columns={
        "category": "Categoria",
        "cosmos_total": "Cosmos total",
        "cosmos_found": "Cosmos encontrados",
        "cosmos_coverage": "Cosmos cobertura (%)",
        "meli_total": "Mercado Livre total",
        "meli_found": "Mercado Livre encontrados",
        "meli_coverage": "Mercado Livre cobertura (%)",
    })
    st.dataframe(table.round(2), hide_index=True, width="stretch")


def show_product_fields(title: str, product: dict | None):
    st.subheader(title)
    if not product:
        st.info("Ficha indisponível.")
        return
    fields = {"ean": "EAN", "description": "Descrição", "brand": "Marca", "category": "Categoria comercial", "netWeight": "Peso líquido", "grossWeight": "Peso bruto", "width": "Largura", "height": "Altura", "length": "Comprimento", "ncm": "NCM", "cest": "CEST"}
    st.dataframe(pd.DataFrame([{"Campo": label, "Valor": str(product.get(key)) if product.get(key) is not None else "—"} for key, label in fields.items()]), hide_index=True, width="stretch")
    image_url = product.get("imageUrl")
    try:
        valid_url = isinstance(image_url, str) and urlsplit(image_url).scheme in ("http", "https") and bool(urlsplit(image_url).hostname)
    except ValueError:
        valid_url = False
    if valid_url:
        st.link_button(f"Abrir imagem — {title}", image_url)
    else:
        st.caption("Imagem indisponível.")


def show_products():
    st.title("Explorar produtos")
    value = require_products()
    query = st.text_input("Buscar EAN (completo ou parcial)", key="product_search").strip()
    matches = value["frame"]
    if query:
        matches = matches.loc[matches["ean"].str.contains(query, regex=False, na=False)]
    if matches.empty:
        st.info("Nenhum EAN corresponde à busca e aos filtros atuais.")
        return
    names = {"ean": "EAN", "category": "Categoria", "status": "Status"}
    table = matches[list(names)].rename(columns=names)
    table["Status"] = table["Status"].map(STATUSES)
    st.dataframe(table, hide_index=True, width="stretch")
    choices = matches["ean"].tolist()
    if st.session_state.get("product_ean") not in choices:
        st.session_state["product_ean"] = choices[0]
    ean = st.selectbox("EAN para inspecionar", choices, key="product_ean")
    product = next(product for product in value["run"].products if product["ean"] == ean)
    columns = st.columns(3)
    columns[0].metric("Status", STATUSES[product["status"]])
    columns[1].metric("Atributos válidos", sum(product["attributes"].values()))
    if product.get("error"):
        st.text(f"Erro: {product['error']}")
    left, right = st.columns(2)
    with left:
        show_product_fields("Marketplace", product["marketplace"])
    with right:
        show_product_fields("Cosmos", product["cosmos"])
    units = value["run"].metadata.get("units", {})
    if isinstance(units, dict):
        st.caption(f"Pesos: {units.get('weight', 'consulte a convenção do collector')}. Dimensões: {units.get('dimensions', 'valores originais, sem conversão')}.")
    st.caption("Os links de imagem abrem o endereço salvo; nenhuma imagem é baixada pelo dashboard.")
    st.subheader("Atributos válidos no Cosmos")
    product_attributes = product.get("attributes")
    if not isinstance(product_attributes, dict):
        product_attributes = {}
    attribute_rows = [
        {"Atributo": label, "Disponível": bool(product_attributes.get(key, False))}
        for key, label in ATTRIBUTES.items()
    ]
    st.dataframe(pd.DataFrame(attribute_rows), hide_index=True, width="stretch")
    st.subheader("Accuracy: comparação determinística")
    labels = {"ean": "EAN", "brand": "Marca normalizada", "netWeight": "Peso líquido", "grossWeight": "Peso bruto", "ncm": "NCM"}
    accuracy = product.get("accuracy", {})
    st.dataframe(pd.DataFrame([{"Atributo": label, "Resultado": "Confere" if accuracy.get(key) is True else "Diverge" if accuracy.get(key) is False else "Não comparável"} for key, label in labels.items()]), hide_index=True, width="stretch")
    st.caption("Não comparável: valor ausente em uma das fontes ou produto não encontrado.")
    if st.checkbox("Visualizar resposta original (raw JSON)", key=f"raw_{value['path'].name}_{ean}"):
        raw, error = load_raw(value["path"], ean)
        if error:
            st.warning(error)
        else:
            st.json(raw, expanded=False)
