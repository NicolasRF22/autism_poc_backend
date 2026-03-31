# Planejamento: Sistema RAG para Geração de PEI

**Data**: 23 de Fevereiro de 2026  
**Projeto**: Autism.IA  
**Feature**: Página "Teste RAG" - Sistema de Geração de Planos Educacionais Individualizados

---

## 📋 Visão Geral

Implementação completa de um sistema RAG (Retrieval-Augmented Generation) para gerar Planos Educacionais Individualizados (PEI) para estudantes autistas. O sistema permitirá upload de documentos, indexação com embeddings, chat conversacional e geração estruturada de PEIs baseados em casos de estudo reais.

### Origem
Baseado no workflow N8N existente (`TFG (1).json`) que atualmente:
- Monitora Google Drive para estudos de caso e cadastros de escolas
- Converte XLSX em PDFs
- Indexa documentos em Supabase usando embeddings do Google Gemini
- Usa DeepSeek/GPT-4/Gemini para gerar PEIs via chat
- Mantém histórico de conversas em PostgreSQL

### Decisões Arquiteturais
- ✅ **Abordagem**: RAG Standalone (independente do N8N)
- ✅ **LLM**: Google Gemini API (gratuito até certo limite)
- ✅ **Vector Store**: ChromaDB (local, sem dependências externas)
- ✅ **Dados**: Upload manual de PDFs (sem Google Drive API)
- ✅ **Escopo**: Chat + RAG + Geração completa de PEI

---

## 🎯 Objetivos

1. Criar interface de chat para interação com documentos indexados
2. Permitir upload e gerenciamento de PDFs (estudos de caso, cadastros)
3. Implementar busca semântica usando embeddings
4. Gerar PEIs estruturados seguindo DSM-5 e BNCC
5. Manter funcionalidade equivalente ao workflow N8N atual

---

## 🏗️ Arquitetura

### Frontend (React)
```
TesteRAG Page
├── DocumentUploader (Coluna 1)
│   ├── Upload de PDFs
│   ├── Lista de documentos indexados
│   └── Ações: visualizar, deletar
├── ChatInterface (Coluna 2)
│   ├── Histórico de mensagens
│   ├── Input de mensagem
│   └── Renderização markdown
└── PEIGenerator (Coluna 3)
    ├── Form com dados do estudante
    ├── Botão "Gerar PEI"
    └── Visualização do PEI gerado
```

### Backend (Flask)
```
RAG Engine
├── document_processor.py
│   ├── extract_text_from_pdf()
│   ├── split_text_into_chunks()
│   └── generate_embeddings()
├── vector_store.py
│   ├── ChromaDB initialization
│   ├── add_documents()
│   ├── search_similar()
│   └── delete_document()
├── rag_engine.py
│   ├── query() - Chat com contexto
│   └── generate_pei() - PEI estruturado
└── prompts.py
    ├── SYSTEM_PROMPT_PEI
    └── SYSTEM_PROMPT_CHAT
```

### Fluxo de Dados
```
1. Upload PDF → extract_text → split_chunks → embeddings → ChromaDB
2. User message → search_similar → retrieve context → Gemini → response
3. Generate PEI → query student docs → structured prompt → Gemini → 10 sections
```

---

## 📦 Dependências

### Backend (requirements.txt)
```txt
Flask==3.0.0
flask-cors==4.0.0
python-dotenv==1.0.0
orjson==3.9.10

# Novas dependências RAG
google-generativeai==0.8.3
chromadb==0.5.23
pypdf2==3.0.1
langchain==0.3.13
langchain-google-genai==2.0.8
```

### Frontend (package.json)
```json
{
  "dependencies": {
    "react-markdown": "^9.0.1",
    "remark-gfm": "^4.0.0"
  }
}
```

### Variáveis de Ambiente (.env)
```bash
# Existentes
PORT=5000
HOST=0.0.0.0
DEBUG=True

# Novas
GOOGLE_API_KEY=your_gemini_api_key_here
CHROMA_DB_PATH=./chroma_db
```

---

## 🔧 Implementação: Passos

### Step 1 — Configuração de Dependências

```bash
# Backend
cd backend
pip install google-generativeai chromadb pypdf2 langchain langchain-google-genai

# Frontend
cd frontend
npm install react-markdown remark-gfm
```

Adicionar `GOOGLE_API_KEY` ao `.env` (obter em https://makersuite.google.com/app/apikey)

---

### Step 2 — `backend/document_processor.py`

```python
import PyPDF2
import google.generativeai as genai
from typing import List

def extract_text_from_pdf(pdf_path: str) -> str:
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
    return text

def split_text_into_chunks(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks

def generate_embeddings(text: str) -> List[float]:
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_document"
    )
    return result['embedding']
```

---

### Step 3 — `backend/vector_store.py`

```python
import chromadb
from typing import List, Dict
import uuid
from datetime import datetime

class VectorStore:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name="documentos_pei",
            metadata={"hnsw:space": "cosine"}
        )

    def add_documents(self, chunks: List[str], embeddings: List[List[float]], metadata: Dict) -> str:
        doc_id = str(uuid.uuid4())
        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [{**metadata, "doc_id": doc_id, "chunk_index": i,
                      "upload_date": datetime.now().isoformat()} for i in range(len(chunks))]
        self.collection.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
        return doc_id

    def search_similar(self, query_embedding: List[float], k: int = 5, filter_metadata: Dict = None) -> List[Dict]:
        results = self.collection.query(
            query_embeddings=[query_embedding], n_results=k, where=filter_metadata
        )
        return [{"text": results['documents'][0][i], "metadata": results['metadatas'][0][i],
                 "distance": results['distances'][0][i]} for i in range(len(results['documents'][0]))]

    def list_documents(self) -> List[Dict]:
        all_docs = self.collection.get()
        unique_docs = {}
        for metadata in all_docs['metadatas']:
            doc_id = metadata.get('doc_id')
            if doc_id not in unique_docs:
                unique_docs[doc_id] = metadata
        return list(unique_docs.values())

    def delete_document(self, doc_id: str):
        self.collection.delete(where={"doc_id": doc_id})
```

---

### Step 4 — `backend/prompts.py`

```python
SYSTEM_PROMPT_CHAT = """Você é um assistente especializado em educação inclusiva e TEA.
- Baseie-se nos documentos fornecidos como contexto
- Use linguagem acessível para educadores e famílias
- Se não tiver informação suficiente no contexto, indique isso claramente
"""

SYSTEM_PROMPT_PEI = """Você é especialista em educação inclusiva, autismo e ABA.

CONHECIMENTOS: DSM-5, BNCC, LBI 13.146/2015, estratégias pedagógicas diferenciadas.

ESTRUTURA OBRIGATÓRIA (10 seções):
1. IDENTIFICAÇÃO DO ESTUDANTE
2. PERFIL FUNCIONAL
3. OBJETIVOS EDUCACIONAIS INDIVIDUALIZADOS (formato SMART)
4. ESTRATÉGIAS PEDAGÓGICAS
5. APOIOS E RECURSOS
6. ADAPTAÇÕES CURRICULARES POR COMPONENTE (alinhado à BNCC)
7. PARTICIPAÇÃO DA FAMÍLIA E EQUIPE ESCOLAR
8. AVALIAÇÃO E MONITORAMENTO
9. CULTURA ESCOLAR E INCLUSÃO
10. MARCOS LEGAIS E REFERÊNCIAS

Use o contexto dos documentos para personalizar cada seção.
Níveis de suporte TEA: N1, N2, N3 conforme DSM-5.
"""
```

---

### Step 5 — `backend/rag_engine.py`

```python
import google.generativeai as genai
from vector_store import VectorStore
from document_processor import generate_embeddings
from prompts import SYSTEM_PROMPT_CHAT, SYSTEM_PROMPT_PEI
from typing import Dict

class RAGEngine:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.vector_store = VectorStore()
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        self.chat_sessions = {}

    def query(self, message: str, session_id: str = "default", context_filter: Dict = None) -> Dict:
        query_embedding = generate_embeddings(message)
        similar_docs = self.vector_store.search_similar(query_embedding, k=5, filter_metadata=context_filter)
        context = "\n\n".join([
            f"[{doc['metadata'].get('file_name', 'Desconhecido')}]\n{doc['text']}"
            for doc in similar_docs
        ])
        if session_id not in self.chat_sessions:
            self.chat_sessions[session_id] = self.model.start_chat(history=[])
        chat = self.chat_sessions[session_id]
        full_prompt = f"Contexto:\n{context}\n\nPergunta: {message}"
        response = chat.send_message(full_prompt)
        return {"response": response.text, "sources": [doc['metadata'] for doc in similar_docs]}

    def generate_pei(self, student_name: str, school: str, additional_info: str = "") -> Dict:
        query_text = f"{student_name} {school} {additional_info}"
        query_embedding = generate_embeddings(query_text)
        docs = self.vector_store.search_similar(query_embedding, k=10)
        context = "\n\n".join([doc['text'] for doc in docs])
        pei_prompt = f"""{SYSTEM_PROMPT_PEI}

DADOS: Nome: {student_name} | Escola: {school} | Info adicional: {additional_info}

CONTEXTO DOS DOCUMENTOS:
{context}

Gere o PEI completo com as 10 seções."""
        response = self.model.generate_content(pei_prompt)
        return {"pei": response.text, "student_name": student_name, "school": school, "sources_count": len(docs)}
```

---

### Step 6 — Novas rotas em `backend/app.py`

```python
# Adicionar ao app.py existente

import os
from werkzeug.utils import secure_filename
from document_processor import extract_text_from_pdf, split_text_into_chunks, generate_embeddings
from rag_engine import RAGEngine

UPLOAD_FOLDER = './uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
rag_engine = RAGEngine(api_key=os.getenv('GOOGLE_API_KEY'))

@app.route('/api/rag/upload', methods=['POST'])
def upload_document():
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400
    file = request.files['file']
    if not file.filename.endswith('.pdf'):
        return jsonify({"error": "Apenas PDFs são permitidos"}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    metadata = json.loads(request.form.get('metadata', '{}'))
    metadata['file_name'] = filename
    try:
        text = extract_text_from_pdf(filepath)
        chunks = split_text_into_chunks(text)
        embeddings = [generate_embeddings(chunk) for chunk in chunks]
        doc_id = rag_engine.vector_store.add_documents(chunks, embeddings, metadata)
        return jsonify({"message": "Indexado com sucesso", "doc_id": doc_id, "chunks_count": len(chunks)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.remove(filepath)

@app.route('/api/rag/documents', methods=['GET'])
def get_rag_documents():
    return jsonify(rag_engine.vector_store.list_documents())

@app.route('/api/rag/documents/<doc_id>', methods=['DELETE'])
def delete_rag_document(doc_id):
    try:
        rag_engine.vector_store.delete_document(doc_id)
        return jsonify({"message": "Documento removido"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/rag/chat', methods=['POST'])
def rag_chat():
    data = request.json
    message = data.get('message')
    if not message:
        return jsonify({"error": "Mensagem não fornecida"}), 400
    try:
        result = rag_engine.query(message, data.get('session_id', 'default'))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/rag/generate-pei', methods=['POST'])
def generate_pei():
    data = request.json
    if not data.get('student_name') or not data.get('school'):
        return jsonify({"error": "Nome do estudante e escola são obrigatórios"}), 400
    try:
        pei = rag_engine.generate_pei(data['student_name'], data['school'], data.get('additional_info', ''))
        return jsonify(pei)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

---

### Step 7 — `frontend/src/services/api.js` (adição)

```javascript
export const ragAPI = {
  uploadDocument: async (file, metadata) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('metadata', JSON.stringify(metadata));
    const response = await api.post('/rag/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  },
  getDocuments: async () => {
    const response = await api.get('/rag/documents');
    return response.data;
  },
  deleteDocument: async (docId) => {
    const response = await api.delete(`/rag/documents/${docId}`);
    return response.data;
  },
  sendMessage: async (message, sessionId = 'default') => {
    const response = await api.post('/rag/chat', { message, session_id: sessionId });
    return response.data;
  },
  generatePEI: async (data) => {
    const response = await api.post('/rag/generate-pei', data);
    return response.data;
  }
};
```

---

### Step 8 — `frontend/src/pages/TesteRAG.jsx`

Estrutura em 3 colunas:
- **Coluna 1**: Upload de PDFs + lista de documentos indexados
- **Coluna 2**: Chat com histórico de mensagens + renderização markdown
- **Coluna 3**: Form de geração de PEI + visualização do resultado

Estados: `messages`, `documents`, `loading`, `uploadLoading`, `peiLoading`, `peiResult`

---

### Step 9 — Roteamento e Navegação

**`frontend/src/App.jsx`**:
```jsx
import TesteRAG from './pages/TesteRAG';
// Adicionar:
<Route path="/teste-rag" element={<TesteRAG />} />
```

**`frontend/src/components/Sidebar.jsx`**:
```jsx
{ path: '/teste-rag', label: 'Teste RAG', icon: '🤖' }
```

---

## 🧪 Testes e Validação

### Checklist de Validação

- [ ] Backend inicia sem erros com as novas dependências
- [ ] `GOOGLE_API_KEY` configurada no `.env`
- [ ] Upload de PDF funciona e retorna `doc_id`
- [ ] Lista de documentos retorna documentos indexados
- [ ] Chat retorna resposta com contexto dos documentos
- [ ] PEI gerado contém as 10 seções obrigatórias
- [ ] Sidebar exibe "Teste RAG 🤖"
- [ ] Navegação para `/teste-rag` funciona
- [ ] Layout responsivo (mobile e desktop)
- [ ] Erros são tratados corretamente no frontend

### Exemplos de Teste via cURL

```bash
# Upload
curl -X POST http://localhost:5000/api/rag/upload \
  -F "file=@exemplo.pdf" \
  -F 'metadata={"student_name":"João Silva","school":"Escola ABC"}'

# Listar documentos
curl http://localhost:5000/api/rag/documents

# Chat
curl -X POST http://localhost:5000/api/rag/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Quais são as características do João?"}'

# Gerar PEI
curl -X POST http://localhost:5000/api/rag/generate-pei \
  -H "Content-Type: application/json" \
  -d '{"student_name":"João Silva","school":"Escola ABC","additional_info":"TEA nível 2, 8 anos"}'
```

---

## 📊 Comparação com Workflow N8N Original

| Feature | N8N Original | Nossa Implementação |
|---|---|---|
| **Fonte de Dados** | Google Drive (automático) | Upload manual de PDFs |
| **Vector Store** | Supabase | ChromaDB (local) |
| **LLM** | DeepSeek / GPT-4 / Gemini | Google Gemini |
| **Embeddings** | text-embedding-004 | text-embedding-004 |
| **Memória de Chat** | PostgreSQL | Em memória (sessões) |
| **Conversão XLSX→PDF** | Serviço externo | N/A (aceita PDFs direto) |
| **Interface** | Webhook chat | React UI completa |
| **Deploy** | Instância N8N | Standalone Flask + React |

---

## 🚀 Próximos Passos (Futuro)

1. **Persistência de chat** — salvar histórico em banco de dados
2. **Google Drive Integration** — sincronizar com pastas do workflow N8N
3. **Autenticação** — controle de acesso a documentos por usuário
4. **Streaming de respostas** — SSE/WebSocket para melhor UX
5. **Download de PEI em PDF** — exportar o plano gerado
6. **Analytics** — dashboard de uso e qualidade das respostas

---

## ⚠️ Limitações Conhecidas

- Memória de chat não persiste após restart do servidor
- ChromaDB local (não compartilhado entre instâncias)
- Sem rate limiting nas chamadas à API do Gemini
- Upload simultâneo pode causar race conditions

---

**Status**: Pronto para implementação  
**Última atualização**: 23/02/2026
