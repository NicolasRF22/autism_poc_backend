import os
import re
import PyPDF2
from google import genai
from google.genai import types
from typing import List
from usage_tracker import extract_input_tokens, record_model_usage


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extrai texto de um arquivo PDF."""
    text = ""
    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


def split_text_into_chunks(
    text: str, chunk_size: int = 800, overlap_units: int = 1
) -> List[str]:
    """Divide texto em chunks respeitando parágrafos e quebras de linha.

    Ao contrário do corte por caracteres, esta abordagem mantém pares
    pergunta/resposta e frases completas juntos no mesmo chunk, evitando
    que respostas curtas (ex: "Sim, gatos.") fiquem separadas da pergunta.

    Args:
        chunk_size:     tamanho máximo em caracteres por chunk.
        overlap_units:  número de parágrafos do chunk anterior a reutilizar
                        no início do próximo (garante contexto entre chunks).
    """
    if not text:
        return []

    # 1. Separar por parágrafos (linhas duplas) ou por linha simples como fallback
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    if len(paragraphs) <= 1:
        # Texto sem parágrafos — usar linhas individuais
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]

    # 2. Agrupar parágrafos até atingir chunk_size
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len > chunk_size and current:
            chunks.append("\n\n".join(current))
            # Overlap: carrega os últimos N parágrafos para o próximo chunk
            current = current[-overlap_units:] + [para]
            current_len = sum(len(p) for p in current)
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def generate_embeddings(
    text: str,
    api_key: str,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> List[float]:
    """Gera embeddings usando Google Gemini (padrão: gemini-embedding-001).

    Args:
        task_type: use "RETRIEVAL_DOCUMENT" ao indexar chunks e
                   "RETRIEVAL_QUERY" ao embedar queries do usuário.
                   Isso otimiza a busca assimétrica do modelo.
    """
    client = genai.Client(api_key=api_key)
    embedding_model = os.getenv("GOOGLE_EMBEDDING_MODEL", "gemini-embedding-001")
    result = client.models.embed_content(
        model=embedding_model,
        contents=text,
        config=types.EmbedContentConfig(task_type=task_type),
    )
    input_tokens = extract_input_tokens(result, fallback_text=text)
    record_model_usage(embedding_model, input_tokens=input_tokens)
    return result.embeddings[0].values
