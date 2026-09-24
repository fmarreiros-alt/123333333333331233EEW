# Análise Cosmos x Mercado Livre

**Data da análise:** 24/09/2026
**Projeto:** `123333333333331233EEW`

## Objetivo

Comparar a cobertura de EANs entre Cosmos e Mercado Livre usando o universo definido em `eans-amostra.csv`, sem utilizar a planilha consolidada anterior.

As fontes utilizadas foram:

- `/home/f.marreiros/Downloads/poc/eans-amostra.csv`
- `/home/f.marreiros/Downloads/poc/cosmo.csv`
- `/home/f.marreiros/Downloads/poc/mercado-livre.csv`

## Método

Os arquivos foram lidos com Python/Pandas usando UTF-8, preservando o EAN como texto para não perder zeros à esquerda.

O denominador dos indicadores é o número de EANs únicos da amostra:

```text
3.269 linhas na amostra
3.268 EANs únicos
```

A amostra possui uma repetição do EAN `8806091131881` associada a duas entidades. Essa repetição não aumenta o denominador.

### Regra de encontrado

**Cosmos**

Um EAN é considerado encontrado quando:

```text
api_status está vazio
E
 description está preenchida
```

**Mercado Livre**

Um EAN é considerado encontrado quando `matched = TRUE`. Os registros repetidos do Mercado Livre são deduplicados por EAN antes da contagem.

O campo `n_results` não é usado como regra principal, pois representa a quantidade de resultados retornados e não necessariamente uma correspondência válida do EAN.

## Resultado geral

| Fonte | Total de EANs | Encontrados | Não encontrados | Cobertura |
|---|---:|---:|---:|---:|
| Cosmos | 3.268 | 726 | 2.542 | 22,22% |
| Mercado Livre | 3.268 | 1.609 | 1.659 | 49,24% |

### Leitura executiva

- O Mercado Livre encontrou **1.609 EANs**, contra **726 no Cosmos**.
- A cobertura do Mercado Livre foi **27,02 pontos percentuais** maior que a do Cosmos.
- O Mercado Livre encontrou **883 EANs a mais** que o Cosmos.
- Foram encontrados nas duas fontes **669 EANs**.
- Foram encontrados somente no Cosmos **57 EANs**.
- Foram encontrados somente no Mercado Livre **940 EANs**.
- Não foram encontrados em nenhuma das duas fontes **1.602 EANs**.

## Resultado por categoria

As categorias do gráfico usam `entity` do Cosmos como categoria canônica. Os EANs do Mercado Livre são associados a essa categoria pelo EAN, garantindo que as barras comparem o mesmo grupo de produtos.

Os valores abaixo representam **EANs encontrados**, e não o total de EANs da categoria.

| Categoria | Cosmos total | Cosmos encontrados | Cosmos cobertura | Mercado Livre total | Mercado Livre encontrados | Mercado Livre cobertura |
|---|---:|---:|---:|---:|---:|---:|
| Smartphone | 400 | 99 | 24,75% | 400 | 121 | 30,25% |
| Cama Box | 300 | 2 | 0,67% | 300 | 43 | 14,33% |
| Armário | 300 | 14 | 4,67% | 300 | 134 | 44,67% |
| Pneu | 300 | 45 | 15,00% | 300 | 167 | 55,67% |
| Sofá | 300 | 3 | 1,00% | 300 | 75 | 25,00% |
| Ar Condicionado | 299 | 126 | 42,14% | 299 | 232 | 77,59% |
| Air Fryer | 200 | 95 | 47,50% | 200 | 134 | 67,00% |
| Notebook | 200 | 31 | 15,50% | 200 | 131 | 65,50% |
| Guarda-roupa | 200 | 8 | 4,00% | 200 | 67 | 33,50% |
| TV | 120 | 45 | 37,50% | 120 | 90 | 75,00% |
| Grill | 100 | 64 | 64,00% | 100 | 72 | 72,00% |
| Colchão | 100 | 4 | 4,00% | 100 | 34 | 34,00% |
| Refrigerador | 100 | 58 | 58,00% | 100 | 90 | 90,00% |
| Tablet | 100 | 9 | 9,00% | 100 | 11 | 11,00% |
| Freezer | 50 | 22 | 44,00% | 50 | 45 | 90,00% |
| Lava e Seca | 50 | 22 | 44,00% | 50 | 42 | 84,00% |
| Lava-louças | 50 | 26 | 52,00% | 50 | 40 | 80,00% |
| Microondas | 50 | 21 | 42,00% | 50 | 34 | 68,00% |
| Lavadora de Roupas | 49 | 32 | 65,31% | 49 | 47 | 95,92% |
| **Total** | **3.268** | **726** | **22,22%** | **3.268** | **1.609** | **49,24%** |

## Maiores diferenças

| Categoria | Cosmos encontrados | Mercado Livre encontrados | Diferença Mercado Livre - Cosmos |
|---|---:|---:|---:|
| Pneu | 45 | 167 | +122 |
| Armário | 14 | 134 | +120 |
| Ar Condicionado | 126 | 232 | +106 |
| Notebook | 31 | 131 | +100 |
| Sofá | 3 | 75 | +72 |

A menor diferença positiva ocorreu em Tablet, com 11 EANs encontrados no Mercado Livre contra 9 no Cosmos.

## Dados para o gráfico

O gráfico recomendado para a apresentação é de barras agrupadas por categoria:

- **Eixo X:** Categoria
- **Eixo Y:** EANs encontrados
- **Série azul:** Cosmos
- **Série amarela:** Mercado Livre
- **Modo:** barras lado a lado, com os valores sobre as barras

Cores utilizadas no dashboard:

```text
Cosmos:         #5DADE2
Mercado Livre:  #F5C242
```

## Observações sobre a base

- `eans-amostra.csv` tem 3.269 linhas e 3.268 EANs únicos.
- `cosmo.csv` tem 3.268 registros e 3.268 EANs únicos.
- `mercado-livre.csv` tem 3.298 linhas brutas e 3.268 EANs únicos; há 30 ocorrências duplicadas.
- Todos os 3.268 EANs únicos da amostra aparecem nas duas fontes.
- A categoria composta `Lava e Seca|Lavadora de Roupas` do Mercado Livre é alinhada à categoria do Cosmos pelo EAN para manter a comparação por grupo consistente.
- As métricas e o gráfico são gerados pelo módulo Python `dashboard/catalog_analysis.py`.
