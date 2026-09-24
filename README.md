# Dashboard Cosmos x Mercado Livre

Dashboard Streamlit para comparar a cobertura de EANs entre Cosmos e Mercado Livre, usando os snapshots públicos versionados em `data/catalog/`.

## Executar localmente

Execute a partir da raiz do repositório, assim como no Streamlit Community Cloud:

```bash
cd 123333333333331233EEW
dashboard/.venv/bin/streamlit run dashboard/app.py
```

Ou, em um ambiente virtual próprio:

```bash
python -m pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

O dashboard possui três páginas:

- **Visão geral**: indicadores de Cosmos e Mercado Livre.
- **Categorias**: comparação por categoria e total de EANs utilizados.
- **Explorar produtos**: consulta dos produtos do run Cosmos versionado em `data/runs/2026-09-16-cosmos-analysis/`.

## Dados

Os arquivos usados pelo catálogo ficam em `data/catalog/`:

- `eans-amostra.csv`: universo de EANs da análise.
- `cosmo.csv`: resultados do Cosmos.
- `mercado-livre.csv`: resultados do Mercado Livre.

O padrão é 3.268 EANs únicos. Os indicadores validados para os snapshots atuais são:

- Cosmos: 726 encontrados, 2.542 não encontrados e 22,22% de cobertura.
- Mercado Livre: 1.609 encontrados, 1.659 não encontrados e 49,24% de cobertura.
- Ambas as fontes: 669 EANs encontrados.

Os CSVs são snapshots públicos do POC. Não coloque credenciais, tokens ou arquivos de secrets no repositório.

## Configuração dos caminhos

Por padrão, o app usa `data/catalog/` relativo à raiz do repositório. É possível substituir o diretório inteiro:

```bash
CATALOG_DATA_DIR=/caminho/para/catalog streamlit run dashboard/app.py
```

Também é possível substituir cada arquivo individualmente com:

- `EANS_SAMPLE_CSV_PATH`
- `COSMOS_CSV_PATH`
- `MELI_CSV_PATH`

Essas variáveis são úteis para validação local ou para apontar para uma cópia atualizada dos dados. No Streamlit Community Cloud, prefira versionar snapshots não sensíveis ou configurar uma origem externa apropriada.

## Deploy no Streamlit Community Cloud

1. Faça push da branch que contém este repositório para o GitHub.
2. No Streamlit Community Cloud, escolha **Create app**.
3. Selecione o repositório `fmarreiros-alt/123333333333331233EEW`.
4. Selecione a branch publicada.
5. Informe `dashboard/app.py` como **Main file path**.
6. Use Python compatível com as versões fixadas em `dashboard/requirements.txt`.
7. Clique em **Deploy** e acompanhe os logs do build.

O Streamlit Community Cloud executa a aplicação a partir da raiz do repositório. O `requirements.txt` localizado junto ao entrypoint é detectado automaticamente.

## Validar antes do push

A partir da raiz do repositório:

```bash
PYTHONPATH=dashboard:dashboard/tests dashboard/.venv/bin/python -m unittest discover -s dashboard/tests -p 'test_*.py'
dashboard/.venv/bin/python -m py_compile dashboard/app.py dashboard/ui.py dashboard/catalog_analysis.py
git diff HEAD --check
```
