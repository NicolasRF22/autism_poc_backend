# Autism.IA — Sistema de PEI com RAG

Sistema full-stack para gerenciamento e geração de **Planos Educacionais Individualizados (PEI)** para alunos com autismo, utilizando **Retrieval-Augmented Generation (RAG)** com Google Gemini.

## Documentação adicional

- [Guia de Autenticação, Permissões e Auditoria](AUTHENTICATION_GUIDE.md)

---

## Como o RAG funciona neste projeto

O RAG (Retrieval-Augmented Generation) é a técnica central do sistema. Em vez de pedir ao modelo de IA que "invente" respostas, ele primeiro **busca informações reais dos documentos do aluno** e só então gera a resposta com base nesse contexto.

### Pipeline completo

```
                        ┌─────────────────────────────────────────────┐
  INDEXAÇÃO             │                                             │
  (upload de PDF)       │  1. Extração de texto  (PyPDF2)             │
                        │         ↓                                   │
                        │  2. Divisão em chunks  (1000 chars, 200     │
                        │     chars de overlap entre chunks)          │
                        │         ↓                                   │
                        │  3. Geração de embeddings por chunk         │
                        │     (Gemini gemini-embedding-001)           │
                        │         ↓                                   │
                        │  4. Armazenamento no ChromaDB               │
                        │     (com metadados: aluno, escola, arquivo) │
                        └─────────────────────────────────────────────┘

                        ┌─────────────────────────────────────────────┐
  CONSULTA              │                                             │
  (chat ou PEI)         │  1. Embedding da pergunta/query             │
                        │         ↓                                   │
                        │  2. Busca por similaridade de cosseno       │
                        │     no ChromaDB (top-5 ou top-10 chunks)    │
                        │         ↓                                   │
                        │  3. Montagem do contexto com os chunks      │
                        │     recuperados                             │
                        │         ↓                                   │
                        │  4. Envio para Gemini 2.5 Flash             │
                        │     [System Prompt + Contexto + Pergunta]   │
                        │         ↓                                   │
                        │  5. Resposta gerada com base nos docs reais │
                        └─────────────────────────────────────────────┘
```

### Por que chunks com overlap?

O texto do PDF é dividido em pedaços de **1000 caracteres** com **200 caracteres de sobreposição** entre chunks consecutivos. O overlap garante que frases e ideias que ficam na fronteira entre dois chunks não percam contexto.

### Por que embeddings?

Embeddings são representações numéricas do significado do texto. Textos semanticamente parecidos geram vetores próximos no espaço vetorial. Isso permite buscar chunks **por significado**, não apenas por palavras-chave exatas.

### Chat com RAG (`/api/rag/chat`)

- Recupera os **5 chunks mais similares** à pergunta
- Mantém **histórico de sessão** usando o sistema de `chats` do Gemini
- Retorna as fontes (nome do arquivo, aluno, escola) junto com a resposta

### Geração de PEI (`/api/rag/generate-pei`)

- Busca os **10 chunks mais relevantes** para o aluno/escola
- Usa um system prompt especializado para estruturar o PEI em 10 seções obrigatórias
- Gera o documento em uma única chamada (sem histórico de sessão)

---

## Estrutura do Projeto

```
Aut/
├── backend/
│   ├── app.py                # API Flask — endpoints REST
│   ├── rag_engine.py         # Orquestrador RAG (chat + geração de PEI)
│   ├── vector_store.py       # Interface com ChromaDB
│   ├── document_processor.py # Extração de PDF, chunking e embeddings
│   ├── prompts.py            # System prompts do Gemini
│   ├── pei_storage.py        # Persistência dos PEIs gerados
│   ├── pdf_generator.py      # Geração do PDF do PEI
│   └── chroma_db/            # Banco vetorial persistido (não versionado)
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Home.jsx
│   │   │   ├── FormsPage.jsx
│   │   │   ├── FormDetail.jsx
│   │   │   ├── SubmissionsPage.jsx
│   │   │   └── TesteRAG.jsx  # Interface de teste do RAG
│   │   └── components/
│   │       └── Sidebar.jsx
│   └── index.html
├── backend/
│   ├── requirements.txt
│   └── scripts/start.sh
```

---

## Tecnologias

| Camada | Tecnologia |
|---|---|
| LLM | Google Gemini 2.5 Flash |
| Embeddings | Google `gemini-embedding-001` |
| Banco vetorial | ChromaDB (persistente, similaridade de cosseno) |
| Backend | Python 3.12 + Flask |
| Frontend | React + Vite |

---

## Instalação e Execução

### Pré-requisitos

- Python 3.12+
- Node.js 20 LTS+ (recomendado 20.19+)
- Chave de API do Google Gemini (`GOOGLE_API_KEY`)

Se você usa WSL/Linux com `nvm`:

```bash
nvm install 20
nvm use 20
nvm alias default 20
node -v
npm -v
```

### Backend

```bash
# Criar e ativar ambiente virtual
python -m venv ~/.virtualenvs/autismia-dotvenv
source ~/.virtualenvs/autismia-dotvenv/bin/activate  # Linux/Mac

# Instalar dependências
pip install -r backend/requirements.txt

# Configurar variável de ambiente
export GOOGLE_API_KEY="sua_chave_aqui"
export GOOGLE_GENERATION_MODEL="gemini-2.5-flash"
export GOOGLE_EMBEDDING_MODEL="gemini-embedding-001"

# Executar
cd backend
python app.py
```

### Frontend

```bash
cd frontend
npm install
npm audit
npm run build
npm run dev
```

Ou use o script de inicialização:

```bash
chmod +x backend/scripts/start.sh
./backend/scripts/start.sh
```

---

## Endpoints da API

### Autenticação (POC)

- Login por JWT simples via `POST /api/auth/login`
- Rotas protegidas por token Bearer (`Authorization: Bearer <token>`)
- Perfis suportados: `admin`, `editor`, `viewer`
- `viewer` possui apenas leitura; `admin` gerencia usuários e auditoria

Credenciais padrão iniciais (podem ser sobrescritas por ambiente):

- `AUTH_ADMIN_USERNAME=admin`
- `AUTH_ADMIN_PASSWORD=admin123`
- `AUTH_JWT_SECRET` para assinatura dos tokens

### RAG
| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/api/rag/upload` | Faz upload e indexa um PDF no ChromaDB |
| `POST` | `/api/rag/chat` | Chat com RAG baseado nos documentos indexados |
| `POST` | `/api/rag/generate-pei` | Gera PEI estruturado para um aluno |
| `GET` | `/api/rag/documents` | Lista documentos indexados |
| `GET` | `/api/rag/students` | Lista alunos com documentos indexados |
| `DELETE` | `/api/rag/documents/<doc_id>` | Remove documento do índice |

### Administração e Auditoria (admin)
| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/auth/users` | Lista usuários cadastrados |
| `POST` | `/api/auth/users` | Cria usuário (`admin`, `editor`, `viewer`) |
| `PUT` | `/api/auth/users/<user_id>/role` | Atualiza perfil do usuário |
| `GET` | `/api/audit/events?limit=200` | Lista eventos de auditoria |
| `GET` | `/api/admin/model-usage` | Uso de modelos Gemini (RPM/TPM/RPD + tokens por operação) |

### Métricas de uso da Gemini API (AI Studio)

O endpoint `/api/admin/model-usage` retorna:

- uso por modelo em janela de 1 minuto e 24h;
- limites configurados (`RPM`, `TPM`, `RPD`);
- breakdown por operação (chat RAG, geração de PEI, embeddings de upload/reindex).

As métricas são de janela móvel de 24h e ficam **em memória** (reiniciam quando o backend reinicia).

#### Variáveis de limite (backend)

Você pode configurar limites globais:

```bash
GOOGLE_RATE_LIMIT_DEFAULT_RPM=10
GOOGLE_RATE_LIMIT_DEFAULT_TPM=250000
GOOGLE_RATE_LIMIT_DEFAULT_RPD=500
```

Ou por modelo (substitui o default):

```bash
GOOGLE_RATE_LIMIT_GEMINI_2_5_FLASH_RPM=10
GOOGLE_RATE_LIMIT_GEMINI_2_5_FLASH_TPM=250000
GOOGLE_RATE_LIMIT_GEMINI_2_5_FLASH_RPD=500

GOOGLE_RATE_LIMIT_GEMINI_EMBEDDING_001_RPM=100
GOOGLE_RATE_LIMIT_GEMINI_EMBEDDING_001_TPM=1000000
GOOGLE_RATE_LIMIT_GEMINI_EMBEDDING_001_RPD=10000
```

> Ajuste esses valores conforme as cotas reais do seu projeto no Google AI Studio.

### Formulários e Submissões
| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/forms` | Lista formulários disponíveis |
| `GET` | `/api/forms/<id>` | Retorna formulário específico |
| `POST` | `/api/submissions` | Submete formulário preenchido |
| `GET` | `/api/submissions` | Lista submissões |
| `GET` | `/api/health` | Status da API |
