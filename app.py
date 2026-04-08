import os
import copy
import unicodedata
import difflib
import time
from io import BytesIO
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, send_file, g
from flask_cors import CORS
from dotenv import load_dotenv
import json
from typing import Dict, List, Optional
import orjson
import jwt
from werkzeug.utils import secure_filename

load_dotenv()


def _to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _parse_cors_origins() -> list:
    raw = os.getenv('CORS_ALLOWED_ORIGINS', '*').strip()
    if not raw:
        return ['*']
    if raw == '*':
        return ['*']
    return [origin.strip() for origin in raw.split(',') if origin.strip()]


def _normalize_student_name(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', (value or '').strip().lower())
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    return ' '.join(normalized.split())


def _name_tokens(value: str) -> List[str]:
    normalized = _normalize_student_name(value)
    return [token for token in normalized.split(' ') if token]

app = Flask(__name__)
DEBUG_MODE = _to_bool(os.getenv('DEBUG', 'False'), default=False)
CORS(app, resources={r'/api/*': {'origins': _parse_cors_origins()}})

# ------------------------------------------------------------------
# RAG Engine (inicializado sob demanda para evitar falha sem API key)
# ------------------------------------------------------------------
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
RAG_DOCUMENTS_FOLDER = os.path.join(os.path.dirname(__file__), 'rag_documents')
PEIS_FOLDER = os.path.join(os.path.dirname(__file__), 'peis')
DIARIES_FOLDER = os.path.join(os.path.dirname(__file__), 'diaries')
PDIS_FOLDER = os.path.join(os.path.dirname(__file__), 'pdis')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RAG_DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(PEIS_FOLDER, exist_ok=True)
os.makedirs(DIARIES_FOLDER, exist_ok=True)
os.makedirs(PDIS_FOLDER, exist_ok=True)

from pei_storage import PEIStorage
from diary_storage import DiaryStorage
from pdi_storage import PDIStorage
from prompt_storage import PromptStorage
from school_storage import SchoolStorage
from student_storage import StudentStorage
from teacher_storage import TeacherStorage
from auth_storage import AuthStorage, VALID_ROLES
from audit_storage import AuditStorage
from postgres_repositories import create_postgres_repositories
from object_storage import ObjectStorageError, build_object_storage
from diary_pdf_parser import parse_diary_pdf, QUESTION_PATTERNS
from usage_tracker import get_usage_snapshot, record_model_usage
from time_utils import now_brasilia_filename, now_brasilia_iso
_pei_storage = PEIStorage(storage_dir=PEIS_FOLDER)
_diary_storage = DiaryStorage(storage_dir=DIARIES_FOLDER)
_pdi_storage = PDIStorage(storage_dir=PDIS_FOLDER)
PROMPTS_FOLDER = os.path.join(os.path.dirname(__file__), 'prompts')
os.makedirs(PROMPTS_FOLDER, exist_ok=True)
_prompt_storage = PromptStorage(storage_dir=PROMPTS_FOLDER)

SCHOOLS_FOLDER = os.path.join(os.path.dirname(__file__), 'schools')
STUDENTS_FOLDER = os.path.join(os.path.dirname(__file__), 'students')
USERS_FOLDER = os.path.join(os.path.dirname(__file__), 'users')
AUDIT_FOLDER = os.path.join(os.path.dirname(__file__), 'audit_logs')
TEACHERS_FOLDER = os.path.join(os.path.dirname(__file__), 'teachers')
os.makedirs(SCHOOLS_FOLDER, exist_ok=True)
os.makedirs(STUDENTS_FOLDER, exist_ok=True)
os.makedirs(USERS_FOLDER, exist_ok=True)
os.makedirs(AUDIT_FOLDER, exist_ok=True)
os.makedirs(TEACHERS_FOLDER, exist_ok=True)
_school_storage = SchoolStorage(storage_dir=SCHOOLS_FOLDER)
_student_storage = StudentStorage(storage_dir=STUDENTS_FOLDER)
_teacher_storage = TeacherStorage(storage_dir=TEACHERS_FOLDER)
_auth_storage = AuthStorage(
    storage_dir=USERS_FOLDER,
    default_admin_username=os.getenv('AUTH_ADMIN_USERNAME', 'admin'),
    default_admin_password=os.getenv('AUTH_ADMIN_PASSWORD', ''),
)
_audit_storage = AuditStorage(storage_dir=AUDIT_FOLDER)

DATA_BACKEND = (os.getenv('DATA_BACKEND', 'file') or 'file').strip().lower()
DATABASE_URL = (os.getenv('DATABASE_URL') or '').strip()
OBJECT_STORAGE_BACKEND = (os.getenv('OBJECT_STORAGE_BACKEND', 'local') or 'local').strip().lower()
SUPABASE_URL = (os.getenv('SUPABASE_URL') or '').strip()
SUPABASE_SERVICE_ROLE_KEY = (os.getenv('SUPABASE_SERVICE_ROLE_KEY') or '').strip()
RAG_STORAGE_BUCKET = (os.getenv('SUPABASE_STORAGE_BUCKET_RAG', 'rag-documents') or 'rag-documents').strip()
PEI_STORAGE_BUCKET = (os.getenv('SUPABASE_STORAGE_BUCKET_PEI', 'pei-documents') or 'pei-documents').strip()

RAG_DOC_TYPE = 'rag_attachment_pdf'
PEI_DOC_TYPE = 'pei_generated_pdf'

_postgres_repositories = None
if DATA_BACKEND in {'postgres', 'dual'}:
    if not DATABASE_URL:
        if DATA_BACKEND == 'postgres':
            raise RuntimeError('DATABASE_URL é obrigatório quando DATA_BACKEND=postgres')
        print('Aviso: DATA_BACKEND=dual sem DATABASE_URL; usando apenas armazenamento em arquivo.')
    else:
        _postgres_repositories = create_postgres_repositories(DATABASE_URL)

try:
    _object_storage = build_object_storage(
        backend=OBJECT_STORAGE_BACKEND,
        local_bucket_dirs={
            RAG_STORAGE_BUCKET: RAG_DOCUMENTS_FOLDER,
            PEI_STORAGE_BUCKET: PEIS_FOLDER,
        },
        supabase_url=SUPABASE_URL,
        supabase_service_role_key=SUPABASE_SERVICE_ROLE_KEY,
    )
except ObjectStorageError as exc:
    raise RuntimeError(f'Falha ao inicializar object storage: {exc}') from exc


def _is_postgres_available() -> bool:
    return _postgres_repositories is not None


def _is_postgres_mode() -> bool:
    return DATA_BACKEND == 'postgres' and _is_postgres_available()


def _is_dual_mode() -> bool:
    return DATA_BACKEND == 'dual' and _is_postgres_available()


def _is_file_mode() -> bool:
    return DATA_BACKEND == 'file' or not _is_postgres_available()


def _read_from_postgres_first() -> bool:
    return DATA_BACKEND in {'postgres', 'dual'} and _is_postgres_available()


def _get_object_metadata_repo():
    if not _is_postgres_available():
        return None
    return _postgres_repositories.get('object_metadata')


def _upsert_object_metadata(
    doc_type: str,
    reference_id: str,
    bucket: str,
    object_key: str,
    original_filename: str,
    mime_type: str = 'application/pdf',
    size_bytes: int = 0,
    extra: Optional[Dict] = None,
):
    repository = _get_object_metadata_repo()
    if not repository:
        return None
    return repository.upsert_file(
        doc_type=doc_type,
        reference_id=reference_id,
        bucket=bucket,
        object_key=object_key,
        original_filename=original_filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        extra=extra or {},
    )


def _get_object_metadata(doc_type: str, reference_id: str) -> Optional[Dict]:
    repository = _get_object_metadata_repo()
    if not repository:
        return None
    return repository.get_file(doc_type=doc_type, reference_id=reference_id)


def _list_object_metadata(doc_type: str, bucket: str = '') -> List[Dict]:
    repository = _get_object_metadata_repo()
    if not repository or not hasattr(repository, 'list_files'):
        return []
    return repository.list_files(doc_type=doc_type, bucket=bucket or None)


def _delete_object_metadata(doc_type: str, reference_id: str):
    repository = _get_object_metadata_repo()
    if not repository:
        return False
    return repository.delete_file(doc_type=doc_type, reference_id=reference_id)


def _build_pei_entry_from_metadata(file_meta: Dict) -> Dict:
    extra = file_meta.get('extra') or {}
    return {
        'id': file_meta.get('reference_id', ''),
        'student_name': extra.get('student_name') or 'Aluno não identificado',
        'school': extra.get('school') or '',
        'created_at': file_meta.get('created_at') or '',
        'pdf_filename': file_meta.get('original_filename') or f"{file_meta.get('reference_id', '')}.pdf",
    }


def _list_all_peis_with_metadata_fallback() -> List[Dict]:
    local_entries = _pei_storage.list_all()
    merged_by_id = {
        str(item.get('id') or '').strip(): dict(item)
        for item in local_entries
        if str(item.get('id') or '').strip()
    }

    for file_meta in _list_object_metadata(PEI_DOC_TYPE, PEI_STORAGE_BUCKET):
        reference_id = str(file_meta.get('reference_id') or '').strip()
        if not reference_id or reference_id in merged_by_id:
            continue
        merged_by_id[reference_id] = _build_pei_entry_from_metadata(file_meta)

    merged_entries = list(merged_by_id.values())
    merged_entries.sort(key=lambda item: item.get('created_at') or '', reverse=True)
    return merged_entries


def _sync_legacy_diary_links() -> int:
    linked_count = 0
    students = _student_storage.list_all_students()
    student_index = []

    for student in students:
        student_name = student.get('name') or ''
        student_index.append({
            'id': student.get('id'),
            'name': student_name,
            'normalized_name': _normalize_student_name(student_name),
            'tokens': _name_tokens(student_name),
        })

    # 1) Linkagem exata por nome normalizado
    for student in students:
        linked_count += _diary_storage.link_entries_to_student(
            student.get('id'),
            student.get('name'),
        )

    # 2) Fallback conservador para nomes muito próximos (ex.: Mariane/Mariana)
    summaries = _diary_storage.list_all_summaries()
    for summary in summaries:
        if summary.get('student_id'):
            continue

        diary_name = summary.get('student_name') or ''
        diary_normalized = _normalize_student_name(diary_name)
        diary_tokens = _name_tokens(diary_name)
        if len(diary_tokens) < 2:
            continue

        best_match = None
        best_ratio = 0.0
        for student in student_index:
            student_tokens = student.get('tokens') or []
            if len(student_tokens) < 2:
                continue
            if diary_tokens[-1] != student_tokens[-1]:
                continue

            ratio = difflib.SequenceMatcher(None, diary_normalized, student.get('normalized_name', '')).ratio()
            if ratio >= 0.92 and ratio > best_ratio:
                best_ratio = ratio
                best_match = student

        if best_match:
            linked_count += _diary_storage.link_entries_to_student(
                best_match.get('id'),
                best_match.get('name'),
            )

    return linked_count


def _sync_legacy_pdi_links() -> int:
    linked_count = 0
    students = _student_storage.list_all_students()
    for student in students:
        linked_count += _pdi_storage.link_pdis_to_student(
            student.get('id'),
            student.get('name'),
        )
    return linked_count

JWT_SECRET = os.getenv('AUTH_JWT_SECRET') or os.getenv('SECRET_KEY')
if not JWT_SECRET:
    if DEBUG_MODE:
        JWT_SECRET = 'dev-only-jwt-secret'
    else:
        raise RuntimeError('AUTH_JWT_SECRET não configurado. Defina no .env para iniciar em produção.')
JWT_ALGORITHM = 'HS256'
JWT_EXP_MINUTES = int(os.getenv('AUTH_TOKEN_EXP_MINUTES', '480'))

PUBLIC_API_PATHS = {
    '/api/health',
    '/api/auth/login',
}

ADMIN_ONLY_PREFIXES = (
    '/api/auth/users',
    '/api/audit',
    '/api/teachers',
    '/api/admin',
)

MUTATING_METHODS = {'POST', 'PUT', 'DELETE', 'PATCH'}

_rag_engine = None

def get_rag_engine():
    global _rag_engine
    if _rag_engine is None:
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return None
        from rag_engine import RAGEngine
        _rag_engine = RAGEngine(api_key=api_key)
    return _rag_engine


def _student_name_from_record(student: Dict) -> str:
    return student.get('name') or student.get('studentName') or ''


def _student_school_from_record(student: Dict) -> str:
    school_id = (student.get('school_id') or '').strip()
    if school_id:
        school = _get_school_record(school_id)
        if school:
            return (school.get('name') or '').strip()
    return (student.get('school_name') or student.get('schoolName') or '').strip()


def _get_diary_entries_for_student(student_name: str, student_id: str = '') -> List[Dict]:
    """Retorna entradas de diário com fallback por nome para casos legados."""
    entries = _read_with_optional_fallback('diary', _diary_storage, 'get_entries_by_student', student_name, student_id=student_id or None)

    if not student_id:
        return entries

    fallback_by_name = _read_with_optional_fallback('diary', _diary_storage, 'get_entries_by_student', student_name, student_id=None)
    if not fallback_by_name:
        return entries

    merged: Dict[str, Dict] = {}
    for entry in entries + fallback_by_name:
        merged[entry.get('id') or f"{entry.get('diary_date', '')}::{entry.get('created_at', '')}"] = entry

    return sorted(list(merged.values()), key=lambda x: x.get('diary_date', ''), reverse=True)


def _get_pdi_for_student(student_name: str, student_id: str = '') -> Dict | None:
    """Retorna PDI com fallback por nome para casos legados."""
    strict_pdi = _read_with_optional_fallback('pdi', _pdi_storage, 'get_pdi_by_student', student_name, student_id=student_id or None)
    if not student_id:
        return strict_pdi

    fallback_pdi = _read_with_optional_fallback('pdi', _pdi_storage, 'get_pdi_by_student', student_name, student_id=None)
    if strict_pdi and fallback_pdi:
        strict_updated = strict_pdi.get('updated_at') or ''
        fallback_updated = fallback_pdi.get('updated_at') or ''
        return strict_pdi if strict_updated >= fallback_updated else fallback_pdi

    return strict_pdi or fallback_pdi


def _summarize_vector_documents_for_student(engine, student_name: str, school: str) -> Dict:
    """Resume docs do RAG, com fallback por nome quando escola diverge."""
    empty = {
        "document_count": 0,
        "documents": [],
    }

    if engine is None or not student_name:
        return empty

    if school:
        strict_summary = engine.vector_store.summarize_student_documents(student_name, school)
        if strict_summary.get('document_count', 0) > 0:
            return strict_summary

    target_student = _normalize_student_name(student_name)
    all_students = engine.vector_store.list_students()
    unique_docs: Dict[str, Dict] = {}

    for item in all_students:
        if _normalize_student_name(item.get('student_name', '')) != target_student:
            continue

        for doc in item.get('documents', []):
            doc_id = doc.get('doc_id')
            if doc_id and doc_id not in unique_docs:
                unique_docs[doc_id] = {
                    'doc_id': doc_id,
                    'file_name': doc.get('file_name', ''),
                    'upload_date': doc.get('upload_date', ''),
                }

    documents = sorted(
        list(unique_docs.values()),
        key=lambda item: item.get('upload_date', ''),
        reverse=True,
    )

    return {
        'document_count': len(documents),
        'documents': documents,
    }


def _default_pei_source_selection() -> Dict[str, bool]:
    return {
        'vector_documents': True,
        'diary': True,
        'pdi': True,
        'student_pre_registration': True,
        'teachers_pre_registration': True,
        'school_pre_registration': True,
        'linked_peis': True,
    }


def _parse_selected_sources(raw_selection) -> Dict[str, bool]:
    defaults = _default_pei_source_selection()
    if not isinstance(raw_selection, dict):
        return defaults

    parsed = dict(defaults)
    for key in defaults:
        if key in raw_selection:
            parsed[key] = bool(raw_selection.get(key))
    return parsed


def _entry_matches_student(entry: Dict, student_id: str, student_name: str, school: str = '') -> bool:
    entry_student_id = (entry.get('student_id') or '').strip()
    if student_id and entry_student_id:
        if entry_student_id != student_id:
            return False
        if school and _normalize_student_name(entry.get('school', '')) != _normalize_student_name(school):
            return False
        return True

    # Compatibilidade: PEIs legados podem não ter student_id salvo.
    # Quando o filtro chega com student_id, priorizamos match por nome do aluno
    # para não perder histórico antigo após esta migração.
    if student_id and not entry_student_id:
        return _normalize_student_name(entry.get('student_name', '')) == _normalize_student_name(student_name)

    if _normalize_student_name(entry.get('student_name', '')) != _normalize_student_name(student_name):
        return False

    if school and _normalize_student_name(entry.get('school', '')) != _normalize_student_name(school):
        return False

    return True


def _list_linked_peis(student_name: str, student_id: str = '', school: str = '', max_items: int = 10) -> List[Dict]:
    entries = []
    for item in _list_all_peis_with_metadata_fallback():
        if not _entry_matches_student(item, student_id=student_id, student_name=student_name, school=school):
            continue
        entries.append(item)

    entries.sort(key=lambda item: item.get('created_at', ''), reverse=True)
    return entries[:max_items]


def _build_integrated_student_context(
    student_name: str,
    student_id: str = '',
    max_diary_entries: int = 8,
    selected_sources: Dict[str, bool] | None = None,
) -> str:
    source_selection = _parse_selected_sources(selected_sources)
    sections: List[str] = []

    student_record = _get_student_record(student_id) if student_id else None
    if not student_record and student_name:
        matches = _find_students_by_name(student_name)
        student_record = matches[0] if matches else None

    canonical_student_name = student_name
    school_record = None
    linked_teacher_records: List[Dict] = []

    if student_record:
        canonical_student_name = _student_name_from_record(student_record) or student_name
        school_id = (student_record.get('school_id') or '').strip()
        if school_id:
            school_record = _get_school_record(school_id)

        teacher_ids = student_record.get('teacher_ids') or []
        if not isinstance(teacher_ids, list):
            teacher_ids = []
        legacy_teacher_id = (student_record.get('teacher_id') or '').strip()
        if legacy_teacher_id and legacy_teacher_id not in teacher_ids:
            teacher_ids.append(legacy_teacher_id)

        for teacher_id in teacher_ids:
            teacher = _get_teacher_record(teacher_id)
            if teacher:
                linked_teacher_records.append(teacher)

    if source_selection.get('student_pre_registration') and student_record:
        sections.append(
            'Pré-cadastro do aluno (JSON):\n'
            + json.dumps(student_record, ensure_ascii=False, indent=2)
        )

    if source_selection.get('school_pre_registration') and school_record:
        sections.append(
            'Pré-cadastro da escola (JSON):\n'
            + json.dumps(school_record, ensure_ascii=False, indent=2)
        )

    if source_selection.get('teachers_pre_registration') and linked_teacher_records:
        sections.append(
            'Pré-cadastro dos docentes vinculados (JSON):\n'
            + json.dumps(linked_teacher_records, ensure_ascii=False, indent=2)
        )

    diary_entries = _get_diary_entries_for_student(canonical_student_name, student_id=student_id)
    diary_entries_count = len(diary_entries)
    if source_selection.get('diary') and diary_entries:
        recent_entries = diary_entries[:max_diary_entries]
        sections.append(
            'Diário de acompanhamento (JSON, entradas mais recentes):\n'
            + json.dumps(recent_entries, ensure_ascii=False, indent=2)
        )

    pdi = _get_pdi_for_student(canonical_student_name, student_id=student_id)
    if source_selection.get('pdi') and pdi:
        sections.append(
            'PDI do aluno (JSON):\n'
            + json.dumps(pdi, ensure_ascii=False, indent=2)
        )

    linked_peis = _list_linked_peis(canonical_student_name, student_id=student_id)
    if source_selection.get('linked_peis') and linked_peis:
        pei_summaries = []
        for entry in linked_peis:
            pei_full = _pei_storage.get(entry.get('id')) or entry
            markdown_text = pei_full.get('markdown') or ''
            pei_summaries.append({
                'id': pei_full.get('id'),
                'created_at': pei_full.get('created_at'),
                'school': pei_full.get('school'),
                'excerpt': markdown_text[:1800],
            })

        sections.append(
            'PEIs anteriores vinculados ao aluno (JSON):\n'
            + json.dumps(pei_summaries, ensure_ascii=False, indent=2)
        )

    source_status = (
        'Status oficial das fontes (use estas flags para responder perguntas de existência de dados):\n'
        f'- diario_entries_count: {diary_entries_count}\n'
        f'- diario_included: {str(source_selection.get("diary") and diary_entries_count > 0).lower()}\n'
        f'- pdi_included: {str(source_selection.get("pdi") and bool(pdi)).lower()}\n'
        f'- student_pre_registration_included: {str(source_selection.get("student_pre_registration") and bool(student_record)).lower()}\n'
        f'- teachers_pre_registration_included: {str(source_selection.get("teachers_pre_registration") and len(linked_teacher_records) > 0).lower()}\n'
        f'- school_pre_registration_included: {str(source_selection.get("school_pre_registration") and bool(school_record)).lower()}\n'
        f'- linked_peis_included: {str(source_selection.get("linked_peis") and len(linked_peis) > 0).lower()}\n'
        'Regra: não classifique PDI como Diário. Se diario_entries_count = 0, responda que não há diário cadastrado.'
    )
    sections.insert(0, source_status)

    if len(sections) == 1:
        return '(Sem dados integrados selecionados para este aluno)'

    return '\n\n---\n\n'.join(sections)


@app.route('/api/rag/pei-sources-preview', methods=['GET'])
def get_pei_sources_preview():
    """Retorna prévia das fontes que serão usadas para gerar PEI."""
    student_id = request.args.get('student_id', '').strip()
    student_name = request.args.get('student_name', '').strip()
    school = request.args.get('school', '').strip()

    student = None
    if student_id:
        student = _get_student_record(student_id)
        if not student:
            return jsonify({"error": "Aluno não encontrado"}), 404
        student_name = _student_name_from_record(student)
        school = _student_school_from_record(student)

    if not student_name:
        return jsonify({"error": "Nome do estudante é obrigatório"}), 400

    if not student:
        matches = _find_students_by_name(student_name)
        student = matches[0] if matches else None

    teacher_records = []
    school_record = None
    if student:
        school_id = (student.get('school_id') or '').strip()
        if school_id:
            school_record = _get_school_record(school_id)

        teacher_ids = student.get('teacher_ids') or []
        if not isinstance(teacher_ids, list):
            teacher_ids = []
        legacy_teacher_id = (student.get('teacher_id') or '').strip()
        if legacy_teacher_id and legacy_teacher_id not in teacher_ids:
            teacher_ids.append(legacy_teacher_id)

        for teacher_id in teacher_ids:
            teacher = _get_teacher_record(teacher_id)
            if teacher:
                teacher_records.append(teacher)

    diary_entries = _get_diary_entries_for_student(student_name, student_id=student_id)
    pdi = _get_pdi_for_student(student_name, student_id=student_id)
    linked_peis = _list_linked_peis(student_name, student_id=student_id, school=school)

    engine = get_rag_engine()
    docs_summary = _summarize_vector_documents_for_student(engine, student_name, school)

    return jsonify({
        "student_name": student_name,
        "school": school,
        "sources": {
            "student_pre_registration": {
                "included": bool(student),
            },
            "teachers_pre_registration": {
                "included": len(teacher_records) > 0,
                "count": len(teacher_records),
                "teachers": [
                    {
                        "id": teacher.get('id'),
                        "name": teacher.get('name'),
                    }
                    for teacher in teacher_records
                ],
            },
            "school_pre_registration": {
                "included": bool(school_record),
                "school_name": school_record.get('name') if school_record else None,
            },
            "vector_documents": {
                "included": docs_summary['document_count'] > 0,
                "document_count": docs_summary['document_count'],
                "documents": docs_summary['documents'],
            },
            "diary": {
                "included": len(diary_entries) > 0,
                "entries_count": len(diary_entries),
            },
            "pdi": {
                "included": bool(pdi),
                "updated_at": pdi.get('updated_at') if pdi else None,
            },
            "linked_peis": {
                "included": len(linked_peis) > 0,
                "count": len(linked_peis),
                "peis": [
                    {
                        "id": item.get('id'),
                        "created_at": item.get('created_at'),
                    }
                    for item in linked_peis
                ],
            },
        },
    })


def _extract_bearer_token() -> str:
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return ''
    return auth_header.split(' ', 1)[1].strip()

def _is_empty_result(value) -> bool:
    if value is None:
        return True
    if value is False:
        return True
    if isinstance(value, (list, dict, tuple, set, str)):
        return len(value) == 0
    return False


def _read_with_optional_fallback(repo_key: str, file_repo, method_name: str, *args, **kwargs):
    if _read_from_postgres_first():
        value = getattr(_postgres_repositories[repo_key], method_name)(*args, **kwargs)
        if _is_dual_mode() and _is_empty_result(value):
            return getattr(file_repo, method_name)(*args, **kwargs)
        return value
    return getattr(file_repo, method_name)(*args, **kwargs)


def _get_student_record(student_id: str):
    return _read_with_optional_fallback('student', _student_storage, 'get_student', student_id)


def _list_student_summaries():
    return _read_with_optional_fallback('student', _student_storage, 'list_all_students')


def _find_students_by_name(candidate_name: str):
    return _read_with_optional_fallback('student', _student_storage, 'find_students_by_name', candidate_name)


def _get_school_record(school_id: str):
    return _read_with_optional_fallback('school', _school_storage, 'get_school', school_id)


def _get_teacher_record(teacher_id: str):
    return _read_with_optional_fallback('teacher', _teacher_storage, 'get_teacher', teacher_id)


def _sync_legacy_diary_links_for_repo(repo, students: List[Dict]) -> int:
    linked_count = 0
    student_index = []

    for student in students:
        student_name = student.get('name') or ''
        student_index.append({
            'id': student.get('id'),
            'name': student_name,
            'normalized_name': _normalize_student_name(student_name),
            'tokens': _name_tokens(student_name),
        })

    for student in students:
        linked_count += repo.link_entries_to_student(
            student.get('id'),
            student.get('name'),
        )

    summaries = repo.list_all_summaries()
    for summary in summaries:
        if summary.get('student_id'):
            continue

        diary_name = summary.get('student_name') or ''
        diary_normalized = _normalize_student_name(diary_name)
        diary_tokens = _name_tokens(diary_name)
        if len(diary_tokens) < 2:
            continue

        best_match = None
        best_ratio = 0.0
        for student in student_index:
            student_tokens = student.get('tokens') or []
            if len(student_tokens) < 2:
                continue
            if diary_tokens[-1] != student_tokens[-1]:
                continue

            ratio = difflib.SequenceMatcher(None, diary_normalized, student.get('normalized_name', '')).ratio()
            if ratio >= 0.92 and ratio > best_ratio:
                best_ratio = ratio
                best_match = student

        if best_match:
            linked_count += repo.link_entries_to_student(
                best_match.get('id'),
                best_match.get('name'),
            )

    return linked_count


def _sync_legacy_diary_links() -> int:
    students = _list_student_summaries()
    if _is_postgres_mode():
        return _sync_legacy_diary_links_for_repo(_postgres_repositories['diary'], students)

    linked = _sync_legacy_diary_links_for_repo(_diary_storage, students)
    if _is_dual_mode():
        linked += _sync_legacy_diary_links_for_repo(_postgres_repositories['diary'], students)
    return linked


def _sync_legacy_pdi_links() -> int:
    students = _list_student_summaries()

    def _sync_repo(repo):
        linked_count = 0
        for student in students:
            linked_count += repo.link_pdis_to_student(
                student.get('id'),
                student.get('name'),
            )
        return linked_count

    if _is_postgres_mode():
        return _sync_repo(_postgres_repositories['pdi'])

    linked = _sync_repo(_pdi_storage)
    if _is_dual_mode():
        linked += _sync_repo(_postgres_repositories['pdi'])
    return linked


def _build_token(user: Dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        'sub': user.get('id'),
        'username': user.get('username'),
        'role': user.get('role'),
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(minutes=JWT_EXP_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _sanitize_current_user(user: Dict) -> Dict:
    return {
        'id': user.get('id'),
        'username': user.get('username'),
        'name': user.get('name') or '',
        'role': user.get('role') or 'viewer',
        'is_active': bool(user.get('is_active', True)),
        'created_at': user.get('created_at'),
        'updated_at': user.get('updated_at'),
    }


def _is_admin_only_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in ADMIN_ONLY_PREFIXES)


def _should_audit_request(path: str, method: str) -> bool:
    if not path.startswith('/api'):
        return False
    if path == '/api/health':
        return False
    if method == 'OPTIONS':
        return False
    return True


@app.before_request
def require_authentication():
    g.current_user = None
    if request.method == 'OPTIONS':
        return None
    if request.path in PUBLIC_API_PATHS:
        return None

    token = _extract_bearer_token()
    if not token:
        return jsonify({'error': 'Token ausente'}), 401

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Sessão expirada. Faça login novamente'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Token inválido'}), 401

    user = _auth_storage.get_user_by_id(payload.get('sub', ''))
    if not user or not user.get('is_active', True):
        return jsonify({'error': 'Usuário inválido ou inativo'}), 401

    g.current_user = _sanitize_current_user(user)

    if _is_admin_only_path(request.path) and g.current_user['role'] != 'admin':
        return jsonify({'error': 'Acesso negado para este perfil'}), 403

    if request.method in MUTATING_METHODS and g.current_user['role'] == 'viewer':
        return jsonify({'error': 'Perfil viewer possui apenas leitura'}), 403

    return None


@app.after_request
def audit_api_requests(response):
    if request.path.startswith('/api') and _should_audit_request(request.path, request.method):
        _audit_storage.log_event(
            action=f'{request.method} {request.path}',
            status_code=response.status_code,
            path=request.path,
            method=request.method,
            user=getattr(g, 'current_user', None),
        )
    return response

# Armazenamento em memória (pode ser substituído por banco de dados)
submissions = []

FORMS = {
    "cadastro_escola": {
        "id": "cadastro_escola",
        "name": "Cadastro da Escola",
        "description": "Formulário para cadastro de instituições educacionais que oferecem atendimento a estudantes com TEA",
        "sections": 8
    },
    "cadastro_aluno": {
        "id": "cadastro_aluno",
        "name": "Estudo de Caso",
        "description": "Formulário para cadastro detalhado de alunos com TEA, incluindo informações pessoais, escolares e familiares",
        "sections": 6
    }
}


def _get_submissions_from_file() -> List[Dict]:
    return list(submissions)


def _get_submissions_form_counts() -> Dict[str, int]:
    if _read_from_postgres_first():
        counts = _postgres_repositories['form_submission'].get_form_counts()
        if _is_dual_mode() and not any(counts.values()):
            counts = {
                form_id: len([s for s in submissions if s.get('form_id') == form_id])
                for form_id in FORMS.keys()
            }
        return counts

    return {
        form_id: len([s for s in submissions if s.get('form_id') == form_id])
        for form_id in FORMS.keys()
    }


def _delete_file_submissions_by_pre_registration(form_id: str, pre_registration_id: str) -> int:
    if not pre_registration_id:
        return 0

    removed = 0
    kept = []
    for item in submissions:
        metadata = item.get('metadata') or {}
        if item.get('form_id') == form_id and str(metadata.get('pre_registration_id', '')) == str(pre_registration_id):
            removed += 1
            continue
        kept.append(item)

    if removed:
        submissions[:] = kept

    return removed


def _delete_form_links_for_pre_registration(form_id: str, pre_registration_id: str) -> int:
    removed = 0

    if _read_from_postgres_first():
        removed += _postgres_repositories['form_submission'].delete_by_pre_registration(form_id, pre_registration_id)
        if _is_dual_mode() and removed == 0:
            removed += _delete_file_submissions_by_pre_registration(form_id, pre_registration_id)
        return removed

    removed += _delete_file_submissions_by_pre_registration(form_id, pre_registration_id)
    if _is_dual_mode():
        _postgres_repositories['form_submission'].delete_by_pre_registration(form_id, pre_registration_id)
    return removed

@app.route('/api/forms', methods=['GET'])
def get_forms():
    """Retorna lista de formulários disponíveis"""
    form_counts = _get_submissions_form_counts()
    forms_list = [
        {
            "id": form["id"],
            "name": form["name"],
            "description": form["description"],
            "submissions_count": form_counts.get(form["id"], 0),
        }
        for form in FORMS.values()
    ]
    return jsonify(forms_list)


@app.route('/api/forms/counts', methods=['GET'])
def get_forms_counts():
    """Retorna contagens de submissões por formulário."""
    counts = _get_submissions_form_counts()
    return jsonify(counts)

@app.route('/api/forms/<form_id>', methods=['GET'])
def get_form(form_id):
    """Retorna um formulário específico"""
    form = FORMS.get(form_id)
    if not form:
        return jsonify({"error": "Formulário não encontrado"}), 404
    return jsonify(form)

@app.route('/api/submissions', methods=['POST'])
def submit_form():
    """Submete um formulário preenchido"""
    data = request.json
    
    if not data or 'form_id' not in data or 'answers' not in data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    form_id = data['form_id']
    form = FORMS.get(form_id)
    if not form:
        return jsonify({"error": "form_id inválido"}), 400

    submitted_at = now_brasilia_iso()
    metadata = data.get('metadata', {}) or {}
    pre_registration_id = metadata.get('pre_registration_id')

    if _is_postgres_mode():
        submission_id = None
        if pre_registration_id:
            existing = _postgres_repositories['form_submission'].get_submission_by_pre_registration(
                form_id,
                str(pre_registration_id),
            )
            submission_id = existing.get('id') if existing else None

        submission = _postgres_repositories['form_submission'].save_submission(
            form_id=form_id,
            answers=data['answers'],
            metadata=metadata,
            submission_id=submission_id,
            submitted_at=submitted_at,
        )
    else:
        submission_id = len(submissions) + 1
        if pre_registration_id:
            existing = next(
                (
                    item for item in submissions
                    if item.get('form_id') == form_id
                    and str((item.get('metadata') or {}).get('pre_registration_id', '')) == str(pre_registration_id)
                ),
                None,
            )
            if existing:
                submission_id = existing['id']

        submission = {
            "id": submission_id,
            "form_id": form_id,
            "form_name": form.get('name', 'Desconhecido'),
            "answers": data['answers'],
            "submitted_at": submitted_at,
            "metadata": metadata,
        }
        if pre_registration_id:
            _delete_file_submissions_by_pre_registration(form_id, str(pre_registration_id))
        submissions.append(submission)

        if _is_dual_mode():
            dual_submission_id = None
            if pre_registration_id:
                existing_pg = _postgres_repositories['form_submission'].get_submission_by_pre_registration(
                    form_id,
                    str(pre_registration_id),
                )
                dual_submission_id = existing_pg.get('id') if existing_pg else None

            _postgres_repositories['form_submission'].save_submission(
                form_id=form_id,
                answers=data['answers'],
                metadata=metadata,
                submission_id=dual_submission_id or str(submission['id']),
                submitted_at=submitted_at,
            )
    
    return jsonify({
        "message": "Formulário submetido com sucesso",
        "submission_id": submission['id']
    }), 201

@app.route('/api/submissions', methods=['GET'])
def get_submissions():
    """Retorna todas as submissões"""
    if _read_from_postgres_first():
        data = _postgres_repositories['form_submission'].list_all_submissions()
        if _is_dual_mode() and not data:
            data = _get_submissions_from_file()
        return jsonify(data)

    return jsonify(_get_submissions_from_file())

@app.route('/api/submissions/<submission_id>', methods=['GET'])
def get_submission(submission_id):
    """Retorna uma submissão específica"""
    if _read_from_postgres_first():
        submission = _postgres_repositories['form_submission'].get_submission(submission_id)
        if _is_dual_mode() and not submission:
            submission = next((s for s in submissions if str(s['id']) == str(submission_id)), None)
    else:
        submission = next((s for s in submissions if str(s['id']) == str(submission_id)), None)

    if not submission:
        return jsonify({"error": "Submissão não encontrada"}), 404
    return jsonify(submission)

@app.route('/api/submissions/<submission_id>/download', methods=['GET'])
def download_submission(submission_id):
    """Baixa uma submissão em formato JSON"""
    if _read_from_postgres_first():
        submission = _postgres_repositories['form_submission'].get_submission(submission_id)
        if _is_dual_mode() and not submission:
            submission = next((s for s in submissions if str(s['id']) == str(submission_id)), None)
    else:
        submission = next((s for s in submissions if str(s['id']) == str(submission_id)), None)

    if not submission:
        return jsonify({"error": "Submissão não encontrada"}), 404
    
    # Cria arquivo JSON temporário
    filename = f"submission_{submission_id}_{submission['form_id']}.json"
    filepath = f"/tmp/{filename}"
    
    with open(filepath, 'wb') as f:
        f.write(orjson.dumps(submission, option=orjson.OPT_INDENT_2))
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/api/submissions/download-all', methods=['GET'])
def download_all_submissions():
    """Baixa todas as submissões em formato JSON"""
    if _read_from_postgres_first():
        all_submissions = _postgres_repositories['form_submission'].list_all_submissions()
        if _is_dual_mode() and not all_submissions:
            all_submissions = _get_submissions_from_file()
    else:
        all_submissions = _get_submissions_from_file()

    if not all_submissions:
        return jsonify({"error": "Nenhuma submissão encontrada"}), 404
    
    filename = f"all_submissions_{now_brasilia_filename()}.json"
    filepath = f"/tmp/{filename}"
    
    with open(filepath, 'wb') as f:
        f.write(orjson.dumps(all_submissions, option=orjson.OPT_INDENT_2))
    
    return send_file(filepath, as_attachment=True, download_name=filename)


@app.route('/api/students/<student_id>/case-study', methods=['DELETE'])
def delete_case_study_form(student_id):
    """Remove o formulário de estudo de caso sem remover o pré-cadastro do aluno."""
    try:
        student = _get_student_record(student_id)
        if not student:
            return jsonify({"error": "Aluno não encontrado"}), 404

        updates = {'case_study_completed': False}

        if _is_postgres_mode():
            _postgres_repositories['student'].update_student(student_id, updates)
        else:
            _student_storage.update_student(student_id, updates)
            if _is_dual_mode():
                _postgres_repositories['student'].update_student(student_id, updates)

        _delete_form_links_for_pre_registration('cadastro_aluno', student_id)
        return jsonify({"message": "Estudo de Caso removido com sucesso"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/schools/<school_id>/registration', methods=['DELETE'])
def delete_school_registration_form(school_id):
    """Remove o formulário de cadastro da escola sem remover o pré-cadastro da escola."""
    try:
        school = _get_school_record(school_id)
        if not school:
            return jsonify({"error": "Escola não encontrada"}), 404

        updates = {'school_registration_completed': False}

        if _is_postgres_mode():
            _postgres_repositories['school'].update_school(school_id, updates)
        else:
            _school_storage.update_school(school_id, updates)
            if _is_dual_mode():
                _postgres_repositories['school'].update_school(school_id, updates)

        _delete_form_links_for_pre_registration('cadastro_escola', school_id)
        return jsonify({"message": "Cadastro da Escola removido com sucesso"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health():
    """Verifica o status da API"""
    return jsonify({"status": "ok", "message": "Autism.IA API is running"})


# ==================================================================
# AUTH ROUTES
# ==================================================================

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """Autentica usuário e retorna JWT."""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'error': 'Usuário e senha são obrigatórios'}), 400

    user = _auth_storage.authenticate(username=username, password=password)
    if not user:
        _audit_storage.log_event(
            action='LOGIN',
            status_code=401,
            path=request.path,
            method=request.method,
            details={'username': username},
        )
        return jsonify({'error': 'Credenciais inválidas'}), 401

    token = _build_token(user)
    safe_user = _sanitize_current_user(user)

    _audit_storage.log_event(
        action='LOGIN',
        status_code=200,
        path=request.path,
        method=request.method,
        user=safe_user,
    )

    return jsonify(
        {
            'token': token,
            'expires_in_minutes': JWT_EXP_MINUTES,
            'user': safe_user,
        }
    )


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    """Retorna usuário autenticado atual."""
    return jsonify({'user': g.current_user})


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """Logout stateless (cliente deve descartar o token)."""
    _audit_storage.log_event(
        action='LOGOUT',
        status_code=200,
        path=request.path,
        method=request.method,
        user=g.current_user,
    )
    return jsonify({'message': 'Logout realizado com sucesso'})


@app.route('/api/auth/users', methods=['GET'])
def list_users():
    """Lista usuários cadastrados (admin)."""
    return jsonify(_auth_storage.list_users())


@app.route('/api/auth/users', methods=['POST'])
def create_user():
    """Cria novo usuário (admin)."""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    role = (data.get('role') or '').strip().lower()

    if role not in VALID_ROLES:
        return jsonify({'error': 'Perfil inválido. Use admin, editor ou viewer'}), 400

    try:
        user = _auth_storage.create_user(username=username, password=password, role=role)
        return jsonify({'message': 'Usuário criado com sucesso', 'user': user}), 201
    except ValueError as err:
        return jsonify({'error': str(err)}), 400


@app.route('/api/auth/users/<user_id>/role', methods=['PUT'])
def update_user_role(user_id):
    """Atualiza perfil de usuário (admin)."""
    data = request.json or {}
    role = (data.get('role') or '').strip().lower()

    if role not in VALID_ROLES:
        return jsonify({'error': 'Perfil inválido. Use admin, editor ou viewer'}), 400

    try:
        user = _auth_storage.update_user_role(user_id=user_id, role=role)
        if not user:
            return jsonify({'error': 'Usuário não encontrado'}), 404
        return jsonify({'message': 'Perfil atualizado com sucesso', 'user': user})
    except ValueError as err:
        return jsonify({'error': str(err)}), 400


# ==================================================================
# AUDIT ROUTES
# ==================================================================

@app.route('/api/audit/events', methods=['GET'])
def get_audit_events():
    """Lista eventos de auditoria (admin)."""
    limit_raw = request.args.get('limit', '200')
    try:
        limit = int(limit_raw)
    except ValueError:
        return jsonify({'error': 'Parâmetro limit inválido'}), 400

    events = _audit_storage.list_events(limit=limit)
    return jsonify(events)


@app.route('/api/admin/model-usage', methods=['GET'])
def get_model_usage():
    """Retorna uso atual e limites configurados por modelo (admin)."""
    include_history = request.args.get('include_history', '0').strip().lower() in {'1', 'true', 'yes'}
    history_limit_raw = request.args.get('history_limit', '').strip()
    history_limit = None
    if history_limit_raw:
        try:
            history_limit = int(history_limit_raw)
        except ValueError:
            return jsonify({'error': 'Parâmetro history_limit inválido'}), 400

    additional_models = [
        os.getenv('GOOGLE_GENERATION_MODEL', 'gemini-2.5-flash'),
        os.getenv('GOOGLE_EMBEDDING_MODEL', 'gemini-embedding-001'),
    ]
    payload = get_usage_snapshot(
        additional_models=additional_models,
        include_history=include_history,
        history_limit=history_limit,
    )
    return jsonify(payload)


# ==================================================================
# DIARY ROUTES
# ==================================================================

@app.route('/api/diary/students', methods=['GET'])
def get_diary_students():
    """Lista todos os alunos com diários (com resumos)"""
    try:
        _sync_legacy_diary_links()
        summaries = _read_with_optional_fallback('diary', _diary_storage, 'list_all_summaries')
        return jsonify(summaries)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/available-students', methods=['GET'])
def get_available_diary_students():
    """Lista alunos cadastrados que ainda não possuem diário."""
    try:
        _sync_legacy_diary_links()
        students = _list_student_summaries()
        diary_summaries = _read_with_optional_fallback('diary', _diary_storage, 'list_all_summaries')

        used_student_ids = {
            (summary.get('student_id') or '').strip()
            for summary in diary_summaries
            if (summary.get('student_id') or '').strip()
        }
        used_student_names = {
            _normalize_student_name(summary.get('student_name') or '')
            for summary in diary_summaries
            if summary.get('student_name')
        }

        available_students = []
        for student in students:
            student_id = (student.get('id') or '').strip()
            student_name = student.get('name') or ''
            normalized_name = _normalize_student_name(student_name)

            if student_id and student_id in used_student_ids:
                continue
            if normalized_name in used_student_names:
                continue

            available_students.append(student)

        return jsonify(available_students)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/entries/<student_name>', methods=['GET'])
def get_student_entries(student_name):
    """Retorna todas as entradas de diário de um aluno específico"""
    try:
        entries = _read_with_optional_fallback('diary', _diary_storage, 'get_entries_by_student', student_name)
        return jsonify(entries)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/students/<student_name>', methods=['DELETE'])
def delete_student_diary(student_name):
    """Remove todas as entradas de diário de um aluno."""
    try:
        student_id = (request.args.get('student_id') or '').strip() or None
        if _is_postgres_mode():
            removed_count = _postgres_repositories['diary'].delete_entries_by_student(student_name, student_id=student_id)
        else:
            removed_count = _diary_storage.delete_entries_by_student(student_name, student_id=student_id)
            if _is_dual_mode():
                _postgres_repositories['diary'].delete_entries_by_student(student_name, student_id=student_id)

        if removed_count == 0:
            return jsonify({"error": "Diário não encontrado para este aluno"}), 404

        return jsonify({
            "message": "Diário removido com sucesso",
            "removed_entries": removed_count,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/entries', methods=['POST'])
def create_diary_entry():
    """Cria uma nova entrada de diário"""
    data = request.json or {}
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    required_fields = ['student_name', 'teachers', 'diary_date', 'answers']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo obrigatório ausente: {field}"}), 400
    
    try:
        student_id = (data.get('student_id') or '').strip()
        if not student_id:
            return jsonify({"error": "student_id é obrigatório para criar diário"}), 400

        student = _get_student_record(student_id)
        if not student:
            return jsonify({"error": "Aluno selecionado não foi encontrado"}), 400

        student_name = student.get('name') or student.get('studentName') or data.get('student_name') or ''
        if not student_name:
            return jsonify({"error": "Aluno selecionado não possui nome válido"}), 400

        if _is_postgres_mode():
            _postgres_repositories['diary'].link_entries_to_student(student_id, student_name)
        else:
            _diary_storage.link_entries_to_student(student_id, student_name)
            if _is_dual_mode():
                _postgres_repositories['diary'].link_entries_to_student(student_id, student_name)

        status = (data.get('status') or 'final').strip().lower()
        source = (data.get('source') or 'manual').strip().lower()
        parse_warnings = data.get('parse_warnings') or []

        if status not in {'draft', 'final'}:
            return jsonify({"error": "Status inválido. Use draft ou final"}), 400

        if not isinstance(parse_warnings, list):
            return jsonify({"error": "parse_warnings deve ser uma lista"}), 400

        warnings = copy.deepcopy(parse_warnings)
        has_conflict = _read_with_optional_fallback(
            'diary',
            _diary_storage,
            'has_date_conflict',
            student_id,
            student_name,
            data['diary_date'],
        )
        if has_conflict:
            warnings.append('Já existe registro para o mesmo aluno e data')

        if _is_postgres_mode():
            entry = _postgres_repositories['diary'].save_entry(
                student_name=student_name,
                teachers=data['teachers'],
                diary_date=data['diary_date'],
                answers=data['answers'],
                open_obs=data.get('open_obs', ''),
                student_id=student_id,
                status=status,
                source=source,
                parse_warnings=warnings,
            )
        else:
            entry = _diary_storage.save_entry(
                student_name=student_name,
                teachers=data['teachers'],
                diary_date=data['diary_date'],
                answers=data['answers'],
                open_obs=data.get('open_obs', ''),
                student_id=student_id,
                status=status,
                source=source,
                parse_warnings=warnings,
            )
            if _is_dual_mode():
                _postgres_repositories['diary'].save_entry(
                    student_name=student_name,
                    teachers=data['teachers'],
                    diary_date=data['diary_date'],
                    answers=data['answers'],
                    open_obs=data.get('open_obs', ''),
                    student_id=student_id,
                    status=status,
                    source=source,
                    parse_warnings=warnings,
                    entry_id=entry.get('id'),
                    created_at=entry.get('created_at'),
                    updated_at=entry.get('updated_at'),
                )
        return jsonify({
            "message": "Entrada de diário criada com sucesso",
            "entry": entry
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/entries/<entry_id>', methods=['GET'])
def get_diary_entry(entry_id):
    """Retorna uma entrada específica de diário"""
    try:
        entry = _read_with_optional_fallback('diary', _diary_storage, 'get_entry', entry_id)
        if not entry:
            return jsonify({"error": "Entrada não encontrada"}), 404
        return jsonify(entry)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/entries/<entry_id>', methods=['PUT'])
def update_diary_entry(entry_id):
    """Atualiza uma entrada existente de diário"""
    data = request.json or {}
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    try:
        existing_entry = _read_with_optional_fallback('diary', _diary_storage, 'get_entry', entry_id)
        if not existing_entry:
            return jsonify({"error": "Entrada não encontrada"}), 404

        student_id = (data.get('student_id') or existing_entry.get('student_id') or '').strip() or None
        if student_id:
            student = _get_student_record(student_id)
            if not student:
                return jsonify({"error": "Aluno selecionado não foi encontrado"}), 400
            student_name = student.get('name') or student.get('studentName') or existing_entry.get('student_name') or ''
        else:
            student_name = data.get('student_name') or existing_entry.get('student_name') or ''

        teachers = data.get('teachers', existing_entry.get('teachers', []))
        if not isinstance(teachers, list) or len(teachers) == 0:
            return jsonify({"error": "Pelo menos um professor é obrigatório"}), 400

        diary_date = (data.get('diary_date') or existing_entry.get('diary_date') or '').strip()
        if not diary_date:
            return jsonify({"error": "Data do registro é obrigatória"}), 400

        answers = data.get('answers', existing_entry.get('answers', {}))
        if not isinstance(answers, dict) or not answers:
            return jsonify({"error": "Respostas do diário são obrigatórias"}), 400

        open_obs = data.get('open_obs', existing_entry.get('open_obs', ''))
        status = (data.get('status') or existing_entry.get('status') or 'final').strip().lower()
        source = (data.get('source') or existing_entry.get('source') or 'manual').strip().lower()
        parse_warnings = data.get('parse_warnings', existing_entry.get('parse_warnings', []))
        if not isinstance(parse_warnings, list):
            return jsonify({"error": "parse_warnings deve ser uma lista"}), 400

        same_student_entries = _read_with_optional_fallback(
            'diary',
            _diary_storage,
            'get_entries_by_student',
            student_name,
            student_id=student_id,
        )
        for entry in same_student_entries:
            if entry.get('id') == entry_id:
                continue
            if (entry.get('diary_date') or '') == diary_date:
                parse_warnings = [*parse_warnings, 'Já existe registro para o mesmo aluno e data']
                break

        if _is_postgres_mode():
            updated_entry = _postgres_repositories['diary'].update_entry(
                entry_id=entry_id,
                student_name=student_name,
                teachers=teachers,
                diary_date=diary_date,
                answers=answers,
                open_obs=open_obs,
                student_id=student_id,
                status=status,
                source=source,
                parse_warnings=parse_warnings,
            )
        else:
            updated_entry = _diary_storage.update_entry(
                entry_id=entry_id,
                student_name=student_name,
                teachers=teachers,
                diary_date=diary_date,
                answers=answers,
                open_obs=open_obs,
                student_id=student_id,
                status=status,
                source=source,
                parse_warnings=parse_warnings,
            )
            if _is_dual_mode() and updated_entry:
                _postgres_repositories['diary'].update_entry(
                    entry_id=entry_id,
                    student_name=student_name,
                    teachers=teachers,
                    diary_date=diary_date,
                    answers=answers,
                    open_obs=open_obs,
                    student_id=student_id,
                    status=status,
                    source=source,
                    parse_warnings=parse_warnings,
                )
        return jsonify({
            "message": "Entrada atualizada com sucesso",
            "entry": updated_entry,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/entries/<entry_id>', methods=['DELETE'])
def delete_diary_entry(entry_id):
    """Remove uma entrada de diário"""
    try:
        if _is_postgres_mode():
            deleted = _postgres_repositories['diary'].delete_entry(entry_id)
        else:
            deleted = _diary_storage.delete_entry(entry_id)
            if _is_dual_mode() and deleted:
                _postgres_repositories['diary'].delete_entry(entry_id)

        if deleted:
            return jsonify({"message": "Entrada removida com sucesso"})
        return jsonify({"error": "Entrada não encontrada"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diary/last-teachers/<student_name>', methods=['GET'])
def get_last_teachers(student_name):
    """Retorna os professores da última entrada de um aluno (para usar como padrão)"""
    try:
        student_id = (request.args.get('student_id') or '').strip() or None
        teachers = _read_with_optional_fallback('diary', _diary_storage, 'get_last_teachers', student_name, student_id=student_id)
        return jsonify({"teachers": teachers})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _resolve_student(student_id: str, student_name: str):
    if student_id:
        student = _get_student_record(student_id)
        if student:
            resolved_name = student.get('name') or student.get('studentName') or student_name
            return student.get('id'), resolved_name, []
        return None, student_name, ['student_id informado não foi encontrado']

    if student_name:
        matches = _find_students_by_name(student_name)
        if len(matches) == 1:
            match = matches[0]
            resolved_name = match.get('name') or match.get('studentName') or student_name
            return match.get('id'), resolved_name, []
        if len(matches) > 1:
            return None, student_name, ['Nome do aluno ambíguo. Selecione manualmente no preview']
        return None, student_name, ['Aluno não encontrado no cadastro']

    return None, '', ['Aluno não identificado no PDF']


def _validate_commit_entry(entry: Dict):
    status = (entry.get('status') or 'draft').strip().lower()
    if status not in {'draft', 'final'}:
        return False, 'Status inválido. Use draft ou final'

    if status == 'final':
        if not entry.get('diary_date'):
            return False, 'Entrada final exige diary_date'
        if not entry.get('teachers'):
            return False, 'Entrada final exige ao menos um professor'

    return True, ''


@app.route('/api/diary/import/preview', methods=['POST'])
def preview_diary_import():
    """Gera preview de importação de diário a partir de PDF, sem persistir."""
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400

    file = request.files['file']
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Apenas arquivos PDF são permitidos'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        preferred_student_id = (request.form.get('student_id') or '').strip()
        preferred_student_name = (request.form.get('student_name') or '').strip()
        use_ocr_raw = (request.form.get('use_ocr') or 'true').strip().lower()
        use_ocr = use_ocr_raw in {'1', 'true', 'yes', 'y'}
        ocr_lang = (request.form.get('ocr_lang') or 'por').strip() or 'por'
        ocr_force_raw = (request.form.get('ocr_force') or 'false').strip().lower()
        ocr_force = ocr_force_raw in {'1', 'true', 'yes', 'y'}

        parsed = parse_diary_pdf(
            filepath,
            use_ocr=use_ocr,
            ocr_lang=ocr_lang,
            ocr_force=ocr_force,
        )
        preview_entries = []

        for index, raw_entry in enumerate(parsed.get('entries', [])):
            base_student_name = preferred_student_name or raw_entry.get('student_name', '')
            resolved_student_id, resolved_student_name, resolve_warnings = _resolve_student(
                preferred_student_id,
                base_student_name,
            )

            warnings = list(raw_entry.get('parse_warnings', []))
            warnings.extend(resolve_warnings)

            diary_date = raw_entry.get('diary_date', '')
            has_conflict = _read_with_optional_fallback(
                'diary',
                _diary_storage,
                'has_date_conflict',
                resolved_student_id,
                resolved_student_name,
                diary_date,
            ) if diary_date else False
            if has_conflict:
                warnings.append('Já existe registro para este aluno na data informada')

            preview_entries.append({
                'preview_id': f'preview_{index + 1}',
                'student_id': resolved_student_id,
                'student_name': resolved_student_name,
                'diary_date': diary_date,
                'teachers': raw_entry.get('teachers', []),
                'answers': raw_entry.get('answers', {}),
                'open_obs': raw_entry.get('open_obs', ''),
                'status': raw_entry.get('status', 'draft'),
                'source': 'pdf_import',
                'parse_warnings': warnings,
            })

        if not preview_entries:
            preview_entries = [{
                'preview_id': 'preview_1',
                'student_id': None,
                'student_name': preferred_student_name,
                'diary_date': '',
                'teachers': [],
                'answers': {},
                'open_obs': '',
                'status': 'draft',
                'source': 'pdf_import',
                'parse_warnings': ['Nenhum bloco diário detectado no PDF'],
            }]

        return jsonify({
            'message': 'Preview gerado com sucesso',
            'entries': preview_entries,
            'metadata': parsed.get('metadata', {}),
            'warnings': parsed.get('warnings', []),
            'question_keys': list(QUESTION_PATTERNS.keys()),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route('/api/diary/import/commit', methods=['POST'])
def commit_diary_import():
    """Persiste entradas revisadas do preview de importação."""
    data = request.json or {}
    entries = data.get('entries') or []
    if not isinstance(entries, list) or not entries:
        return jsonify({'error': 'Nenhuma entrada fornecida para importação'}), 400

    saved_entries = []

    try:
        for entry in entries:
            student_id = (entry.get('student_id') or '').strip() or None
            student_name = (entry.get('student_name') or '').strip()

            resolved_student_id, resolved_student_name, resolve_warnings = _resolve_student(student_id, student_name)
            parse_warnings = list(entry.get('parse_warnings') or [])
            parse_warnings.extend(resolve_warnings)

            normalized_entry = {
                'student_id': resolved_student_id,
                'student_name': resolved_student_name,
                'teachers': entry.get('teachers') or [],
                'diary_date': (entry.get('diary_date') or '').strip(),
                'answers': entry.get('answers') or {},
                'open_obs': entry.get('open_obs') or '',
                'status': (entry.get('status') or 'draft').strip().lower(),
                'source': 'pdf_import',
                'parse_warnings': parse_warnings,
            }

            is_valid, error_message = _validate_commit_entry(normalized_entry)
            if not is_valid:
                return jsonify({'error': error_message, 'entry': normalized_entry}), 400

            has_conflict = _read_with_optional_fallback(
                'diary',
                _diary_storage,
                'has_date_conflict',
                normalized_entry['student_id'],
                normalized_entry['student_name'],
                normalized_entry['diary_date'],
            )
            if has_conflict:
                normalized_entry['parse_warnings'].append('Já existe registro para o mesmo aluno e data')

            if _is_postgres_mode():
                saved = _postgres_repositories['diary'].save_entry(
                    student_name=normalized_entry['student_name'],
                    teachers=normalized_entry['teachers'],
                    diary_date=normalized_entry['diary_date'],
                    answers=normalized_entry['answers'],
                    open_obs=normalized_entry['open_obs'],
                    student_id=normalized_entry['student_id'],
                    status=normalized_entry['status'],
                    source=normalized_entry['source'],
                    parse_warnings=normalized_entry['parse_warnings'],
                )
            else:
                saved = _diary_storage.save_entry(
                    student_name=normalized_entry['student_name'],
                    teachers=normalized_entry['teachers'],
                    diary_date=normalized_entry['diary_date'],
                    answers=normalized_entry['answers'],
                    open_obs=normalized_entry['open_obs'],
                    student_id=normalized_entry['student_id'],
                    status=normalized_entry['status'],
                    source=normalized_entry['source'],
                    parse_warnings=normalized_entry['parse_warnings'],
                )
                if _is_dual_mode():
                    _postgres_repositories['diary'].save_entry(
                        student_name=normalized_entry['student_name'],
                        teachers=normalized_entry['teachers'],
                        diary_date=normalized_entry['diary_date'],
                        answers=normalized_entry['answers'],
                        open_obs=normalized_entry['open_obs'],
                        student_id=normalized_entry['student_id'],
                        status=normalized_entry['status'],
                        source=normalized_entry['source'],
                        parse_warnings=normalized_entry['parse_warnings'],
                        entry_id=saved.get('id'),
                        created_at=saved.get('created_at'),
                        updated_at=saved.get('updated_at'),
                    )
            saved_entries.append(saved)

        return jsonify({
            'message': 'Importação concluída com sucesso',
            'saved_count': len(saved_entries),
            'entries': saved_entries,
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================================================================
# PDI ROUTES
# ==================================================================

@app.route('/api/pdi/all', methods=['GET'])
def get_all_pdis():
    """Lista todos os PDIs com informações resumidas"""
    try:
        _sync_legacy_pdi_links()
        pdis = _read_with_optional_fallback('pdi', _pdi_storage, 'list_all_pdis')
        return jsonify(pdis)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pdi/available-students', methods=['GET'])
def get_available_pdi_students():
    """Lista alunos cadastrados que ainda não possuem PDI."""
    try:
        _sync_legacy_pdi_links()
        students = _list_student_summaries()
        pdis = _read_with_optional_fallback('pdi', _pdi_storage, 'list_all_pdis')

        used_student_ids = {
            (pdi.get('student_id') or '').strip()
            for pdi in pdis
            if (pdi.get('student_id') or '').strip()
        }
        used_student_names = {
            _normalize_student_name(pdi.get('student_name') or '')
            for pdi in pdis
            if pdi.get('student_name')
        }

        available_students = []
        for student in students:
            student_id = (student.get('id') or '').strip()
            student_name = student.get('name') or ''
            normalized_name = _normalize_student_name(student_name)

            if student_id and student_id in used_student_ids:
                continue
            if normalized_name in used_student_names:
                continue

            available_students.append(student)

        return jsonify(available_students)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pdi/<student_name>', methods=['GET'])
def get_pdi_by_student(student_name):
    """Retorna o PDI de um aluno específico"""
    try:
        _sync_legacy_pdi_links()
        student_id = (request.args.get('student_id') or '').strip() or None
        pdi = _read_with_optional_fallback('pdi', _pdi_storage, 'get_pdi_by_student', student_name, student_id=student_id)
        if not pdi:
            return jsonify({"error": "PDI não encontrado para este aluno"}), 404
        return jsonify(pdi)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pdi/id/<pdi_id>', methods=['GET'])
def get_pdi_by_id(pdi_id):
    """Retorna um PDI específico por ID"""
    try:
        _sync_legacy_pdi_links()
        pdi = _read_with_optional_fallback('pdi', _pdi_storage, 'get_pdi', pdi_id)
        if not pdi:
            return jsonify({"error": "PDI não encontrado"}), 404
        return jsonify(pdi)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pdi', methods=['POST'])
def create_pdi():
    """Cria um novo PDI"""
    data = request.json
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    required_fields = ['student_id', 'student_name', 'birth_date', 'guardians', 'diagnosis', 'class', 'teachers', 'trimesters']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo obrigatório ausente: {field}"}), 400
    
    # Validar que há pelo menos 1 guardian e 1 teacher
    if not data['guardians'] or len(data['guardians']) == 0:
        return jsonify({"error": "Pelo menos uma filiação é obrigatória"}), 400
    
    if not data['teachers'] or len(data['teachers']) == 0:
        return jsonify({"error": "Pelo menos um docente é obrigatório"}), 400
    
    try:
        _sync_legacy_pdi_links()
        student_id = (data.get('student_id') or '').strip()
        if not student_id:
            return jsonify({"error": "student_id é obrigatório para criar PDI"}), 400

        student = _get_student_record(student_id)
        if not student:
            return jsonify({"error": "Aluno selecionado não foi encontrado"}), 400

        student_name = student.get('name') or student.get('studentName') or data.get('student_name') or ''
        if not student_name:
            return jsonify({"error": "Aluno selecionado não possui nome válido"}), 400

        if _is_postgres_mode():
            _postgres_repositories['pdi'].link_pdis_to_student(student_id, student_name)
        else:
            _pdi_storage.link_pdis_to_student(student_id, student_name)
            if _is_dual_mode():
                _postgres_repositories['pdi'].link_pdis_to_student(student_id, student_name)

        has_pdi = _read_with_optional_fallback(
            'pdi',
            _pdi_storage,
            'has_pdi_for_student',
            student_name=student_name,
            student_id=student_id,
        )
        if has_pdi:
            return jsonify({"error": "Este aluno já possui um PDI cadastrado"}), 400

        if _is_postgres_mode():
            pdi = _postgres_repositories['pdi'].save_pdi(
                student_name=student_name,
                birth_date=data['birth_date'],
                guardians=data['guardians'],
                diagnosis=data['diagnosis'],
                class_name=data['class'],
                teachers=data['teachers'],
                trimesters=data['trimesters'],
                student_id=student_id,
            )
        else:
            pdi = _pdi_storage.save_pdi(
                student_name=student_name,
                birth_date=data['birth_date'],
                guardians=data['guardians'],
                diagnosis=data['diagnosis'],
                class_name=data['class'],
                teachers=data['teachers'],
                trimesters=data['trimesters'],
                student_id=student_id,
            )
            if _is_dual_mode():
                _postgres_repositories['pdi'].save_pdi(
                    student_name=student_name,
                    birth_date=data['birth_date'],
                    guardians=data['guardians'],
                    diagnosis=data['diagnosis'],
                    class_name=data['class'],
                    teachers=data['teachers'],
                    trimesters=data['trimesters'],
                    student_id=student_id,
                    pdi_id=pdi.get('id'),
                    created_at=pdi.get('created_at'),
                    updated_at=pdi.get('updated_at'),
                )
        return jsonify({
            "message": "PDI criado com sucesso",
            "pdi": pdi
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pdi/<pdi_id>', methods=['PUT'])
def update_pdi(pdi_id):
    """Atualiza um PDI existente"""
    data = request.json
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    required_fields = ['student_id', 'student_name', 'birth_date', 'guardians', 'diagnosis', 'class', 'teachers', 'trimesters']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo obrigatório ausente: {field}"}), 400
    
    # Validar que há pelo menos 1 guardian e 1 teacher
    if not data['guardians'] or len(data['guardians']) == 0:
        return jsonify({"error": "Pelo menos uma filiação é obrigatória"}), 400
    
    if not data['teachers'] or len(data['teachers']) == 0:
        return jsonify({"error": "Pelo menos um docente é obrigatório"}), 400
    
    try:
        _sync_legacy_pdi_links()
        existing_pdi = _read_with_optional_fallback('pdi', _pdi_storage, 'get_pdi', pdi_id)
        if not existing_pdi:
            return jsonify({"error": "PDI não encontrado"}), 404

        student_id = (data.get('student_id') or '').strip()
        if not student_id:
            return jsonify({"error": "student_id é obrigatório para atualizar PDI"}), 400

        student = _get_student_record(student_id)
        if not student:
            return jsonify({"error": "Aluno selecionado não foi encontrado"}), 400

        student_name = student.get('name') or student.get('studentName') or data.get('student_name') or ''
        if not student_name:
            return jsonify({"error": "Aluno selecionado não possui nome válido"}), 400

        has_pdi = _read_with_optional_fallback(
            'pdi',
            _pdi_storage,
            'has_pdi_for_student',
            student_name=student_name,
            student_id=student_id,
            exclude_pdi_id=pdi_id,
        )
        if has_pdi:
            return jsonify({"error": "Este aluno já possui um PDI cadastrado"}), 400

        if _is_postgres_mode():
            pdi = _postgres_repositories['pdi'].update_pdi(
                pdi_id=pdi_id,
                student_name=student_name,
                birth_date=data['birth_date'],
                guardians=data['guardians'],
                diagnosis=data['diagnosis'],
                class_name=data['class'],
                teachers=data['teachers'],
                trimesters=data['trimesters'],
                student_id=student_id,
            )
        else:
            pdi = _pdi_storage.update_pdi(
                pdi_id=pdi_id,
                student_name=student_name,
                birth_date=data['birth_date'],
                guardians=data['guardians'],
                diagnosis=data['diagnosis'],
                class_name=data['class'],
                teachers=data['teachers'],
                trimesters=data['trimesters'],
                student_id=student_id,
            )
            if _is_dual_mode() and pdi:
                _postgres_repositories['pdi'].update_pdi(
                    pdi_id=pdi_id,
                    student_name=student_name,
                    birth_date=data['birth_date'],
                    guardians=data['guardians'],
                    diagnosis=data['diagnosis'],
                    class_name=data['class'],
                    teachers=data['teachers'],
                    trimesters=data['trimesters'],
                    student_id=student_id,
                )
        
        return jsonify({
            "message": "PDI atualizado com sucesso",
            "pdi": pdi
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pdi/<pdi_id>', methods=['DELETE'])
def delete_pdi(pdi_id):
    """Remove um PDI"""
    try:
        if _is_postgres_mode():
            deleted = _postgres_repositories['pdi'].delete_pdi(pdi_id)
        else:
            deleted = _pdi_storage.delete_pdi(pdi_id)
            if _is_dual_mode() and deleted:
                _postgres_repositories['pdi'].delete_pdi(pdi_id)

        if deleted:
            return jsonify({"message": "PDI removido com sucesso"})
        return jsonify({"error": "PDI não encontrado"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================================================================
# SCHOOL ROUTES
# ==================================================================

@app.route('/api/schools', methods=['GET'])
def get_all_schools():
    """Lista todas as escolas cadastradas"""
    try:
        if _read_from_postgres_first():
            schools_pg = _postgres_repositories['school'].list_all_schools()
            if schools_pg or _is_postgres_mode():
                return jsonify(schools_pg)
        schools = _school_storage.list_all_schools()
        return jsonify(schools)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/schools/<school_id>', methods=['GET'])
def get_school(school_id):
    """Retorna uma escola específica por ID"""
    try:
        if _read_from_postgres_first():
            school_pg = _postgres_repositories['school'].get_school(school_id)
            if school_pg or _is_postgres_mode():
                if not school_pg:
                    return jsonify({"error": "Escola não encontrada"}), 404
                return jsonify(school_pg)

        school = _school_storage.get_school(school_id)
        if not school:
            return jsonify({"error": "Escola não encontrada"}), 404
        return jsonify(school)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/schools', methods=['POST'])
def create_school():
    """Cria um novo cadastro de escola"""
    data = request.json
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    try:
        if _is_postgres_mode():
            school = _postgres_repositories['school'].create_school(data)
            return jsonify({
                "message": "Escola cadastrada com sucesso",
                "school": school
            }), 201

        school = _school_storage.create_school(data)

        if _is_dual_mode():
            _postgres_repositories['school'].create_school(
                data,
                school_id=school.get('id'),
                created_at=school.get('created_at'),
                updated_at=school.get('updated_at'),
            )

        return jsonify({
            "message": "Escola cadastrada com sucesso",
            "school": school
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/schools/<school_id>', methods=['PUT'])
def update_school(school_id):
    """Atualiza um cadastro de escola existente"""
    data = request.json
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400
    
    try:
        if _is_postgres_mode():
            school = _postgres_repositories['school'].update_school(school_id, data)

            if not school:
                return jsonify({"error": "Escola não encontrada"}), 404

            return jsonify({
                "message": "Escola atualizada com sucesso",
                "school": school
            })

        school = _school_storage.update_school(school_id, data)

        if _is_dual_mode() and school:
            _postgres_repositories['school'].update_school(school_id, data)
        
        if not school:
            return jsonify({"error": "Escola não encontrada"}), 404
        
        return jsonify({
            "message": "Escola atualizada com sucesso",
            "school": school
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/schools/<school_id>', methods=['DELETE'])
def delete_school(school_id):
    """Remove um cadastro de escola"""
    try:
        if _is_postgres_mode():
            if _postgres_repositories['school'].delete_school(school_id):
                _delete_form_links_for_pre_registration('cadastro_escola', school_id)
                return jsonify({"message": "Escola removida com sucesso"})
            return jsonify({"error": "Escola não encontrada"}), 404

        if _school_storage.delete_school(school_id):
            _delete_form_links_for_pre_registration('cadastro_escola', school_id)
            if _is_dual_mode():
                _postgres_repositories['school'].delete_school(school_id)
            return jsonify({"message": "Escola removida com sucesso"})
        return jsonify({"error": "Escola não encontrada"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================================================================
# STUDENT ROUTES
# ==================================================================

@app.route('/api/students', methods=['GET'])
def get_all_students():
    """Lista todos os alunos cadastrados"""
    try:
        if _read_from_postgres_first():
            students_pg = _postgres_repositories['student'].list_all_students()
            if students_pg or _is_postgres_mode():
                return jsonify(students_pg)
        students = _student_storage.list_all_students()
        return jsonify(students)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/students/<student_id>', methods=['GET'])
def get_student(student_id):
    """Retorna um aluno específico por ID"""
    try:
        if _read_from_postgres_first():
            student_pg = _postgres_repositories['student'].get_student(student_id)
            if student_pg or _is_postgres_mode():
                if not student_pg:
                    return jsonify({"error": "Aluno não encontrado"}), 404
                return jsonify(student_pg)

        student = _student_storage.get_student(student_id)
        if not student:
            return jsonify({"error": "Aluno não encontrado"}), 404
        return jsonify(student)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/students', methods=['POST'])
def create_student():
    """Cria um novo cadastro de aluno"""
    data = request.json
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    school_id = str(data.get('school_id', '')).strip()
    if not school_id:
        return jsonify({"error": "Selecione uma escola cadastrada para o aluno"}), 400

    school = _get_school_record(school_id)
    if not school:
        return jsonify({"error": "Escola selecionada não foi encontrada"}), 400

    teacher_ids_raw = data.get('teacher_ids')
    teacher_ids: List[str] = []
    if isinstance(teacher_ids_raw, list):
        teacher_ids = [str(value).strip() for value in teacher_ids_raw if str(value).strip()]
    elif teacher_ids_raw:
        teacher_ids = [str(teacher_ids_raw).strip()]

    teacher_id_legacy = str(data.get('teacher_id', '')).strip()
    if teacher_id_legacy and teacher_id_legacy not in teacher_ids:
        teacher_ids.append(teacher_id_legacy)

    if not teacher_ids:
        return jsonify({"error": "Selecione ao menos um docente cadastrado para o aluno"}), 400

    resolved_teacher_names: List[str] = []
    for teacher_id in teacher_ids:
        teacher = _get_teacher_record(teacher_id)
        if not teacher:
            return jsonify({"error": "Docente selecionado não foi encontrado"}), 400
        resolved_teacher_names.append(teacher.get('name', ''))

    data['teacher_ids'] = teacher_ids
    data['teachers'] = resolved_teacher_names
    data['teacher_id'] = teacher_ids[0]
    data['teacher_name'] = resolved_teacher_names[0] if resolved_teacher_names else ''

    data['school_name'] = school.get('name', '')
    
    try:
        if _is_postgres_mode():
            student = _postgres_repositories['student'].create_student(data)
            return jsonify({
                "message": "Aluno cadastrado com sucesso",
                "student": student
            }), 201

        student = _student_storage.create_student(data)

        if _is_dual_mode():
            _postgres_repositories['student'].create_student(
                data,
                student_id=student.get('id'),
                created_at=student.get('created_at'),
                updated_at=student.get('updated_at'),
            )

        return jsonify({
            "message": "Aluno cadastrado com sucesso",
            "student": student
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/students/<student_id>', methods=['PUT'])
def update_student(student_id):
    """Atualiza um cadastro de aluno existente"""
    data = request.json
    
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    if 'school_id' in data:
        school_id = str(data.get('school_id', '')).strip()
        if not school_id:
            return jsonify({"error": "Selecione uma escola cadastrada para o aluno"}), 400
        school = _get_school_record(school_id)
        if not school:
            return jsonify({"error": "Escola selecionada não foi encontrada"}), 400
        data['school_name'] = school.get('name', '')

    if 'teacher_ids' in data or 'teacher_id' in data:
        teacher_ids_raw = data.get('teacher_ids')
        teacher_ids: List[str] = []
        if isinstance(teacher_ids_raw, list):
            teacher_ids = [str(value).strip() for value in teacher_ids_raw if str(value).strip()]
        elif teacher_ids_raw:
            teacher_ids = [str(teacher_ids_raw).strip()]

        teacher_id_legacy = str(data.get('teacher_id', '')).strip()
        if teacher_id_legacy and teacher_id_legacy not in teacher_ids:
            teacher_ids.append(teacher_id_legacy)

        if not teacher_ids:
            return jsonify({"error": "Selecione ao menos um docente cadastrado para o aluno"}), 400

        resolved_teacher_names: List[str] = []
        for teacher_id in teacher_ids:
            teacher = _get_teacher_record(teacher_id)
            if not teacher:
                return jsonify({"error": "Docente selecionado não foi encontrado"}), 400
            resolved_teacher_names.append(teacher.get('name', ''))

        data['teacher_ids'] = teacher_ids
        data['teachers'] = resolved_teacher_names
        data['teacher_id'] = teacher_ids[0]
        data['teacher_name'] = resolved_teacher_names[0] if resolved_teacher_names else ''
    
    try:
        if _is_postgres_mode():
            student = _postgres_repositories['student'].update_student(student_id, data)

            if not student:
                return jsonify({"error": "Aluno não encontrado"}), 404

            return jsonify({
                "message": "Aluno atualizado com sucesso",
                "student": student
            })

        student = _student_storage.update_student(student_id, data)

        if _is_dual_mode() and student:
            _postgres_repositories['student'].update_student(student_id, data)
        
        if not student:
            return jsonify({"error": "Aluno não encontrado"}), 404
        
        return jsonify({
            "message": "Aluno atualizado com sucesso",
            "student": student
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/students/<student_id>', methods=['DELETE'])
def delete_student(student_id):
    """Remove um cadastro de aluno"""
    try:
        if _is_postgres_mode():
            if _postgres_repositories['student'].delete_student(student_id):
                _delete_form_links_for_pre_registration('cadastro_aluno', student_id)
                return jsonify({"message": "Aluno removido com sucesso"})
            return jsonify({"error": "Aluno não encontrado"}), 404

        if _student_storage.delete_student(student_id):
            _delete_form_links_for_pre_registration('cadastro_aluno', student_id)
            if _is_dual_mode():
                _postgres_repositories['student'].delete_student(student_id)
            return jsonify({"message": "Aluno removido com sucesso"})
        return jsonify({"error": "Aluno não encontrado"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================================================================
# TEACHER ROUTES
# ==================================================================

@app.route('/api/teachers', methods=['GET'])
def get_all_teachers():
    """Lista todos os docentes cadastrados."""
    try:
        if _read_from_postgres_first():
            teachers_pg = _postgres_repositories['teacher'].list_all_teachers()
            if teachers_pg or _is_postgres_mode():
                return jsonify(teachers_pg)
        teachers = _teacher_storage.list_all_teachers()
        return jsonify(teachers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/teachers/<teacher_id>', methods=['GET'])
def get_teacher(teacher_id):
    """Retorna um docente específico por ID."""
    try:
        if _read_from_postgres_first():
            teacher_pg = _postgres_repositories['teacher'].get_teacher(teacher_id)
            if teacher_pg or _is_postgres_mode():
                if not teacher_pg:
                    return jsonify({"error": "Docente não encontrado"}), 404
                return jsonify(teacher_pg)

        teacher = _teacher_storage.get_teacher(teacher_id)
        if not teacher:
            return jsonify({"error": "Docente não encontrado"}), 404
        return jsonify(teacher)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/teachers', methods=['POST'])
def create_teacher():
    """Cria um novo cadastro de docente."""
    data = request.json

    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    if not str(data.get('name', '')).strip():
        return jsonify({"error": "Nome do docente é obrigatório"}), 400

    school_id = str(data.get('school_id', '')).strip()
    if not school_id:
        return jsonify({"error": "Selecione uma escola cadastrada para o docente"}), 400

    school = _get_school_record(school_id)
    if not school:
        return jsonify({"error": "Escola selecionada não foi encontrada"}), 400

    data['school_name'] = school.get('name', '')

    try:
        if _is_postgres_mode():
            teacher = _postgres_repositories['teacher'].create_teacher(data)
            return jsonify({
                "message": "Docente cadastrado com sucesso",
                "teacher": teacher
            }), 201

        teacher = _teacher_storage.create_teacher(data)

        if _is_dual_mode():
            _postgres_repositories['teacher'].create_teacher(
                data,
                teacher_id=teacher.get('id'),
                created_at=teacher.get('created_at'),
                updated_at=teacher.get('updated_at'),
            )

        return jsonify({
            "message": "Docente cadastrado com sucesso",
            "teacher": teacher
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/teachers/<teacher_id>', methods=['PUT'])
def update_teacher(teacher_id):
    """Atualiza um cadastro de docente existente."""
    data = request.json

    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    if not str(data.get('name', '')).strip():
        return jsonify({"error": "Nome do docente é obrigatório"}), 400

    school_id = str(data.get('school_id', '')).strip()
    if not school_id:
        return jsonify({"error": "Selecione uma escola cadastrada para o docente"}), 400

    school = _get_school_record(school_id)
    if not school:
        return jsonify({"error": "Escola selecionada não foi encontrada"}), 400

    data['school_name'] = school.get('name', '')

    try:
        if _is_postgres_mode():
            teacher = _postgres_repositories['teacher'].update_teacher(teacher_id, data)

            if not teacher:
                return jsonify({"error": "Docente não encontrado"}), 404

            return jsonify({
                "message": "Docente atualizado com sucesso",
                "teacher": teacher
            })

        teacher = _teacher_storage.update_teacher(teacher_id, data)

        if _is_dual_mode() and teacher:
            _postgres_repositories['teacher'].update_teacher(teacher_id, data)

        if not teacher:
            return jsonify({"error": "Docente não encontrado"}), 404

        return jsonify({
            "message": "Docente atualizado com sucesso",
            "teacher": teacher
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/teachers/<teacher_id>', methods=['DELETE'])
def delete_teacher(teacher_id):
    """Remove um cadastro de docente."""
    try:
        if _is_postgres_mode():
            if _postgres_repositories['teacher'].delete_teacher(teacher_id):
                return jsonify({"message": "Docente removido com sucesso"})
            return jsonify({"error": "Docente não encontrado"}), 404

        if _teacher_storage.delete_teacher(teacher_id):
            if _is_dual_mode():
                _postgres_repositories['teacher'].delete_teacher(teacher_id)
            return jsonify({"message": "Docente removido com sucesso"})
        return jsonify({"error": "Docente não encontrado"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================================================================
# RAG ROUTES
# ==================================================================

@app.route('/api/rag/upload', methods=['POST'])
def upload_document():
    """Upload e indexação de PDF no vector store"""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503

    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files['file']
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Apenas arquivos PDF são permitidos"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        metadata_raw = request.form.get('metadata', '{}')
        metadata = json.loads(metadata_raw)
        metadata['file_name'] = filename

        from document_processor import extract_text_from_pdf, split_text_into_chunks, generate_embeddings
        text = extract_text_from_pdf(filepath)
        if not text:
            return jsonify({"error": "Não foi possível extrair texto do PDF"}), 400

        chunks = split_text_into_chunks(text)
        embeddings = [
            generate_embeddings(
                chunk,
                os.getenv('GOOGLE_API_KEY'),
                task_type="RETRIEVAL_DOCUMENT",
                operation='rag_upload_document_embedding',
            )
            for chunk in chunks
        ]
        doc_id = engine.vector_store.add_documents(chunks, embeddings, metadata)

        with open(filepath, 'rb') as uploaded_file:
            file_bytes = uploaded_file.read()

        object_key = f'{doc_id}.pdf'
        _object_storage.upload_file(
            bucket=RAG_STORAGE_BUCKET,
            object_key=object_key,
            content=file_bytes,
            content_type='application/pdf',
        )

        _upsert_object_metadata(
            doc_type=RAG_DOC_TYPE,
            reference_id=doc_id,
            bucket=RAG_STORAGE_BUCKET,
            object_key=object_key,
            original_filename=filename,
            mime_type='application/pdf',
            size_bytes=len(file_bytes),
            extra={
                'student_name': metadata.get('student_name', ''),
                'school': metadata.get('school', ''),
            },
        )

        filepath = None

        return jsonify({
            "message": "Documento indexado com sucesso",
            "doc_id": doc_id,
            "chunks_count": len(chunks),
            "file_name": filename
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)


@app.route('/api/rag/students', methods=['GET'])
def get_rag_students():
    """Lista estudantes únicos agrupados por nome + escola"""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503
    try:
        students = engine.vector_store.list_students()
        return jsonify(students)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/documents', methods=['GET'])
def get_rag_documents():
    """Lista documentos indexados no vector store"""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503
    try:
        docs = engine.vector_store.list_documents()
        return jsonify(docs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/documents/<doc_id>', methods=['DELETE'])
def delete_rag_document(doc_id):
    """Remove documento do vector store"""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503
    try:
        engine.vector_store.delete_document(doc_id)

        file_meta = _get_object_metadata(RAG_DOC_TYPE, doc_id)
        object_key = file_meta.get('object_key') if file_meta else f'{doc_id}.pdf'
        _object_storage.delete_file(RAG_STORAGE_BUCKET, object_key)
        _delete_object_metadata(RAG_DOC_TYPE, doc_id)

        return jsonify({"message": "Documento removido com sucesso"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/documents/<doc_id>/download', methods=['GET'])
def download_rag_document(doc_id):
    """Baixa o PDF original de um documento indexado no RAG."""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503

    doc = engine.vector_store.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Documento não encontrado"}), 404

    file_meta = _get_object_metadata(RAG_DOC_TYPE, doc_id)
    object_key = file_meta.get('object_key') if file_meta else f'{doc_id}.pdf'

    try:
        file_bytes = _object_storage.download_file(RAG_STORAGE_BUCKET, object_key)
    except FileNotFoundError:
        return jsonify({"error": "Arquivo original não disponível para download"}), 404

    download_name = doc.get('file_name') or f'{doc_id}.pdf'
    return send_file(
        BytesIO(file_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=download_name,
    )


@app.route('/api/rag/reindex', methods=['POST'])
def reindex_documents():
    """Re-embeda todos os chunks existentes no ChromaDB com as configurações atuais.

    Necessário após atualizar chunk_size, overlap ou task_type dos embeddings.
    Lê os textos já armazenados (não precisa dos PDFs originais), deleta os
    embeddings antigos e reindexa com RETRIEVAL_DOCUMENT task_type.
    """
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503

    from document_processor import generate_embeddings

    try:
        collection = engine.vector_store.collection
        total = collection.count()
        if total == 0:
            return jsonify({"message": "Nenhum documento para reindexar", "reindexed": 0})

        # Buscar TODOS os chunks (textos + metadados + ids)
        all_data = collection.get(include=["documents", "metadatas", "embeddings"])
        ids = all_data["ids"]
        documents = all_data["documents"]
        metadatas = all_data["metadatas"]

        google_api_key = os.getenv('GOOGLE_API_KEY')

        # Re-gerar embeddings com task_type correto
        new_embeddings = []
        for chunk in documents:
            emb = generate_embeddings(
                chunk,
                google_api_key,
                task_type="RETRIEVAL_DOCUMENT",
                operation='rag_reindex_document_embedding',
            )
            new_embeddings.append(emb)

        # Atualizar embeddings no ChromaDB (upsert preserva textos e metadados)
        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=new_embeddings,
            metadatas=metadatas,
        )

        return jsonify({
            "message": "Reindexação concluída com sucesso",
            "reindexed": len(ids),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/chat', methods=['POST'])
def rag_chat():
    """Chat com contexto RAG"""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503

    data = request.json or {}
    message = data.get('message', '').strip()
    if not message:
        return jsonify({"error": "Mensagem não fornecida"}), 400

    try:
        student_id = data.get('student_id', '').strip()
        student_name = data.get('student_name', '').strip()
        school = data.get('school', '').strip()
        selected_sources = _parse_selected_sources(data.get('selected_sources'))
        include_vector_documents = bool(selected_sources.get('vector_documents'))
        chat_prompt_data = _prompt_storage.get_chat_prompt()
        context_filter = None
        if include_vector_documents and student_name and school:
            context_filter = {"$and": [{"student_name": {"$eq": student_name}}, {"school": {"$eq": school}}]}
        elif include_vector_documents and student_name:
            context_filter = {"student_name": {"$eq": student_name}}

        integrated_context = ''
        if student_name:
            integrated_context = _build_integrated_student_context(
                student_name=student_name,
                student_id=student_id,
                max_diary_entries=3,
                selected_sources=selected_sources,
            )

        session_id = data.get('session_id') or (f"{student_name}__{school}" if student_name else 'default')

        result = engine.query(
            message=message,
            session_id=session_id,
            context_filter=context_filter,
            include_vector_documents=include_vector_documents,
            integrated_context=integrated_context,
            system_prompt_chat=chat_prompt_data['prompt'],
        )
        result['selected_sources'] = selected_sources
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/generate-pei', methods=['POST'])
def generate_pei():
    """Gera PEI estruturado completo e salva como PDF"""
    engine = get_rag_engine()
    if engine is None:
        return jsonify({"error": "GOOGLE_API_KEY não configurada no .env"}), 503

    started_at = time.perf_counter()

    data = request.json or {}
    student_id = data.get('student_id', '').strip()
    student_name = data.get('student_name', '').strip()
    school = data.get('school', '').strip()
    selected_sources = _parse_selected_sources(data.get('selected_sources'))

    if not student_name or not school:
        return jsonify({"error": "Nome do estudante e escola são obrigatórios"}), 400

    try:
        pei_prompt_data = _prompt_storage.get_pei_prompt()
        context_filter = None
        include_vector_documents = bool(selected_sources.get('vector_documents'))
        if include_vector_documents:
            strict_filter = {
                "$and": [
                    {"student_name": {"$eq": student_name}},
                    {"school": {"$eq": school}},
                ]
            }
            context_filter = strict_filter

            docs_summary = _summarize_vector_documents_for_student(engine, student_name, school)
            if docs_summary.get('document_count', 0) == 0:
                context_filter = {"student_name": {"$eq": student_name}}

        integrated_context = _build_integrated_student_context(
            student_name=student_name,
            student_id=student_id,
            selected_sources=selected_sources,
        )
        result = engine.generate_pei(
            student_name=student_name,
            school=school,
            additional_info=data.get('additional_info', ''),
            system_prompt_pei=pei_prompt_data['prompt'],
            context_filter=context_filter,
            include_vector_documents=include_vector_documents,
            integrated_context=integrated_context,
        )
        markdown_text = result['pei']

        # Gerar PDF
        from pdf_generator import markdown_to_pdf
        safe_name = student_name.replace(' ', '_')
        pdf_filename = f"PEI_{safe_name}_{now_brasilia_filename()}.pdf"
        temp_pdf_path = os.path.join(UPLOAD_FOLDER, pdf_filename)
        markdown_to_pdf(markdown_text, student_name, school, temp_pdf_path)

        # Salvar no índice
        entry = _pei_storage.save(
            student_name=student_name,
            school=school,
            markdown_text=markdown_text,
            pdf_path=temp_pdf_path,
            student_id=student_id or None,
            generated_by_user_id=(getattr(g, 'current_user', {}) or {}).get('id'),
            generated_by_username=(getattr(g, 'current_user', {}) or {}).get('username'),
        )

        with open(temp_pdf_path, 'rb') as generated_pdf:
            pdf_bytes = generated_pdf.read()

        pei_object_key = entry.get('pdf_filename') or f"{entry['id']}.pdf"
        _object_storage.upload_file(
            bucket=PEI_STORAGE_BUCKET,
            object_key=pei_object_key,
            content=pdf_bytes,
            content_type='application/pdf',
        )

        _upsert_object_metadata(
            doc_type=PEI_DOC_TYPE,
            reference_id=entry['id'],
            bucket=PEI_STORAGE_BUCKET,
            object_key=pei_object_key,
            original_filename=entry.get('pdf_filename') or pdf_filename,
            mime_type='application/pdf',
            size_bytes=len(pdf_bytes),
            extra={
                'student_name': student_name,
                'school': school,
            },
        )

        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        usage = result.get('usage') or {}
        record_model_usage(
            engine.generation_model,
            input_tokens=usage.get('input_tokens', 0),
            output_tokens=usage.get('output_tokens', 0),
            total_tokens=usage.get('total_tokens'),
            operation='pei_generation',
            duration_ms=duration_ms,
        )

        result['pei_id'] = entry['id']
        result['pdf_url'] = f"/api/rag/peis/{entry['id']}/pdf"
        result['server_generation_time_ms'] = duration_ms
        result['server_generation_time_seconds'] = round(duration_ms / 1000, 2)
        result['selected_sources'] = selected_sources
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/pei-prompt', methods=['GET'])
def get_pei_prompt():
    """Retorna o prompt atual usado na geração de PEI."""
    try:
        return jsonify(_prompt_storage.get_pei_prompt())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/pei-prompt', methods=['PUT'])
def update_pei_prompt():
    """Atualiza o prompt de geração de PEI."""
    data = request.json or {}
    prompt = (data.get('prompt') or '').strip()
    if not prompt:
        return jsonify({"error": "Prompt é obrigatório"}), 400

    try:
        saved = _prompt_storage.save_pei_prompt(prompt)
        return jsonify(saved)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/pei-prompt/reset', methods=['POST'])
def reset_pei_prompt():
    """Restaura o prompt atual para o prompt base salvo."""
    try:
        restored = _prompt_storage.reset_pei_prompt_to_base()
        return jsonify(restored)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/chat-prompt', methods=['GET'])
def get_chat_prompt():
    """Retorna o prompt atual usado no chat RAG."""
    try:
        return jsonify(_prompt_storage.get_chat_prompt())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/chat-prompt', methods=['PUT'])
def update_chat_prompt():
    """Atualiza o prompt de chat RAG."""
    data = request.json or {}
    prompt = (data.get('prompt') or '').strip()
    if not prompt:
        return jsonify({"error": "Prompt é obrigatório"}), 400

    try:
        saved = _prompt_storage.save_chat_prompt(prompt)
        return jsonify(saved)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/chat-prompt/reset', methods=['POST'])
def reset_chat_prompt():
    """Restaura o prompt atual do chat para o prompt base salvo."""
    try:
        restored = _prompt_storage.reset_chat_prompt_to_base()
        return jsonify(restored)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/peis', methods=['GET'])
def list_peis():
    """Lista todos os PEIs gerados"""
    try:
        student_id_filter = request.args.get('student_id', '').strip()
        student_filter = request.args.get('student_name', '').strip()
        school_filter = request.args.get('school', '').strip()
        peis = _list_all_peis_with_metadata_fallback()
        if student_id_filter or student_filter or school_filter:
            peis = [
                p for p in peis
                if _entry_matches_student(
                    p,
                    student_id=student_id_filter,
                    student_name=student_filter or p.get('student_name', ''),
                    school=school_filter,
                )
            ]
        return jsonify(peis)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rag/peis/<pei_id>/pdf', methods=['GET'])
def get_pei_pdf(pei_id):
    """Serve o arquivo PDF de um PEI"""
    pei_entry = _pei_storage.get(pei_id)
    file_meta = _get_object_metadata(PEI_DOC_TYPE, pei_id)

    if not pei_entry and not file_meta:
        return jsonify({"error": "PEI não encontrado"}), 404

    object_key = file_meta.get('object_key') if file_meta else f'{pei_id}.pdf'

    try:
        file_bytes = _object_storage.download_file(PEI_STORAGE_BUCKET, object_key)
    except FileNotFoundError:
        return jsonify({"error": "Arquivo PDF do PEI não disponível"}), 404

    return send_file(
        BytesIO(file_bytes),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=(
            (pei_entry or {}).get('pdf_filename')
            or (file_meta or {}).get('original_filename')
            or f'{pei_id}.pdf'
        ),
    )


@app.route('/api/rag/peis/<pei_id>', methods=['DELETE'])
def delete_pei(pei_id):
    """Remove um PEI gerado"""
    file_meta = _get_object_metadata(PEI_DOC_TYPE, pei_id)
    object_key = file_meta.get('object_key') if file_meta else f'{pei_id}.pdf'
    _object_storage.delete_file(PEI_STORAGE_BUCKET, object_key)
    _delete_object_metadata(PEI_DOC_TYPE, pei_id)

    local_deleted = _pei_storage.delete(pei_id)
    if local_deleted or file_meta:
        return jsonify({"message": "PEI removido"})
    return jsonify({"error": "PEI não encontrado"}), 404


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    debug = DEBUG_MODE
    
    app.run(host=host, port=port, debug=debug)
