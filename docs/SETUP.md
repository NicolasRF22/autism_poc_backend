# Autism.IA - Guia de Execução

## 📋 Pré-requisitos

- Python 3.8+ instalado
- Node.js 20 LTS+ (recomendado 20.19+) e npm instalados
- Git (opcional)

### Versão de Node recomendada (WSL/Linux)

O frontend usa Vite 6 e `@vitejs/plugin-react` 5, que pedem Node.js 20 LTS+ (recomendado 20.19+).

```bash
# Se você usa nvm
nvm install 20
nvm use 20
nvm alias default 20

# Validar versões
node -v
npm -v
```

## 🚀 Instalação e Primeira Execução

### 1. Ambiente Python (Backend)

O ambiente virtual já foi criado. Ative-o e instale as dependências:

```bash
# Ativar ambiente virtual
source ~/.virtualenvs/autismia-dotvenv/bin/activate  # Linux/Mac

# Instalar dependências Python
pip install -r backend/requirements.txt
```

### 2. Dependências React (Frontend)

```bash
cd frontend
npm install
npm audit
npm run build
cd ..
```

## 🎯 Executar a Aplicação

### Opção 1: Script Automático (Recomendado)

Execute o script que inicia backend e frontend juntos:

```bash
chmod +x backend/scripts/start.sh
./backend/scripts/start.sh
```

### Opção 2: Executar Manualmente

**Terminal 1 - Backend:**
```bash
source ~/.virtualenvs/autismia-dotvenv/bin/activate
cd backend
python app.py
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

## 🌐 Acessar a Aplicação

- **Frontend (Interface Web)**: http://localhost:3000
- **Backend (API)**: http://localhost:5000
- **Health Check**: http://localhost:5000/api/health

### 🔐 Primeiro login (POC)

- Usuário inicial: `admin`
- Senha inicial: `admin123`
- Após login, a aplicação libera as rotas conforme o perfil (`admin`, `secretaria`, `coordenacao`, `professor`, `viewer`)

## 📁 Estrutura do Projeto

```
Aut/
├── backend/
│   ├── app.py              # API Flask com todos os endpoints
│   ├── requirements.txt
│   ├── .env                # Variáveis de ambiente do backend
│   └── scripts/start.sh    # Script de inicialização
├── frontend/
│   ├── src/
│   │   ├── components/     # Componentes React (Sidebar)
│   │   ├── pages/          # Páginas (Home, Formulários, Respostas)
│   │   ├── services/       # Integração com API
│   │   ├── App.jsx         # Componente principal
│   │   └── main.jsx        # Ponto de entrada
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── .gitignore
└── README.md
```

## 🎨 Funcionalidades Implementadas

### ✅ Backend (Flask API)

- **POST /api/auth/login** - Login e emissão de token JWT
- **GET /api/auth/me** - Retorna usuário autenticado
- **POST /api/auth/logout** - Logout (stateless)
- **GET /api/auth/users** - Lista usuários (admin)
- **POST /api/auth/users** - Cria usuário (admin)
- **PUT /api/auth/users/<user_id>/role** - Atualiza perfil (admin)
- **GET /api/audit/events** - Lista trilha de auditoria (admin)

- **GET /api/forms** - Lista todos os formulários disponíveis
- **GET /api/forms/<form_id>** - Retorna formulário específico
- **POST /api/submissions** - Submete formulário preenchido
- **GET /api/submissions** - Lista todas as submissões
- **GET /api/submissions/<id>** - Retorna submissão específica
- **GET /api/submissions/<id>/download** - Download de submissão em JSON
- **GET /api/submissions/download-all** - Download de todas as submissões
- **GET /api/health** - Status da API

### ✅ Frontend (React)

- **Página Inicial** - Apresentação da aplicação e features
- **Sidebar** - Navegação entre páginas
- **Página de Formulários** - Seleção de formulários disponíveis
- **Formulário Individual** - Preenchimento de questões
- **Página de Respostas** - Visualização e download de submissões

### 📋 Formulários Incluídos

1. **M-CHAT** - Modified Checklist for Autism in Toddlers (10 questões)
2. **CARS** - Childhood Autism Rating Scale (8 questões)
3. **ADOS-2** - Autism Diagnostic Observation Schedule (7 questões)

## 🔧 Configuração

Edite o arquivo `backend/.env` para alterar configurações:

```env
APP_NAME=Autism.IA
DEBUG=True
HOST=0.0.0.0
PORT=5000
GOOGLE_API_KEY=sua_chave_google
GOOGLE_GENERATION_MODEL=gemini-2.5-flash
GOOGLE_EMBEDDING_MODEL=gemini-embedding-001

# Limites para página admin de gastos (opcional)
GOOGLE_RATE_LIMIT_DEFAULT_RPM=
GOOGLE_RATE_LIMIT_DEFAULT_TPM=
GOOGLE_RATE_LIMIT_DEFAULT_RPD=

# Exemplo por modelo (sobrescreve o default)
GOOGLE_RATE_LIMIT_GEMINI_2_5_FLASH_RPM=
GOOGLE_RATE_LIMIT_GEMINI_2_5_FLASH_TPM=
GOOGLE_RATE_LIMIT_GEMINI_2_5_FLASH_RPD=
GOOGLE_RATE_LIMIT_GEMINI_EMBEDDING_001_RPM=
GOOGLE_RATE_LIMIT_GEMINI_EMBEDDING_001_TPM=
GOOGLE_RATE_LIMIT_GEMINI_EMBEDDING_001_RPD=

# Autenticação
AUTH_ADMIN_USERNAME=admin
AUTH_ADMIN_PASSWORD=admin123
AUTH_JWT_SECRET=troque-este-valor-em-producao
AUTH_TOKEN_EXP_MINUTES=480

# Dados estruturados
DATA_BACKEND=postgres
DATABASE_URL=postgresql+psycopg2://...pooler.supabase.com:5432/postgres?sslmode=require

# Object Storage (PDFs)
OBJECT_STORAGE_BACKEND=supabase
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sb_secret_xxx
SUPABASE_STORAGE_BUCKET_RAG=rag-documents
SUPABASE_STORAGE_BUCKET_PEI=pei-documents
```

### Buckets necessários no Supabase Storage

- `rag-documents` (privado)
- `pei-documents` (privado)

### Backfill de arquivos legados (local → Supabase)

Após configurar o `.env` e reiniciar o backend:

```bash
cd backend
python3 scripts/backfill_object_storage.py
```

Esse script migra PDFs locais de `rag_documents/` e `peis/` para os buckets e registra metadados em `object_storage_files`.

## 📊 Export de Dados

Os dados podem ser exportados em formato JSON:

- **Individual**: Clique em "Baixar JSON" em cada submissão
- **Todas**: Clique em "Baixar Todas (JSON)" no topo da página de respostas

## 🛠️ Tecnologias Utilizadas

### Backend
- Python 3.12
- Flask 3.0.0
- Flask-CORS
- SQLAlchemy
- Pydantic
- orjson

### Frontend
- React 18
- React Router DOM
- Axios
- Vite 6

## 📝 Próximas Melhorias

- [ ] Adicionar refresh token e revogação de sessão
- [ ] Migrar usuários/auditoria para banco relacional
- [ ] Adicionar mais formulários de avaliação
- [ ] Gráficos e análises estatísticas
- [ ] Export em PDF
- [ ] Testes automatizados

## 🐛 Solução de Problemas

### Backend não inicia
- Verifique se o ambiente virtual está ativado
- Confirme que todas as dependências foram instaladas
- Verifique se a porta 5000 está disponível

### Frontend não carrega dados
- Confirme que o backend está rodando em http://localhost:5000
- Verifique o console do navegador para erros
- Teste o endpoint: http://localhost:5000/api/health

### Erro de CORS
- O Flask-CORS já está configurado
- Verifique se ambos os servidores estão rodando

## 📞 Suporte

Para dúvidas ou problemas, consulte os logs no terminal onde os servidores estão rodando.

---

**Desenvolvido para o projeto Autism.IA** 🧩
