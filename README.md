# Olist Data Pipeline — Medallion Architecture

Pipeline de dados do marketplace Olist implementado com PySpark + Delta Lake, seguindo a arquitetura Medallion (Bronze → Silver → Gold). Simula localmente o fluxo que em produção seria orquestrado pelo **Azure Data Factory** com dados disponibilizados via **Delta Sharing**.

---

## a) Diagrama da arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                          FONTE DE DADOS                             │
│          data/raw/*.csv  (Brazilian E-Commerce — Olist)             │
└────────────────────────────────┬────────────────────────────────────┘
                                 │  01_bronze.py
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BRONZE  (delta/bronze/)                                            │
│  Ingestão fiel dos CSVs — sem transformações                        │
│  + coluna ingest_timestamp                                          │
│                                                                     │
│  orders │ order_items │ customers │ products │ sellers              │
│  payments │ reviews                                                 │
└────────────────────────────────┬────────────────────────────────────┘
                                 │  02_silver.py
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SILVER  (delta/silver/)                                            │
│  Limpeza, tipagem e consolidação                                    │
│                                                                     │
│  • Converte colunas de data para TimestampType                      │
│  • Remove order_id / customer_id nulos                              │
│  • Deduplicação por order_id (mais recente prevalece)               │
│  • Filtra apenas status: delivered | shipped                        │
│  • Join: orders + order_items + customers + products + sellers      │
│                                                                     │
│  orders_consolidated │ payments_summary                             │
└────────────────────────────────┬────────────────────────────────────┘
                                 │  03_gold.py
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GOLD  (delta/gold/)                                                │
│  Agregações analíticas prontas para o Dashboard                     │
│                                                                     │
│  customer_summary │ product_summary │ seller_summary                │
└────────────────────────────────┬────────────────────────────────────┘
                                 │  04_share_simulation.py
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  OUTPUT  (output/)                                                  │
│  Simulação de Delta Sharing — CSVs exportados para o Dashboard      │
│                                                                     │
│  gold_customer_summary_export.csv                                   │
│  gold_product_summary_export.csv                                    │
│  gold_seller_summary_export.csv                                     │
└─────────────────────────────────────────────────────────────────────┘
```

O arquivo `pipeline_runner.py` orquestra as etapas Bronze → Silver → Gold em sequência, registrando timestamps e capturando falhas sem interromper as etapas seguintes.

---

## b) Decisões de design

### 1. Status de pedidos descartados na Silver (não na Bronze)

Os status descartados foram: `created`, `approved`, `processing`, `invoiced`, `unavailable`, `canceled`.

**Por que descartar na Silver e não na Bronze?**
A Bronze é uma zona de pouso fiel à fonte — nenhum dado deve ser alterado ou removido lá, pois ela serve como auditoria e permite reprocessamento. A Silver é a camada de negócio: faz sentido analítico trabalhar apenas com pedidos que efetivamente geraram movimento logístico e receita realizável. Pedidos `canceled` ou `unavailable` distorceriam métricas de receita e volume. Pedidos `created`/`processing` ainda não confirmaram entrega, tornando-os prematuros para análise de vendas.

### 2. Deduplicação por order_id com Window Function

Em vez de um simples `dropDuplicates()`, foi usada uma `Window` particionada por `order_id` ordenada por `order_purchase_timestamp DESC`, mantendo sempre o registro mais recente. Isso preserva a rastreabilidade e é a abordagem correta quando um mesmo pedido pode ter aparecido em múltiplas ingestões com estados diferentes.

### 3. Cálculo de receita total como `price + freight_value`

A receita foi calculada somando `price` (valor do produto) e `freight_value` (frete), pois ambos compõem o valor total pago pelo cliente e faturado pelo vendedor. Usar só o `price` subestimaria a receita real da plataforma e do vendedor. O `total_paid` da tabela de pagamentos foi mantido separado (em `payments_summary`) por representar o que o cliente efetivamente pagou, que pode incluir descontos ou diferenças de parcelamento.

### 4. payments_summary calculado independentemente

A agregação de pagamentos foi feita diretamente sobre a tabela `bronze.payments` (não sobre a `orders_consolidated`), pois um mesmo pedido pode ter múltiplas linhas de pagamento (ex.: cartão + voucher). Agregar antes do join evita multiplicação de linhas e garante valores corretos de `total_paid`.

---

## c) Como rodar o projeto

### Pré-requisitos

- Python 3.9+
- Java 11+ (necessário para o PySpark)

```bash
# Verificar versões
python --version
java -version
```

### Instalação das dependências

```bash
pip install pyspark delta-spark pandas
```

### Estrutura de pastas esperada

```
olist-pipeline/
├── data/
│   └── raw/                  ← coloque os CSVs do Kaggle aqui
├── delta/                    ← criado automaticamente pelo pipeline
├── output/                   ← criado automaticamente pelo share_simulation
├── 01_bronze.py
├── 02_silver.py
├── 03_gold.py
├── 04_share_simulation.py
├── pipeline_runner.py
└── README.md
```

### Download dos dados

1. Acesse [https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
2. Faça download e descompacte
3. Copie os arquivos abaixo para `data/raw/`:

```
olist_orders_dataset.csv
olist_order_items_dataset.csv
olist_customers_dataset.csv
olist_products_dataset.csv
olist_sellers_dataset.csv
olist_order_payments_dataset.csv
olist_order_reviews_dataset.csv
```

### Executar o pipeline completo

```bash
# Opção 1 — orquestrador (recomendado)
python pipeline_runner.py

# Opção 2 — etapas individuais
python 01_bronze.py
python 02_silver.py
python 03_gold.py

# Simulação de Delta Sharing (exporta CSVs)
python 04_share_simulation.py
```

---

## d) O que mudaria em produção

| Aspecto | Implementação local | Produção (Databricks + ADF + Delta Sharing) |
|---|---|---|
| **Orquestração** | `pipeline_runner.py` com `subprocess` | Azure Data Factory com pipelines, triggers e dependências entre atividades |
| **Escalabilidade** | SparkSession local, limitada pela RAM da máquina | Cluster Databricks auto-scaling, processamento distribuído real |
| **Delta Sharing** | Exportação manual para CSV | Delta Sharing com personal token, compartilhamento seguro sem cópia de dados |
| **Monitoramento** | `print()` no console | Azure Monitor, alertas, logs centralizados, retry automático |
| **Qualidade de dados** | Filtros básicos na Silver | Great Expectations ou Delta Live Tables com expectativas declarativas |
| **Versionamento de dados** | Delta local sem controle de schema | Delta Lake com Schema Evolution, `OPTIMIZE` e `VACUUM` agendados |
| **Segurança** | Sem autenticação | Unity Catalog com controle de acesso por coluna/linha e auditoria |

---

## e) Limitações

- **Sem testes automatizados**: não há testes unitários para as transformações; em produção, cada função deveria ter cobertura com `pytest` + mocks de DataFrames Spark.
- **Schema não validado**: a Bronze aceita qualquer schema do CSV; em produção seria necessário validar contra um schema esperado e versionar com Schema Registry.
- **Sem particionamento**: as tabelas Delta não estão particionadas (ex.: por `order_purchase_timestamp`), o que impacta performance em queries analíticas em datasets maiores.
- **`payments_summary` não integrada ao Gold**: a tabela foi gerada na Silver mas não foi usada nas agregações Gold (customer_summary e seller_summary usam `price + freight_value` direto). Um join com `payments_summary` poderia enriquecer as análises com dados de forma de pagamento.
- **Sem tratamento de dados nulos nas métricas Gold**: produtos sem `product_category_name` são agrupados como `null`; em produção seria adequado atribuir uma categoria padrão ("sem categoria") ou tratá-los separadamente.
- **Pipeline não incremental**: todas as etapas fazem `overwrite` completo; em produção seria necessário lógica de processamento incremental (ex.: merge/upsert via Delta).
#   P r o j e t o - F r a m e w o r k - - - R e t h i n k  
 