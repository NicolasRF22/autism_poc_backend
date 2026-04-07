# Fase 2 — Relatório de Execução (2026-04-06)

## Escopo desta validação

- Integração backend `file|postgres|dual` para domínios:
  - `diary`
  - `pdi`
- Rotas cobertas pelo smoke da Fase 2:
  - `POST/GET/PUT/DELETE /api/diary/entries`
  - `GET /api/diary/students`
  - `POST/GET/PUT/DELETE /api/pdi`
  - `GET /api/pdi/id/<id>`
  - `GET /api/pdi/all`

## Artefatos criados

- Script de smoke Fase 2:
  - [backend/scripts/smoke_phase2.sh](backend/scripts/smoke_phase2.sh)

## Estado da execução nesta sessão

- **Modo `postgres`: APROVADO**
  - API iniciada em `http://localhost:5054`
  - Fluxo completo de smoke executado (login, create/read/update/delete para `diary` e `pdi`)
  - Limpeza final de registros de teste executada com sucesso

- **Modo `dual`: APROVADO**
  - API iniciada em `http://localhost:5055`
  - Fluxo completo de smoke executado com sucesso
  - Escrita e remoção via API confirmadas com respostas `200/201`

Observação operacional desta sessão:
- no início, o `.env` local estava sem `DATABASE_URL`; após fornecer a string do Supabase Session Pooler, os testes foram executados com sucesso.
- foi necessário reset controlado de `users/index.json` apenas para padronizar credenciais de teste, com restauração do backup ao final.

## Comandos utilizados na execução

### 1) Subir API em `postgres`

```bash
cd backend
DATA_BACKEND=postgres python3 app.py
```

### 2) Rodar smoke Fase 2 em `postgres`

```bash
cd backend
API_BASE="http://localhost:5000/api" ADMIN_USER="admin" ADMIN_PASS="<SENHA_ADMIN>" ./scripts/smoke_phase2.sh
```

### 3) Subir API em `dual`

```bash
cd backend
DATA_BACKEND=dual python3 app.py
```

### 4) Rodar smoke Fase 2 em `dual`

```bash
cd backend
API_BASE="http://localhost:5000/api" ADMIN_USER="admin" ADMIN_PASS="<SENHA_ADMIN>" ./scripts/smoke_phase2.sh
```

## Critério de aprovação

- `postgres`: CRUD completo de diary/pdi funcionando e persistindo no banco.
- `dual`: CRUD completo funcionando via API com escrita simultânea em arquivo + Postgres.
- Sem regressão em respostas HTTP e payloads já usados pelo frontend.

## Evidências resumidas (logs HTTP)

- `postgres`:
  - `POST /api/diary/entries` → `201`
  - `PUT /api/diary/entries/<id>` → `200`
  - `POST /api/pdi` → `201`
  - `PUT /api/pdi/<id>` → `200`
  - `GET /api/diary/students` e `GET /api/pdi/all` → `200`
  - `DELETE` de `diary`, `pdi`, `student`, `school` → `200`

- `dual`:
  - mesmo fluxo acima com respostas `200/201`
  - limpeza final de entidades de teste concluída com sucesso

## Validação final determinística (2026-04-06)

- Execução do smoke de Fase 2 em `postgres` com log em `/tmp/smoke_phase2_postgres_final.log`:
  - `EXIT:0`
  - conclusão explícita: `Smoke test da Fase 2 concluído com sucesso`

- Execução do smoke de Fase 2 em `dual` com log em `/tmp/smoke_phase2_dual_final.log`:
  - `EXIT:0`
  - conclusão explícita: `Smoke test da Fase 2 concluído com sucesso`

- Validação de Fase 1 também executada nesta sessão em `postgres` e `dual`:
  - `Smoke test da Fase 1 concluído com sucesso`
