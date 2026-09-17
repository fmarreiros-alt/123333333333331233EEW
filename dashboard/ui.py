"""Shared controls live in the entrypoint so filters survive page navigation."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
import plotly.express as px
import streamlit as st

from data import (
    ANALYSIS_METRICS, ATTRIBUTES, RUNS_DIR, STATUSES, aggregate, category_metrics, filter_products,
    list_runs, load_raw, load_run, product_frame, run_signature,
)


@st.cache_data(show_spinner=False, max_entries=16)
def cached_run(path: str, signature: tuple):
    # signature deliberately participates in the cache key; files remain on disk once.
    return load_run(Path(path))


def clear_filters():
    for key in list(st.session_state):
        if key.startswith("filter_") or key in ("product_search", "product_ean"):
            del st.session_state[key]


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


def category_chart(categories: pd.DataFrame, metrics: list[str], title: str):
    labels = {"coverage": "Cobertura"}
    melted = categories.melt(id_vars="category", value_vars=metrics, var_name="Métrica", value_name="Valor")
    melted["Métrica"] = melted["Métrica"].map(labels)
    figure = px.bar(melted, x="category", y="Valor", color="Métrica", barmode="group", title=title, labels={"category": "Categoria"})
    figure.update_yaxes(range=[0, 100])
    st.plotly_chart(figure, width="stretch")


def show_overview():
    st.title("Visão geral")
    value = context()
    metrics = aggregate(value["frame"])
    cards = [
        ("Total de EANs", metrics["total"]), ("Encontrados", metrics["found"]),
        ("Não encontrados", metrics["notFound"]), ("Erros", metrics["errors"]),
        ("Cobertura", f"{metrics['coverage']:.1f}%"),
    ]
    for group in (cards[:4], cards[4:]):
        for column, (label, number) in zip(st.columns(len(group)), group):
            column.metric(label, number)
    require_products()
    categories = category_metrics(value["frame"])
    category_chart(categories, ["coverage"], "Cobertura por categoria (%)")
    found = value["frame"].loc[value["frame"]["found"]]
    if not found.empty:
        counts = metrics["analysisCounts"]
        attribute_counts = pd.DataFrame({"Atributo": [ANALYSIS_METRICS[key] for key in counts], "Registros": list(counts.values())})
        figure = px.bar(attribute_counts, x="Atributo", y="Registros", title="Registros encontrados com cada atributo")
        st.plotly_chart(figure, width="stretch")


def show_categories():
    st.title("Categorias")
    categories = category_metrics(require_products()["frame"])
    names = {"category": "Categoria", "total": "EANs", "found": "Encontrados", "notFound": "Não encontrados", "errors": "Erros", "coverage": "Cobertura (%)"}
    table = categories[list(names)].rename(columns=names).copy()
    sort_column = st.selectbox("Ordenar por", list(names.values()), index=5, key="category_sort")
    descending = st.checkbox("Ordem decrescente", value=True, key="category_descending")
    st.dataframe(table.sort_values(sort_column, ascending=not descending).round(2), hide_index=True, width="stretch")
    st.caption("A tabela também pode ser ordenada clicando no cabeçalho de cada coluna.")
    category_chart(categories, ["coverage"], "Cobertura por grupo (%)")


def show_attributes():
    st.title("Atributos")
    frame = require_products()["frame"]
    metrics = aggregate(frame)
    if not metrics["found"]:
        st.info("Não há produtos encontrados nos filtros atuais. A cobertura de atributos não pode ser calculada.")
        return
    coverage = pd.DataFrame({"Atributo": list(ATTRIBUTES.values()), "Cobertura (%)": list(metrics["attributeCoverage"].values())})
    st.subheader("Cobertura global entre encontrados")
    st.dataframe(coverage.round(2), hide_index=True, width="stretch")
    figure = px.bar(coverage, x="Atributo", y="Cobertura (%)")
    figure.update_yaxes(range=[0, 100])
    st.plotly_chart(figure, width="stretch")
    categories = category_metrics(frame)
    heatmap = categories.set_index("category")[list(ATTRIBUTES)].rename(columns=ATTRIBUTES)
    for category in categories.loc[categories["found"] == 0, "category"]:
        heatmap.loc[category] = float("nan")
    figure = px.imshow(heatmap, zmin=0, zmax=100, text_auto=".1f", aspect="auto", color_continuous_scale="Blues", labels={"x": "Atributo", "y": "Categoria", "color": "Cobertura (%)"}, title="Cobertura por categoria (%)")
    st.plotly_chart(figure, width="stretch")
    st.caption("Células vazias representam categorias sem produtos encontrados; 0% significa que nenhum encontrado possui o atributo.")


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
