"""Migra eventos de uso do JSONL para o banco de dados Supabase.

Uso:
    DATABASE_URL=postgresql://... python scripts/backfill_usage_to_db.py

Execute uma única vez após configurar o banco. O script é idempotente —
re-execuções não duplicam registros (o ID do evento é derivado do hash da linha).
"""
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL:
    print('Erro: variável DATABASE_URL não definida.')
    sys.exit(1)

JSONL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'usage_logs',
    'events.jsonl',
)

if not os.path.exists(JSONL_PATH):
    print(f'Arquivo não encontrado: {JSONL_PATH}')
    sys.exit(0)


def _stable_id(line: str) -> str:
    import hashlib
    return str(uuid.UUID(hashlib.md5(line.encode()).hexdigest()))


engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

with open(JSONL_PATH, 'r', encoding='utf-8') as f:
    lines = [l.strip() for l in f if l.strip()]

print(f'{len(lines)} eventos encontrados no JSONL.')

inserted = 0
skipped = 0
errors = 0

with SessionLocal() as session:
    for raw_line in lines:
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            errors += 1
            continue

        event_id = _stable_id(raw_line)

        exists = session.execute(
            text('SELECT 1 FROM ai_usage_events WHERE id = :id'),
            {'id': event_id},
        ).fetchone()

        if exists:
            skipped += 1
            continue

        session.execute(
            text("""
                INSERT INTO ai_usage_events
                    (id, timestamp, model, operation,
                     input_tokens, output_tokens, total_tokens,
                     duration_ms, user_id, username)
                VALUES
                    (:id, :timestamp, :model, :operation,
                     :input_tokens, :output_tokens, :total_tokens,
                     :duration_ms, :user_id, :username)
            """),
            {
                'id': event_id,
                'timestamp': event.get('timestamp', ''),
                'model': event.get('model', ''),
                'operation': event.get('operation', 'unspecified'),
                'input_tokens': event.get('input_tokens', 0),
                'output_tokens': event.get('output_tokens', 0),
                'total_tokens': event.get('total_tokens', 0),
                'duration_ms': event.get('duration_ms'),
                'user_id': event.get('user_id'),
                'username': event.get('username'),
            },
        )
        inserted += 1

    session.commit()

print(f'Concluído: {inserted} inseridos, {skipped} já existiam, {errors} erros de parse.')
