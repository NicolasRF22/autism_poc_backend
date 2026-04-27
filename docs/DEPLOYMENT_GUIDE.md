# 🚀 Guia de Deploy - Autism.IA

Este guia explica como configurar e implantar a aplicação Autism.IA em um servidor com IP público.

## 📋 Pré-requisitos

- Servidor Linux com IP público
- Python 3.12+
- Node.js 20 LTS+ (recomendado 20.19+)
- Nginx (recomendado para produção)

Se você usa `nvm` no servidor:

```bash
nvm install 20
nvm use 20
nvm alias default 20
node -v
npm -v
```

## 🔑 Configuração de Variáveis de Ambiente

### 1. Backend (.env)

Crie/edite o arquivo `.env` em `backend/`:

```bash
cp backend/.env.example backend/.env
nano backend/.env
```

**Variáveis OBRIGATÓRIAS a configurar:**

#### `GOOGLE_API_KEY` (CRÍTICO)
1. Acesse: https://aistudio.google.com/app/apikey
2. Crie uma nova chave de API
3. Cole no arquivo `.env`:
```
GOOGLE_API_KEY=sua_chave_google_gemini_aqui
```

#### `AUTH_JWT_SECRET` (CRÍTICO)
Defina um segredo forte para assinatura dos tokens JWT:
```
AUTH_JWT_SECRET=troque-por-um-segredo-forte
```

#### `AUTH_ADMIN_USERNAME` e `AUTH_ADMIN_PASSWORD`
Usuário admin inicial da aplicação:
```
AUTH_ADMIN_USERNAME=admin
AUTH_ADMIN_PASSWORD=troque-esta-senha
```

#### `AUTH_TOKEN_EXP_MINUTES`
Tempo de expiração do token JWT:
```
AUTH_TOKEN_EXP_MINUTES=480
```

#### `DEBUG` (IMPORTANTE)
Para produção, **SEMPRE use**:
```
DEBUG=False
```

#### `HOST` e `PORT`
Mantenha:
```
HOST=0.0.0.0
PORT=5000
```

#### `CORS_ALLOWED_ORIGINS` (WEB)
Em produção, informe o(s) domínio(s) do frontend:
```
CORS_ALLOWED_ORIGINS=https://app.seudominio.com
```

#### `CHROMA_DB_PATH` ou `CHROMA_HOST` (RAG)
Escolha **um** modo de uso do ChromaDB:

- Local persistente (na mesma máquina do backend):
```
CHROMA_DB_PATH=./backend/chroma_db
```

- Remoto via servidor HTTP (máquina separada):
```
CHROMA_HOST=seu-host-chroma
CHROMA_PORT=8000
CHROMA_SSL=false
CHROMA_COLLECTION_NAME=documentos_pei
```

### 📝 Sobre Armazenamento de Dados

Arquitetura atual de produção:

- **PostgreSQL (Supabase)** para dados estruturados (cadastros, diário, PDI etc.)
- **ChromaDB** para vetor/embeddings do RAG
- **Supabase Storage (privado)** para PDFs de anexos e PEIs
- **Tabela `object_storage_files`** no Postgres para metadados de arquivos remotos

No Render, o backend deve subir com `DATA_BACKEND=postgres` e `OBJECT_STORAGE_BACKEND=supabase`.
Além disso, o `startCommand` do serviço executa um espelhamento idempotente antes de iniciar o Flask,
para copiar os JSONs versionados no repositório para o Supabase sempre que houver deploy,
incluindo remoções locais que precisem refletir no banco remoto.
Os usuários de autenticação também seguem esse mesmo fluxo e passam a ser persistidos em `public.user_profiles`.

Arquivos locais criados automaticamente (compatibilidade/temporário):
- `backend/schools/index.json`
- `backend/students/index.json`
- `backend/diaries/`
- `backend/peis/`
- `backend/pdis/`
- `backend/chroma_db/` (vector store)
- `backend/users/index.json` (usuários)
- `backend/audit_logs/events.jsonl` (auditoria)

### Object Storage (obrigatório para PDFs remotos)

Configure no `.env`:

```env
OBJECT_STORAGE_BACKEND=supabase
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sb_secret_xxx
SUPABASE_STORAGE_BUCKET_RAG=rag-documents
SUPABASE_STORAGE_BUCKET_PEI=pei-documents
```

No painel Supabase Storage, crie buckets privados:

- `rag-documents`
- `pei-documents`

### 2. Frontend (Variável de ambiente)

O frontend precisa saber onde está o backend.

#### Configuração recomendada

Crie o arquivo `.env` na pasta `frontend/`:

```bash
# IP ou domínio do seu servidor
VITE_API_BASE_URL=http://SEU_IP_AQUI:5000/api

# (Opcional, apenas para `npm run dev`)
VITE_DEV_PROXY_TARGET=http://SEU_IP_AQUI:5000
```

Exemplo:
```bash
VITE_API_BASE_URL=http://123.45.67.89:5000/api
VITE_DEV_PROXY_TARGET=http://123.45.67.89:5000
```

No código, a base da API já está pronta em `frontend/src/services/api.js`:
```javascript
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api').replace(/\/+$/, '');
```

## 📦 Instalação e Deploy

### 1. Backend

```bash
# Instalar dependências
pip install -r backend/requirements.txt

# Testar configuração
python -c "from dotenv import load_dotenv; import os; load_dotenv('backend/.env'); print('API Key:', 'OK' if os.getenv('GOOGLE_API_KEY') else 'FALTANDO')"

# Rodar em produção
cd backend && python app.py
```

No Render, use o `render.yaml` do repositório ou configure manualmente o serviço com:

```env
DATA_BACKEND=postgres
OBJECT_STORAGE_BACKEND=supabase
DATABASE_URL=<sua-url-do-supabase>
SUPABASE_URL=<sua-url-do-supabase>
SUPABASE_SERVICE_ROLE_KEY=<sua-service-role-key>
```

### 2. Frontend

```bash
cd frontend

# Instalar dependências
npm install

# Build para produção
npm run build

# Servir com um servidor web simples
npm install -g serve
serve -s dist -l 3000
```

## 🔒 Segurança em Produção

### Checklist de Segurança:

- [ ] `DEBUG=False` no .env
- [ ] `AUTH_JWT_SECRET` forte e único
- [ ] Senha do admin inicial alterada
- [ ] Firewall configurado (abrir apenas portas necessárias)
- [ ] HTTPS configurado (use Nginx + Let's Encrypt)
- [ ] `.env` no `.gitignore` (não versionar credenciais)
- [ ] Limitar taxa de requisições (rate limiting)
- [ ] Fazer backup regular do Postgres + Storage + ChromaDB
- [ ] Rotacionar `SUPABASE_SERVICE_ROLE_KEY` se compartilhada fora de cofre seguro

### Configuração Nginx (Recomendado)

```nginx
server {
    listen 80;
    server_name SEU_IP_OU_DOMINIO;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 🔧 Configuração com PM2 (Manter rodando)

### Backend
```bash
# Instalar PM2
npm install -g pm2

# Iniciar backend
pm2 start backend/app.py --name autism-backend --interpreter python3

# Iniciar frontend (se não usar Nginx)
pm2 start "serve -s frontend/dist -l 3000" --name autism-frontend

# Salvar configuração
pm2 save

# Auto-iniciar no boot
pm2 startup
```

## 📊 Monitoramento

```bash
# Ver logs do backend
pm2 logs autism-backend

# Status dos processos
pm2 status

# Reiniciar aplicação
pm2 restart autism-backend
```

## ⚠️ Troubleshooting

### Erro: "GOOGLE_API_KEY não configurada"
- Verifique se o arquivo `.env` está na raiz do projeto
- Confirme que a variável está definida: `cat .env | grep GOOGLE_API_KEY`

### Frontend não conecta ao backend
- Verifique se o IP no frontend está correto
- Confirme que a porta 5000 está aberta no firewall
- Teste: `curl http://SEU_IP:5000/api/forms`

### CORS errors
- Certifique-se de que o backend tem `CORS(app)` habilitado
- Verifique se está acessando pela URL correta

### Erro 401 em `/api/auth/me` com `OPTIONS`
- Atualize para a versão atual do backend, que libera preflight `OPTIONS` sem autenticação

## 📝 Resumo das Credenciais Necessárias

| Variável | Onde Obter | Obrigatório |
|----------|-----------|-------------|
| `GOOGLE_API_KEY` | https://aistudio.google.com/app/apikey | ✅ Sim |
| `AUTH_JWT_SECRET` | Definido por você | ✅ Sim |
| `AUTH_ADMIN_USERNAME` | Definido por você | ✅ Sim |
| `AUTH_ADMIN_PASSWORD` | Definido por você | ✅ Sim |
| `AUTH_TOKEN_EXP_MINUTES` | Definido por você | ✅ Sim |
| `DEBUG` | Definir como `False` | ✅ Sim (produção) |
| `HOST` | Usar `0.0.0.0` | ✅ Sim |
| `PORT` | Usar `5000` ou outro | ✅ Sim |

## 🌐 URLs de Acesso

Depois de configurado:
- Frontend: `http://SEU_IP:3000`
- Backend API: `http://SEU_IP:5000/api`
- Documentação API: `http://SEU_IP:5000/api/forms`
