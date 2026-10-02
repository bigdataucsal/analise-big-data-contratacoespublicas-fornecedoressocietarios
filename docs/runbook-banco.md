# Runbook do banco (PostgreSQL gratuito da Aiven)

Como operar, verificar e recuperar o banco do projeto. 

## 1. Identificação do serviço

| Item | Valor |
| --- | --- |
| Projeto na Aiven | afonso-214 |
| Nome do serviço | pg-contratacoes |
| Plano | free-1-1gb (conforme o branch da T1; confirmar no console) |
| Nuvem e região | do-sfo (conforme o branch da T1; confirmar no console) |
| Versão do PostgreSQL | PostgreSQL 18.6 |
| Quem tem acesso ao projeto | T1 e T2 |
| Gerenciado por | Terraform (recurso `banco_projeto`, com `prevent_destroy`) |

## 2. Limites do plano gratuito

- 1 GB de disco. O orçamento utilizável para dados é de 500 a 700 MB (decisão D2).
- 20 conexões simultâneas e sem pool.
- O serviço desliga por inatividade, com aviso antes. Religa-se pelo console.
- Um serviço gratuito por organização.

## 3. Credenciais

- A URI de conexão é lida da variável de ambiente `DATABASE_URL`. Ela nunca vai para arquivo versionado, para chat ou para print.
- No PowerShell, vale só para a janela aberta:

```powershell
$env:DATABASE_URL = "<URI copiada do console da Aiven>"
```

- Para o pipeline agendado, a URI fica nos GitHub Secrets.
- Se a URI ou o token aparecer em um commit, apagar no commit seguinte não basta: rotacionar a senha do serviço no console e o token da Aiven.

## 4. Verificação diária e antes da apresentação

1. Abrir o console da Aiven e conferir que o serviço está em execução. Se estiver desligado, religar e esperar ficar disponível.
2. Testar a conexão (se o `psql` estiver instalado):

```powershell
psql $env:DATABASE_URL -c "select 1"
```

3. Conferir o espaço usado:

```sql
SELECT pg_size_pretty(pg_database_size(current_database()));
```

4. Na semana da apresentação: religar e testar o painel na véspera e de novo uma hora antes, em janela anônima. Manter capturas de tela de cada interação do painel num slide oculto como plano B.

## 5. Benchmark no PostgreSQL

O `etl/benchmark_postgres.py` carrega a fato em um schema isolado, mede a consulta com e sem índice e informa o tamanho real das tabelas.

- Rodar primeiro o ensaio e só depois a rodada completa:

```powershell
python etl/benchmark_postgres.py --linhas 200000
python etl/benchmark_postgres.py --linhas 0
```

- Antes da rodada completa, extrapolar o tamanho do ensaio (tabela mais índice) para 2.005.068 linhas e comparar com o orçamento da seção 2.
- O script trabalha no schema bench e o apaga ao terminar. Se for interrompido ou rodado com --manter, apagar manualmente: DROP SCHEMA IF EXISTS bench CASCADE;
Tamanho de cada tabela, para registrar no documento de escolha do banco:

```sql
SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS tamanho
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

## 6. Se algo der errado

| Sintoma | O que fazer |
| --- | --- |
| Serviço desligado | Religar pelo console, esperar ficar disponível e testar a conexão. |
| Disco cheio ou perto do limite | Apagar o schema do benchmark; conferir os tamanhos pela consulta da seção 5; reduzir colunas ou índices da fato. |
| Erro de conexões esgotadas | Fechar sessões abertas; garantir que o painel use cache e uma conexão reaproveitada; lembrar que não há pool. |
| Painel lento ao vivo | Consultar tabelas ou views materializadas, não a fato; conferir se o cache do Streamlit está ativo. |
| Credencial exposta | Rotacionar a senha do serviço e o token da Aiven; remover o segredo do repositório. |

## 7. Relação com o Terraform

- O banco é criado e mantido pelo Terraform. Alterações de plano, nuvem ou nome pelo console geram divergência com o código.
- Antes de qualquer `terraform apply`, rodar `terraform plan`. O resultado esperado para o banco em uso é "No changes". Se o plano propuser destruir ou substituir o serviço, parar e avisar a T1.
- O `terraform apply` nunca roda ao vivo na apresentação.