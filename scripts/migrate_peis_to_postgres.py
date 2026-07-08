"""
Migra PEIs do JSON local (peis/index.json) para a tabela PostgreSQL `peis`.

Uso:
    cd back/autism_poc_backend
    python scripts/migrate_peis_to_postgres.py

Requer DATABASE_URL configurado no .env.
O script é idempotente: PEIs já migrados (mesmo ID) são ignorados via upsert.
"""
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if not DATABASE_URL:
    print('ERRO: DATABASE_URL não configurado no .env')
    sys.exit(1)

from postgres_repositories import create_postgres_repositories

INDEX_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'peis', 'index.json')

if not os.path.exists(INDEX_PATH):
    print(f'Nenhum arquivo encontrado em {INDEX_PATH}. Nada a migrar.')
    sys.exit(0)

with open(INDEX_PATH, 'r', encoding='utf-8') as f:
    entries = json.load(f)

if not entries:
    print('index.json está vazio. Nada a migrar.')
    sys.exit(0)

repos = create_postgres_repositories(DATABASE_URL)
pei_repo = repos['pei']

migrated = 0
skipped = 0

for entry in entries:
    pei_id = (entry.get('id') or '').strip()
    if not pei_id:
        print(f'  IGNORADO: entrada sem id ({entry})')
        skipped += 1
        continue

    existing = pei_repo.get(pei_id)
    if existing:
        print(f'  JÁ EXISTE: {pei_id} ({entry.get("student_name")})')
        skipped += 1
        continue

    student_name = entry.get('student_name') or ''
    school = entry.get('school') or ''
    markdown_text = entry.get('markdown') or ''
    pdf_filename = entry.get('pdf_filename') or f'{pei_id}.pdf'
    # Para PEIs legados sem object_key, usamos o pdf_filename como object_key
    object_key = entry.get('object_key') or pdf_filename
    bucket = entry.get('bucket') or 'pei-documents'
    student_id = entry.get('student_id') or None
    generated_by_user_id = entry.get('generated_by_user_id') or None
    generated_by_username = entry.get('generated_by_username') or None
    created_at = entry.get('created_at') or ''

    # Verifica se o student_id existe no PostgreSQL; se não, migra sem ele
    # (o aluno pode existir só no JSON local — o PEI ainda é encontrado por student_name)
    if student_id:
        from sqlalchemy import create_engine, text as _text
        _engine = create_engine(DATABASE_URL, future=True)
        with _engine.connect() as conn:
            found = conn.execute(
                _text("SELECT 1 FROM students WHERE id = :sid"),
                {'sid': student_id},
            ).fetchone()
        if not found:
            print(f'    AVISO: student_id {student_id} não encontrado no PostgreSQL — migrado sem FK')
            student_id = None
        _engine.dispose()

    pei_repo.save(
        student_name=student_name,
        school=school,
        markdown_text=markdown_text,
        pdf_filename=pdf_filename,
        object_key=object_key,
        bucket=bucket,
        student_id=student_id,
        generated_by_user_id=generated_by_user_id,
        generated_by_username=generated_by_username,
        pei_id=pei_id,
        created_at=created_at or None,
    )
    print(f'  MIGRADO: {pei_id} ({student_name})')
    migrated += 1

print(f'\nConcluído. {migrated} migrado(s), {skipped} ignorado(s).')
