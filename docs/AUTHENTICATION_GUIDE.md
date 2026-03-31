# Guia de Autenticação, Permissões e Auditoria (POC)

Este documento descreve como funciona o sistema de autenticação implementado no projeto, como gerenciar permissões e como acompanhar auditoria de ações.

---

## 1) Visão Geral

A autenticação foi implementada com JWT no backend Flask, com autorização por perfil (RBAC) e trilha de auditoria em arquivo JSONL.

### Componentes principais

- Backend Flask valida token Bearer em todas as rotas `/api/*` (exceto login e health).
- Usuários são persistidos em arquivo JSON.
- Eventos de auditoria são gravados em modo append-only em arquivo `.jsonl`.
- Frontend exige login para acessar as páginas e injeta automaticamente o token nas requisições.

---

## 2) Arquivos e responsabilidades

### Backend

- `backend/app.py`
  - Configuração JWT
  - Middleware de autenticação/autorização (`before_request`)
  - Middleware de auditoria (`after_request`)
  - Endpoints de auth, usuários e auditoria

- `backend/auth_storage.py`
  - Persistência de usuários em `backend/users/index.json`
  - Hash de senha com `werkzeug.security`
  - Criação automática de usuário admin inicial

- `backend/audit_storage.py`
  - Escrita de eventos em `backend/audit_logs/events.jsonl`
  - Leitura dos últimos eventos (com limite)

### Frontend

- `frontend/src/services/api.js`
  - Sessão local (token + usuário)
  - Interceptor Axios para enviar `Authorization: Bearer ...`
  - Tratamento central de 401 (expiração/token inválido)

- `frontend/src/main.jsx`
  - Patch global de `fetch` legado para anexar token automaticamente

- `frontend/src/App.jsx`
  - Proteção de rotas
  - Bootstrap de sessão (`/api/auth/me`)
  - Fluxo de login/logout

- `frontend/src/pages/LoginPage.jsx`
  - Tela de login

- `frontend/src/components/Sidebar.jsx`
  - Exibição de usuário/perfil atual
  - Botão de logout

---

## 3) Fluxo de autenticação

1. Usuário envia `username` e `password` para `POST /api/auth/login`.
2. Backend valida credenciais no `AuthStorage`.
3. Se válido, backend emite JWT com:
   - `sub`: id do usuário
   - `username`
   - `role`
   - `iat`
   - `exp`
4. Frontend salva token e usuário no `localStorage`.
5. Requisições seguintes enviam `Authorization: Bearer <token>` automaticamente.
6. Backend valida token em todas as rotas protegidas.
7. Em caso de 401 no frontend, sessão local é limpa e usuário volta para login.

---

## 4) Perfis e permissões (RBAC)

Perfis disponíveis:

- `admin`
  - Acesso total
  - Pode gerenciar usuários
  - Pode consultar auditoria

- `editor`
  - Pode ler e alterar dados de negócio
  - Não pode acessar rotas admin

- `viewer`
  - Somente leitura
  - Bloqueado em métodos de mutação (`POST`, `PUT`, `DELETE`, `PATCH`)

### Regras aplicadas

- Rotas admin (prefixos):
  - `/api/auth/users`
  - `/api/audit`

- Rotas públicas:
  - `/api/health`
  - `/api/auth/login`

---

## 5) Auditoria

A trilha de auditoria é gravada em `backend/audit_logs/events.jsonl`.

### O que é auditado

- Requisições mutáveis (`POST`, `PUT`, `DELETE`, `PATCH`)
- Downloads (`download` no path)
- PDFs (`/pdf` no path)
- Eventos de login/logout

### Estrutura do evento

Cada linha JSON possui campos como:

- `timestamp`
- `action`
- `path`
- `method`
- `status_code`
- `outcome` (`success`/`error`)
- `user` (id, username, role)
- `details` (quando aplicável)

---

## 6) Endpoints de autenticação e administração

### Autenticação

- `POST /api/auth/login`
  - Body: `{ "username": "...", "password": "..." }`
  - Retorno: token JWT + dados de usuário

- `GET /api/auth/me`
  - Retorna usuário autenticado atual

- `POST /api/auth/logout`
  - Logout stateless (cliente descarta token)

### Usuários (admin)

- `GET /api/auth/users`
  - Lista usuários cadastrados

- `POST /api/auth/users`
  - Cria usuário
  - Body: `{ "username": "...", "password": "...", "role": "admin|editor|viewer" }`

- `PUT /api/auth/users/<user_id>/role`
  - Atualiza perfil
  - Body: `{ "role": "admin|editor|viewer" }`

### Auditoria (admin)

- `GET /api/audit/events?limit=200`
  - Lista os últimos eventos

---

## 7) Configuração por ambiente

Variáveis suportadas:

- `AUTH_ADMIN_USERNAME`
- `AUTH_ADMIN_PASSWORD`
- `AUTH_JWT_SECRET`
- `AUTH_TOKEN_EXP_MINUTES`

Defaults usados para POC:

- admin inicial: `admin` / `admin123`
- expiração do token: 480 minutos

> Importante: em produção, defina sempre `AUTH_JWT_SECRET` forte e não use senha padrão.

---

## 8) Como usar agora (passo a passo)

### 8.1 Subir backend e frontend

1. Instale dependências backend (`requirements.txt`, com PyJWT).
2. Suba o backend Flask na porta 5000.
3. No frontend, execute o Vite (`npm run dev`).

### 8.2 Primeiro acesso

1. Abra a aplicação no navegador.
2. Você será redirecionado para tela de login.
3. Entre com o admin inicial:
   - usuário: `admin`
   - senha: `admin123`

### 8.3 Criar usuários da equipe

Use o usuário admin para criar contas por API:

- Criar editor para operação
- Criar viewer para consulta

Sugestão operacional:

- Admin: coordenação TI/gestão
- Editor: equipe pedagógica
- Viewer: consulta/supervisão

### 8.4 Ajustar perfil de um usuário

Se alguém precisar de mais/menos acesso, admin chama endpoint de atualização de role.

### 8.5 Usar normalmente a aplicação

Após login, o token fica salvo localmente e as telas passam a funcionar como antes.

- Se o token expirar, o frontend força novo login automaticamente.
- Se um usuário viewer tentar alterar algo, backend retorna 403.

### 8.6 Consultar auditoria

Admin pode acessar endpoint de auditoria para verificar:

- tentativas de login
- criação/edição/exclusão de dados
- downloads e geração de PDF

---

## 9) Limitações da versão POC

- JWT sem refresh token e sem blacklist de revogação
- Logout é stateless (remove token no cliente)
- Usuários e auditoria em arquivo local (JSON/JSONL)
- Não há MFA/SSO/políticas avançadas de senha

Para evolução futura (produção):

- refresh token + rotação
- revogação central (blacklist/jti)
- banco relacional para usuários/auditoria
- hardening de CORS, rate-limit e trilhas LGPD

---

## 10) Troubleshooting rápido

### Erro 401 Token ausente

- Usuário não autenticado ou token removido.
- Faça login novamente.

### Erro 401 Sessão expirada

- Token venceu.
- Faça login novamente.

### Erro 403 Acesso negado

- Role não permite a ação.
- Ajuste perfil com usuário admin.

### Não consigo logar com admin

- Verifique se `backend/users/index.json` já existe com outro admin.
- Confira variáveis `AUTH_ADMIN_USERNAME` e `AUTH_ADMIN_PASSWORD`.

---

## 11) Checklist mínimo de operação

- Definir `AUTH_JWT_SECRET` forte
- Trocar senha do admin padrão
- Criar usuários reais por perfil
- Validar auditoria (`/api/audit/events`)
- Testar permissão viewer (bloqueio de escrita)
- Testar expiração de token
