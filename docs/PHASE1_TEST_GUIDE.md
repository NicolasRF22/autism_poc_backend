# Fase 1 — Guia de Teste e Validação

Este guia valida a Fase 1 já implementada:
- Persistência configurável por `DATA_BACKEND` (`file`, `postgres`, `dual`)
- Migração inicial dos domínios `schools`, `students`, `teachers`
- Fallback seguro para armazenamento em arquivo

## 1) O que foi implementado

- Nova camada de repositórios PostgreSQL para cadastros em [backend/postgres_repositories.py](backend/postgres_repositories.py)
- Integração por feature flag em [backend/app.py](backend/app.py)
- Novas variáveis de ambiente documentadas em [backend/.env.example](backend/.env.example)
- Driver Postgres incluído em [backend/requirements.txt](backend/requirements.txt)

## 2) Pré-requisitos

- Python 3.12+
- Dependências instaladas do backend
- Banco PostgreSQL acessível (local, Render Postgres, Supabase, Neon etc.) para teste `postgres`/`dual`
- Token JWT válido para acessar endpoints protegidos

## 3) Configuração de ambiente

Crie um `.env` no backend com base em [backend/.env.example](backend/.env.example).

Campos relevantes para Fase 1:

```env
DATA_BACKEND=file
DATABASE_URL=
AUTH_ADMIN_USERNAME=admin
AUTH_ADMIN_PASSWORD=SEU_PASSWORD_FORTE
AUTH_JWT_SECRET=SEU_SEGREDO_FORTE
```

Exemplo Postgres:

```env
DATA_BACKEND=postgres
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/database
```

Exemplo Supabase Pooler (recomendado quando houver problema de IPv6 no host `db.<ref>.supabase.co`):

```env
DATA_BACKEND=postgres
DATABASE_URL=postgresql+psycopg2://postgres.<project-ref>:<PASSWORD>@aws-1-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require
```

Exemplo dual-write:

```env
DATA_BACKEND=dual
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/database
```

## 4) Instalação e execução local

No diretório `backend`:

```bash
pip install -r requirements.txt
python app.py
```

Se `DATA_BACKEND=postgres` e `DATABASE_URL` estiver ausente, a aplicação deve falhar no startup com erro explícito.

## 5) Smoke test de API (file, postgres e dual)

### 5.1 Login (obter token)

```bash
API_BASE="http://localhost:5000/api"
TOKEN=$(curl -s -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"SEU_PASSWORD_FORTE"}' | jq -r '.token')

echo "$TOKEN"
```

### 5.2 Criar escola

```bash
curl -s -X POST "$API_BASE/schools" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"Escola Teste Fase1",
    "cnpj":"00.000.000/0001-00",
    "institution_type":"Municipal",
    "address":{"city":"Itajubá"}
  }' | jq
```

### 5.3 Listar escolas

```bash
curl -s "$API_BASE/schools" \
  -H "Authorization: Bearer $TOKEN" | jq
```

### 5.4 Criar aluno (vinculado a escola)

```bash
SCHOOL_ID=$(curl -s "$API_BASE/schools" -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')

curl -s -X POST "$API_BASE/students" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\":\"Aluno Teste Fase1\",
    \"age\":\"10\",
    \"school_id\":\"$SCHOOL_ID\",
    \"school_name\":\"Escola Teste Fase1\",
    \"grade\":\"5\",
    \"class\":\"A\"
  }" | jq
```

### 5.5 Criar docente

```bash
curl -s -X POST "$API_BASE/teachers" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"Docente Teste Fase1",
    "school_name":"Escola Teste Fase1",
    "specialization":"AEE"
  }' | jq
```

### 5.6 Validar leitura

```bash
curl -s "$API_BASE/students" -H "Authorization: Bearer $TOKEN" | jq
curl -s "$API_BASE/teachers" -H "Authorization: Bearer $TOKEN" | jq
```

## 6) Critérios de aprovação por modo

### A) Modo `file`

- CRUD de `schools`, `students`, `teachers` funciona
- Dados aparecem em:
  - [backend/schools/index.json](backend/schools/index.json)
  - [backend/students/index.json](backend/students/index.json)
  - [backend/teachers/index.json](backend/teachers/index.json)

### B) Modo `postgres`

- CRUD funciona com os mesmos endpoints
- Dados persistem no banco
- Se o banco estiver vazio, as listas retornam vazias (sem fallback para arquivo)

### C) Modo `dual`

- CRUD funciona
- Escrita ocorre em arquivo e Postgres
- Leitura prioriza Postgres; se vazio em listas, pode cair para arquivo (comportamento de transição)

## 7) Verificação no banco PostgreSQL (opcional)

```sql
select id, updated_at from schools order by updated_at desc limit 10;
select id, updated_at from students order by updated_at desc limit 10;
select id, updated_at from teachers order by updated_at desc limit 10;
```

## 8) Checklist de QA antes da Fase 2

- [ ] `DATA_BACKEND=file` aprovado
- [ ] `DATA_BACKEND=postgres` aprovado
- [ ] `DATA_BACKEND=dual` aprovado
- [ ] Login + JWT funcionando nos três modos
- [ ] CRUD completo para `schools/students/teachers`
- [ ] Sem regressão de frontend nessas telas

## 9) Troubleshooting

- `Import "sqlalchemy" could not be resolved` na IDE:
  - normalmente é ambiente Python não selecionado no editor; em runtime resolve após `pip install -r requirements.txt`
- Erro de startup com `DATA_BACKEND=postgres`:
  - verifique `DATABASE_URL`
- Erro de rede para `db.<project-ref>.supabase.co:5432`:
  - use a URI do **Session Pooler** no Supabase (aba Connect)
- Erro `password authentication failed` com senha entre colchetes:
  - use a senha real sem `[` e `]` (colchetes no painel geralmente são placeholder)
- 401 em qualquer endpoint:
  - obter `token` via `/api/auth/login` e enviar header `Authorization: Bearer <token>`
- `Credenciais inválidas` no login local:
  - confirme `AUTH_ADMIN_USERNAME` e `AUTH_ADMIN_PASSWORD` no `.env`
  - se já existir admin antigo em [backend/users/index.json](backend/users/index.json), o backend não sobrescreve senha automaticamente
  - para reset local controlado: faça backup de [backend/users/index.json](backend/users/index.json), apague o arquivo, ajuste `AUTH_ADMIN_PASSWORD` no `.env` e reinicie o backend para recriar o admin inicial

## 10) Próximo passo recomendado

Após aprovação desta checklist, avançar para Fase 2 com o mesmo padrão para `diary` e `pdi`.
