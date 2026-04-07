# Fase 1 — Relatório de Execução (2026-04-06)

## Escopo validado nesta sessão

- Modo `file` (persistência local) para domínios:
  - `schools`
  - `students`
  - `teachers`
- Modo `postgres` (persistência em Supabase Postgres pooler)
- Modo `dual` (escrita em arquivo + Postgres, leitura priorizando Postgres)
- Feature flags carregadas em runtime:
  - `DATA_BACKEND=file|postgres|dual`
  - `DATABASE_URL`

## Resultado

- **Modo `file`: APROVADO**
  - Login JWT OK
  - Create school OK
  - Create student OK
  - Create teacher OK
  - List schools/students/teachers OK
  - Delete school/student/teacher OK

- **Modo `postgres`: APROVADO**
  - Conexão com Supabase pooler OK
  - Login JWT OK
  - CRUD completo para schools/students/teachers OK
  - Limpeza final de registros de teste OK

- **Modo `dual`: APROVADO**
  - Login JWT OK
  - CRUD via API OK
  - Escrita em arquivo local confirmada para schools/students/teachers
  - Remoção em arquivo local confirmada
  - Remoção via API (404 pós-delete) confirmada

## Evidências técnicas

- Backend de teste executado em `http://localhost:5051`
- Backend de teste `postgres` executado em `http://localhost:5052`
- Backend de teste `dual` executado em `http://localhost:5053`
- Logs de requests `201/200` para criação/listagem e `200` para remoções.
- Script de referência:
  - [backend/scripts/smoke_phase1.sh](backend/scripts/smoke_phase1.sh)
- Guia de execução:
  - [backend/docs/PHASE1_TEST_GUIDE.md](backend/docs/PHASE1_TEST_GUIDE.md)

String de conexão validada (formato):

```env
postgresql+psycopg2://postgres.<project-ref>:<PASSWORD>@aws-1-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require
```

Notas de troubleshooting encontradas durante os testes:
- Host `db.<project-ref>.supabase.co:5432` falhou por rota IPv6 no ambiente WSL testado.
- Pooler funcionou via IPv4.
- Senha com colchetes (`[senha]`) falhou; senha real sem colchetes funcionou.

## Pendências para concluir Fase 1 completa

- Nenhuma pendência funcional da Fase 1.
- Próximo passo recomendado: iniciar Fase 2 (`diary` e `pdi`) usando o mesmo padrão de backend `file|postgres|dual`.

## Pré-requisito para concluir os 2 modos restantes

Definir no `.env`:

```env
DATA_BACKEND=postgres
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/database
```

ou

```env
DATA_BACKEND=dual
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/database
```

Depois, repetir o smoke test do guia.

## Segurança/limpeza aplicada durante o teste

- Backup de [backend/users/index.json](backend/users/index.json) criado em `/tmp/aut_users_index_backup.json`
- Arquivo original de usuários restaurado ao final
- Registros de teste criados durante o smoke foram removidos no final
