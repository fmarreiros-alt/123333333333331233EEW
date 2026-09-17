import streamlit as st

from ui import prepare_context


st.set_page_config(page_title="Cosmos Catalog Benchmark", page_icon="📊", layout="wide")
page = st.navigation([
    st.Page("pages/1_overview.py", title="Visão geral", default=True),
    st.Page("pages/2_categories.py", title="Categorias", url_path="categorias"),
    st.Page("pages/3_attributes.py", title="Atributos", url_path="atributos"),
    st.Page("pages/4_products.py", title="Explorar produtos", url_path="produtos"),
])
prepare_context()
page.run()
