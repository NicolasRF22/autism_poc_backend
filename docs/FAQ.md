# 🔍 FAQ - Perguntas Frequentes

## 1. Para que serve o DEBUG?

### O que é?
`DEBUG` controla o **modo de desenvolvimento do Flask**.

```env
# Desenvolvimento (local)
DEBUG=True

# Produção (servidor público)
DEBUG=False
```

### Diferenças:

| Recurso | DEBUG=True | DEBUG=False |
|---------|------------|-------------|
| **Auto-reload** | ✅ Reinicia ao editar código | ❌ Precisa reiniciar manualmente |
| **Erros detalhados** | ✅ Stack trace completo | ❌ Mensagem genérica |
| **Performance** | ⚠️ Mais lento | ✅ Otimizado |
| **Segurança** | ❌ Expõe código | ✅ Protegido |
| **Debugger interativo** | ✅ Disponível | ❌ Desabilitado |
| **Logs** | ✅ Verbosos | ✅ Apenas essenciais |

### ⚠️ Por que DEBUG=False em produção?

**Segurança!** Com DEBUG=True, erros mostram:
- Caminhos completos dos arquivos
- Código-fonte da aplicação
- Variáveis de ambiente
- Stack traces detalhados

**Exemplo de erro com DEBUG=True:**
```
Traceback (most recent call last):
  File "/home/usuario/Aut/backend/app.py", line 125, in get_student
    student = _student_storage.get_student(student_id)
  File "/home/usuario/Aut/backend/student_storage.py", line 45, in get_student
    return self._index[student_id]
KeyError: 'uuid-123'

Environment:
GOOGLE_API_KEY: AIza...
SECRET_KEY: abc123...
```

**Com DEBUG=False:**
```
500 Internal Server Error
```

---

## 2. Estamos usando MongoDB?

### ❌ NÃO! Você está usando **ChromaDB**

Muita gente confunde porque tanto MongoDB quanto ChromaDB são bancos "NoSQL", mas são completamente diferentes:

| MongoDB | ChromaDB |
|---------|----------|
| Banco de **documentos** | Banco de **vetores** (embeddings) |
| Armazena JSON | Armazena vetores numéricos + metadados |
| Servidor separado | 100% Local (arquivos) |
| Precisa credenciais | Sem credenciais |
| Para dados estruturados | Para busca semântica (IA) |
| `mongodb://user:pass@host` | `./chroma_db` (pasta local) |

### Como o ChromaDB funciona na sua aplicação:

```python
# backend/vector_store.py
self.client = chromadb.PersistentClient(path="./chroma_db")
```

É só uma **pasta local** com arquivos:

```
backend/
└── chroma_db/
    ├── chroma.sqlite3        # Índice (tipo um "índice.json")
    └── 2c68e894-.../          # Dados vetoriais
        ├── data_level0.bin
        ├── header.bin
        └── link_lists.bin
```

### ✅ Credenciais necessárias: NENHUMA!

O ChromaDB:
- É local (como os arquivos JSON)
- Criado automaticamente
- Não precisa de servidor
- Não precisa de usuário/senha
- Apenas precisa de acesso ao sistema de arquivos

---

## 3. Resumo do Armazenamento

Sua aplicação usa **2 tipos de armazenamento local**:

### 📁 JSON (Dados estruturados)
```
backend/schools/index.json    ← Escolas
backend/students/index.json   ← Alunos
backend/diaries/*.json        ← Diários
backend/peis/*.json           ← PEIs
backend/pdis/*.json           ← PDIs
```
- ✅ Legível por humanos
- ✅ Fácil de editar manualmente
- ✅ Fácil de fazer backup

### 🔢 ChromaDB (Vetores para RAG)
```
backend/chroma_db/
```
- ✅ Busca semântica rápida
- ✅ Armazena embeddings dos documentos
- ✅ Usado pelo Google Gemini para RAG
- ⚠️ Formato binário (não editável manualmente)

---

## 4. Variáveis de Ambiente - O que cada uma faz?

```env
# ============================================
# DEBUG - Modo de desenvolvimento
# ============================================
DEBUG=False                    # False = produção, True = desenvolvimento

# ============================================
# Servidor
# ============================================
HOST=0.0.0.0                  # 0.0.0.0 = aceita conexões externas
PORT=5000                      # Porta do backend

# ============================================
# API do Google Gemini
# ============================================
GOOGLE_API_KEY=sua_chave       # Obrigatória para recursos de IA

# ============================================
# Autenticação
# ============================================
AUTH_JWT_SECRET=seu_segredo_forte
AUTH_ADMIN_USERNAME=admin
AUTH_ADMIN_PASSWORD=troque-esta-senha
AUTH_TOKEN_EXP_MINUTES=480
```

Inclua essas variáveis no `.env` de produção.

---

## 5. Credenciais necessárias - Lista completa

| Item | Necessário? | Como obter |
|------|-------------|------------|
| **GOOGLE_API_KEY** | ✅ SIM | https://aistudio.google.com/app/apikey |
| **AUTH_JWT_SECRET** | ✅ SIM | Definido por você |
| **AUTH_ADMIN_USERNAME** | ✅ SIM | Definido por você |
| **AUTH_ADMIN_PASSWORD** | ✅ SIM | Definido por você |
| **AUTH_TOKEN_EXP_MINUTES** | ✅ SIM | Definido por você |
| **IP do servidor** | ✅ SIM | Seu provedor de hospedagem |
| MongoDB credentials | ❌ NÃO | Não usa MongoDB |
| ChromaDB credentials | ❌ NÃO | É local |
| Database password | ❌ NÃO | Não usa banco SQL |

---

## 6. Backup - O que precisa ser salvo?

Para backup completo, salvar:

```bash
backend/schools/       # Cadastros de escolas
backend/students/      # Cadastros de alunos
backend/diaries/       # Entradas de diário
backend/peis/          # PEIs gerados
backend/pdis/          # PDIs gerados
backend/chroma_db/     # Embeddings (RAG)
backend/uploads/       # Arquivos enviados (se houver)
backend/users/         # Usuários e perfis
backend/audit_logs/    # Trilha de auditoria (JSONL)
```

### Script de backup simples:
```bash
tar -czf backup_$(date +%Y%m%d).tar.gz \\
  backend/schools \\
  backend/students \\
  backend/diaries \\
  backend/peis \\
  backend/pdis \\
  backend/chroma_db
```

---

## 7. Quando migrar para banco de dados "real"?

Considere PostgreSQL/MongoDB quando:
- ✅ Mais de **1.000 registros**
- ✅ **Múltiplos usuários simultâneos** editando
- ✅ Necessidade de **queries complexas**
- ✅ **Relatórios e analytics**
- ✅ **Transações complexas**

Mas para uso educacional com centenas de registros, **JSON + ChromaDB é perfeito!** 🎉

---

## 8. Troubleshooting Comum

### ❌ "ChromaDB not found"
```bash
pip install chromadb
```

### ❌ "Permission denied: chroma_db/"
```bash
chmod -R 755 backend/chroma_db
```

### ❌ "Cannot connect to database"
**Não há banco de dados!** É tudo local. Verifique se as pastas existem:
```bash
ls -la backend/schools
ls -la backend/chroma_db
```

### ❌ Erros mostram código-fonte
**DEBUG=True** em produção! Mudar para `DEBUG=False`.

---

## 9. Performance

### Quantos registros suporta?

| Tipo | Limite Prático |
|------|----------------|
| **Escolas** | ~5.000 |
| **Alunos** | ~10.000 |
| **Diários** | ~50.000 |
| **ChromaDB** | ~100.000 vetores |

Acima disso, considere migrar para PostgreSQL.

### Como melhorar performance?

1. **Índices** - ChromaDB já usa (HNSW)
2. **Paginação** - Limitar resultados por página
3. **Cache** - Usar Redis para dados frequentes
4. **CDN** - Para arquivos estáticos do frontend

---

## 10. Segurança em Produção

### Checklist:

- [ ] `DEBUG=False`
- [ ] `AUTH_JWT_SECRET` forte
- [ ] Senha admin inicial alterada
- [ ] HTTPS (Nginx + Let's Encrypt)
- [ ] Firewall configurado
- [ ] `.env` no `.gitignore`
- [ ] Permissões corretas (`chmod 700 backend/`)
- [ ] Backups automáticos
- [ ] Rate limiting (evitar abuso da API)
- [ ] Validação de inputs
- [ ] CORS configurado corretamente

### HTTPS com Nginx:
```nginx
server {
    listen 443 ssl;
    server_name seu-dominio.com;

    ssl_certificate /etc/letsencrypt/live/seu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/seu-dominio.com/privkey.pem;

    location / {
        proxy_pass http://localhost:3000;
    }

    location /api {
        proxy_pass http://localhost:5000;
    }
}
```

---

## 📚 Leia também:

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Guia completo de deploy
- [STORAGE_INFO.md](STORAGE_INFO.md) - Detalhes sobre armazenamento
- [CHECKLIST_DEPLOY.txt](CHECKLIST_DEPLOY.txt) - Checklist rápido

---

## 💡 TL;DR (Resumão)

1. **DEBUG=False** em produção (segurança)
2. **Não é MongoDB**, é **ChromaDB** (local, sem credenciais)
3. **Autenticação JWT + RBAC está ativa** (`admin`, `secretaria`, `coordenacao`, `professor`, `viewer`)
4. **Configure GOOGLE_API_KEY + AUTH_JWT_SECRET + credenciais admin**
5. **JSON + ChromaDB + users + audit_logs** é suficiente para a POC
6. **Fazer backups** das pastas `backend/`
