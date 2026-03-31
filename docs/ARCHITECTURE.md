# 🏗️ Arquitetura da Aplicação Autism.IA

## 📊 Visão Geral

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                    🌐 FRONTEND (React)                      │
│                    http://IP:3000                           │
│                                                             │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  │ HTTP/REST
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│               🐍 BACKEND (Flask/Python)                     │
│               http://IP:5000/api                            │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                  Rotas da API                        │  │
│  │  /auth  /audit  /schools  /students  /diary  /pdi  /rag │  │
│  └──────────────────┬───────────────────────────────────┘  │
│                     │                                       │
│       ┌─────────────┬─────────────┬─────────────┐         │
│       ▼             ▼             ▼             ▼         │
│  ┌─────────────┐ ┌───────────┐ ┌───────────┐ ┌──────────┐│
│  │   Storage   │ │ Auth/JWT  │ │ Auditoria │ │ RAG      ││
│  │   (JSON)    │ │ + RBAC    │ │ (JSONL)   │ │ Engine   ││
│  └─────────────┘ └───────────┘ └───────────┘ └──────────┘│
│                                                             │
└─────────┬─────────────────────────────┬─────────────────────┘
          │                             │
          ▼                             ▼
┌────────────────────┐      ┌──────────────────────┐
│   📁 Arquivos JSON │      │  🔢 ChromaDB         │
│                    │      │  (Vector Store)      │
│  schools/          │      │                      │
│  students/         │      │  chroma_db/          │
│  diaries/          │      │  ├── chroma.sqlite3  │
│  peis/             │      │  └── [uuid]/         │
│  pdis/             │      │      └── *.bin       │
│  users/            │      │                      │
│  audit_logs/       │      │                      │
└────────────────────┘      └──────────────────────┘
    Dados Estruturados + Auth     Embeddings (vetores)
```

---

## 🗄️ Armazenamento Detalhado

### 1. Arquivos JSON (Dados Estruturados)

```
backend/
├── schools/
│   └── index.json              📋 Lista de todas as escolas
│       [
│         {
│           "id": "uuid-1",
│           "name": "Escola ABC",
│           "address": "Rua X, 123",
│           ...
│         }
│       ]
│
├── students/
│   └── index.json              📋 Lista de todos os alunos
│       [
│         {
│           "id": "uuid-2",
│           "name": "João Silva",
│           "school_id": "uuid-1",
│           ...
│         }
│       ]
│
├── diaries/
│   ├── index.json              📋 Índice de diários
│   └── [diary_id].json         📝 Entrada individual
│
├── peis/
│   ├── index.json              📋 Índice de PEIs
│   ├── [pei_id].json           📄 Dados do PEI
│   └── [pei_id].pdf             📑 PDF gerado
│
└── pdis/
    ├── index.json              📋 Índice de PDIs
    └── [pdi_id].json           📄 Dados do PDI
```

**Características:**
- ✅ Legível por humanos
- ✅ Fácil de fazer backup (copiar pasta)
- ✅ Não precisa servidor separado
- ✅ Não precisa credenciais
- ⚠️ Limite prático: ~10.000 registros
- ⚠️ Sem transações ACID

---

### 2. ChromaDB (Vector Store)

```
backend/
└── chroma_db/
    ├── chroma.sqlite3          🗄️ Índice interno (SQLite)
    │                              Armazena metadados e índices
    │
    └── 2c68e894-uuid.../        🔢 Collection "documentos_pei"
        ├── data_level0.bin        Vetores de embeddings
        ├── header.bin             Metadados da coleção
        ├── link_lists.bin         Índice HNSW (busca rápida)
        └── length.bin             Informações de comprimento
```

**O que é armazenado:**
```python
# Para cada documento carregado:
{
    "id": "doc_uuid_0",
    "document": "chunk de texto aqui...",
    "embedding": [0.123, -0.456, 0.789, ...],  # 768 dimensões
    "metadata": {
        "doc_id": "doc_uuid",
        "filename": "cartilha.pdf",
        "chunk_index": 0,
        "upload_date": "2026-03-10T10:30:00"
    }
}
```

**Características:**
- ✅ Busca semântica ultra-rápida
- ✅ Suporta milhões de vetores
- ✅ Local (sem servidor externo)
- ✅ Não precisa credenciais
- ❌ Não é legível por humanos (binário)
- ❌ Não é MongoDB!

---

## 🔄 Fluxo de Dados

### 1. Cadastro de Escola/Aluno

```
Frontend          Backend              JSON Files
   │                 │                     │
   ├─── POST /api/schools ──►             │
   │                 │                     │
   │              valida                  │
   │              dados                   │
   │                 │                     │
   │              gera UUID                │
   │                 │                     │
   │                 ├───► salva em ──────►
   │                 │     schools/index.json
   │                 │                     │
   │◄─── retorna ────                     │
   │    { id, ... }                       │
```

### 2. Upload de Documento para RAG

```
Frontend          Backend         Gemini API      ChromaDB
   │                │                 │               │
   ├─ POST /upload ►                 │               │
   │    (PDF)       │                 │               │
   │                │                 │               │
   │             extrai               │               │
   │             texto                │               │
   │                │                 │               │
   │             divide               │               │
   │             em chunks            │               │
   │                │                 │               │
   │                ├─ gera embeddings►              │
   │                │                 │               │
   │                │◄─ vetores ──────               │
   │                │    [0.1, 0.2,...]              │
   │                │                 │               │
   │                ├─────────────────┴─► armazena   │
   │                │                     vetores +  │
   │                │                     chunks     │
   │                │                                │
   │◄─── sucesso ───                                │
```

### 3. Geração de PEI (RAG)

```
Frontend          Backend         RAG Engine     ChromaDB      Gemini
   │                │                 │             │            │
   ├─ POST /pei ────►                │             │            │
   │   { student,   │                │             │            │
   │     school }   │                │             │            │
   │                │                │             │            │
   │                ├─ monta contexto►            │            │
   │                │                 │             │            │
   │                │              busca dados     │            │
   │                │              similares       │            │
   │                │                 │             │            │
   │                │                 ├─ query ───►│            │
   │                │                 │  vetores   │            │
   │                │                 │             │            │
   │                │                 │◄─ chunks ──┘            │
   │                │                 │  relevantes             │
   │                │                 │                         │
   │                │                 ├─ gera PEI ─────────────►
   │                │                 │  com contexto           │
   │                │                 │                         │
   │                │                 │◄─ PEI markdown ─────────┘
   │                │                 │                         │
   │                │◄─ retorna PEI ──                         │
   │                │   + PDF                                   │
   │                │                                           │
   │◄─── PEI ───────                                           │
   │    pronto                                                  │
```

---

## 🔑 Variáveis de Ambiente

```env
# ============================================
# DEBUG
# ============================================
# Controla modo de desenvolvimento do Flask
# 
# DEBUG=True:
#   ✅ Auto-reload ao editar código
#   ✅ Erros detalhados com stack trace
#   ✅ Debugger interativo no browser
#   ❌ Expõe informações sensíveis
#   ❌ Performance reduzida
#
# DEBUG=False:
#   ✅ Performance otimizada
#   ✅ Seguro (não expõe código)
#   ✅ Logs limpos
#   ❌ Sem auto-reload
#   ❌ Erros genéricos

DEBUG=False  # Sempre False em produção!

# ============================================
# Servidor
# ============================================
HOST=0.0.0.0  # 0.0.0.0 = aceita conexões externas
              # 127.0.0.1 = apenas localhost
              
PORT=5000     # Porta do backend

# ============================================
# Google Gemini API
# ============================================
# Credencial obrigatória para recursos de IA
# Usada para:
#   - Gerar embeddings (vetores)
#   - Responder perguntas (RAG)
#   - Gerar PEIs contextualizados
#   - Chat inteligente

GOOGLE_API_KEY=sua_chave_aqui

# ============================================
# Autenticação JWT + RBAC
# ============================================
AUTH_JWT_SECRET=troque-por-um-segredo-forte
AUTH_ADMIN_USERNAME=admin
AUTH_ADMIN_PASSWORD=troque-esta-senha
AUTH_TOKEN_EXP_MINUTES=480
```

---

## 📦 Dependências Principais

```python
# Web Framework
Flask==3.0.0          # Backend REST API
Flask-CORS==4.0.0     # Permite frontend acessar backend

# Armazenamento
# (Não usa ORM porque é JSON direto)

# RAG & IA
google-genai>=1.7.0            # Cliente Google Gemini
chromadb>=0.5.23               # Vector store local
langchain>=0.3.13              # Framework RAG
langchain-google-genai>=2.0.8  # Integração Gemini

# Processamento de Documentos
PyPDF2>=3.0.1         # Ler PDFs
fpdf2                 # Gerar PDFs
markdown              # Converter MD para HTML

# Utilitários
python-dotenv==1.0.0  # Ler .env
orjson==3.9.10        # JSON mais rápido
```

---

## 🛡️ Segurança

### Dados Sensíveis
- ✅ `.env` no `.gitignore`
- ✅ CORS habilitado com suporte a preflight
- ✅ Autenticação JWT com controle de perfil (`admin`, `editor`, `viewer`)
- ✅ Auditoria de ações mutáveis e downloads/PDF
- ✅ Validação de inputs
- ⚠️ Dados não criptografados (considere em produção)

### Armazenamento
```bash
# Permissões recomendadas
chmod 700 backend/schools
chmod 700 backend/students
chmod 700 backend/chroma_db
chown -R usuario_app:usuario_app backend/
```

### API Rate Limiting
Considere adicionar:
```python
from flask_limiter import Limiter

limiter = Limiter(
    app,
    key_func=lambda: request.remote_addr,
    default_limits=["200 per day", "50 per hour"]
)
```

---

## 🚀 Escalabilidade

### Atual (JSON + ChromaDB)
- ✅ Até 10.000 registros
- ✅ 1-10 usuários simultâneos
- ✅ Deployment simples
- ✅ Backup fácil

### Quando migrar para DB?
- Mais de 10.000 registros
- Mais de 50 usuários simultâneos
- Necessidade de queries complexas
- Múltiplos servidores (load balancing)

### Migração futura (PostgreSQL)
```
Backend (Flask)
     │
     ├─► PostgreSQL (dados estruturados)
     │      ├── schools
     │      ├── students
     │      ├── diaries
     │      ├── peis
     │      └── pdis
     │
     └─► ChromaDB (continua local)
          └── Embeddings (RAG)
```

---

## 📊 Performance

### Benchmarks estimados:

| Operação | Tempo | Observações |
|----------|-------|-------------|
| Criar escola | ~10ms | JSON write |
| Listar 100 alunos | ~20ms | JSON read + parse |
| Gerar embedding | ~500ms | API Gemini |
| Busca vetorial | ~50ms | ChromaDB (HNSW) |
| Gerar PEI completo | ~5-10s | Gemini API + RAG |
| Upload PDF 10MB | ~2-3s | Parse + embeddings |

### Gargalos:
1. **API Gemini** - Principal gargalo (chamadas externas)
2. **JSON parse** - Para grandes listas (>1000 itens)
3. **Concorrência** - Escrita simultânea em JSON

### Otimizações possíveis:
- Cache (Redis) para dados frequentes
- CDN para frontend
- Workers assíncronos (Celery)
- PostgreSQL para dados estruturados

---

## 🔧 Manutenção

### Backup Automático
```bash
#!/bin/bash
# /etc/cron.daily/backup-autism-ia

BACKUP_DIR="/backups/autism-ia"
SOURCE="/home/usuario/Aut/backend"
DATE=$(date +%Y%m%d)

tar -czf "$BACKUP_DIR/backup_$DATE.tar.gz" \
  "$SOURCE/schools" \
  "$SOURCE/students" \
  "$SOURCE/diaries" \
  "$SOURCE/peis" \
  "$SOURCE/pdis" \
  "$SOURCE/chroma_db"

# Manter apenas últimos 30 dias
find "$BACKUP_DIR" -name "backup_*.tar.gz" -mtime +30 -delete
```

### Monitoramento
```bash
# Ver uso de disco
du -sh backend/*

# Ver quantidade de registros
jq '. | length' backend/schools/index.json
jq '. | length' backend/students/index.json

# Ver logs do backend
pm2 logs autism-backend --lines 100
```

### Limpeza
```bash
# Remover PEIs antigos (>90 dias)
find backend/peis -name "*.pdf" -mtime +90 -delete

# Limpar uploads temporários
find backend/uploads -name "*" -mtime +7 -delete
```

---

## 📚 Recursos Adicionais

- [FAQ.md](FAQ.md) - Perguntas frequentes
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Guia de deploy
- [STORAGE_INFO.md](STORAGE_INFO.md) - Detalhes de armazenamento
- [CHECKLIST_DEPLOY.txt](CHECKLIST_DEPLOY.txt) - Checklist rápido
