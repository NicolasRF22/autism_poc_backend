# 🚀 Essenciais para Deploy - Autism.IA

## 📋 Índice
1. [O que é DEBUG e por que é crítico](#1-debug-modo-de-desenvolvimento)
2. [Checklist de Deploy](#2-checklist-de-deploy)
3. [Estrutura do ChromaDB](#3-estrutura-do-chromadb)

---

## 1. DEBUG - Modo de Desenvolvimento

### 🔍 O que é?

O `DEBUG` é uma variável que controla o **modo de desenvolvimento do Flask**:

```python
# backend/app.py (linha 794-796)
debug = os.getenv('DEBUG', 'True') == 'True'
app.run(host=host, port=port, debug=debug)
```

### ⚙️ Configuração

```env
# .env
DEBUG=True   # Desenvolvimento (seu computador)
DEBUG=False  # Produção (servidor público)
```

---

### 🆚 Diferenças entre DEBUG=True e DEBUG=False

| Aspecto | DEBUG=True (Dev) | DEBUG=False (Produção) |
|---------|------------------|------------------------|
| **Auto-reload** | ✅ Reinicia ao editar código | ❌ Precisa reiniciar manualmente |
| **Mensagens de erro** | ✅ Stack trace completo | ❌ Mensagem genérica |
| **Código visível** | ❌ Expõe código-fonte | ✅ Protegido |
| **Performance** | ❌ Mais lento | ✅ Otimizado |
| **Segurança** | ❌ **INSEGURO** | ✅ **SEGURO** |
| **Debugger interativo** | ✅ Disponível | ❌ Desabilitado |
| **Logs** | ✅ Muito detalhado | ✅ Apenas essenciais |

---

### ⚠️ POR QUE DEBUG=False EM PRODUÇÃO É CRÍTICO?

Com `DEBUG=True`, **qualquer erro expõe informações sensíveis:**

#### Exemplo de erro com DEBUG=True:
```
Traceback (most recent call last):
  File "/home/nicolas/Aut/backend/app.py", line 125, in get_student
    student = _student_storage.get_student(student_id)
  File "/home/nicolas/Aut/backend/student_storage.py", line 45
    return self._index[student_id]
KeyError: 'uuid-inexistente'

🔴 Environment variables:
    GOOGLE_API_KEY: [REDACTED_EXAMPLE]
   HOST: 0.0.0.0
   PORT: 5000
   
🔴 Código-fonte completo:
   def get_student(self, student_id):
       # TODO: adicionar validação
       return self._index[student_id]  # linha 45
       
🔴 Caminhos completos:
   /home/nicolas/Aut/backend/
   /home/nicolas/Aut/.env
```

**Consequências:**
- 💀 **API Key exposta** publicamente
- 💀 **Código-fonte** revelado (vulnerabilidades)
- 💀 **Estrutura de pastas** descoberta
- 💀 **Variáveis de ambiente** visíveis
- 💀 **Lógica de negócio** exposta

#### Com DEBUG=False:
```
500 Internal Server Error

The server encountered an internal error and was unable to complete your request.
```

**Resultado:**
- ✅ API Key protegida
- ✅ Código oculto
- ✅ Estrutura protegida
- ✅ Apenas log no servidor

---

### 🎯 Quando usar cada modo

#### DEBUG=True - Apenas em Desenvolvimento
```
✅ Editando código no seu computador
✅ Testando localmente (localhost)
✅ Debugando erros
✅ Ambiente isolado (não acessível publicamente)
```

#### DEBUG=False - SEMPRE em Produção
```
✅ Servidor com IP público
✅ Acessível pela internet
✅ Dados reais de usuários
✅ Qualquer ambiente de produção
```

---

### 🔄 Como alternar entre os modos

```bash
# Desenvolvimento (local)
echo "DEBUG=True" > .env

# Antes de fazer deploy
echo "DEBUG=False" > .env

# Ou editar manualmente:
nano .env
# Mudar DEBUG=True para DEBUG=False
```

---

## 2. Checklist de Deploy

### ✅ Obrigatórios (CRÍTICOS)

#### 1. **DEBUG=False**
```env
DEBUG=False
```
**Por quê?** Segurança! Evita vazamento de código e credenciais.

#### 2. **GOOGLE_API_KEY**
```env
GOOGLE_API_KEY=sua_chave_real_aqui
```
**Como obter:** https://aistudio.google.com/app/apikey

**Por quê?** É necessária para:
- Gerar embeddings (vetores)
- RAG (busca semântica)
- Geração de PEIs
- Chat inteligente

#### 3. **AUTH_JWT_SECRET (OBRIGATÓRIO)**
```env
AUTH_JWT_SECRET=troque-por-um-segredo-forte
```
**Por quê?** Assina os tokens JWT de autenticação.

#### 4. **Credenciais admin iniciais**
```env
AUTH_ADMIN_USERNAME=admin
AUTH_ADMIN_PASSWORD=troque-esta-senha
```
**Por quê?** Define usuário inicial com permissão total.

#### 3. **Configurar IP do Servidor no Frontend**

Opção A - Variável de ambiente (recomendado):
```bash
# frontend/.env
VITE_API_BASE_URL=http://SEU_IP:5000/api
```

Opção B - Hardcode:
```javascript
// frontend/src/services/api.js
const API_BASE_URL = 'http://SEU_IP:5000/api';
```

Substituir em:
- `frontend/src/services/api.js` (linha 3)
- `frontend/src/pages/StudentForm.jsx` (linhas 120, 258-259)
- `frontend/src/pages/SchoolFormNew.jsx` (linhas 104, 242-243)
- `frontend/src/pages/DiaryPage.jsx` (linha 94)
- `frontend/vite.config.js` (linha 10)

#### 5. **Firewall - Liberar Portas**
```bash
# Ubuntu/Debian
sudo ufw allow 5000   # Backend
sudo ufw allow 3000   # Frontend (ou 80/443 com Nginx)
sudo ufw enable

# Verificar
sudo ufw status
```

#### 6. **Permissões de Arquivos**
```bash
# Backend deve ter permissão de escrita
chmod 700 backend/schools
chmod 700 backend/students
chmod 700 backend/diaries
chmod 700 backend/peis
chmod 700 backend/pdis
chmod 700 backend/chroma_db
chmod 700 backend/users
chmod 700 backend/audit_logs

# Dono correto
chown -R usuario_app:usuario_app backend/
```

---

### ⚙️ Recomendados (Segurança & Performance)

#### 7. **HTTPS com Nginx**
```nginx
server {
    listen 443 ssl;
    server_name seu-dominio.com;

    ssl_certificate /etc/letsencrypt/live/seu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/seu-dominio.com/privkey.pem;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
    }

    # Backend
    location /api {
        proxy_pass http://localhost:5000;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### 8. **PM2 - Manter aplicação rodando**
```bash
# Instalar
npm install -g pm2

# Backend
pm2 start backend/app.py --name autism-backend --interpreter python3

# Frontend
cd frontend && npm run build
pm2 start "npx serve -s dist -l 3000" --name autism-frontend

# Salvar para reiniciar automaticamente
pm2 save
pm2 startup
```

#### 9. **Backup Automático**
```bash
# Criar script /etc/cron.daily/backup-autism.sh
#!/bin/bash
BACKUP_DIR="/backups/autism-ia"
DATE=$(date +%Y%m%d)

tar -czf "$BACKUP_DIR/backup_$DATE.tar.gz" \
  /caminho/Aut/backend/schools \
  /caminho/Aut/backend/students \
  /caminho/Aut/backend/diaries \
  /caminho/Aut/backend/peis \
  /caminho/Aut/backend/pdis \
  /caminho/Aut/backend/chroma_db
    /caminho/Aut/backend/users
    /caminho/Aut/backend/audit_logs

# Manter apenas últimos 7 dias
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete
```

#### 10. **Monitoramento**
```bash
# Ver logs
pm2 logs autism-backend --lines 100

# Status
pm2 status

# Uso de recursos
pm2 monit

# Reiniciar se necessário
pm2 restart autism-backend
```

#### 11. **Arquivo .gitignore**
```gitignore
# Variáveis de ambiente (CRÍTICO!)
.env
.env.local
.env.production

# Dados sensíveis
backend/schools/
backend/students/
backend/diaries/
backend/peis/
backend/pdis/
backend/chroma_db/
backend/uploads/
backend/users/
backend/audit_logs/

# Node
node_modules/
frontend/dist/
frontend/.env

# Python
__pycache__/
*.pyc
*.pyo
```

---

### 📋 Checklist Visual

```
🔐 SEGURANÇA
├─ [ ] DEBUG=False no .env
├─ [ ] AUTH_JWT_SECRET forte configurado
├─ [ ] Senha do admin inicial alterada
├─ [ ] .env no .gitignore
├─ [ ] HTTPS configurado (Nginx + Let's Encrypt)
├─ [ ] Firewall ativo (portas 5000 e 3000/80/443)
└─ [ ] Permissões corretas (chmod 700)

🔑 CREDENCIAIS
├─ [ ] GOOGLE_API_KEY configurada
└─ [ ] IP do servidor configurado no frontend

🚀 INFRAESTRUTURA
├─ [ ] Python 3.12+ instalado
├─ [ ] Node.js 20 LTS+ (recomendado 20.19+) instalado
├─ [ ] Dependências instaladas (pip + npm)
├─ [ ] Build do frontend (npm run build)
└─ [ ] PM2 ou supervisor para manter rodando

💾 BACKUP
├─ [ ] Script de backup criado
├─ [ ] Cron configurado (backups automáticos)
└─ [ ] Testado restauração de backup

📊 MONITORAMENTO
├─ [ ] PM2 configurado
├─ [ ] Logs sendo salvos
└─ [ ] Alertas configurados (opcional)
```

---

### 🚨 Erros Comuns no Deploy

| Erro | Causa | Solução |
|------|-------|---------|
| **Código exposto em erros** | `DEBUG=True` | Mudar para `DEBUG=False` |
| **"GOOGLE_API_KEY não configurada"** | .env ausente ou incorreto | Verificar arquivo backend/.env |
| **Frontend não conecta** | IP errado | Atualizar frontend/.env ou api.js |
| **"Permission denied"** | Permissões incorretas | `chmod 700` nas pastas |
| **"Connection refused"** | Firewall bloqueando | `ufw allow 5000` |
| **App para ao fechar terminal** | Sem gerenciador de processo | Usar PM2 |

---

## 3. Estrutura do ChromaDB

### 🔢 O que é ChromaDB?

**ChromaDB** é um banco de dados vetorial usado para armazenar **embeddings** (representações numéricas de texto) que permitem busca semântica para o RAG.

```
📝 Texto: "criança com autismo precisa de apoio"
       ↓ (Google Gemini API)
🔢 Vetor: [0.123, -0.456, 0.789, ..., 0.234]  (768 dimensões)
       ↓ (armazenado)
💾 ChromaDB
```

---

### 📁 Estrutura de Arquivos

```
backend/
└── chroma_db/                              📂 Diretório principal
    ├── chroma.sqlite3                      🗄️ Índice SQLite
    │   └── Metadados das coleções
    │       ├── Nomes das coleções
    │       ├── Configurações
    │       └── Índices de busca
    │
    └── 2c68e894-e492-449b-9154.../         📦 Collection "documentos_pei"
        ├── data_level0.bin                 🔢 Vetores principais
        │   └── Embeddings de 768 dimensões
        │       [doc1]: [0.1, 0.2, ..., 0.8]
        │       [doc2]: [0.3, -0.1, ..., 0.5]
        │       [doc3]: [0.2, 0.4, ..., 0.9]
        │
        ├── header.bin                      📋 Metadados da coleção
        │   ├── Nome: "documentos_pei"
        │   ├── Tipo de distância: "cosine"
        │   ├── Dimensões: 768
        │   └── Total de documentos
        │
        ├── link_lists.bin                  🔗 Índice HNSW
        │   └── Estrutura de grafos para busca rápida
        │       (Hierarchical Navigable Small World)
        │
        └── length.bin                      📏 Informações de tamanho
            └── Tamanhos dos vetores
```

---

### 🗂️ O que é armazenado em cada documento?

Quando você faz upload de um PDF, ele é processado assim:

```python
# 1. Extrair texto do PDF
texto = "O Plano Educacional Individualizado (PEI) é uma ferramenta..."

# 2. Dividir em chunks (pedaços)
chunks = [
    "O Plano Educacional Individualizado (PEI) é uma ferramenta...",
    "A elaboração do PEI deve considerar as necessidades...",
    "O acompanhamento regular é fundamental para..."
]

# 3. Gerar embeddings (Google Gemini)
embeddings = [
    [0.123, -0.456, 0.789, ...],  # 768 números
    [0.234, 0.567, -0.123, ...],
    [-0.345, 0.678, 0.234, ...]
]

# 4. Armazenar no ChromaDB
{
    "id": "doc_abc123_0",
    "document": "O Plano Educacional Individualizado...",
    "embedding": [0.123, -0.456, 0.789, ...],
    "metadata": {
        "doc_id": "doc_abc123",
        "filename": "cartilha_pei.pdf",
        "chunk_index": 0,
        "upload_date": "2026-03-10T14:30:00"
    }
}
```

---

### 🎯 Collection: "documentos_pei"

A aplicação usa **uma coleção** para armazenar todos os documentos de referência:

```python
# backend/vector_store.py (linhas 9-12)
self.collection = self.client.get_or_create_collection(
    name="documentos_pei",
    metadata={"hnsw:space": "cosine"},  # Distância cosseno
)
```

**Configuração:**
- **Nome:** `documentos_pei`
- **Métrica:** Similaridade por cosseno
- **Dimensões:** 768 (definido pelo Google Gemini)
- **Índice:** HNSW (Hierarchical Navigable Small World)

---

### 🔍 Como funciona a busca?

```python
# 1. Usuário faz uma pergunta
pergunta = "Como elaborar um PEI?"

# 2. Converte pergunta em embedding
embedding_pergunta = [0.234, 0.123, -0.567, ...]  # 768 dimensões

# 3. ChromaDB busca chunks similares
resultados = collection.query(
    query_embeddings=[embedding_pergunta],
    n_results=5  # Top 5 mais similares
)

# 4. Retorna chunks relevantes
[
    {
        "document": "O PEI deve considerar as necessidades individuais...",
        "distance": 0.15,  # Muito similar (0 = idêntico)
        "metadata": {"filename": "cartilha_pei.pdf"}
    },
    {
        "document": "A elaboração do PEI envolve múltiplos profissionais...",
        "distance": 0.23,
        "metadata": {"filename": "manual_tea.pdf"}
    },
    ...
]
```

---

### 📊 Exemplo Visual

```
Pergunta do usuário:
"Como fazer adaptações curriculares?"
              ↓
         [Embedding]
       [0.5, 0.2, ...]
              ↓
    ┌─────────────────┐
    │   ChromaDB      │
    │  (busca HNSW)   │
    └─────────────────┘
              ↓
    Busca vetores similares:
    
    🎯 Distância 0.12 (muito similar!)
    "Adaptações curriculares devem ser..."
    Fonte: cartilha_inclusao.pdf
    
    🎯 Distância 0.18
    "O processo de adaptação considera..."
    Fonte: guia_tea.pdf
    
    🎯 Distância 0.25
    "Modificações no currículo incluem..."
    Fonte: manual_educacao.pdf
              ↓
    Chunks enviados para Gemini API
              ↓
    Resposta contextualizada gerada
```

---

### 🔧 Operações Principais

#### 1. **Upload de Documento**
```python
# backend/app.py (rota /api/rag/upload)

# Extrair texto do PDF
texto = extrair_texto_pdf(arquivo)

# Dividir em chunks
chunks = dividir_em_chunks(texto, tamanho=500)

# Gerar embeddings
embeddings = []
for chunk in chunks:
    emb = gerar_embedding(chunk, GOOGLE_API_KEY)
    embeddings.append(emb)

# Adicionar ao ChromaDB
doc_id = vector_store.add_documents(
    chunks=chunks,
    embeddings=embeddings,
    metadata={"filename": "cartilha.pdf"}
)
```

#### 2. **Busca Semântica (RAG)**
```python
# backend/rag_engine.py (método query)

# Usuário pergunta
pergunta = "Como avaliar progressos?"

# Gerar embedding da pergunta
emb_pergunta = gerar_embedding(pergunta, api_key)

# Buscar documentos similares
resultados = vector_store.search(
    query_embedding=emb_pergunta,
    top_k=5
)

# Montar contexto
contexto = "\n".join([r["document"] for r in resultados])

# Enviar para Gemini
resposta = gemini_chat(
    prompt=f"Contexto: {contexto}\n\nPergunta: {pergunta}"
)
```

---

### 📈 Capacidade e Performance

| Métrica | Valor |
|---------|-------|
| **Documentos suportados** | ~100.000 chunks |
| **Tamanho do embedding** | 768 dimensões |
| **Velocidade de busca** | ~50ms (5 resultados) |
| **Velocidade de inserção** | ~100 chunks/segundo |
| **Espaço em disco** | ~1KB por chunk |
| **Tipo de índice** | HNSW (grafo navegável) |

**Exemplo:**
- Upload de PDF 50 páginas → ~100 chunks → ~100KB no ChromaDB
- Busca em 10.000 chunks → ~50-100ms

---

### 💾 Backup do ChromaDB

```bash
# Backup completo (incluir no backup regular)
tar -czf chroma_backup_$(date +%Y%m%d).tar.gz backend/chroma_db/

# Restaurar
tar -xzf chroma_backup_20260310.tar.gz -C backend/

# Verificar integridade
ls -lh backend/chroma_db/
# Deve conter:
# - chroma.sqlite3
# - [uuid]/ (pasta da collection)
```

---

### 🔄 Regenerar Embeddings

Se perder o ChromaDB, pode regenerar (se ainda tiver os PDFs):

```bash
# Fazer upload novamente dos documentos
# A API /api/rag/upload processa e cria os embeddings
curl -X POST http://localhost:5000/api/rag/upload \
  -F "file=@cartilha_pei.pdf"
```

Ou usar a rota de re-embedding:
```bash
# Re-embeda todos os chunks existentes
curl -X POST http://localhost:5000/api/rag/re-embed
```

---

### 🚨 Problemas Comuns

| Problema | Causa | Solução |
|----------|-------|---------|
| **"Collection not found"** | ChromaDB vazio | Fazer upload de documentos |
| **Busca não retorna resultados** | Embeddings não compatíveis | Regenerar com mesma API |
| **Permission denied** | Permissões incorretas | `chmod 755 backend/chroma_db` |
| **SQLite locked** | Múltiplos processos | Usar apenas uma instância |
| **Slow queries** | Índice corrompido | Deletar e regenerar ChromaDB |

---

### 🎓 Resumo Técnico

**ChromaDB na aplicação Autism.IA:**

1. **Local** - Não precisa servidor separado
2. **Sem credenciais** - Funciona automaticamente
3. **Uma collection** - "documentos_pei"
4. **768 dimensões** - Embeddings do Google Gemini
5. **Busca HNSW** - Ultra-rápida (~50ms)
6. **Persistente** - Dados salvos em disco
7. **Backup simples** - Copiar pasta `chroma_db/`

---

## 🎯 Resumo Final

### Para fazer deploy com segurança:

```
1. DEBUG=False          → Segurança crítica
2. GOOGLE_API_KEY       → IA/RAG
3. AUTH_JWT_SECRET      → Segurança dos tokens JWT
4. Credenciais admin    → AUTH_ADMIN_USERNAME / AUTH_ADMIN_PASSWORD
5. IP no frontend       → Para conectar ao backend
6. Firewall             → Portas 5000 e 3000
7. PM2                  → Manter rodando
8. Backup               → Automatizar backups
9. HTTPS                → Nginx + Let's Encrypt (recomendado)
```

### Armazenamento:

```
📁 JSON                  → Escolas, alunos, diários, PEIs, PDIs, usuários
🧾 JSONL                 → Auditoria (events.jsonl)
🔢 ChromaDB             → Embeddings para RAG (local, sem credenciais)
```

### Lembre-se:

- ⚠️ **DEBUG=False é CRÍTICO** para segurança
- ✅ **ChromaDB** não é MongoDB (é local!)
- ✅ **Apenas GOOGLE_API_KEY** necessária
- ✅ **Backups regulares** das pastas backend/

---

## 📚 Documentação Adicional

- [FAQ.md](FAQ.md) - Perguntas frequentes
- [ARCHITECTURE.md](ARCHITECTURE.md) - Arquitetura completa
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Guia detalhado de deploy
- [STORAGE_INFO.md](STORAGE_INFO.md) - Informações sobre armazenamento
- [CHECKLIST_DEPLOY.txt](CHECKLIST_DEPLOY.txt) - Checklist rápido
