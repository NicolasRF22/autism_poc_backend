# Supabase — Painel + Validação Passo a Passo

## 1) O que precisa estar pronto no painel do Supabase

1. Abra o projeto no Supabase.
2. Vá em **Project Settings → Database**.
3. Confirme estes itens:
   - **Database password** definida e conhecida (a senha real, sem colchetes).
   - **Connection pooling** ativo (Session Pooler).
4. Em **Connection string**, copie a URI do **Session Pooler (port 5432)**.
5. Garanta que a conexão use SSL (`sslmode=require`).

### 1.1 Storage (buckets privados)

Em **Storage → Files**, criar:

- `rag-documents`
- `pei-documents`

Ambos privados (não públicos).

## 2) Configuração no backend

No arquivo `backend/.env`:

- `DATA_BACKEND=postgres`
- `DATABASE_URL=postgresql+psycopg2://...pooler.supabase.com:5432/postgres?sslmode=require`

Para object storage:

- `OBJECT_STORAGE_BACKEND=supabase`
- `SUPABASE_URL=https://<project-ref>.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY=sb_secret_xxx`
- `SUPABASE_STORAGE_BUCKET_RAG=rag-documents`
- `SUPABASE_STORAGE_BUCKET_PEI=pei-documents`

Para transição (escrever em arquivo + Postgres), usar temporariamente:

- `DATA_BACKEND=dual`

## 3) Validação técnica (backend local)

### 3.1 Subir API

```bash
cd backend
python3 app.py
```

### 3.2 Validar health

```bash
curl -s http://localhost:5000/api/health
```

### 3.3 Smoke da Fase 2 (diary/pdi)

```bash
cd backend
API_BASE="http://localhost:5000/api" ADMIN_USER="admin" ADMIN_PASS="<SENHA_ADMIN>" ./scripts/smoke_phase2.sh
```

Resultado esperado ao final:

- `Smoke test da Fase 2 concluído com sucesso`

### 3.4 Backfill de PDFs legados

```bash
cd backend
python3 scripts/backfill_object_storage.py
```

Resultado esperado: contagem de migrados/pulados/falhas para RAG e PEI.

## 4) RLS no Supabase

Para remover os avisos `UNRESTRICTED` e fechar o acesso direto às tabelas sensíveis, execute os scripts nesta ordem no **SQL Editor**:

1. `scripts/phase1_scope_chat_schema.sql`
2. `scripts/phase2_scope_core_policies.sql`
3. `scripts/phase3_enable_rls_hardening.sql`

O backend atual usa a `service role key` do Supabase para ler e escrever, então continuar com RLS ligado não quebra a aplicação. O efeito prático é bloquear acesso direto por `anon`/`authenticated` e deixar o backend como ponto central de acesso.

Tabelas cobertas por essa proteção:

- `user_profiles`
- `chat_sessions`
- `chat_messages`
- `municipalities`
- `schools`
- `students`
- `teachers`
- `teacher_student_links`
- `diary_entries`
- `pdis`
- `case_study_submissions`
- `school_registration_submissions`
- `object_storage_files`

## 5) Validação no painel Supabase (SQL Editor)

Abra **SQL Editor** e execute:

```sql
select count(*) as schools_count from schools;
select count(*) as students_count from students;
select count(*) as teachers_count from teachers;
select count(*) as diary_count from diary_entries;
select count(*) as pdi_count from pdis;
select count(*) as object_storage_files_count from object_storage_files;
```

Para verificar últimas escritas:

```sql
select id, updated_at from diary_entries order by updated_at desc nulls last limit 10;
select id, updated_at from pdis order by updated_at desc nulls last limit 10;
```

### Resultado da última validação automática (2026-04-06)

Consultas executadas via `DATABASE_URL` do backend:

- `schools_count = 4`
- `students_count = 4`
- `teachers_count = 0`
- `diary_count = 4`
- `pdi_count = 3`

Últimos registros observados:

- `diary_entries` com `updated_at` recente (3 registros mais novos retornados)
- `pdis` com `updated_at` recente (3 registros mais novos retornados)

Interpretação:

- Persistência no Supabase está funcional para os domínios validados no smoke.
- `teachers_count = 0` é compatível com o smoke atual, que cria e remove docente ao final.

## 6) Checklist de produção no painel

- Ativar/confirmar **Point-in-time Recovery (PITR)**.
- Confirmar política de backup do projeto.
- Guardar credenciais em cofre (não em docs públicos).
- Rotacionar senha se ela foi compartilhada em canais inseguros.
- (Opcional) Criar usuário de banco dedicado para aplicação, evitando usar usuário master.

### Itens que só você pode confirmar no painel

- `Project Settings -> Database`: rotação da senha do banco após uso em ambiente de teste/chat.
- `Project Settings -> Database`: confirmar Session Pooler ativo e URL correta.
- `Database Backups`: confirmar PITR/backup do projeto.

## 7) Estratégia de rollout recomendada

1. Iniciar com `DATA_BACKEND=dual` por curto período.
2. Rodar smoke e validar leituras/escritas no Supabase.
3. Trocar para `DATA_BACKEND=postgres`.
4. Monitorar erros por 24-48h.
5. Congelar escrita em arquivo local.

## 8) Troubleshooting rápido

- `RuntimeError: DATABASE_URL é obrigatório...`
  - `DATABASE_URL` não carregada no ambiente.
- `password authentication failed`
  - senha incorreta ou com caracteres não codificados.
- timeout/conexão
  - use Session Pooler (5432), não Direct se houver problema de rota IPv6.
- 401 no smoke
  - usuário/senha admin não conferem com `users/index.json` atual.
- erro de storage (`Dependência supabase não instalada`)
  - executar `pip install -r backend/requirements.txt`.
- erro de bucket não encontrado
  - confirmar nomes exatos: `rag-documents` e `pei-documents`.
