# Runbook do banco (PostgreSQL gratuito da Aiven)

Como operar, verificar e recuperar o banco do projeto.

## 1. Identificação do serviço

| Item | Valor |
| --- | --- |
| Projeto na Aiven | afonso-214 |
| Nome do serviço | pg-contratacoes |
| Plano | free-1-1gb, conforme o Terraform da T1; o console mostra 1 CPU, 1 GB de RAM e 1 GB de disco |
| Nuvem e região | do-sfo (conforme o branch da T1; confirmar no console) |
| Versão do PostgreSQL | PostgreSQL 18.6 |
| Quem tem acesso ao projeto | T1 e T2 |
| Gerenciado por | Terraform (recurso `banco_projeto`, com `prevent_destroy`) |

## 2. Limites do plano gratuito

- 1 GB de disco. O orçamento utilizável para dados é de 500 a 700 MB (decisão D2).
- 1 CPU e 1 GB de RAM.
- 20 conexões simultâneas e sem pool.
- O serviço desliga por inatividade, com aviso antes. Religa-se pelo console.
- Um serviço gratuito por organização.

## 3. Credenciais

- A URI de conexão é lida da variável de ambiente `DATABASE_URL`. Ela nunca vai para arquivo versionado, para chat ou para print.
- No PowerShell, vale só para a janela aberta. Para não deixar a URI no histórico do terminal, usar:

```powershell
$env:DATABASE_URL = Read-Host "Cole a URI"
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

O valor deve ficar perto de 8 MB quando não há dados carregados. O console mostra o uso do plano (memória, armazenamento e CPU dos últimos 60 minutos).

4. Na semana da apresentação: religar e testar o painel na véspera e de novo uma hora antes, em janela anônima. Manter capturas de tela de cada interação do painel num slide oculto como plano B.

## 5. Benchmark no PostgreSQL

O `etl/benchmark_postgres.py` carrega a fato no schema `bench`, mede a consulta com e sem índice e informa o tamanho real das tabelas. Ele apaga o schema ao terminar, exceto com `--manter`. Se for interrompido, apagar manualmente:

```sql
DROP SCHEMA IF EXISTS bench CASCADE;
```

Resultados de 02/10/2026, com o serviço gratuito (evidências em `docs/evidencias/`):

| Linhas na fato | Fato com índices | Consulta no servidor, sem índices | Consulta no servidor, com índices |
| --- | --- | --- | --- |
| 200 mil | 23,1 MB | 1,5 s | 1,6 s |
| 1 milhão | 111,3 MB | 14,3 s | 6,0 s |
| 2.005.068 | 177 MB sem índices (medido); com índices, estimativa de 213 a 223 MB | a conexão caiu | não medido |

Na rodada completa (`--linhas 0`) a carga funcionou, mas a consulta derrubou a conexão (`SSL connection has been closed unexpectedly`) e o schema ficou no banco até ser apagado à mão. A causa não foi confirmada: o console mostrou memória em 80% e picos de CPU perto de 100%.

**Não rodar `--linhas 0` no nó gratuito.** Usar o ensaio (200 mil) ou, no máximo, 1 milhão de linhas, com o serviço ligado e o banco perto de 8 MB. Os arquivos temporários de uma rodada de 1 milhão somaram 1.164 MB acumulados, e esse espaço conta na cota de disco enquanto a consulta roda.

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
| Nome do servidor não resolve (`could not translate host name`) | Conferir no console que o serviço está em execução e que o host da URI é o atual; testar com `nslookup`. |
| Conexão cai no meio de uma consulta | Consulta pesada sobre a fato. Conferir memória e CPU no console, apagar o schema `bench` se ficou carregado e consultar agregados. |
| Disco cheio ou perto do limite | Apagar o schema do benchmark; conferir os tamanhos pela consulta da seção 5; reduzir colunas ou índices da fato. |
| Erro de conexões esgotadas | Fechar sessões abertas; garantir que o painel use cache e uma conexão reaproveitada; lembrar que não há pool. |
| Painel lento ao vivo | Consultar tabelas ou views materializadas, não a fato; conferir se o cache do Streamlit está ativo. |
| Credencial exposta | Rotacionar a senha do serviço e o token da Aiven; remover o segredo do repositório. |

## 7. Relação com o Terraform

- O banco é criado e mantido pelo Terraform. Alterações de plano, nuvem ou nome pelo console geram divergência com o código.
- Antes de qualquer `terraform apply`, rodar `terraform plan`. O resultado esperado para o banco em uso é "No changes". Se o plano propuser destruir ou substituir o serviço, parar e avisar a T1.
- O `terraform apply` nunca roda ao vivo na apresentação.