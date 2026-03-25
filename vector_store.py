import chromadb
import os
import json
from typing import List, Dict, Optional
import uuid
from datetime import datetime


class VectorStore:
    def __init__(self, persist_directory: str = "./chroma_db"):
        chroma_api_key = os.getenv("CHROMA_API_KEY", "").strip()
        chroma_tenant = os.getenv("CHROMA_TENANT", "").strip()
        chroma_database = os.getenv("CHROMA_DATABASE", "").strip()
        chroma_host = os.getenv("CHROMA_HOST", "").strip()
        collection_name = os.getenv("CHROMA_COLLECTION_NAME", "documentos_pei")

        if chroma_api_key and chroma_tenant and chroma_database:
            self.client = chromadb.CloudClient(
                api_key=chroma_api_key,
                tenant=chroma_tenant,
                database=chroma_database,
            )
        elif chroma_host:
            headers = {}
            auth_token = os.getenv("CHROMA_AUTH_TOKEN", "").strip()
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"

            if chroma_api_key:
                headers["x-api-key"] = chroma_api_key

            raw_headers_json = os.getenv("CHROMA_HEADERS_JSON", "").strip()
            if raw_headers_json:
                try:
                    parsed_headers = json.loads(raw_headers_json)
                    if isinstance(parsed_headers, dict):
                        headers.update(parsed_headers)
                except Exception:
                    pass

            self.client = chromadb.HttpClient(
                host=chroma_host,
                port=int(os.getenv("CHROMA_PORT", "8000")),
                ssl=os.getenv("CHROMA_SSL", "false").strip().lower() in {"1", "true", "yes", "y", "on"},
                headers=headers or None,
                tenant=os.getenv("CHROMA_TENANT", "default_tenant"),
                database=os.getenv("CHROMA_DATABASE", "default_database"),
            )
        else:
            db_path = os.getenv("CHROMA_DB_PATH", persist_directory)
            self.client = chromadb.PersistentClient(path=db_path)

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(
        self,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: Dict,
    ) -> str:
        """Indexa chunks de um documento com seus embeddings."""
        doc_id = str(uuid.uuid4())
        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                **metadata,
                "doc_id": doc_id,
                "chunk_index": i,
                "upload_date": datetime.now().isoformat(),
            }
            for i in range(len(chunks))
        ]
        self.collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return doc_id

    def search_similar(
        self,
        query_embedding: List[float],
        k: int = 5,
        filter_metadata: Optional[Dict] = None,
    ) -> List[Dict]:
        """Busca os chunks mais similares à query."""
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": min(k, self.collection.count() or 1),
        }
        if filter_metadata:
            kwargs["where"] = filter_metadata

        results = self.collection.query(**kwargs)

        return [
            {
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            }
            for i in range(len(results["documents"][0]))
        ]

    def list_documents(self) -> List[Dict]:
        """Lista todos os documentos únicos indexados."""
        if self.collection.count() == 0:
            return []

        all_docs = self.collection.get()
        unique_docs: Dict[str, Dict] = {}
        for metadata in all_docs["metadatas"]:
            doc_id = metadata.get("doc_id")
            if doc_id and doc_id not in unique_docs:
                unique_docs[doc_id] = {
                    "doc_id": doc_id,
                    "file_name": metadata.get("file_name", "Desconhecido"),
                    "student_name": metadata.get("student_name", ""),
                    "school": metadata.get("school", ""),
                    "upload_date": metadata.get("upload_date", ""),
                }
        return list(unique_docs.values())

    def list_students(self) -> List[Dict]:
        """Lista estudantes únicos agrupados por (student_name, school)."""
        if self.collection.count() == 0:
            return []

        all_docs = self.collection.get()
        students: Dict[tuple, Dict] = {}
        for metadata in all_docs["metadatas"]:
            key = (
                metadata.get("student_name", ""),
                metadata.get("school", ""),
            )
            doc_id = metadata.get("doc_id", "")
            if key not in students:
                students[key] = {
                    "student_name": key[0],
                    "school": key[1],
                    "doc_ids": set(),
                    "files": {},
                }
            if doc_id:
                students[key]["doc_ids"].add(doc_id)
                if doc_id not in students[key]["files"]:
                    students[key]["files"][doc_id] = {
                        "doc_id": doc_id,
                        "file_name": metadata.get("file_name", ""),
                        "upload_date": metadata.get("upload_date", ""),
                    }

        result = []
        for data in students.values():
            result.append({
                "student_name": data["student_name"],
                "school": data["school"],
                "document_count": len(data["doc_ids"]),
                "documents": sorted(
                    list(data["files"].values()),
                    key=lambda d: d.get("upload_date", ""),
                ),
            })
        return sorted(result, key=lambda x: x["student_name"].lower())

    def keyword_search(
        self,
        terms: List[str],
        k: int = 5,
        filter_metadata: Optional[Dict] = None,
    ) -> List[Dict]:
        """Busca por termos exatos no texto dos chunks (fallback keyword).

        Usa o filtro where_document do ChromaDB, que não depende de embeddings.
        Ideal para termos específicos como nomes próprios e palavras-chave curtas.
        """
        if not terms or self.collection.count() == 0:
            return []

        # Monta filtro $contains — case-insensitive não é suportado, usar lower()
        terms_lower = [t.lower() for t in terms if len(t) >= 3]
        if not terms_lower:
            return []

        if len(terms_lower) == 1:
            where_doc = {"$contains": terms_lower[0]}
        else:
            where_doc = {"$or": [{"$contains": t} for t in terms_lower]}

        kwargs: Dict = {
            "where_document": where_doc,
            "include": ["documents", "metadatas"],
        }
        if filter_metadata:
            kwargs["where"] = filter_metadata

        try:
            results = self.collection.get(**kwargs)
        except Exception:
            return []

        docs = [
            {
                "text": results["documents"][i],
                "metadata": results["metadatas"][i],
                "distance": 0.0,  # match por palavra-chave = relevância máxima
            }
            for i in range(len(results["documents"]))
        ]
        return docs[:k]

    def hybrid_search(
        self,
        query_embedding: List[float],
        terms: List[str],
        k: int = 10,
        filter_metadata: Optional[Dict] = None,
    ) -> List[Dict]:
        """Combina busca vetorial + keyword e deduplica por chunk.

        - Busca vetorial garante relevância semântica geral.
        - Busca keyword garante que chunks com termos exatos nunca sejam perdidos.
        Resultado final limitado a k chunks, vetorial primeiro, keyword depois.
        """
        vector_results = self.search_similar(
            query_embedding, k=k, filter_metadata=filter_metadata
        )
        keyword_results = self.keyword_search(
            terms, k=max(k // 2, 3), filter_metadata=filter_metadata
        )

        seen: set = set()
        merged: List[Dict] = []

        for doc in vector_results:
            key = (
                doc["metadata"].get("doc_id", "")
                + "_"
                + str(doc["metadata"].get("chunk_index", ""))
            )
            if key not in seen:
                seen.add(key)
                merged.append(doc)

        for doc in keyword_results:
            key = (
                doc["metadata"].get("doc_id", "")
                + "_"
                + str(doc["metadata"].get("chunk_index", ""))
            )
            if key not in seen:
                seen.add(key)
                merged.append(doc)

        return merged[:k]

    def delete_document(self, doc_id: str) -> None:
        """Remove todos os chunks de um documento pelo doc_id."""
        self.collection.delete(where={"doc_id": doc_id})

    def count(self) -> int:
        """Retorna número total de chunks indexados."""
        return self.collection.count()
