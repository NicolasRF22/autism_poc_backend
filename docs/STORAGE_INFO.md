# 📁 Armazenamento de Dados - Autism.IA

## Estado atual (2026-04)

A aplicação usa arquitetura híbrida de armazenamento:

1. **PostgreSQL (Supabase)** para dados estruturados da aplicação.
2. **ChromaDB** para embeddings e metadados vetoriais do RAG.
3. **Object Storage (Supabase Storage)** para PDFs (anexos e PEIs gerados).
4. **Arquivos locais** apenas como compatibilidade/temporário (modo local e arquivos transitórios).

---

## 1) Dados estruturados (PostgreSQL)

Controlado por `DATA_BACKEND` no `backend/.env`:

- `file`: armazenamento local em JSON.
- `postgres`: armazenamento principal em PostgreSQL.
- `dual`: escrita em file + postgres (migração/rollout).

No ambiente atual, o backend está operando com suporte a PostgreSQL e metadados de storage remoto.

### Tabelas relevantes

- `schools`, `students`, `teachers`
- `diary_entries`, `pdis`
- `case_study_submissions`, `school_registration_submissions`
- `object_storage_files` (**nova**) para rastrear objetos no Storage

Campos principais em `object_storage_files`:

- `doc_type` (ex.: `rag_attachment_pdf`, `pei_generated_pdf`)
- `reference_id` (ex.: `doc_id` do RAG, `pei_id`)
- `bucket`, `object_key`
- `original_filename`, `mime_type`, `size_bytes`
- `extra` (JSON de contexto: aluno, escola etc.)

---

## 2) Embeddings e recuperação semântica (ChromaDB)

ChromaDB continua sendo usado para:

- armazenar chunks de texto indexados;
- armazenar embeddings por chunk;
- busca semântica para chat RAG e geração de PEI.

Isso não mudou com a migração para Supabase Storage: o **vetor continua no Chroma**.

---

## 3) PDFs no Supabase Storage (novo padrão)

### Buckets privados

- `rag-documents`
- `pei-documents`

### Fluxo de Anexo RAG

1. API recebe PDF (`/api/rag/upload`).
2. Salva temporário em `uploads/`.
3. Extrai texto, divide em chunks, gera embeddings.
4. Indexa chunks + embeddings no ChromaDB.
5. Envia PDF original para bucket `rag-documents` com key `{doc_id}.pdf`.
6. Registra metadado em `object_storage_files`.

### Fluxo de PEI

1. API gera markdown do PEI (`/api/rag/generate-pei`).
2. Renderiza PDF temporário.
3. Envia PDF para bucket `pei-documents` com key `{pei_id}.pdf`.
4. Registra metadado em `object_storage_files`.
5. Mantém índice de PEI (`peis/index.json`) para compatibilidade do domínio.

### Download/remoção

Downloads seguem por **proxy autenticado no backend**:

- `/api/rag/documents/<doc_id>/download`
- `/api/rag/peis/<pei_id>/pdf`

Ao remover, backend apaga do vector/index + Storage + metadados.

---

## 4) Variáveis de ambiente de Storage

```env
OBJECT_STORAGE_BACKEND=supabase
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sb_secret_xxx
SUPABASE_STORAGE_BUCKET_RAG=rag-documents
SUPABASE_STORAGE_BUCKET_PEI=pei-documents
```

Quando `OBJECT_STORAGE_BACKEND=local`, o backend usa pastas locais equivalentes.

---

## 5) Backfill de arquivos legados

Script implementado para migração de PDFs locais existentes:

- `backend/scripts/backfill_object_storage.py`

Ele:

- sobe arquivos de `backend/rag_documents/` e `backend/peis/` para os buckets;
- cria metadados em `object_storage_files`;
- mantém idempotência básica (pula referências já registradas).

---

## 6) Backup e recuperação

### Banco relacional

- usar backup/PITR do Supabase para tabelas.

### Object storage

- usar política de retenção/backup do bucket (conforme plano Supabase).

### ChromaDB

- manter backup de `backend/chroma_db/` ou volume persistente equivalente.

---

## 7) Resumo rápido

| Camada | Tecnologia | Conteúdo |
|---|---|---|
| Dados estruturados | Supabase Postgres | Cadastros, diário, PDI, metadados de arquivos |
| Vetorial | ChromaDB | Chunks e embeddings do RAG |
| Binários | Supabase Storage (privado) | PDFs de anexos e PEIs |
| Compatibilidade | Arquivos locais | Transitório/local fallback |

# 📁 Armazenamento de Dados - Autism.IA

## Sobre o Sistema de Armazenamento

Esta aplicação **NÃO utiliza banco de dados tradicional** (SQL/MongoDB/PostgreSQL).

### 🗄️ Como os dados são armazenados?

A aplicação usa **dois sistemas de armazenamento**:

#### 1. Arquivos JSON (Dados Estruturados)
Todos os cadastros e formulários são salvos como arquivos JSON:

```
backend/
├── schools/
│   └── index.json           # Lista de escolas cadastradas
├── students/
│   └── index.json           # Lista de alunos cadastrados
├── diaries/
│   └── index.json           # Índice de diários
│   └── [id].json            # Cada entrada de diário
├── peis/
│   └── index.json           # Índice de PEIs gerados
│   └── [id].json            # Cada PEI
│   └── [id].pdf             # PDF do PEI
└── pdis/
    └── index.json           # Índice de PDIs
    └── [id].json            # Cada PDI
├── users/
│   └── index.json           # Usuários e perfis (admin/secretaria/coordenacao/professor/viewer)
└── audit_logs/
  └── events.jsonl         # Trilha de auditoria (append-only)
```

**Vantagens:**
- ✅ Simples de entender e debugar
- ✅ Fácil fazer backup (copiar pasta)
- ✅ Não precisa configurar servidor de banco
- ✅ Portável entre sistemas

**Desvantagens:**
- ⚠️ Não é ideal para MUITOS registros (>10k)
- ⚠️ Sem transações ACID
- ⚠️ Possível perda de dados em escrita concorrente

#### 2. ChromaDB (Vector Store)
Usado **apenas** para armazenar embeddings do RAG:

```
backend/
└── chroma_db/
    ├── chroma.sqlite3       # Índice do ChromaDB
    └── [collection_id]/     # Vetores e metadados
```

**Para que serve:**
- Armazena embeddings dos documentos carregados
- Permite busca semântica (RAG)
- Essencial para a geração de PEIs contextualizados

## 🔄 Quando considerar migrar para banco de dados?

Se você planeja:
- Ter **mais de 1.000 escolas/alunos** cadastrados
- Múltiplos usuários **editando simultaneamente**
- Precisar de **queries complexas** (relatórios, estatísticas)
- Ter **alta concorrência** de acessos

Considere migrar para PostgreSQL ou MongoDB.

## 💾 Como fazer Backup?

### Backup Manual
```bash
# Criar backup de todos os dados
tar -czf backup_$(date +%Y%m%d).tar.gz \\
  backend/schools \\
  backend/students \\
  backend/diaries \\
  backend/peis \\
  backend/pdis \\
  backend/chroma_db \
  backend/users \
  backend/audit_logs

# Restaurar backup
tar -xzf backup_20260310.tar.gz -C /caminho/destino/
```

### Backup Automático (Cron)
```bash
# Adicionar ao crontab (crontab -e)
# Backup diário às 2h da manhã
0 2 * * * cd /caminho/autism.ia && tar -czf backups/backup_$(date +\%Y\%m\%d).tar.gz backend/schools backend/students backend/diaries backend/peis backend/pdis backend/chroma_db
```

### Script de Backup
```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/caminho/backups"
SOURCE_DIR="/caminho/autism.ia/backend"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Fazer backup
tar -czf "$BACKUP_DIR/autism_ia_$DATE.tar.gz" \\
  "$SOURCE_DIR/schools" \\
  "$SOURCE_DIR/students" \\
  "$SOURCE_DIR/diaries" \\
  "$SOURCE_DIR/peis" \\
  "$SOURCE_DIR/pdis" \\
  "$SOURCE_DIR/chroma_db" \
  "$SOURCE_DIR/users" \
  "$SOURCE_DIR/audit_logs"

# Manter apenas últimos 7 backups
ls -t "$BACKUP_DIR"/autism_ia_*.tar.gz | tail -n +8 | xargs rm -f

echo "Backup criado: autism_ia_$DATE.tar.gz"
```

## 🔍 Estrutura dos Dados

### Exemplo: schools/index.json
```json
[
  {
    "id": "uuid-aqui",
    "name": "Escola Municipal ABC",
    "address": "Rua exemplo, 123",
    "phone": "(11) 1234-5678",
    "created_at": "2026-03-10T10:30:00",
    "updated_at": "2026-03-10T10:30:00"
  }
]
```

### Exemplo: students/index.json
```json
[
  {
    "id": "uuid-aqui",
    "name": "João Silva",
    "birth_date": "2015-05-10",
    "school_id": "uuid-escola",
    "diagnosis": "TEA Nível 1",
    "created_at": "2026-03-10T11:00:00",
    "updated_at": "2026-03-10T11:00:00"
  }
]
```

## ⚙️ Variáveis de Ambiente Relacionadas

```env
# Não existem variáveis de configuração de banco de dados
# O armazenamento é feito diretamente nas pastas do projeto

# Apenas o ChromaDB pode ter seu caminho customizado no código
# Por padrão: backend/chroma_db/
```

## 🚀 Migração Futura para Banco de Dados

Se decidir migrar no futuro, você precisará:

1. **Escolher o banco** (PostgreSQL recomendado)
2. **Criar schema/modelos** (usando SQLAlchemy ou similar)
3. **Script de migração** para importar JSONs:

```python
# Exemplo conceitual
import json
from models import School, Student
from database import db

# Migrar escolas
with open('backend/schools/index.json') as f:
    schools = json.load(f)
    for school_data in schools:
        school = School(**school_data)
        db.session.add(school)
    db.session.commit()

# Similar para students, diaries, etc.
```

4. **Atualizar os storage files** (`*_storage.py`) para usar ORM
5. **Adicionar variável DATABASE_URL** ao .env

## 📝 Notas Importantes

1. **Sem DATABASE_URL necessária**: Não há conexão com banco SQL tradicional
2. **Autenticação usa JWT + JSON local**: usuários ficam em `backend/users/index.json`
3. **Auditoria é persistida em JSONL**: eventos em `backend/audit_logs/events.jsonl`
4. **ChromaDB é independente**: Mesmo que perca os JSONs, pode regenerar embeddings
5. **Arquivos são o "banco de dados"**: Proteja com backups regulares
6. **Permissões**: Certifique-se que o usuário do servidor tem permissão de leitura/escrita

## 🔐 Segurança

- ✅ Arquivos .json não são acessíveis via web (apenas via API)
- ✅ Backend valida todos os dados antes de salvar
- ⚠️ Considere criptografar dados sensíveis em produção
- ⚠️ Use HTTPS para proteger transmissão de dados
- ⚠️ Configure permissões adequadas no sistema de arquivos:

```bash
# Apenas o usuário da aplicação deve ter acesso
chmod 700 backend/schools backend/students backend/diaries backend/peis backend/pdis
chmod 700 backend/users backend/audit_logs
chown -R usuario_app:usuario_app backend/
```

## 💡 Resumo

| Aspecto | Solução Atual |
|---------|---------------|
| **Cadastros** | Arquivos JSON |
| **Autenticação** | `backend/users/index.json` |
| **Auditoria** | `backend/audit_logs/events.jsonl` |
| **Vector Store** | ChromaDB |
| **Banco SQL** | Não usado |
| **MongoDB** | Não usado |
| **Backup** | Copiar pastas manualmente |
| **Migração** | Possível quando necessário |

**Para a maioria dos casos de uso educacionais, o sistema atual de arquivos JSON é suficiente e funciona perfeitamente!** 🎉
