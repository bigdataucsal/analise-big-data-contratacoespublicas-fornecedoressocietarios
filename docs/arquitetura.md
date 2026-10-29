# Arquitetura da solução

Descreve o desenho fim a fim do pipeline, do dado bruto ao painel, e registra o estado atual de implementação na Fase 2. Os números vêm da coleta completa de 2025 e da competência 2026-09-14 da Receita.

## Diagrama

```mermaid
flowchart LR
    subgraph FONTES["Fontes abertas"]
        PNCP["PNCP<br/>API REST - JSON"]
        RFB["Receita Federal<br/>CNPJ - ZIP e CSV"]
        IBGE["IBGE<br/>API de nomes e SIDRA 9605"]
        CGU["Portal da Transparencia<br/>CEIS e CNEP - Fase 2"]
    end

    subgraph ETL["ETL local em Python - C:/dados-bigdata, fora do Git"]
        COL["Coleta dia a dia<br/>JSONL bruto - 3,62 GB"]
        TRAT["Tratamento DuckDB<br/>Parquet - 254,1 MB"]
        REC["Recorte<br/>239.605 raizes de CNPJ"]
        FIL["Filtro em chunks<br/>28,67 GB para 69,05 MB"]
        GEN["Inferencia<br/>genero RN-04 e RN-05<br/>proxy racial RN-06"]
    end

    subgraph ARM["Armazenamento e Servico"]
        PQ[("Parquet local<br/>base nacional")]
        PG[("PostgreSQL 18.6 Aiven free<br/>10 tabelas, 2 MVs e 13 indices")]
        OS[("OpenSearch<br/>texto do objeto - condicional")]
    end

    subgraph APR["Apresentacao"]
        ST["Streamlit Cloud<br/>filtro cruzado, metrica, drill-down"]
    end

    subgraph OPS["Infraestrutura e CI/CD"]
        TF["Terraform IaC<br/>afonso-214a / pg-contratacoes<br/>prevent_destroy ativo"]
        GHA["GitHub Actions CI/ETL<br/>valida Terraform, scripts e indices"]
    end

    PNCP --> COL
    COL --> TRAT
    TRAT --> REC
    REC --> FIL
    RFB --> FIL
    IBGE --> GEN
    FIL --> GEN
    TRAT --> PQ
    GEN --> PQ
    CGU -.-> PQ
    PQ -->|"carga da fato reduzida"| PG
    TRAT -.->|"texto do objeto"| OS
    PG -->|"leitura exclusiva de MVs"| ST
    OS -.-> ST
    TF -->|"provisiona e protege"| PG
    GHA -->|"terraform fmt e validate"| TF
    GHA -->|"valida DDL, 13 indices e cota 1 GB"| PG