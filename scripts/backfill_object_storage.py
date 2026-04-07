import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from object_storage import build_object_storage
from postgres_repositories import create_postgres_repositories
from vector_store import VectorStore
from pei_storage import PEIStorage


def _env(name: str, default: str = '') -> str:
    return (os.getenv(name) or default).strip()


def main():
    load_dotenv()

    database_url = _env('DATABASE_URL')
    if not database_url:
        raise RuntimeError('DATABASE_URL é obrigatório para backfill de metadados')

    object_storage_backend = _env('OBJECT_STORAGE_BACKEND', 'local')
    supabase_url = _env('SUPABASE_URL')
    supabase_service_role_key = _env('SUPABASE_SERVICE_ROLE_KEY')
    rag_bucket = _env('SUPABASE_STORAGE_BUCKET_RAG', 'rag-documents')
    pei_bucket = _env('SUPABASE_STORAGE_BUCKET_PEI', 'pei-documents')

    rag_dir = BACKEND_DIR / 'rag_documents'
    pei_dir = BACKEND_DIR / 'peis'

    storage = build_object_storage(
        backend=object_storage_backend,
        local_bucket_dirs={
            rag_bucket: str(rag_dir),
            pei_bucket: str(pei_dir),
        },
        supabase_url=supabase_url,
        supabase_service_role_key=supabase_service_role_key,
    )

    repos = create_postgres_repositories(database_url)
    metadata_repo = repos['object_metadata']

    vector_store = VectorStore()
    pei_storage = PEIStorage(storage_dir=str(pei_dir))

    migrated_rag = 0
    skipped_rag = 0
    failed_rag = 0

    for pdf_path in sorted(rag_dir.glob('*.pdf')):
        doc_id = pdf_path.stem
        object_key = f'{doc_id}.pdf'

        if metadata_repo.get_file('rag_attachment_pdf', doc_id):
            skipped_rag += 1
            continue

        try:
            file_bytes = pdf_path.read_bytes()
            storage.upload_file(rag_bucket, object_key, file_bytes, 'application/pdf')

            rag_doc = vector_store.get_document(doc_id) or {}
            metadata_repo.upsert_file(
                doc_type='rag_attachment_pdf',
                reference_id=doc_id,
                bucket=rag_bucket,
                object_key=object_key,
                original_filename=rag_doc.get('file_name') or pdf_path.name,
                mime_type='application/pdf',
                size_bytes=len(file_bytes),
                extra={
                    'student_name': rag_doc.get('student_name', ''),
                    'school': rag_doc.get('school', ''),
                    'backfilled_from': str(pdf_path),
                },
            )
            migrated_rag += 1
        except Exception as exc:
            failed_rag += 1
            print(f'[RAG][ERRO] {pdf_path.name}: {exc}')

    migrated_pei = 0
    skipped_pei = 0
    failed_pei = 0

    for pei in pei_storage.list_all():
        pei_id = str(pei.get('id') or '').strip()
        if not pei_id:
            continue

        if metadata_repo.get_file('pei_generated_pdf', pei_id):
            skipped_pei += 1
            continue

        pdf_filename = (pei.get('pdf_filename') or '').strip()
        if not pdf_filename:
            failed_pei += 1
            print(f'[PEI][ERRO] {pei_id}: sem pdf_filename no índice')
            continue

        pdf_path = pei_dir / pdf_filename
        if not pdf_path.exists():
            failed_pei += 1
            print(f'[PEI][ERRO] {pei_id}: arquivo local não encontrado ({pdf_filename})')
            continue

        try:
            file_bytes = pdf_path.read_bytes()
            object_key = f'{pei_id}.pdf'
            storage.upload_file(pei_bucket, object_key, file_bytes, 'application/pdf')

            metadata_repo.upsert_file(
                doc_type='pei_generated_pdf',
                reference_id=pei_id,
                bucket=pei_bucket,
                object_key=object_key,
                original_filename=pdf_filename,
                mime_type='application/pdf',
                size_bytes=len(file_bytes),
                extra={
                    'student_name': pei.get('student_name', ''),
                    'school': pei.get('school', ''),
                    'backfilled_from': str(pdf_path),
                },
            )
            migrated_pei += 1
        except Exception as exc:
            failed_pei += 1
            print(f'[PEI][ERRO] {pei_id}: {exc}')

    print('\n=== BACKFILL CONCLUÍDO ===')
    print(f'RAG  -> migrados: {migrated_rag} | pulados: {skipped_rag} | falhas: {failed_rag}')
    print(f'PEI  -> migrados: {migrated_pei} | pulados: {skipped_pei} | falhas: {failed_pei}')


if __name__ == '__main__':
    main()
