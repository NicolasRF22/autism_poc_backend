import os
import re
from google import genai
from google.genai import types
from vector_store import VectorStore
from document_processor import generate_embeddings
from prompts import SYSTEM_PROMPT_CHAT, SYSTEM_PROMPT_PEI
from typing import Dict, List, Optional
from usage_tracker import extract_usage_metrics, record_model_usage

# Stopwords básicas em português para extração de keywords
_STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da",
    "dos", "das", "em", "no", "na", "nos", "nas", "por", "para", "com",
    "que", "se", "não", "ele", "ela", "você", "seu", "sua", "e", "é",
    "tem", "ter", "ao", "à", "isso", "este", "esta", "me", "nos", "lhe",
    "mais", "mas", "como", "quando", "qual", "quais", "onde", "já", "também",
}


def _extract_keywords(text: str, max_terms: int = 6) -> List[str]:
    """Extrai termos relevantes de uma mensagem para busca keyword.

    Remove stopwords e palavras muito curtas. Retorna até max_terms termos
    únicos em minúsculas para uso no where_document $contains do ChromaDB.
    """
    words = re.findall(r'\b\w{3,}\b', text.lower())
    seen: set = set()
    keywords: List[str] = []
    for w in words:
        if w not in _STOPWORDS and w not in seen:
            seen.add(w)
            keywords.append(w)
        if len(keywords) >= max_terms:
            break
    return keywords


class RAGEngine:
    def __init__(self, api_key: str, db_path: str = "./chroma_db"):
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        self.vector_store = VectorStore(persist_directory=db_path)
        self.chat_sessions: Dict = {}
        self.generation_model = os.getenv("GOOGLE_GENERATION_MODEL", "gemini-2.5-flash")

    # ------------------------------------------------------------------
    # Chat com RAG
    # ------------------------------------------------------------------
    def query(
        self,
        message: str,
        session_id: str = "default",
        context_filter: Optional[Dict] = None,
        integrated_context: str = "",
        system_prompt_chat: Optional[str] = None,
    ) -> Dict:
        """Processa mensagem usando RAG: busca contexto e responde com Gemini."""
        # 1. Embedding da query com task_type correto para busca assimétrica
        query_embedding = generate_embeddings(
            message,
            self.api_key,
            task_type="RETRIEVAL_QUERY",
            operation="rag_chat_query_embedding",
        )

        # 2. Extrair termos-chave para busca híbrida (keyword fallback)
        keywords = _extract_keywords(message)

        # 3. Busca híbrida: vetorial + keyword, k=10 para maior recall
        similar_docs = self.vector_store.hybrid_search(
            query_embedding, terms=keywords, k=10, filter_metadata=context_filter
        )

        # 3. Montar contexto
        if similar_docs:
            context_parts = [
                f"[{doc['metadata'].get('file_name', 'Documento')}]\n{doc['text']}"
                for doc in similar_docs
            ]
            context = "\n\n---\n\n".join(context_parts)
            context_block = f"\nContexto dos documentos:\n{context}\n"
        else:
            context_block = "\n(Nenhum documento indexado encontrado.)\n"

        # 4. Gerenciar sessão de chat
        chat_system_prompt = (system_prompt_chat or SYSTEM_PROMPT_CHAT).strip()
        chat_session_key = f"{session_id}::{hash(chat_system_prompt)}"
        if chat_session_key not in self.chat_sessions:
            self.chat_sessions[chat_session_key] = self.client.chats.create(
                model=self.generation_model,
                config=types.GenerateContentConfig(
                    system_instruction=chat_system_prompt,
                ),
            )

        chat = self.chat_sessions[chat_session_key]

        # 5. Enviar mensagem com contexto
        integrated_block = ""
        if integrated_context and integrated_context.strip():
            integrated_block = f"\nContexto integrado (cadastro/diário/PDI):\n{integrated_context}\n"

        full_prompt = f"{context_block}{integrated_block}\nPergunta: {message}"
        response = chat.send_message(full_prompt)
        usage = extract_usage_metrics(response, fallback_text=full_prompt)
        record_model_usage(
            self.generation_model,
            input_tokens=usage['input_tokens'],
            output_tokens=usage['output_tokens'],
            total_tokens=usage['total_tokens'],
            operation='rag_chat_generation',
        )

        return {
            "response": response.text,
            "usage": usage,
            "sources": [
                {
                    "file_name": d["metadata"].get("file_name", ""),
                    "student_name": d["metadata"].get("student_name", ""),
                    "school": d["metadata"].get("school", ""),
                }
                for d in similar_docs
            ],
        }

    # ------------------------------------------------------------------
    # Geração de PEI
    # ------------------------------------------------------------------
    def generate_pei(
        self,
        student_name: str,
        school: str,
        additional_info: str = "",
        system_prompt_pei: Optional[str] = None,
        context_filter: Optional[Dict] = None,
        integrated_context: str = "",
    ) -> Dict:
        """Gera PEI completo estruturado a partir dos documentos indexados."""
        # 1. Buscar documentos relacionados ao estudante
        query_text = f"{student_name} {school} {additional_info}"
        query_embedding = generate_embeddings(
            query_text,
            self.api_key,
            task_type="RETRIEVAL_QUERY",
            operation="pei_query_embedding",
        )
        docs = self.vector_store.hybrid_search(
            query_embedding,
            terms=_extract_keywords(query_text),
            k=15,
            filter_metadata=context_filter,
        )

        # 2. Montar contexto
        if docs:
            context = "\n\n---\n\n".join([doc["text"] for doc in docs])
        else:
            context = "(Nenhum documento encontrado. Gere o PEI com base nas informações fornecidas.)"

        # 3. Prompt completo
        pei_system_prompt = (system_prompt_pei or SYSTEM_PROMPT_PEI).strip()
        pei_prompt = f"""{pei_system_prompt}

DADOS DO ESTUDANTE:
- Nome: {student_name}
- Escola: {school}
- Informações adicionais: {additional_info or 'Não informadas'}

CONTEXTO DOS DOCUMENTOS INDEXADOS:
{context}

CONTEXTO INTEGRADO (CADASTRO/DIÁRIO/PDI):
{integrated_context or '(Sem dados adicionais integrados para este aluno)'}

Gere agora o PEI COMPLETO com as 10 seções obrigatórias, personalizado para {student_name}."""

        # 4. Chamar Gemini
        response = self.client.models.generate_content(
            model=self.generation_model,
            contents=pei_prompt,
        )
        usage = extract_usage_metrics(response, fallback_text=pei_prompt)

        return {
            "pei": response.text,
            "student_name": student_name,
            "school": school,
            "sources_count": len(docs),
            "usage": usage,
        }
