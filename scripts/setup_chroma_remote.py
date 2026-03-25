import json
import os
from pathlib import Path
from typing import Dict, Optional

import chromadb
from dotenv import load_dotenv


def _load_env() -> None:
    script_path = Path(__file__).resolve()
    project_root = script_path.parents[2]

    load_dotenv(project_root / ".env.back", override=False)
    load_dotenv(project_root / ".env_back", override=False)
    load_dotenv(project_root / ".env", override=False)


def _to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _build_headers() -> Optional[Dict[str, str]]:
    headers: Dict[str, str] = {}

    auth_token = os.getenv("CHROMA_AUTH_TOKEN", "").strip()
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    api_key = os.getenv("CHROMA_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key

    raw_headers = os.getenv("CHROMA_HEADERS_JSON", "").strip()
    if raw_headers:
        parsed = json.loads(raw_headers)
        if isinstance(parsed, dict):
            headers.update({str(k): str(v) for k, v in parsed.items()})

    return headers or None


def _build_client() -> chromadb.ClientAPI:
    api_key = os.getenv("CHROMA_API_KEY", "").strip()
    tenant = os.getenv("CHROMA_TENANT", "").strip()
    database = os.getenv("CHROMA_DATABASE", "").strip()

    if api_key and tenant and database:
        return chromadb.CloudClient(
            api_key=api_key,
            tenant=tenant,
            database=database,
        )

    host = os.getenv("CHROMA_HOST", "").strip()
    if not host:
        raise RuntimeError(
            "Configure CHROMA_API_KEY + CHROMA_TENANT + CHROMA_DATABASE (TryChroma) "
            "ou CHROMA_HOST (HTTP self-hosted)."
        )

    ssl = _to_bool(os.getenv("CHROMA_SSL", "true"), default=True)
    default_port = "443" if ssl else "8000"
    port = int(os.getenv("CHROMA_PORT", default_port))

    tenant = os.getenv("CHROMA_TENANT", "default_tenant")
    database = os.getenv("CHROMA_DATABASE", "default_database")
    headers = _build_headers()

    return chromadb.HttpClient(
        host=host,
        port=port,
        ssl=ssl,
        headers=headers,
        tenant=tenant,
        database=database,
    )


def main() -> None:
    _load_env()

    collection_name = os.getenv("CHROMA_COLLECTION_NAME", "documentos_pei")

    try:
        client = _build_client()

        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        print("✅ Conectado ao Chroma remoto com sucesso")
        print(f"- collection: {collection.name}")
        print(f"- chunks atuais: {collection.count()}")
        print("\nPronto: banco remoto acessível e collection garantida.")
    except Exception as exc:
        print("❌ Falha ao inicializar Chroma remoto")
        print(f"Erro: {exc}")
        print("\nConfira estas variáveis em .env_back:")
        print("- CHROMA_API_KEY")
        print("- CHROMA_TENANT")
        print("- CHROMA_DATABASE")
        print("- (ou modo self-hosted) CHROMA_HOST, CHROMA_PORT, CHROMA_SSL")
        print("- CHROMA_AUTH_TOKEN e/ou CHROMA_HEADERS_JSON")
        raise


if __name__ == "__main__":
    main()
