import uuid
import os
from contextlib import contextmanager
from typing import Dict, List, Optional

from sqlalchemy import (
    Boolean, JSON, ForeignKey, Integer, String, Text,
    UniqueConstraint, create_engine, delete, func, select, text, update,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from pdi_defaults import get_pdi_subject_ids_for_grade, normalize_trimesters
from time_utils import now_brasilia_iso


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ORM Models — declarados na ordem das dependências de FK
# ---------------------------------------------------------------------------

class MunicipalityRecord(Base):
    """Sem FKs — é a raiz da hierarquia geográfica."""
    __tablename__ = 'municipalities'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class SchoolRecord(Base):
    """FK: municipio_id → municipalities.id"""
    __tablename__ = 'schools'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    municipio_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('municipalities.id', ondelete='SET NULL', name='fk_schools_municipio'),
        nullable=True,
        index=True,
    )
    # Dados originais (escritos pelo usuário)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cnpj: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    institution_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    school_registration_completed: Mapped[bool] = mapped_column(nullable=False, default=False, server_default='false')
    # Respostas do formulário de Cadastro Completo da Escola (chave/valor livre, sem coluna dedicada por campo)
    registration_answers: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # JSON anônimo para IA — sem dados pessoais (LGPD)
    anonymized_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class TeacherRecord(Base):
    """FK: school_id → schools.id"""
    __tablename__ = 'teachers'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    school_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('schools.id', ondelete='SET NULL', name='fk_teachers_school'),
        nullable=True,
        index=True,
    )
    # Dados originais
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    specialization: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    school_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON anônimo para IA (LGPD)
    anonymized_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class StudentRecord(Base):
    """FK: school_id → schools.id"""
    __tablename__ = 'students'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    school_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('schools.id', ondelete='SET NULL', name='fk_students_school'),
        nullable=True,
        index=True,
    )
    # Dados originais
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    age: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    birth_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    class_name: Mapped[Optional[str]] = mapped_column('class', Text, nullable=True)
    grade: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    school_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    case_study_completed: Mapped[bool] = mapped_column(nullable=False, default=False, server_default='false')
    # Respostas do formulário de Estudo de Caso (chave/valor livre, sem coluna dedicada por campo)
    case_study_answers: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # JSON anônimo para IA (LGPD)
    anonymized_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class TeacherStudentLinkRecord(Base):
    """
    Tabela de junção M:N entre teachers e students.
    FKs: teacher_id → teachers.id (CASCADE), student_id → students.id (CASCADE)
    """
    __tablename__ = 'teacher_student_links'
    __table_args__ = (
        UniqueConstraint('teacher_id', 'student_id', name='uq_tsl_teacher_student'),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    teacher_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey('teachers.id', ondelete='CASCADE', name='fk_tsl_teacher'),
        nullable=False,
        index=True,
    )
    student_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey('students.id', ondelete='CASCADE', name='fk_tsl_student'),
        nullable=False,
        index=True,
    )
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class ParentStudentLinkRecord(Base):
    """
    Tabela de junção M:N entre usuários (role='pais') e students.
    FKs: user_id → user_profiles.id (CASCADE), student_id → students.id (CASCADE)
    """
    __tablename__ = 'parent_student_links'
    __table_args__ = (
        UniqueConstraint('user_id', 'student_id', name='uq_psl_user_student'),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey('user_profiles.id', ondelete='CASCADE', name='fk_psl_user'),
        nullable=False,
        index=True,
    )
    student_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey('students.id', ondelete='CASCADE', name='fk_psl_student'),
        nullable=False,
        index=True,
    )
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class DiaryEntryRecord(Base):
    """FK: student_id → students.id (CASCADE)"""
    __tablename__ = 'diary_entries'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('students.id', ondelete='CASCADE', name='fk_diary_student'),
        nullable=True,
        index=True,
    )
    # Dados originais
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attendance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diary_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    student_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    open_obs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    absence_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answers: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    teacher_names: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    teacher_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    parse_warnings: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # JSON anônimo para IA (LGPD)
    anonymized_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='false')
    deleted_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    deleted_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Auditoria de edição
    last_edited_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_edited_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class FamilyDiaryEntryRecord(Base):
    """
    Diário Familiar: registros escritos pelos responsáveis (role='pais') sobre o aluno.
    FKs: student_id → students.id (CASCADE), author_user_id → user_profiles.id (CASCADE)
    """
    __tablename__ = 'family_diary_entries'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey('students.id', ondelete='CASCADE', name='fk_fde_student'),
        nullable=False,
        index=True,
    )
    author_user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey('user_profiles.id', ondelete='CASCADE', name='fk_fde_author'),
        nullable=False,
        index=True,
    )
    author_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entry_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    observations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='false')
    deleted_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    deleted_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DiarySummaryRecord(Base):
    """
    Resumo de período gerado por IA a partir de entradas do diário escolar e/ou familiar,
    salvo pelo usuário. FKs: student_id → students.id (CASCADE), author_user_id → user_profiles.id (CASCADE)
    """
    __tablename__ = 'diary_summaries'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey('students.id', ondelete='CASCADE', name='fk_ds_student'),
        nullable=False,
        index=True,
    )
    author_user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey('user_profiles.id', ondelete='CASCADE', name='fk_ds_author'),
        nullable=False,
        index=True,
    )
    author_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    period_start: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    period_end: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Lista de entradas-fonte: [{"type": "escolar"|"familiar", "id": "...", "date": "..."}]
    source_entries: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='false')
    deleted_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    deleted_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PDIRecord(Base):
    """FK: student_id → students.id (CASCADE)"""
    __tablename__ = 'pdis'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('students.id', ondelete='CASCADE', name='fk_pdis_student'),
        nullable=True,
        index=True,
    )
    # Dados originais
    student_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    student_grade: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    class_name: Mapped[Optional[str]] = mapped_column('class', Text, nullable=True)
    diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    birth_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    guardian_names: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    teacher_names: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    teacher_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    trimesters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # JSON anônimo para IA (LGPD)
    anonymized_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class UserProfileRecord(Base):
    """FKs: municipio_id → municipalities, school_id → schools, teacher_id → teachers"""
    __tablename__ = 'user_profiles'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    municipio_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('municipalities.id', ondelete='SET NULL', name='fk_user_profiles_municipio'),
        nullable=True,
        index=True,
    )
    school_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('schools.id', ondelete='SET NULL', name='fk_user_profiles_school'),
        nullable=True,
        index=True,
    )
    teacher_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('teachers.id', ondelete='SET NULL', name='fk_user_profiles_teacher'),
        nullable=True,
    )
    evaluator_scope: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class CaseStudySubmissionRecord(Base):
    __tablename__ = 'case_study_submissions'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    answers: Mapped[dict] = mapped_column(JSON, nullable=False)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSON, nullable=False)
    submitted_at: Mapped[str] = mapped_column(String(40), nullable=False)


class SchoolRegistrationSubmissionRecord(Base):
    __tablename__ = 'school_registration_submissions'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    answers: Mapped[dict] = mapped_column(JSON, nullable=False)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSON, nullable=False)
    submitted_at: Mapped[str] = mapped_column(String(40), nullable=False)


class ObjectStorageFileRecord(Base):
    """
    reference_id é uma referência polimórfica (depende de doc_type).
    student_id e school_id são FKs explícitas adicionadas para facilitar queries por aluno/escola.
    """
    __tablename__ = 'object_storage_files'
    __table_args__ = (
        UniqueConstraint('doc_type', 'reference_id', name='uq_object_storage_doc_ref'),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(128), nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    student_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('students.id', ondelete='SET NULL', name='fk_osf_student'),
        nullable=True,
        index=True,
    )
    school_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('schools.id', ondelete='SET NULL', name='fk_osf_school'),
        nullable=True,
        index=True,
    )
    extra_json: Mapped[dict] = mapped_column('extra', JSON, nullable=False, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class PEIRecord(Base):
    """PEIs gerados por IA. FK: student_id → students (SET NULL)."""
    __tablename__ = 'peis'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('students.id', ondelete='SET NULL', name='fk_peis_student'),
        nullable=True,
        index=True,
    )
    student_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    school: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_by_user_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_by_username: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pdf_filename: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    object_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bucket: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    anonymized_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class ChatSessionRecord(Base):
    """
    FKs: created_by_user_id → user_profiles (CASCADE),
         municipio_id → municipalities (SET NULL),
         school_id → schools (SET NULL),
         teacher_id → teachers (SET NULL),
         student_id → students (SET NULL)
    """
    __tablename__ = 'chat_sessions'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    created_by_user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey('user_profiles.id', ondelete='CASCADE', name='fk_chat_sessions_user'),
        nullable=False,
        index=True,
    )
    created_by_username: Mapped[str] = mapped_column(String(120), nullable=False)
    created_by_role: Mapped[str] = mapped_column(String(64), nullable=False)
    municipio_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('municipalities.id', ondelete='SET NULL', name='fk_chat_sessions_municipio'),
        nullable=True,
        index=True,
    )
    school_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('schools.id', ondelete='SET NULL', name='fk_chat_sessions_school'),
        nullable=True,
        index=True,
    )
    teacher_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('teachers.id', ondelete='SET NULL', name='fk_chat_sessions_teacher'),
        nullable=True,
    )
    student_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('students.id', ondelete='SET NULL', name='fk_chat_sessions_student'),
        nullable=True,
        index=True,
    )
    student_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    school_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    extra_json: Mapped[dict] = mapped_column('extra', JSON, nullable=False, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class ChatMessageRecord(Base):
    """
    FKs: session_id → chat_sessions (CASCADE),
         user_id → user_profiles (SET NULL)
    """
    __tablename__ = 'chat_messages'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey('chat_sessions.id', ondelete='CASCADE', name='fk_chat_messages_session'),
        nullable=False,
        index=True,
    )
    message_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey('user_profiles.id', ondelete='SET NULL', name='fk_chat_messages_user'),
        nullable=True,
    )
    username: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    sources_json: Mapped[dict] = mapped_column('sources', JSON, nullable=False, default=dict)
    extra_json: Mapped[dict] = mapped_column('extra', JSON, nullable=False, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


# ---------------------------------------------------------------------------
# AI Usage Events  (sem FKs — tabela de telemetria independente)
# ---------------------------------------------------------------------------

class AIUsageEventRecord(Base):
    __tablename__ = 'ai_usage_events'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timestamp: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    model: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Repositórios
# ---------------------------------------------------------------------------

class _BaseRepository:
    def __init__(self, session_factory, model):
        self._session_factory = session_factory
        self._model = model

    @contextmanager
    def _session(self):
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _to_entity(self, record) -> Dict:
        """
        Método base: mescla payload JSON com colunas estruturais.
        Subclasses devem sobrescrever para incluir suas colunas FK extraídas.
        """
        payload = dict(record.payload or {})
        payload['id'] = record.id
        payload['created_at'] = record.created_at
        payload['updated_at'] = record.updated_at
        return payload

    def _get(self, entity_id: str) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(self._model, entity_id)
            if not record:
                return None
            return self._to_entity(record)

    def _delete(self, entity_id: str) -> bool:
        with self._session() as session:
            record = session.get(self._model, entity_id)
            if not record:
                return False
            session.delete(record)
            return True


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class PostgresAuthRepository:
    VALID_ROLES = {
        'admin',
        'secretaria',
        'coordenacao',
        'professor',
        'viewer',
        'avaliador',
        'pais',
    }

    def __init__(self, session_factory, default_admin_username: str = 'admin', default_admin_password: str = ''):
        self._session_factory = session_factory
        self.default_admin_username = str(default_admin_username or 'admin').strip() or 'admin'
        self.default_admin_password = default_admin_password or ''
        self._ensure_default_admin()

    @contextmanager
    def _session(self):
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _sanitize_user(user: UserProfileRecord) -> Dict:
        return {
            'id': user.id,
            'username': user.username,
            'name': user.full_name or '',
            'role': user.role,
            'municipio_id': user.municipio_id or '',
            'school_id': user.school_id or '',
            'teacher_id': user.teacher_id or '',
            'evaluator_scope': user.evaluator_scope or {},
            'is_active': bool(user.is_active),
            'created_at': user.created_at,
            'updated_at': user.updated_at,
        }

    def _get_raw_user_by_id(self, user_id: str) -> Optional[UserProfileRecord]:
        with self._session() as session:
            return session.get(UserProfileRecord, str(user_id or '').strip())

    def _get_raw_user_by_username(self, username: str) -> Optional[UserProfileRecord]:
        normalized_username = str(username or '').strip().lower()
        if not normalized_username:
            return None
        with self._session() as session:
            return session.execute(
                select(UserProfileRecord).where(text('lower(username) = :username')).params(username=normalized_username)
            ).scalar_one_or_none()

    def _ensure_default_admin(self) -> None:
        if self.list_users():
            return
        if not self.default_admin_password:
            raise RuntimeError('AUTH_ADMIN_PASSWORD não configurada. Defina no .env para criar o admin inicial.')

        self.create_user(
            username=self.default_admin_username,
            password=self.default_admin_password,
            role='admin',
            name='Administrador',
        )

    def list_users(self) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(select(UserProfileRecord)).scalars().all()
        users = [self._sanitize_user(row) for row in rows]
        return sorted(users, key=lambda item: item['username'].lower())

    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        with self._session() as session:
            user = session.get(UserProfileRecord, str(user_id or '').strip())
            return self._sanitize_user(user) if user else None

    def authenticate(self, username: str, password: str) -> Optional[Dict]:
        from werkzeug.security import check_password_hash

        user = self._get_raw_user_by_username(username)
        if not user or not user.is_active:
            return None

        if not user.password_hash or not check_password_hash(user.password_hash, password):
            return None

        return self._sanitize_user(user)

    def _validate_role(self, role: str) -> str:
        role = (role or '').strip().lower()
        if role not in self.VALID_ROLES:
            raise ValueError('Perfil inválido')
        return role

    def _validate_scope(self, role: str, municipio_id: str, school_id: str) -> None:
        if role == 'secretaria' and not municipio_id:
            raise ValueError('Usuário secretaria exige municipio_id')
        if role == 'coordenacao' and not school_id:
            raise ValueError('Usuário de coordenação exige school_id')
        if role == 'professor' and not school_id:
            raise ValueError('Usuário professor exige school_id')
        if role == 'viewer' and not (municipio_id or school_id):
            raise ValueError('Usuário viewer exige municipio_id ou school_id')

    def create_user(
        self,
        username: str,
        password: str,
        role: str,
        name: str = '',
        municipio_id: str = '',
        school_id: str = '',
        teacher_id: str = '',
        evaluator_scope: Optional[dict] = None,
    ) -> Dict:
        from werkzeug.security import generate_password_hash

        username = (username or '').strip().lower()
        role = self._validate_role(role)
        if len(username) < 3:
            raise ValueError('Nome de usuário deve ter ao menos 3 caracteres')
        if len(password or '') < 6:
            raise ValueError('Senha deve ter ao menos 6 caracteres')
        if self._get_raw_user_by_username(username):
            raise ValueError('Nome de usuário já existe')

        name = (name or '').strip()
        municipio_id = (municipio_id or '').strip()
        school_id = (school_id or '').strip()
        teacher_id = (teacher_id or '').strip()
        self._validate_scope(role, municipio_id, school_id)

        now = now_brasilia_iso()
        with self._session() as session:
            user = UserProfileRecord(
                id=str(uuid.uuid4()),
                username=username,
                password_hash=generate_password_hash(password),
                full_name=name,
                role=role,
                municipio_id=municipio_id or None,
                school_id=school_id or None,
                teacher_id=teacher_id or None,
                evaluator_scope=evaluator_scope or None,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.flush()
            return self._sanitize_user(user)

    def upsert_user(
        self,
        user_id: str,
        username: str,
        password_hash: Optional[str],
        role: str,
        name: str = '',
        municipio_id: str = '',
        school_id: str = '',
        teacher_id: str = '',
        evaluator_scope: Optional[dict] = None,
        is_active: bool = True,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> Dict:
        role = self._validate_role(role)
        username = (username or '').strip().lower()
        if len(username) < 3:
            raise ValueError('Nome de usuário deve ter ao menos 3 caracteres')

        name = (name or '').strip()
        municipio_id = (municipio_id or '').strip()
        school_id = (school_id or '').strip()
        teacher_id = (teacher_id or '').strip()
        self._validate_scope(role, municipio_id, school_id)

        now = now_brasilia_iso()
        user_id = str(user_id or '').strip() or str(uuid.uuid4())
        with self._session() as session:
            record = session.get(UserProfileRecord, user_id)
            if record is None:
                record = UserProfileRecord(
                    id=user_id,
                    username=username,
                    password_hash=password_hash,
                    full_name=name,
                    role=role,
                    municipio_id=municipio_id or None,
                    school_id=school_id or None,
                    teacher_id=teacher_id or None,
                    evaluator_scope=evaluator_scope or None,
                    is_active=bool(is_active),
                    created_at=created_at or now,
                    updated_at=updated_at or now,
                )
                session.add(record)
                session.flush()
                return self._sanitize_user(record)

            record.username = username
            if password_hash:
                record.password_hash = password_hash
            record.full_name = name
            record.role = role
            record.municipio_id = municipio_id or None
            record.school_id = school_id or None
            record.teacher_id = teacher_id or None
            record.evaluator_scope = evaluator_scope or None
            record.is_active = bool(is_active)
            if created_at:
                record.created_at = created_at
            record.updated_at = updated_at or now
            session.flush()
            return self._sanitize_user(record)

    def update_user_role(self, user_id: str, role: str) -> Optional[Dict]:
        role = self._validate_role(role)
        with self._session() as session:
            record = session.get(UserProfileRecord, str(user_id or '').strip())
            if not record:
                return None

            record.role = role
            record.updated_at = now_brasilia_iso()
            return self._sanitize_user(record)

    def update_evaluator_scope(self, user_id: str, evaluator_scope: Dict) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(UserProfileRecord, str(user_id or '').strip())
            if not record:
                return None

            if (record.role or '').strip().lower() != 'avaliador':
                raise ValueError('Escopo só pode ser atualizado para usuários avaliador')

            record.evaluator_scope = evaluator_scope
            record.updated_at = now_brasilia_iso()
            session.flush()
            return self._sanitize_user(record)

    def update_user(
        self,
        user_id: str,
        name: Optional[str] = None,
        role: Optional[str] = None,
        municipio_id: Optional[str] = None,
        school_id: Optional[str] = None,
        teacher_id: Optional[str] = None,
        evaluator_scope: Optional[dict] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(UserProfileRecord, str(user_id or '').strip())
            if not record:
                return None

            if role is not None:
                record.role = self._validate_role(role)

            if name is not None:
                record.full_name = (name or '').strip()

            if municipio_id is not None:
                record.municipio_id = (municipio_id or '').strip() or None

            if school_id is not None:
                record.school_id = (school_id or '').strip() or None

            if teacher_id is not None:
                record.teacher_id = (teacher_id or '').strip() or None

            if evaluator_scope is not None:
                record.evaluator_scope = evaluator_scope

            if is_active is not None:
                record.is_active = bool(is_active)

            # Validar escopo geral do usuário
            self._validate_scope(record.role, record.municipio_id or '', record.school_id or '')

            record.updated_at = now_brasilia_iso()
            session.flush()
            return self._sanitize_user(record)

    def change_password(self, user_id: str, new_password: str) -> Optional[Dict]:
        user_id = str(user_id or '').strip()
        new_password = (new_password or '').strip()
        if not user_id:
            return None
        if not new_password:
            raise ValueError('Nova senha é obrigatória')
        if len(new_password) < 6:
            raise ValueError('A senha deve ter pelo menos 6 caracteres')
        from werkzeug.security import generate_password_hash
        with self._session() as session:
            record = session.get(UserProfileRecord, user_id)
            if not record:
                return None
            record.password_hash = generate_password_hash(new_password)
            record.updated_at = now_brasilia_iso()
            session.flush()
            return self._sanitize_user(record)

    def delete_user(self, user_id: str, acting_user_id: str = '') -> Optional[Dict]:
        user_id = str(user_id or '').strip()
        acting_user_id = str(acting_user_id or '').strip()
        with self._session() as session:
            record = session.get(UserProfileRecord, user_id)
            if not record:
                return None

            if acting_user_id and user_id == acting_user_id:
                raise ValueError('Você não pode apagar o seu próprio usuário')

            if record.role == 'admin':
                admin_count = session.execute(
                    select(UserProfileRecord.id).where(UserProfileRecord.role == 'admin')
                ).all()
                if len(admin_count) <= 1:
                    raise ValueError('Não é possível apagar o último usuário admin')

            sanitized = self._sanitize_user(record)
            session.delete(record)
            return sanitized


# ---------------------------------------------------------------------------
# Helper de resolução de nomes de professores → IDs (usado por Diary e PDI)
# ---------------------------------------------------------------------------

def _resolve_teacher_ids(session, teacher_names: List[str], student_id: Optional[str] = None) -> List[str]:
    """
    Converte lista de nomes de professores em UUIDs consultando a tabela teachers.
    Se student_id fornecido, filtra pela escola do aluno para reduzir ambiguidade.
    """
    import unicodedata

    if not teacher_names:
        return []

    def _norm(s: str) -> str:
        s = unicodedata.normalize('NFKD', (s or '').strip().lower())
        s = ''.join(c for c in s if not unicodedata.combining(c))
        return ' '.join(s.split())

    school_id: Optional[str] = None
    if student_id:
        school_id = session.execute(
            select(StudentRecord.school_id).where(StudentRecord.id == student_id)
        ).scalar_one_or_none()

    stmt = select(TeacherRecord.id, TeacherRecord.name)
    if school_id:
        stmt = stmt.where(TeacherRecord.school_id == school_id)

    teacher_rows = session.execute(stmt).all()
    name_to_id = {_norm(row.name): row.id for row in teacher_rows if row.name}

    return [name_to_id[_norm(n)] for n in teacher_names if _norm(n) in name_to_id]


# ---------------------------------------------------------------------------
# Schools  (FK: municipio_id → municipalities)
# ---------------------------------------------------------------------------

class SchoolPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, SchoolRecord)

    def _to_entity(self, record: SchoolRecord) -> Dict:
        return {
            **(record.registration_answers or {}),
            'id': record.id,
            'municipio_id': record.municipio_id or '',
            'name': record.name or '',
            'cnpj': record.cnpj or '',
            'institution_type': record.institution_type or '',
            'address': dict(record.address or {}),
            'notes': record.notes or '',
            'school_registration_completed': bool(record.school_registration_completed),
            'anonymized_data': dict(record.anonymized_data or {}),
            'created_at': record.created_at,
            'updated_at': record.updated_at,
        }

    def create_school(
        self,
        school_data: Dict,
        school_id: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        school_id = school_id or str(uuid.uuid4())
        data = dict(school_data)
        for k in ('id', 'created_at', 'updated_at', 'anonymized_data'):
            data.pop(k, None)

        municipio_id = data.pop('municipio_id', None) or None
        name = data.pop('name', '') or ''
        cnpj = data.pop('cnpj', '') or ''
        institution_type = data.pop('institution_type', '') or ''
        address = data.pop('address', None) or None
        notes = data.pop('notes', '') or ''
        completed = bool(data.pop('school_registration_completed', False))

        anonymized_data = {
            'school_id': school_id,
            'institution_type': institution_type,
        }

        with self._session() as session:
            record = SchoolRecord(
                id=school_id,
                municipio_id=municipio_id,
                name=name,
                cnpj=cnpj,
                institution_type=institution_type,
                address=address,
                notes=notes,
                school_registration_completed=completed,
                registration_answers=data or None,
                anonymized_data=anonymized_data,
                created_at=created_at or now,
                updated_at=updated_at or now,
            )
            session.merge(record)
            return self._to_entity(record)

    def update_school(self, school_id: str, school_data: Dict) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(SchoolRecord, school_id)
            if not record:
                return None

            data = dict(school_data)
            for k in ('id', 'created_at', 'updated_at', 'anonymized_data'):
                data.pop(k, None)

            if 'municipio_id' in data:
                record.municipio_id = data.pop('municipio_id') or None
            if 'name' in data:
                record.name = data.pop('name')
            if 'cnpj' in data:
                record.cnpj = data.pop('cnpj')
            if 'institution_type' in data:
                record.institution_type = data.pop('institution_type')
            if 'address' in data:
                record.address = data.pop('address') or None
            if 'notes' in data:
                record.notes = data.pop('notes')
            if 'school_registration_completed' in data:
                record.school_registration_completed = bool(data.pop('school_registration_completed'))

            if data:
                record.registration_answers = {**(record.registration_answers or {}), **data}

            record.anonymized_data = {
                'school_id': school_id,
                'institution_type': record.institution_type or '',
            }
            record.updated_at = now_brasilia_iso()
            return self._to_entity(record)

    def get_school(self, school_id: str) -> Optional[Dict]:
        return self._get(school_id)

    def list_schools_by_scope(self, scope: Dict) -> List[Dict]:
        """
        Retorna escolas filtradas por escopo via SQL — sem N+1.
        scope: {'role', 'school_id', 'municipio_id'}
        """
        role = (scope.get('role') or '').lower()
        school_id = (scope.get('school_id') or '').strip()
        municipio_id = (scope.get('municipio_id') or '').strip()

        with self._session() as session:
            stmt = select(SchoolRecord)

            if role == 'admin':
                pass  # sem filtro
            elif role in ('coordenacao', 'professor') or (role == 'viewer' and school_id):
                if not school_id:
                    return []
                stmt = stmt.where(SchoolRecord.id == school_id)
            elif role == 'secretaria' or (role == 'viewer' and municipio_id):
                if not municipio_id:
                    return []
                stmt = stmt.where(SchoolRecord.municipio_id == municipio_id)
            else:
                return []

            rows = session.execute(stmt).scalars().all()

        summaries = []
        for row in rows:
            school = self._to_entity(row)
            summaries.append({
                'id': school['id'],
                'name': school.get('name', ''),
                'cnpj': school.get('cnpj', ''),
                'institution_type': school.get('institution_type', ''),
                'municipio_id': school.get('municipio_id', ''),
                'city': school.get('address', {}).get('city', '') if isinstance(school.get('address'), dict) else '',
                'school_registration_completed': bool(school.get('school_registration_completed', False)),
                'updated_at': school['updated_at'],
            })
        return sorted(summaries, key=lambda x: x['name'].lower())

    def list_all_schools(self) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(select(SchoolRecord)).scalars().all()

        summaries = []
        for row in rows:
            school = self._to_entity(row)
            summaries.append({
                'id': school['id'],
                'name': school.get('name', ''),
                'cnpj': school.get('cnpj', ''),
                'institution_type': school.get('institution_type', ''),
                'municipio_id': school.get('municipio_id', ''),
                'city': school.get('address', {}).get('city', '') if isinstance(school.get('address'), dict) else '',
                'school_registration_completed': bool(school.get('school_registration_completed', False)),
                'updated_at': school['updated_at'],
            })

        return sorted(summaries, key=lambda x: x['name'].lower())

    def delete_school(self, school_id: str) -> bool:
        return self._delete(school_id)


# ---------------------------------------------------------------------------
# Students  (FK: school_id → schools; M:N com teachers via teacher_student_links)
# ---------------------------------------------------------------------------

class StudentPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, StudentRecord)

    # --- Helpers internos ---

    @staticmethod
    def _get_teacher_ids(session: Session, student_id: str) -> List[str]:
        """Busca teacher_ids via tabela de junção."""
        rows = session.execute(
            select(TeacherStudentLinkRecord.teacher_id).where(
                TeacherStudentLinkRecord.student_id == student_id
            )
        ).scalars().all()
        return list(rows)

    @staticmethod
    def _get_teacher_names_by_ids(session: Session, teacher_ids: List[str]) -> List[str]:
        """Converte lista de teacher_ids em lista de teacher_names."""
        if not teacher_ids:
            return []
        rows = session.execute(
            select(TeacherRecord.id, TeacherRecord.name).where(
                TeacherRecord.id.in_(teacher_ids)
            )
        ).all()
        id_to_name = {row.id: (row.name or '') for row in rows}
        return [id_to_name[tid] for tid in teacher_ids if tid in id_to_name]

    @staticmethod
    def _sync_teacher_links(session: Session, student_id: str, teacher_ids: List[str]) -> None:
        """
        Sincroniza a tabela teacher_student_links para o aluno:
        apaga vínculos antigos e insere os novos.
        Ignora teacher_ids que não existam na tabela teachers (evita FK violation).
        """
        session.execute(
            delete(TeacherStudentLinkRecord).where(
                TeacherStudentLinkRecord.student_id == student_id
            )
        )
        now = now_brasilia_iso()
        seen: set = set()
        for tid in teacher_ids:
            tid = (tid or '').strip()
            if not tid or tid in seen:
                continue
            seen.add(tid)
            # Verifica se o teacher existe antes de inserir (evita FK violation)
            exists = session.execute(
                select(TeacherRecord.id).where(TeacherRecord.id == tid)
            ).scalar_one_or_none()
            if exists is None:
                continue
            session.add(TeacherStudentLinkRecord(
                id=str(uuid.uuid4()),
                teacher_id=tid,
                student_id=student_id,
                created_at=now,
            ))

    @staticmethod
    def _get_parent_ids(session: Session, student_id: str) -> List[str]:
        """Busca parent_ids (usuários com role 'pais') via tabela de junção."""
        rows = session.execute(
            select(ParentStudentLinkRecord.user_id).where(
                ParentStudentLinkRecord.student_id == student_id
            )
        ).scalars().all()
        return list(rows)

    @staticmethod
    def _get_parent_names_by_ids(session: Session, parent_ids: List[str]) -> List[str]:
        """Converte lista de parent_ids em lista de nomes de exibição."""
        if not parent_ids:
            return []
        rows = session.execute(
            select(UserProfileRecord.id, UserProfileRecord.full_name, UserProfileRecord.username).where(
                UserProfileRecord.id.in_(parent_ids)
            )
        ).all()
        id_to_name = {row.id: (row.full_name or row.username or '') for row in rows}
        return [id_to_name[pid] for pid in parent_ids if pid in id_to_name]

    @staticmethod
    def _sync_parent_links(session: Session, student_id: str, parent_ids: List[str]) -> None:
        """
        Sincroniza a tabela parent_student_links para o aluno:
        apaga vínculos antigos e insere os novos.
        Ignora parent_ids que não correspondam a um usuário com role 'pais' (evita FK violation / vínculo incorreto).
        """
        session.execute(
            delete(ParentStudentLinkRecord).where(
                ParentStudentLinkRecord.student_id == student_id
            )
        )
        now = now_brasilia_iso()
        seen: set = set()
        for pid in parent_ids:
            pid = (pid or '').strip()
            if not pid or pid in seen:
                continue
            seen.add(pid)
            exists = session.execute(
                select(UserProfileRecord.id).where(
                    UserProfileRecord.id == pid,
                    UserProfileRecord.role == 'pais',
                )
            ).scalar_one_or_none()
            if exists is None:
                continue
            session.add(ParentStudentLinkRecord(
                id=str(uuid.uuid4()),
                user_id=pid,
                student_id=student_id,
                created_at=now,
            ))

    @staticmethod
    def _student_entity(
        record: StudentRecord,
        teacher_ids: List[str],
        teacher_names: Optional[List[str]] = None,
        parent_ids: Optional[List[str]] = None,
        parent_names: Optional[List[str]] = None,
    ) -> Dict:
        names = teacher_names or []
        p_ids = parent_ids or []
        p_names = parent_names or []
        return {
            **(record.case_study_answers or {}),
            'id': record.id,
            'school_id': record.school_id or '',
            'name': record.name or '',
            'age': record.age or '',
            'birth_date': record.birth_date or '',
            'class': record.class_name or '',
            'grade': record.grade or '',
            'school_name': record.school_name or '',
            'case_study_completed': bool(record.case_study_completed),
            'teacher_ids': teacher_ids,
            'teacher_id': teacher_ids[0] if teacher_ids else '',
            'teachers': names,
            'teacher_names': names,
            'teacher_name': names[0] if names else '',
            'parent_ids': p_ids,
            'parent_names': p_names,
            'anonymized_data': dict(record.anonymized_data or {}),
            'created_at': record.created_at,
            'updated_at': record.updated_at,
        }

    # --- CRUD público ---

    def create_student(
        self,
        student_data: Dict,
        student_id: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        student_id = student_id or str(uuid.uuid4())
        data = dict(student_data)
        for k in ('id', 'created_at', 'updated_at', 'anonymized_data'):
            data.pop(k, None)

        school_id = data.pop('school_id', None) or None
        raw_teacher_ids = data.pop('teacher_ids', []) or []
        data.pop('teacher_id', None)

        name = data.pop('name', None) or data.pop('studentName', '') or ''
        age = data.pop('age', None) or data.pop('studentAge', '') or ''
        birth_date = data.pop('birth_date', None) or data.pop('birthDate', '') or ''
        class_name = data.pop('class', None) or data.pop('className', '') or ''
        grade = data.pop('grade', None) or data.pop('schoolYear', '') or ''
        school_name = data.pop('school_name', None) or data.pop('schoolName', '') or ''
        completed = bool(data.pop('case_study_completed', False))
        # consume leftover aliases
        for k in ('studentName', 'studentAge', 'className', 'schoolYear', 'schoolName'):
            data.pop(k, None)

        teacher_ids = [str(t) for t in raw_teacher_ids if t]
        anonymized_data = {
            'student_id': student_id,
            'school_id': school_id or '',
            'age': age,
            'grade': grade,
            'class': class_name,
        }

        with self._session() as session:
            record = StudentRecord(
                id=student_id,
                school_id=school_id,
                name=name,
                age=age,
                birth_date=birth_date or None,
                class_name=class_name,
                grade=grade,
                school_name=school_name,
                case_study_completed=completed,
                case_study_answers=data or None,
                anonymized_data=anonymized_data,
                created_at=created_at or now,
                updated_at=updated_at or now,
            )
            session.merge(record)
            session.flush()
            self._sync_teacher_links(session, student_id, teacher_ids)
            teacher_names = self._get_teacher_names_by_ids(session, teacher_ids)
            return self._student_entity(record, teacher_ids, teacher_names)

    def update_student(self, student_id: str, student_data: Dict) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(StudentRecord, student_id)
            if not record:
                return None

            data = dict(student_data)
            for k in ('id', 'created_at', 'updated_at', 'anonymized_data'):
                data.pop(k, None)

            raw_teacher_ids = data.pop('teacher_ids', None)
            data.pop('teacher_id', None)
            raw_parent_ids = data.pop('parent_ids', None)

            if 'school_id' in data:
                record.school_id = data.pop('school_id') or None
            if 'name' in data:
                record.name = data.pop('name')
            elif 'studentName' in data:
                record.name = data.pop('studentName')
            if 'age' in data:
                record.age = data.pop('age')
            elif 'studentAge' in data:
                record.age = data.pop('studentAge')
            if 'birth_date' in data:
                record.birth_date = data.pop('birth_date') or None
            elif 'birthDate' in data:
                record.birth_date = data.pop('birthDate') or None
            if 'class' in data:
                record.class_name = data.pop('class')
            elif 'className' in data:
                record.class_name = data.pop('className')
            if 'grade' in data:
                record.grade = data.pop('grade')
            elif 'schoolYear' in data:
                record.grade = data.pop('schoolYear')
            if 'school_name' in data:
                record.school_name = data.pop('school_name')
            elif 'schoolName' in data:
                record.school_name = data.pop('schoolName')
            if 'case_study_completed' in data:
                record.case_study_completed = bool(data.pop('case_study_completed'))

            if data:
                record.case_study_answers = {**(record.case_study_answers or {}), **data}

            record.anonymized_data = {
                'student_id': student_id,
                'school_id': record.school_id or '',
                'age': record.age or '',
                'grade': record.grade or '',
                'class': record.class_name or '',
            }
            record.updated_at = now_brasilia_iso()
            session.flush()

            if raw_teacher_ids is not None:
                teacher_ids = [str(t) for t in raw_teacher_ids if t]
                self._sync_teacher_links(session, student_id, teacher_ids)
            else:
                teacher_ids = self._get_teacher_ids(session, student_id)

            if raw_parent_ids is not None:
                parent_ids = [str(p) for p in raw_parent_ids if p]
                self._sync_parent_links(session, student_id, parent_ids)
            else:
                parent_ids = self._get_parent_ids(session, student_id)

            teacher_names = self._get_teacher_names_by_ids(session, teacher_ids)
            parent_names = self._get_parent_names_by_ids(session, parent_ids)
            return self._student_entity(record, teacher_ids, teacher_names, parent_ids, parent_names)

    def get_student(self, student_id: str) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(StudentRecord, student_id)
            if not record:
                return None
            teacher_ids = self._get_teacher_ids(session, student_id)
            teacher_names = self._get_teacher_names_by_ids(session, teacher_ids)
            parent_ids = self._get_parent_ids(session, student_id)
            parent_names = self._get_parent_names_by_ids(session, parent_ids)
            return self._student_entity(record, teacher_ids, teacher_names, parent_ids, parent_names)

    def list_all_students(self) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(select(StudentRecord)).scalars().all()

            # Batch: busca todos os links de uma vez (evita N+1)
            student_ids = [r.id for r in rows]
            link_rows = session.execute(
                select(TeacherStudentLinkRecord).where(
                    TeacherStudentLinkRecord.student_id.in_(student_ids)
                )
            ).scalars().all()

            all_teacher_ids = list({link.teacher_id for link in link_rows})
            teacher_name_rows = session.execute(
                select(TeacherRecord.id, TeacherRecord.name).where(
                    TeacherRecord.id.in_(all_teacher_ids)
                )
            ).all() if all_teacher_ids else []
            teacher_id_to_name = {r.id: (r.name or '') for r in teacher_name_rows}

            parent_link_rows = session.execute(
                select(ParentStudentLinkRecord).where(
                    ParentStudentLinkRecord.student_id.in_(student_ids)
                )
            ).scalars().all()

        teacher_ids_map: Dict[str, List[str]] = {}
        for link in link_rows:
            teacher_ids_map.setdefault(link.student_id, []).append(link.teacher_id)

        parent_ids_map: Dict[str, List[str]] = {}
        for link in parent_link_rows:
            parent_ids_map.setdefault(link.student_id, []).append(link.user_id)

        summaries = []
        for row in rows:
            teacher_ids = teacher_ids_map.get(row.id, [])
            t_names = [teacher_id_to_name[tid] for tid in teacher_ids if tid in teacher_id_to_name]
            parent_ids = parent_ids_map.get(row.id, [])
            student = self._student_entity(row, teacher_ids, t_names, parent_ids)
            summaries.append({
                'id': student['id'],
                'name': student.get('name', student.get('studentName', '')),
                'age': student.get('age', student.get('studentAge', '')),
                'school_id': student.get('school_id', ''),
                'school_name': student.get('school_name', student.get('schoolName', '')),
                'teacher_ids': teacher_ids,
                'teacher_id': teacher_ids[0] if teacher_ids else '',
                'teachers': t_names,
                'teacher_names': t_names,
                'teacher_name': t_names[0] if t_names else '',
                'parent_ids': parent_ids,
                'class': student.get('class', student.get('className', '')),
                'grade': student.get('grade', student.get('schoolYear', '')),
                'case_study_completed': bool(student.get('case_study_completed', False)),
                'updated_at': student['updated_at'],
            })

        return sorted(summaries, key=lambda x: x['name'].lower())

    def list_students_by_scope(self, scope: Dict) -> List[Dict]:
        """
        Retorna alunos filtrados por escopo via JOIN SQL — sem N+1.
        scope: {'role', 'school_id', 'municipio_id', 'teacher_ids'}
        """
        role = (scope.get('role') or '').lower()
        school_id = (scope.get('school_id') or '').strip()
        municipio_id = (scope.get('municipio_id') or '').strip()
        teacher_ids = scope.get('teacher_ids') or []

        with self._session() as session:
            stmt = select(StudentRecord)

            if role == 'admin':
                pass  # sem filtro
            elif role == 'coordenacao' or (role == 'viewer' and school_id):
                if not school_id:
                    return []
                stmt = stmt.where(StudentRecord.school_id == school_id)
            elif role == 'secretaria' or (role == 'viewer' and municipio_id):
                if not municipio_id:
                    return []
                stmt = (stmt
                        .join(SchoolRecord, StudentRecord.school_id == SchoolRecord.id)
                        .where(SchoolRecord.municipio_id == municipio_id))
            elif role == 'professor':
                if not teacher_ids:
                    return []
                stmt = (stmt
                        .join(TeacherStudentLinkRecord,
                              StudentRecord.id == TeacherStudentLinkRecord.student_id)
                        .where(TeacherStudentLinkRecord.teacher_id.in_(teacher_ids))
                        .distinct(StudentRecord.id))
            else:
                return []

            rows = session.execute(stmt).scalars().all()
            if not rows:
                return []

            student_ids = [r.id for r in rows]
            link_rows = session.execute(
                select(TeacherStudentLinkRecord).where(
                    TeacherStudentLinkRecord.student_id.in_(student_ids)
                )
            ).scalars().all()

            all_teacher_ids_scope = list({link.teacher_id for link in link_rows})
            teacher_name_rows_scope = session.execute(
                select(TeacherRecord.id, TeacherRecord.name).where(
                    TeacherRecord.id.in_(all_teacher_ids_scope)
                )
            ).all() if all_teacher_ids_scope else []
            teacher_id_to_name_scope = {r.id: (r.name or '') for r in teacher_name_rows_scope}

        teacher_ids_map: Dict[str, List[str]] = {}
        for link in link_rows:
            teacher_ids_map.setdefault(link.student_id, []).append(link.teacher_id)

        summaries = []
        for row in rows:
            t_ids = teacher_ids_map.get(row.id, [])
            t_names = [teacher_id_to_name_scope[tid] for tid in t_ids if tid in teacher_id_to_name_scope]
            student = self._student_entity(row, t_ids, t_names)
            summaries.append({
                'id': student['id'],
                'name': student.get('name', student.get('studentName', '')),
                'age': student.get('age', student.get('studentAge', '')),
                'school_id': student.get('school_id', ''),
                'school_name': student.get('school_name', student.get('schoolName', '')),
                'teacher_ids': t_ids,
                'teacher_id': t_ids[0] if t_ids else '',
                'teachers': t_names,
                'teacher_names': t_names,
                'teacher_name': t_names[0] if t_names else '',
                'class': student.get('class', student.get('className', '')),
                'grade': student.get('grade', student.get('schoolYear', '')),
                'case_study_completed': bool(student.get('case_study_completed', False)),
                'updated_at': student['updated_at'],
            })

        return sorted(summaries, key=lambda x: x['name'].lower())

    def find_students_by_name(self, candidate_name: str) -> List[Dict]:
        normalized_candidate = self._normalize_name(candidate_name)
        if not normalized_candidate:
            return []

        with self._session() as session:
            rows = session.execute(select(StudentRecord)).scalars().all()

            student_ids = [r.id for r in rows]
            link_rows = session.execute(
                select(TeacherStudentLinkRecord).where(
                    TeacherStudentLinkRecord.student_id.in_(student_ids)
                )
            ).scalars().all()

            all_teacher_ids_find = list({link.teacher_id for link in link_rows})
            teacher_name_rows_find = session.execute(
                select(TeacherRecord.id, TeacherRecord.name).where(
                    TeacherRecord.id.in_(all_teacher_ids_find)
                )
            ).all() if all_teacher_ids_find else []
            teacher_id_to_name_find = {r.id: (r.name or '') for r in teacher_name_rows_find}

        teacher_ids_map: Dict[str, List[str]] = {}
        for link in link_rows:
            teacher_ids_map.setdefault(link.student_id, []).append(link.teacher_id)

        matches = []
        for row in rows:
            if self._normalize_name(row.name or '') == normalized_candidate:
                teacher_ids = teacher_ids_map.get(row.id, [])
                t_names = [teacher_id_to_name_find[tid] for tid in teacher_ids if tid in teacher_id_to_name_find]
                matches.append(self._student_entity(row, teacher_ids, t_names))

        return matches

    def _normalize_name(self, value: str) -> str:
        import unicodedata
        normalized = unicodedata.normalize('NFKD', (value or '').strip().lower())
        normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
        return ' '.join(normalized.split())

    def delete_student(self, student_id: str) -> bool:
        # teacher_student_links, diary_entries e pdis são deletados via CASCADE
        return self._delete(student_id)


# ---------------------------------------------------------------------------
# Teachers  (FK: school_id → schools)
# ---------------------------------------------------------------------------

class TeacherPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, TeacherRecord)

    def _to_entity(self, record: TeacherRecord) -> Dict:
        return {
            'id': record.id,
            'school_id': record.school_id or '',
            'name': record.name or '',
            'email': record.email or '',
            'phone': record.phone or '',
            'specialization': record.specialization or '',
            'notes': record.notes or '',
            'school_name': record.school_name or '',
            'anonymized_data': dict(record.anonymized_data or {}),
            'created_at': record.created_at,
            'updated_at': record.updated_at,
        }

    def create_teacher(
        self,
        teacher_data: Dict,
        teacher_id: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        teacher_id = teacher_id or str(uuid.uuid4())
        data = dict(teacher_data)
        for k in ('id', 'created_at', 'updated_at', 'anonymized_data'):
            data.pop(k, None)

        school_id = data.pop('school_id', None) or None
        name = data.pop('name', '') or ''
        email = data.pop('email', '') or ''
        phone = data.pop('phone', '') or ''
        specialization = data.pop('specialization', '') or ''
        notes = data.pop('notes', '') or ''
        school_name = data.pop('school_name', '') or ''

        anonymized_data = {
            'teacher_id': teacher_id,
            'school_id': school_id or '',
            'specialization': specialization,
        }

        with self._session() as session:
            record = TeacherRecord(
                id=teacher_id,
                school_id=school_id,
                name=name,
                email=email,
                phone=phone,
                specialization=specialization,
                notes=notes,
                school_name=school_name,
                anonymized_data=anonymized_data,
                created_at=created_at or now,
                updated_at=updated_at or now,
            )
            session.merge(record)
            return self._to_entity(record)

    def _sync_student_links(self, session: Session, teacher_id: str, student_ids: List[str]) -> None:
        """
        Sincroniza a tabela teacher_student_links para o professor:
        apaga vínculos antigos e insere os novos.
        Ignora student_ids que não existam na tabela students (evita FK violation).
        """
        session.execute(
            delete(TeacherStudentLinkRecord).where(
                TeacherStudentLinkRecord.teacher_id == teacher_id
            )
        )
        now = now_brasilia_iso()
        seen = set()
        for sid in student_ids:
            sid = (sid or '').strip()
            if not sid or sid in seen:
                continue
            seen.add(sid)
            # Verifica se o student existe antes de inserir (evita FK violation)
            exists = session.execute(
                select(StudentRecord.id).where(StudentRecord.id == sid)
            ).scalar_one_or_none()
            if exists is None:
                continue
            session.add(TeacherStudentLinkRecord(
                id=str(uuid.uuid4()),
                teacher_id=teacher_id,
                student_id=sid,
                created_at=now,
            ))

    def update_teacher(self, teacher_id: str, teacher_data: Dict) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(TeacherRecord, teacher_id)
            if not record:
                return None

            data = dict(teacher_data)
            for k in ('id', 'created_at', 'updated_at', 'anonymized_data'):
                data.pop(k, None)

            # Extrai student_ids antes de processar os demais campos
            raw_student_ids = data.pop('student_ids', None)

            if 'school_id' in data:
                record.school_id = data.pop('school_id') or None
            record.name = data.get('name', record.name) or record.name
            record.email = data.get('email', record.email)
            record.phone = data.get('phone', record.phone)
            record.specialization = data.get('specialization', record.specialization)
            record.notes = data.get('notes', record.notes)
            record.school_name = data.get('school_name', record.school_name)

            record.anonymized_data = {
                'teacher_id': teacher_id,
                'school_id': record.school_id or '',
                'specialization': record.specialization or '',
            }

            record.updated_at = now_brasilia_iso()

            if raw_student_ids is not None:
                self._sync_student_links(session, teacher_id, [str(s) for s in raw_student_ids if s])

            session.flush()
            return self._to_entity(record)

    def get_teacher(self, teacher_id: str) -> Optional[Dict]:
        return self._get(teacher_id)

    def list_teachers_by_scope(self, scope: Dict) -> List[Dict]:
        """
        Retorna docentes filtrados por escopo via JOIN SQL — sem N+1.
        scope: {'role', 'school_id', 'municipio_id', 'teacher_ids'}
        """
        role = (scope.get('role') or '').lower()
        school_id = (scope.get('school_id') or '').strip()
        municipio_id = (scope.get('municipio_id') or '').strip()
        teacher_ids = scope.get('teacher_ids') or []

        with self._session() as session:
            stmt = select(TeacherRecord)

            if role == 'admin':
                pass  # sem filtro
            elif role == 'professor':
                # Professor vê apenas seu(s) próprio(s) registro(s) de docente
                if not teacher_ids:
                    return []
                stmt = stmt.where(TeacherRecord.id.in_(teacher_ids))
            elif role == 'coordenacao' or (role == 'viewer' and school_id):
                if not school_id:
                    return []
                stmt = stmt.where(TeacherRecord.school_id == school_id)
            elif role == 'secretaria' or (role == 'viewer' and municipio_id):
                if not municipio_id:
                    return []
                stmt = (stmt
                        .join(SchoolRecord, TeacherRecord.school_id == SchoolRecord.id)
                        .where(SchoolRecord.municipio_id == municipio_id))
            else:
                return []

            rows = session.execute(stmt).scalars().all()

        summaries = []
        for row in rows:
            teacher = self._to_entity(row)
            summaries.append({
                'id': teacher['id'],
                'name': teacher.get('name', ''),
                'school_id': teacher.get('school_id', ''),
                'school_name': teacher.get('school_name', ''),
                'specialization': teacher.get('specialization', ''),
                'updated_at': teacher['updated_at'],
            })
        return sorted(summaries, key=lambda x: x['name'].lower())

    def list_all_teachers(self) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(select(TeacherRecord)).scalars().all()

        summaries = []
        for row in rows:
            teacher = self._to_entity(row)
            summaries.append({
                'id': teacher['id'],
                'name': teacher.get('name', ''),
                'school_id': teacher.get('school_id', ''),
                'school_name': teacher.get('school_name', ''),
                'specialization': teacher.get('specialization', ''),
                'updated_at': teacher['updated_at'],
            })

        return sorted(summaries, key=lambda value: value['name'].lower())

    def delete_teacher(self, teacher_id: str) -> bool:
        return self._delete(teacher_id)


# ---------------------------------------------------------------------------
# Municipalities  (sem FKs)
# ---------------------------------------------------------------------------

class MunicipalityPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, MunicipalityRecord)

    def create_municipality(
        self,
        municipio_id: str,
        name: str,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        created_at = created_at or now
        updated_at = updated_at or now

        payload = {'name': name}

        with self._session() as session:
            existing = session.get(MunicipalityRecord, municipio_id)
            if existing:
                raise ValueError('Municipio já existe')

            record = MunicipalityRecord(
                id=municipio_id,
                payload=payload,
                created_at=created_at,
                updated_at=updated_at,
            )
            session.add(record)
            session.flush()
            return self._to_entity(record)

    def update_municipality(
        self,
        municipio_id: str,
        name: str,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(MunicipalityRecord, municipio_id)
            if not record:
                return None

            record.payload = {'name': name}
            if created_at:
                record.created_at = created_at
            record.updated_at = updated_at or now_brasilia_iso()
            return self._to_entity(record)

    def get_municipality(self, municipio_id: str) -> Optional[Dict]:
        return self._get(municipio_id)

    def list_all_municipalities(self) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(select(MunicipalityRecord)).scalars().all()

        municipalities = [self._to_entity(row) for row in rows]
        return sorted(municipalities, key=lambda value: (value.get('name') or '').lower())

    def delete_municipality(self, municipio_id: str) -> bool:
        return self._delete(municipio_id)


# ---------------------------------------------------------------------------
# Diary  (FK: student_id → students CASCADE)
# ---------------------------------------------------------------------------

class DiaryPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, DiaryEntryRecord)

    def _to_entity(self, record: DiaryEntryRecord) -> Dict:
        teacher_names = list(record.teacher_names or [])
        return {
            'id': record.id,
            'student_id': record.student_id or '',
            'source': record.source or '',
            'status': record.status or '',
            'attendance': record.attendance or '',
            'diary_date': record.diary_date or '',
            'student_name': record.student_name or '',
            'open_obs': record.open_obs or '',
            'absence_explanation': record.absence_explanation or '',
            'answers': dict(record.answers or {}),
            'teachers': teacher_names,
            'teacher_names': teacher_names,
            'teacher_ids': list(record.teacher_ids or []),
            'parse_warnings': list(record.parse_warnings or []),
            'anonymized_data': dict(record.anonymized_data or {}),
            'created_at': record.created_at,
            'updated_at': record.updated_at or '',
            'is_deleted': bool(record.is_deleted),
            'deleted_at': record.deleted_at or '',
            'deleted_by': record.deleted_by or '',
            'last_edited_by': record.last_edited_by or '',
            'last_edited_at': record.last_edited_at or '',
        }

    def _normalize_name(self, value: str) -> str:
        import unicodedata
        normalized = unicodedata.normalize('NFKD', (value or '').strip().lower())
        normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
        return ' '.join(normalized.split())

    def _entry_matches_student(self, entry: Dict, student_id: Optional[str], student_name: str) -> bool:
        entry_student_id = (entry.get('student_id') or '').strip()
        if student_id and entry_student_id:
            return entry_student_id == student_id

        if student_name:
            return self._normalize_name(entry.get('student_name', '')) == self._normalize_name(student_name)

        return False

    def save_entry(
        self,
        student_name: str,
        teachers: List[str],
        diary_date: str,
        answers: Dict,
        open_obs: str,
        attendance: str = 'presente',
        absence_explanation: str = '',
        student_id: Optional[str] = None,
        status: str = 'final',
        source: str = 'manual',
        parse_warnings: Optional[List[str]] = None,
        entry_id: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        entry_id = entry_id or str(uuid.uuid4())

        with self._session() as session:
            teacher_ids = _resolve_teacher_ids(session, teachers or [], student_id)

            school_id: Optional[str] = None
            if student_id:
                school_id = session.execute(
                    select(StudentRecord.school_id).where(StudentRecord.id == student_id)
                ).scalar_one_or_none()

            anonymized_data = {
                'student_id': student_id or '',
                'teacher_ids': teacher_ids,
                'school_id': school_id or '',
                'diary_date': diary_date,
                'attendance': attendance,
                'answers': dict(answers or {}),
                'open_obs': open_obs or '',
                'absence_explanation': absence_explanation or '',
                'parse_warnings': list(parse_warnings or []),
                'status': status,
                'source': source,
            }

            record = DiaryEntryRecord(
                id=entry_id,
                student_id=student_id or None,
                source=source,
                status=status,
                attendance=attendance,
                diary_date=diary_date,
                student_name=student_name,
                open_obs=open_obs,
                absence_explanation=absence_explanation,
                answers=dict(answers or {}),
                teacher_names=list(teachers or []),
                teacher_ids=teacher_ids,
                parse_warnings=list(parse_warnings or []),
                anonymized_data=anonymized_data,
                created_at=created_at or now,
                updated_at=updated_at,
            )
            session.merge(record)
            return self._to_entity(record)

    def get_entry(self, entry_id: str) -> Optional[Dict]:
        return self._get(entry_id)

    def list_all_entries(self) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(
                select(DiaryEntryRecord).where(DiaryEntryRecord.is_deleted == False)  # noqa: E712
            ).scalars().all()
        return [self._to_entity(row) for row in rows]

    def count_entries_by_student_in_range(
        self, student_ids: List[str], start_date: str = '', end_date: str = ''
    ) -> Dict[str, int]:
        """Conta entradas por student_id num período, numa única query (evita N+1)."""
        if not student_ids:
            return {}
        with self._session() as session:
            stmt = select(DiaryEntryRecord.student_id, func.count(DiaryEntryRecord.id)).where(
                DiaryEntryRecord.student_id.in_(student_ids),
                DiaryEntryRecord.is_deleted == False,  # noqa: E712
            )
            if start_date:
                stmt = stmt.where(DiaryEntryRecord.diary_date >= start_date)
            if end_date:
                stmt = stmt.where(DiaryEntryRecord.diary_date <= end_date)
            stmt = stmt.group_by(DiaryEntryRecord.student_id)
            rows = session.execute(stmt).all()
        return {row[0]: row[1] for row in rows if row[0]}

    def get_entries_by_student(
        self,
        student_name: str,
        student_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict]:
        with self._session() as session:
            if student_id:
                # Caminho rápido: usa o índice da coluna FK student_id
                conditions = [
                    DiaryEntryRecord.student_id == student_id,
                    DiaryEntryRecord.is_deleted == False,  # noqa: E712
                ]
                if start_date:
                    conditions.append(DiaryEntryRecord.diary_date >= start_date)
                if end_date:
                    conditions.append(DiaryEntryRecord.diary_date <= end_date)
                rows = session.execute(
                    select(DiaryEntryRecord).where(*conditions)
                ).scalars().all()
                entries = [self._to_entity(row) for row in rows]
            else:
                # Fallback por nome: full scan (student_id não disponível)
                conditions = [DiaryEntryRecord.is_deleted == False]  # noqa: E712
                if start_date:
                    conditions.append(DiaryEntryRecord.diary_date >= start_date)
                if end_date:
                    conditions.append(DiaryEntryRecord.diary_date <= end_date)
                rows = session.execute(
                    select(DiaryEntryRecord).where(*conditions)
                ).scalars().all()
                entities = [self._to_entity(row) for row in rows]
                entries = [e for e in entities
                           if self._entry_matches_student(e, None, student_name)]

        return sorted(entries, key=lambda x: x.get('diary_date', ''), reverse=True)

    def count_entries_by_student(self, student_name: str, student_id: Optional[str] = None) -> int:
        """Retorna o total de entradas não deletadas de um aluno, sem filtro de data."""
        with self._session() as session:
            if student_id:
                result = session.execute(
                    select(func.count()).select_from(DiaryEntryRecord).where(
                        DiaryEntryRecord.student_id == student_id,
                        DiaryEntryRecord.is_deleted == False,  # noqa: E712
                    )
                ).scalar()
            else:
                result = session.execute(
                    select(func.count()).select_from(DiaryEntryRecord).where(
                        DiaryEntryRecord.is_deleted == False,  # noqa: E712
                        DiaryEntryRecord.student_name == student_name,
                    )
                ).scalar()
            return int(result or 0)

    def has_date_conflict(self, student_id: Optional[str], student_name: str, diary_date: str) -> bool:
        if not diary_date:
            return False
        # Reutiliza get_entries_by_student que já usa o índice FK
        entries = self.get_entries_by_student(student_name, student_id=student_id)
        return any((e.get('diary_date') or '') == diary_date for e in entries)

    def update_entry(
        self,
        entry_id: str,
        student_name: str,
        teachers: List[str],
        diary_date: str,
        answers: Dict,
        open_obs: str,
        attendance: str = 'presente',
        absence_explanation: str = '',
        student_id: Optional[str] = None,
        status: str = 'final',
        source: str = 'manual',
        parse_warnings: Optional[List[str]] = None,
        last_edited_by: Optional[str] = None,
        last_edited_at: Optional[str] = None,
    ) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(DiaryEntryRecord, entry_id)
            if not record:
                return None

            if student_id is not None:
                record.student_id = student_id or None

            teacher_ids = _resolve_teacher_ids(session, teachers or [], record.student_id)

            school_id: Optional[str] = None
            if record.student_id:
                school_id = session.execute(
                    select(StudentRecord.school_id).where(StudentRecord.id == record.student_id)
                ).scalar_one_or_none()

            record.source = source
            record.status = status
            record.attendance = attendance
            record.diary_date = diary_date
            record.student_name = student_name
            record.open_obs = open_obs
            record.absence_explanation = absence_explanation
            record.answers = dict(answers or {})
            record.teacher_names = list(teachers or [])
            record.teacher_ids = teacher_ids
            record.parse_warnings = list(parse_warnings or [])
            record.anonymized_data = {
                'student_id': record.student_id or '',
                'teacher_ids': teacher_ids,
                'school_id': school_id or '',
                'diary_date': diary_date,
                'attendance': attendance,
                'answers': dict(answers or {}),
                'open_obs': open_obs or '',
                'absence_explanation': absence_explanation or '',
                'parse_warnings': list(parse_warnings or []),
                'status': status,
                'source': source,
            }
            record.updated_at = now_brasilia_iso()
            return self._to_entity(record)

    def delete_entry(self, entry_id: str, deleted_by: Optional[str] = None) -> bool:
        with self._session() as session:
            record = session.get(DiaryEntryRecord, entry_id)
            if not record:
                return False
            record.is_deleted = True
            record.deleted_at = now_brasilia_iso()
            record.deleted_by = deleted_by or ''
            return True

    def delete_entries_by_student(self, student_name: str, student_id: Optional[str] = None, deleted_by: Optional[str] = None) -> int:
        now = now_brasilia_iso()
        with self._session() as session:
            if student_id:
                rows = session.execute(
                    select(DiaryEntryRecord).where(
                        DiaryEntryRecord.student_id == student_id,
                        DiaryEntryRecord.is_deleted == False,  # noqa: E712
                    )
                ).scalars().all()
            else:
                all_rows = session.execute(
                    select(DiaryEntryRecord).where(DiaryEntryRecord.is_deleted == False)  # noqa: E712
                ).scalars().all()
                rows = [r for r in all_rows
                        if self._entry_matches_student(self._to_entity(r), None, student_name)]

            for row in rows:
                row.is_deleted = True
                row.deleted_at = now
                row.deleted_by = deleted_by or ''

            return len(rows)

    def get_last_teachers(self, student_name: str, student_id: Optional[str] = None) -> List[str]:
        entries = self.get_entries_by_student(student_name, student_id=student_id)
        if entries:
            return entries[0].get('teachers', [])
        return []

    def get_student_summary(self, student_name: str, student_id: Optional[str] = None) -> Optional[Dict]:
        entries = self.get_entries_by_student(student_name, student_id=student_id)
        if not entries:
            return None

        last_entry = entries[0]
        return {
            'student_id': last_entry.get('student_id'),
            'student_name': student_name,
            'last_date': last_entry.get('diary_date', ''),
            'last_teachers': last_entry.get('teachers', []),
            'total_entries': len(entries),
        }

    def _group_into_summaries(self, entries: List[Dict]) -> List[Dict]:
        """Agrupa entradas de diário por aluno e retorna resumos ordenados por nome."""
        grouped: Dict[str, Dict] = {}
        by_key: Dict[str, List[Dict]] = {}

        for entry in entries:
            student_id = (entry.get('student_id') or '').strip()
            student_name = entry.get('student_name') or ''
            key = f"id:{student_id}" if student_id else f"name:{self._normalize_name(student_name)}"

            if key not in grouped:
                grouped[key] = {'student_id': student_id or None, 'student_name': student_name}
                by_key[key] = []
            by_key[key].append(entry)

        summaries = []
        for key, group in grouped.items():
            entries_sorted = sorted(by_key[key], key=lambda x: x.get('diary_date', ''), reverse=True)
            if not entries_sorted:
                continue
            last = entries_sorted[0]
            summaries.append({
                'student_id': group['student_id'],
                'student_name': group['student_name'],
                'last_date': last.get('diary_date', ''),
                'last_teachers': last.get('teachers', []),
                'total_entries': len(entries_sorted),
            })

        return sorted(summaries, key=lambda x: (x.get('student_name') or '').lower())

    def list_all_summaries(self) -> List[Dict]:
        return self._group_into_summaries(self.list_all_entries())

    def list_diary_summaries_by_scope(self, scope: Dict) -> List[Dict]:
        """
        Retorna resumos de diário filtrados por escopo via JOIN SQL — sem N+1.
        scope: {'role', 'school_id', 'municipio_id', 'teacher_ids'}
        """
        role = (scope.get('role') or '').lower()
        school_id = (scope.get('school_id') or '').strip()
        municipio_id = (scope.get('municipio_id') or '').strip()
        teacher_ids = scope.get('teacher_ids') or []

        with self._session() as session:
            stmt = select(DiaryEntryRecord).where(DiaryEntryRecord.is_deleted == False)  # noqa: E712

            if role == 'admin':
                pass  # sem filtro adicional
            elif role == 'coordenacao' or (role == 'viewer' and school_id):
                if not school_id:
                    return []
                stmt = (stmt
                        .join(StudentRecord, DiaryEntryRecord.student_id == StudentRecord.id)
                        .where(StudentRecord.school_id == school_id))
            elif role == 'secretaria' or (role == 'viewer' and municipio_id):
                if not municipio_id:
                    return []
                stmt = (stmt
                        .join(StudentRecord, DiaryEntryRecord.student_id == StudentRecord.id)
                        .join(SchoolRecord, StudentRecord.school_id == SchoolRecord.id)
                        .where(SchoolRecord.municipio_id == municipio_id))
            elif role == 'professor':
                if not teacher_ids:
                    return []
                stmt = (stmt
                        .join(TeacherStudentLinkRecord,
                              DiaryEntryRecord.student_id == TeacherStudentLinkRecord.student_id)
                        .where(TeacherStudentLinkRecord.teacher_id.in_(teacher_ids))
                        .distinct(DiaryEntryRecord.id))
            else:
                return []

            rows = session.execute(stmt).scalars().all()

        return self._group_into_summaries([self._to_entity(row) for row in rows])

    def link_entries_to_student(self, student_id: str, student_name: str) -> int:
        """Vincula entradas sem student_id à coluna FK pelo nome do aluno."""
        if not student_id or not student_name:
            return 0

        normalized_name = self._normalize_name(student_name)
        linked_count = 0

        with self._session() as session:
            rows = session.execute(
                select(DiaryEntryRecord).where(DiaryEntryRecord.student_id.is_(None))
            ).scalars().all()
            for row in rows:
                if self._normalize_name(row.student_name or '') != normalized_name:
                    continue
                row.student_id = student_id
                row.student_name = student_name
                linked_count += 1

        return linked_count


# ---------------------------------------------------------------------------
# Family Diary  (Diário Familiar — escrito pelos responsáveis; FK: student_id →
# students CASCADE, author_user_id → user_profiles CASCADE)
# ---------------------------------------------------------------------------

class FamilyDiaryPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, FamilyDiaryEntryRecord)

    @staticmethod
    def _to_entity(record: FamilyDiaryEntryRecord) -> Dict:
        return {
            'id': record.id,
            'student_id': record.student_id or '',
            'author_user_id': record.author_user_id or '',
            'author_name': record.author_name or '',
            'entry_date': record.entry_date or '',
            'observations': record.observations or '',
            'created_at': record.created_at,
            'updated_at': record.updated_at or '',
            'is_deleted': bool(record.is_deleted),
            'deleted_at': record.deleted_at or '',
            'deleted_by': record.deleted_by or '',
        }

    def count_entries_by_student_in_range(
        self, student_ids: List[str], start_date: str = '', end_date: str = ''
    ) -> Dict[str, int]:
        """Conta entradas por student_id num período, numa única query (evita N+1)."""
        if not student_ids:
            return {}
        with self._session() as session:
            stmt = select(FamilyDiaryEntryRecord.student_id, func.count(FamilyDiaryEntryRecord.id)).where(
                FamilyDiaryEntryRecord.student_id.in_(student_ids),
                FamilyDiaryEntryRecord.is_deleted == False,  # noqa: E712
            )
            if start_date:
                stmt = stmt.where(FamilyDiaryEntryRecord.entry_date >= start_date)
            if end_date:
                stmt = stmt.where(FamilyDiaryEntryRecord.entry_date <= end_date)
            stmt = stmt.group_by(FamilyDiaryEntryRecord.student_id)
            rows = session.execute(stmt).all()
        return {row[0]: row[1] for row in rows if row[0]}

    def create_entry(
        self,
        student_id: str,
        author_user_id: str,
        author_name: str,
        entry_date: str,
        observations: str,
    ) -> Dict:
        now = now_brasilia_iso()
        entry_id = str(uuid.uuid4())
        with self._session() as session:
            record = FamilyDiaryEntryRecord(
                id=entry_id,
                student_id=student_id,
                author_user_id=author_user_id,
                author_name=author_name,
                entry_date=entry_date,
                observations=observations,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            return self._to_entity(record)

    def get_entry(self, entry_id: str) -> Optional[Dict]:
        return self._get(entry_id)

    def get_entries_by_student(self, student_id: str) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(
                select(FamilyDiaryEntryRecord).where(
                    FamilyDiaryEntryRecord.student_id == student_id,
                    FamilyDiaryEntryRecord.is_deleted == False,  # noqa: E712
                )
            ).scalars().all()
        entries = [self._to_entity(row) for row in rows]
        return sorted(entries, key=lambda x: x.get('created_at', ''), reverse=True)

    def update_entry(self, entry_id: str, observations: str, entry_date: Optional[str] = None) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(FamilyDiaryEntryRecord, entry_id)
            if not record:
                return None
            record.observations = observations
            if entry_date is not None:
                record.entry_date = entry_date
            record.updated_at = now_brasilia_iso()
            return self._to_entity(record)

    def delete_entry(self, entry_id: str, deleted_by: Optional[str] = None) -> bool:
        with self._session() as session:
            record = session.get(FamilyDiaryEntryRecord, entry_id)
            if not record:
                return False
            record.is_deleted = True
            record.deleted_at = now_brasilia_iso()
            record.deleted_by = deleted_by or ''
            return True


# ---------------------------------------------------------------------------
# Diary Summary  (Resumo Diário — resumos de IA salvos a partir de entradas do
# diário escolar e/ou familiar; FK: student_id → students CASCADE,
# author_user_id → user_profiles CASCADE)
# ---------------------------------------------------------------------------

class DiarySummaryPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, DiarySummaryRecord)

    @staticmethod
    def _to_entity(record: DiarySummaryRecord) -> Dict:
        return {
            'id': record.id,
            'student_id': record.student_id or '',
            'author_user_id': record.author_user_id or '',
            'author_name': record.author_name or '',
            'period_start': record.period_start or '',
            'period_end': record.period_end or '',
            'summary_text': record.summary_text or '',
            'source_entries': list(record.source_entries or []),
            'created_at': record.created_at,
            'is_deleted': bool(record.is_deleted),
        }

    def create_summary(
        self,
        student_id: str,
        author_user_id: str,
        author_name: str,
        period_start: str,
        period_end: str,
        summary_text: str,
        source_entries: List[Dict],
    ) -> Dict:
        now = now_brasilia_iso()
        with self._session() as session:
            record = DiarySummaryRecord(
                id=str(uuid.uuid4()),
                student_id=student_id,
                author_user_id=author_user_id,
                author_name=author_name,
                period_start=period_start,
                period_end=period_end,
                summary_text=summary_text,
                source_entries=list(source_entries or []),
                created_at=now,
            )
            session.add(record)
            session.flush()
            return self._to_entity(record)

    def get_summaries_by_student(self, student_id: str) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(
                select(DiarySummaryRecord).where(
                    DiarySummaryRecord.student_id == student_id,
                    DiarySummaryRecord.is_deleted == False,  # noqa: E712
                )
            ).scalars().all()
        summaries = [self._to_entity(row) for row in rows]
        return sorted(summaries, key=lambda x: x.get('created_at', ''), reverse=True)

    def get_summary(self, summary_id: str) -> Optional[Dict]:
        return self._get(summary_id)

    def delete_summary(self, summary_id: str, deleted_by: Optional[str] = None) -> bool:
        with self._session() as session:
            record = session.get(DiarySummaryRecord, summary_id)
            if not record:
                return False
            record.is_deleted = True
            record.deleted_at = now_brasilia_iso()
            record.deleted_by = deleted_by or ''
            return True


# ---------------------------------------------------------------------------
# PDI  (FK: student_id → students CASCADE)
# ---------------------------------------------------------------------------

class PDIPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, PDIRecord)

    def _to_entity(self, record: PDIRecord) -> Dict:
        teacher_names = list(record.teacher_names or [])
        return {
            'id': record.id,
            'student_id': record.student_id or '',
            'student_name': record.student_name or '',
            'student_grade': record.student_grade or '',
            'class': record.class_name or '',
            'diagnosis': record.diagnosis or '',
            'birth_date': record.birth_date or '',
            'teachers': teacher_names,
            'teacher_names': teacher_names,
            'teacher_ids': list(record.teacher_ids or []),
            'trimesters': dict(record.trimesters or {}),
            'anonymized_data': dict(record.anonymized_data or {}),
            'created_at': record.created_at,
            'updated_at': record.updated_at,
        }

    def _normalize_name(self, value: str) -> str:
        import unicodedata
        normalized = unicodedata.normalize('NFKD', (value or '').strip().lower())
        normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
        return ' '.join(normalized.split())

    def _pdi_matches_student(self, pdi: Dict, student_id: Optional[str], student_name: str) -> bool:
        pdi_student_id = (pdi.get('student_id') or '').strip()
        if student_id and pdi_student_id:
            return pdi_student_id == student_id

        if student_name:
            return self._normalize_name(pdi.get('student_name', '')) == self._normalize_name(student_name)

        return False

    def save_pdi(
        self,
        student_name: str,
        birth_date: str,
        diagnosis: str,
        class_name: str,
        teachers: List[str],
        trimesters: Dict,
        student_id: Optional[str] = None,
        student_grade: Optional[str] = None,
        pdi_id: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        pdi_id = pdi_id or str(uuid.uuid4())

        normalized_trimesters = normalize_trimesters(
            trimesters,
            subject_ids=get_pdi_subject_ids_for_grade(student_grade),
        )

        with self._session() as session:
            teacher_ids = _resolve_teacher_ids(session, teachers or [], student_id)

            school_id: Optional[str] = None
            if student_id:
                school_id = session.execute(
                    select(StudentRecord.school_id).where(StudentRecord.id == student_id)
                ).scalar_one_or_none()

            anonymized_data = {
                'student_id': student_id or '',
                'teacher_ids': teacher_ids,
                'school_id': school_id or '',
                'student_grade': student_grade or '',
                'class': class_name or '',
                'diagnosis': diagnosis or '',
                'trimesters': normalized_trimesters,
            }

            record = PDIRecord(
                id=pdi_id,
                student_id=student_id or None,
                student_name=student_name,
                student_grade=student_grade or '',
                class_name=class_name,
                diagnosis=diagnosis,
                birth_date=birth_date,
                teacher_names=list(teachers or []),
                teacher_ids=teacher_ids,
                trimesters=normalized_trimesters,
                anonymized_data=anonymized_data,
                created_at=created_at or now,
                updated_at=updated_at or now,
            )
            session.merge(record)
            return self._to_entity(record)

    def update_pdi(
        self,
        pdi_id: str,
        student_name: str,
        birth_date: str,
        diagnosis: str,
        class_name: str,
        teachers: List[str],
        trimesters: Dict,
        student_id: Optional[str] = None,
        student_grade: Optional[str] = None,
    ) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(PDIRecord, pdi_id)
            if not record:
                return None

            if student_id is not None:
                record.student_id = student_id or None

            effective_grade = student_grade or record.student_grade or ''
            normalized_trimesters = normalize_trimesters(
                trimesters,
                subject_ids=get_pdi_subject_ids_for_grade(effective_grade),
            )

            teacher_ids = _resolve_teacher_ids(session, teachers or [], record.student_id)

            school_id: Optional[str] = None
            if record.student_id:
                school_id = session.execute(
                    select(StudentRecord.school_id).where(StudentRecord.id == record.student_id)
                ).scalar_one_or_none()

            record.student_name = student_name
            record.student_grade = effective_grade
            record.class_name = class_name
            record.diagnosis = diagnosis
            record.birth_date = birth_date
            record.teacher_names = list(teachers or [])
            record.teacher_ids = teacher_ids
            record.trimesters = normalized_trimesters
            record.anonymized_data = {
                'student_id': record.student_id or '',
                'teacher_ids': teacher_ids,
                'school_id': school_id or '',
                'student_grade': effective_grade,
                'class': class_name or '',
                'diagnosis': diagnosis or '',
                'trimesters': normalized_trimesters,
            }
            record.updated_at = now_brasilia_iso()
            return self._to_entity(record)

    def normalize_existing_pdis(self) -> int:
        updated_count = 0
        with self._session() as session:
            rows = session.execute(select(PDIRecord)).scalars().all()
            for row in rows:
                normalized_trimesters = normalize_trimesters(
                    row.trimesters,
                    subject_ids=get_pdi_subject_ids_for_grade(row.student_grade),
                )
                if normalized_trimesters == (row.trimesters or {}):
                    continue

                row.trimesters = normalized_trimesters
                row.updated_at = now_brasilia_iso()
                updated_count += 1

        return updated_count

    def get_pdi(self, pdi_id: str) -> Optional[Dict]:
        return self._get(pdi_id)

    def _get_pdis_by_student_id(self, session: Session, student_id: str) -> List[Dict]:
        """Busca PDIs por student_id usando o índice FK — caminho rápido."""
        rows = session.execute(
            select(PDIRecord).where(PDIRecord.student_id == student_id)
        ).scalars().all()
        return [self._to_entity(row) for row in rows]

    def get_pdi_by_student(self, student_name: str, student_id: Optional[str] = None) -> Optional[Dict]:
        with self._session() as session:
            if student_id:
                # Caminho rápido: usa índice FK
                pdis = self._get_pdis_by_student_id(session, student_id)
            else:
                # Fallback por nome: full scan
                rows = session.execute(select(PDIRecord)).scalars().all()
                all_pdis = [self._to_entity(row) for row in rows]
                pdis = [p for p in all_pdis
                        if self._pdi_matches_student(p, None, student_name)]

        if pdis:
            return sorted(pdis, key=lambda x: x.get('updated_at', ''), reverse=True)[0]
        return None

    def has_pdi_for_student(self, student_name: str, student_id: Optional[str] = None, exclude_pdi_id: Optional[str] = None) -> bool:
        with self._session() as session:
            if student_id:
                # Caminho rápido: usa índice FK
                pdis = self._get_pdis_by_student_id(session, student_id)
            else:
                rows = session.execute(select(PDIRecord)).scalars().all()
                all_pdis = [self._to_entity(row) for row in rows]
                pdis = [p for p in all_pdis
                        if self._pdi_matches_student(p, None, student_name)]

        for pdi in pdis:
            if exclude_pdi_id and pdi.get('id') == exclude_pdi_id:
                continue
            return True
        return False

    def list_all_full_pdis(self) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(select(PDIRecord)).scalars().all()
        return [self._to_entity(row) for row in rows]

    def _pdi_to_summary(self, pdi: Dict) -> Dict:
        return {
            'id': pdi['id'],
            'student_id': pdi.get('student_id'),
            'student_name': pdi.get('student_name', ''),
            'student_grade': pdi.get('student_grade', pdi.get('grade', '')),
            'class': pdi.get('class', ''),
            'diagnosis': pdi.get('diagnosis', ''),
            'updated_at': pdi.get('updated_at', ''),
            'teachers': pdi.get('teachers', []),
        }

    def list_all_pdis(self) -> List[Dict]:
        summaries = [self._pdi_to_summary(p) for p in self.list_all_full_pdis()]
        return sorted(summaries, key=lambda x: x.get('updated_at', ''), reverse=True)

    def list_pdis_by_scope(self, scope: Dict) -> List[Dict]:
        """
        Retorna PDIs filtrados por escopo via JOIN SQL — sem N+1.
        scope: {'role', 'school_id', 'municipio_id', 'teacher_ids'}
        """
        role = (scope.get('role') or '').lower()
        school_id = (scope.get('school_id') or '').strip()
        municipio_id = (scope.get('municipio_id') or '').strip()
        teacher_ids = scope.get('teacher_ids') or []

        with self._session() as session:
            stmt = select(PDIRecord)

            if role == 'admin':
                pass  # sem filtro
            elif role == 'coordenacao' or (role == 'viewer' and school_id):
                if not school_id:
                    return []
                stmt = (stmt
                        .join(StudentRecord, PDIRecord.student_id == StudentRecord.id)
                        .where(StudentRecord.school_id == school_id))
            elif role == 'secretaria' or (role == 'viewer' and municipio_id):
                if not municipio_id:
                    return []
                stmt = (stmt
                        .join(StudentRecord, PDIRecord.student_id == StudentRecord.id)
                        .join(SchoolRecord, StudentRecord.school_id == SchoolRecord.id)
                        .where(SchoolRecord.municipio_id == municipio_id))
            elif role == 'professor':
                if not teacher_ids:
                    return []
                stmt = (stmt
                        .join(TeacherStudentLinkRecord,
                              PDIRecord.student_id == TeacherStudentLinkRecord.student_id)
                        .where(TeacherStudentLinkRecord.teacher_id.in_(teacher_ids))
                        .distinct(PDIRecord.id))
            else:
                return []

            rows = session.execute(stmt).scalars().all()

        summaries = [self._pdi_to_summary(self._to_entity(row)) for row in rows]
        return sorted(summaries, key=lambda x: x.get('updated_at', ''), reverse=True)

    def delete_pdi(self, pdi_id: str) -> bool:
        return self._delete(pdi_id)

    def link_pdis_to_student(self, student_id: str, student_name: str) -> int:
        """Vincula PDIs sem student_id à coluna FK pelo nome do aluno."""
        if not student_id or not student_name:
            return 0

        normalized_name = self._normalize_name(student_name)
        linked_count = 0

        with self._session() as session:
            rows = session.execute(
                select(PDIRecord).where(PDIRecord.student_id.is_(None))
            ).scalars().all()
            for row in rows:
                if self._normalize_name(row.student_name or '') != normalized_name:
                    continue
                row.student_id = student_id
                row.student_name = student_name
                row.updated_at = now_brasilia_iso()
                linked_count += 1

        return linked_count


# ---------------------------------------------------------------------------
# Form Submissions  (sem FKs)
# ---------------------------------------------------------------------------

class FormSubmissionsPostgresRepository:
    FORM_TO_MODEL = {
        'cadastro_aluno': CaseStudySubmissionRecord,
        'cadastro_escola': SchoolRegistrationSubmissionRecord,
    }

    FORM_TO_NAME = {
        'cadastro_aluno': 'Estudo de Caso',
        'cadastro_escola': 'Cadastro da Escola',
    }

    def __init__(self, session_factory):
        self._session_factory = session_factory

    @contextmanager
    def _session(self):
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _resolve_model(self, form_id: str):
        model = self.FORM_TO_MODEL.get(form_id)
        if not model:
            raise ValueError('form_id inválido para persistência')
        return model

    def _to_submission(self, row, form_id: str) -> Dict:
        return {
            'id': row.id,
            'form_id': form_id,
            'form_name': self.FORM_TO_NAME.get(form_id, form_id),
            'answers': dict(row.answers or {}),
            'metadata': dict(row.metadata_json or {}),
            'submitted_at': row.submitted_at,
        }

    def save_submission(
        self,
        form_id: str,
        answers: Dict,
        metadata: Optional[Dict] = None,
        submission_id: Optional[str] = None,
        submitted_at: Optional[str] = None,
    ) -> Dict:
        model = self._resolve_model(form_id)
        submission_id = submission_id or str(uuid.uuid4())
        submitted_at = submitted_at or now_brasilia_iso()

        with self._session() as session:
            row = model(
                id=submission_id,
                answers=dict(answers or {}),
                metadata_json=dict(metadata or {}),
                submitted_at=submitted_at,
            )
            session.merge(row)
            return self._to_submission(row, form_id)

    def list_all_submissions(self) -> List[Dict]:
        with self._session() as session:
            case_rows = session.execute(select(CaseStudySubmissionRecord)).scalars().all()
            school_rows = session.execute(select(SchoolRegistrationSubmissionRecord)).scalars().all()

        result = [self._to_submission(row, 'cadastro_aluno') for row in case_rows]
        result.extend(self._to_submission(row, 'cadastro_escola') for row in school_rows)
        return sorted(result, key=lambda item: item.get('submitted_at', ''), reverse=True)

    def get_submission(self, submission_id: str) -> Optional[Dict]:
        with self._session() as session:
            row = session.get(CaseStudySubmissionRecord, submission_id)
            if row:
                return self._to_submission(row, 'cadastro_aluno')

            row = session.get(SchoolRegistrationSubmissionRecord, submission_id)
            if row:
                return self._to_submission(row, 'cadastro_escola')

        return None

    def get_submission_by_pre_registration(self, form_id: str, pre_registration_id: str) -> Optional[Dict]:
        if not pre_registration_id:
            return None

        model = self._resolve_model(form_id)
        pre_registration_id = str(pre_registration_id)

        with self._session() as session:
            rows = session.execute(select(model)).scalars().all()
            for row in rows:
                metadata = dict(row.metadata_json or {})
                if str(metadata.get('pre_registration_id', '')) == pre_registration_id:
                    return self._to_submission(row, form_id)

        return None

    def delete_submission(self, submission_id: str) -> bool:
        with self._session() as session:
            row = session.get(CaseStudySubmissionRecord, submission_id)
            if row:
                session.delete(row)
                return True

            row = session.get(SchoolRegistrationSubmissionRecord, submission_id)
            if row:
                session.delete(row)
                return True

        return False

    def delete_by_pre_registration(self, form_id: str, pre_registration_id: str) -> int:
        if not pre_registration_id:
            return 0

        model = self._resolve_model(form_id)
        pre_registration_id = str(pre_registration_id)

        with self._session() as session:
            rows = session.execute(select(model)).scalars().all()
            to_delete = []
            for row in rows:
                metadata = dict(row.metadata_json or {})
                if str(metadata.get('pre_registration_id', '')) == pre_registration_id:
                    to_delete.append(row)

            for row in to_delete:
                session.delete(row)

            return len(to_delete)

    def get_form_counts(self) -> Dict[str, int]:
        with self._session() as session:
            case_count = len(session.execute(select(CaseStudySubmissionRecord.id)).all())
            school_count = len(session.execute(select(SchoolRegistrationSubmissionRecord.id)).all())

        return {
            'cadastro_aluno': case_count,
            'cadastro_escola': school_count,
        }


# ---------------------------------------------------------------------------
# Object Storage  (sem FK formal — referência polimórfica)
# ---------------------------------------------------------------------------

class ObjectStorageMetadataPostgresRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @contextmanager
    def _session(self):
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _to_entity(record: ObjectStorageFileRecord) -> Dict:
        return {
            'id': record.id,
            'doc_type': record.doc_type,
            'reference_id': record.reference_id,
            'bucket': record.bucket,
            'object_key': record.object_key,
            'original_filename': record.original_filename,
            'mime_type': record.mime_type,
            'size_bytes': record.size_bytes,
            'student_id': record.student_id or '',
            'school_id': record.school_id or '',
            'extra': dict(record.extra_json or {}),
            'created_at': record.created_at,
            'updated_at': record.updated_at,
        }

    def upsert_file(
        self,
        doc_type: str,
        reference_id: str,
        bucket: str,
        object_key: str,
        original_filename: str,
        mime_type: str,
        size_bytes: int,
        extra: Optional[Dict] = None,
        student_id: Optional[str] = None,
        school_id: Optional[str] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        doc_type = str(doc_type or '').strip()
        reference_id = str(reference_id or '').strip()

        with self._session() as session:
            record = session.execute(
                select(ObjectStorageFileRecord).where(
                    ObjectStorageFileRecord.doc_type == doc_type,
                    ObjectStorageFileRecord.reference_id == reference_id,
                )
            ).scalar_one_or_none()

            if record is None:
                record = ObjectStorageFileRecord(
                    id=str(uuid.uuid4()),
                    doc_type=doc_type,
                    reference_id=reference_id,
                    bucket=bucket,
                    object_key=object_key,
                    original_filename=original_filename,
                    mime_type=mime_type,
                    size_bytes=max(0, int(size_bytes or 0)),
                    student_id=student_id or None,
                    school_id=school_id or None,
                    extra_json=dict(extra or {}),
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
                session.flush()
                return self._to_entity(record)

            record.bucket = bucket
            record.object_key = object_key
            record.original_filename = original_filename
            record.mime_type = mime_type
            record.size_bytes = max(0, int(size_bytes or 0))
            if student_id is not None:
                record.student_id = student_id or None
            if school_id is not None:
                record.school_id = school_id or None
            record.extra_json = dict(extra or {})
            record.updated_at = now
            session.flush()
            return self._to_entity(record)

    def get_file(self, doc_type: str, reference_id: str) -> Optional[Dict]:
        with self._session() as session:
            record = session.execute(
                select(ObjectStorageFileRecord).where(
                    ObjectStorageFileRecord.doc_type == str(doc_type or '').strip(),
                    ObjectStorageFileRecord.reference_id == str(reference_id or '').strip(),
                )
            ).scalar_one_or_none()
            if not record:
                return None
            return self._to_entity(record)

    def list_files(self, doc_type: str, bucket: Optional[str] = None) -> List[Dict]:
        with self._session() as session:
            stmt = select(ObjectStorageFileRecord).where(
                ObjectStorageFileRecord.doc_type == str(doc_type or '').strip(),
            )
            if bucket:
                stmt = stmt.where(ObjectStorageFileRecord.bucket == str(bucket).strip())

            records = session.execute(stmt).scalars().all()
            entities = [self._to_entity(record) for record in records]
            entities.sort(key=lambda item: item.get('created_at') or '', reverse=True)
            return entities

    def delete_file(self, doc_type: str, reference_id: str) -> bool:
        with self._session() as session:
            record = session.execute(
                select(ObjectStorageFileRecord).where(
                    ObjectStorageFileRecord.doc_type == str(doc_type or '').strip(),
                    ObjectStorageFileRecord.reference_id == str(reference_id or '').strip(),
                )
            ).scalar_one_or_none()
            if not record:
                return False
            session.delete(record)
            return True


# ---------------------------------------------------------------------------
# PEI  (Planos Educacionais Individualizados gerados por IA)
# ---------------------------------------------------------------------------

class PEIPostgresRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @contextmanager
    def _session(self):
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _to_entity(self, record: PEIRecord, include_markdown: bool = False) -> Dict:
        entity = {
            'id': record.id,
            'student_id': record.student_id or '',
            'student_name': record.student_name or '',
            'school': record.school or '',
            'generated_by_user_id': record.generated_by_user_id or '',
            'generated_by_username': record.generated_by_username or '',
            'pdf_filename': record.pdf_filename or '',
            'object_key': record.object_key or '',
            'bucket': record.bucket or '',
            'created_at': record.created_at,
        }
        if include_markdown:
            entity['markdown'] = record.markdown or ''
        return entity

    def save(
        self,
        student_name: str,
        school: str,
        markdown_text: str,
        pdf_filename: str,
        object_key: str,
        bucket: str,
        student_id: Optional[str] = None,
        generated_by_user_id: Optional[str] = None,
        generated_by_username: Optional[str] = None,
        pei_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Dict:
        pei_id = pei_id or str(uuid.uuid4())
        record = PEIRecord(
            id=pei_id,
            student_id=student_id or None,
            student_name=student_name,
            school=school,
            generated_by_user_id=generated_by_user_id or None,
            generated_by_username=generated_by_username or None,
            pdf_filename=pdf_filename,
            object_key=object_key,
            bucket=bucket,
            markdown=markdown_text,
            created_at=created_at or now_brasilia_iso(),
        )
        with self._session() as session:
            session.merge(record)
        return self._to_entity(record, include_markdown=True)

    def get(self, pei_id: str) -> Optional[Dict]:
        with self._session() as session:
            record = session.execute(
                select(PEIRecord).where(PEIRecord.id == str(pei_id).strip())
            ).scalar_one_or_none()
            if not record:
                return None
            return self._to_entity(record, include_markdown=True)

    def list_all(self) -> List[Dict]:
        with self._session() as session:
            records = session.execute(
                select(PEIRecord).order_by(PEIRecord.created_at.desc())
            ).scalars().all()
            return [self._to_entity(r) for r in records]

    def delete(self, pei_id: str) -> bool:
        with self._session() as session:
            record = session.execute(
                select(PEIRecord).where(PEIRecord.id == str(pei_id).strip())
            ).scalar_one_or_none()
            if not record:
                return False
            session.delete(record)
            return True


# ---------------------------------------------------------------------------
# Chat  (FKs nas sessões e mensagens)
# ---------------------------------------------------------------------------

class ChatHistoryPostgresRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @contextmanager
    def _session(self):
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _to_session(record: ChatSessionRecord) -> Dict:
        return {
            'id': record.id,
            'session_date': record.session_date,
            'created_by_user_id': record.created_by_user_id,
            'created_by_username': record.created_by_username,
            'created_by_role': record.created_by_role,
            'municipio_id': record.municipio_id or '',
            'school_id': record.school_id or '',
            'teacher_id': record.teacher_id or '',
            'student_id': record.student_id or '',
            'student_name': record.student_name or '',
            'school_name': record.school_name or '',
            'extra': dict(record.extra_json or {}),
            'created_at': record.created_at,
            'updated_at': record.updated_at,
        }

    @staticmethod
    def _to_message(record: ChatMessageRecord) -> Dict:
        return {
            'id': record.id,
            'session_id': record.session_id,
            'message_index': int(record.message_index or 0),
            'role': record.role,
            'content': record.content,
            'user_id': record.user_id or '',
            'username': record.username or '',
            'sources': dict(record.sources_json or {}),
            'extra': dict(record.extra_json or {}),
            'created_at': record.created_at,
            'updated_at': record.updated_at,
        }

    def create_or_update_session(
        self,
        session_id: str,
        session_date: str,
        created_by_user_id: str,
        created_by_username: str,
        created_by_role: str,
        municipio_id: str = '',
        school_id: str = '',
        teacher_id: str = '',
        student_id: str = '',
        student_name: str = '',
        school_name: str = '',
        extra: Optional[Dict] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        session_id = str(session_id or '').strip() or str(uuid.uuid4())
        session_date = str(session_date or '').strip() or now[:10]

        with self._session() as session:
            record = session.get(ChatSessionRecord, session_id)
            if record is None:
                record = ChatSessionRecord(
                    id=session_id,
                    session_date=session_date,
                    created_by_user_id=str(created_by_user_id or '').strip(),
                    created_by_username=str(created_by_username or '').strip(),
                    created_by_role=str(created_by_role or '').strip(),
                    municipio_id=str(municipio_id or '').strip() or None,
                    school_id=str(school_id or '').strip() or None,
                    teacher_id=str(teacher_id or '').strip() or None,
                    student_id=str(student_id or '').strip() or None,
                    student_name=str(student_name or '').strip() or None,
                    school_name=str(school_name or '').strip() or None,
                    extra_json=dict(extra or {}),
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
                session.flush()
                return self._to_session(record)

            record.session_date = session_date
            record.municipio_id = str(municipio_id or '').strip() or None
            record.school_id = str(school_id or '').strip() or None
            record.teacher_id = str(teacher_id or '').strip() or None
            record.student_id = str(student_id or '').strip() or None
            record.student_name = str(student_name or '').strip() or None
            record.school_name = str(school_name or '').strip() or None
            record.extra_json = dict(extra or {})
            record.updated_at = now
            session.flush()
            return self._to_session(record)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: str = '',
        username: str = '',
        sources: Optional[Dict] = None,
        extra: Optional[Dict] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        session_id = str(session_id or '').strip()
        if not session_id:
            raise ValueError('session_id é obrigatório')

        with self._session() as session:
            existing_rows = session.execute(
                select(ChatMessageRecord).where(ChatMessageRecord.session_id == session_id)
            ).scalars().all()
            next_index = len(existing_rows)

            row = ChatMessageRecord(
                id=str(uuid.uuid4()),
                session_id=session_id,
                message_index=next_index,
                role=str(role or '').strip() or 'assistant',
                content=str(content or '').strip(),
                user_id=str(user_id or '').strip() or None,
                username=str(username or '').strip() or None,
                sources_json=dict(sources or {}),
                extra_json=dict(extra or {}),
                created_at=now,
                updated_at=now,
            )
            session.add(row)

            session_row = session.get(ChatSessionRecord, session_id)
            if session_row:
                session_row.updated_at = now

            session.flush()
            return self._to_message(row)

    def get_session(self, session_id: str) -> Optional[Dict]:
        with self._session() as session:
            row = session.get(ChatSessionRecord, session_id)
            if not row:
                return None
            return self._to_session(row)

    def list_sessions(
        self,
        day: str = '',
        student_id: str = '',
    ) -> List[Dict]:
        with self._session() as session:
            stmt = select(ChatSessionRecord)

            day = str(day or '').strip()
            student_id = str(student_id or '').strip()
            if day:
                stmt = stmt.where(ChatSessionRecord.session_date == day)
            if student_id:
                stmt = stmt.where(ChatSessionRecord.student_id == student_id)

            rows = session.execute(stmt).scalars().all()
            entities = [self._to_session(row) for row in rows]
            entities.sort(key=lambda item: item.get('updated_at') or '', reverse=True)
            return entities

    def list_messages(self, session_id: str) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(
                select(ChatMessageRecord).where(
                    ChatMessageRecord.session_id == str(session_id or '').strip()
                )
            ).scalars().all()
            entities = [self._to_message(row) for row in rows]
            entities.sort(key=lambda item: item.get('message_index', 0))
            return entities

    def delete_session(self, session_id: str) -> bool:
        session_id = str(session_id or '').strip()
        if not session_id:
            return False

        with self._session() as session:
            session_row = session.get(ChatSessionRecord, session_id)
            if not session_row:
                return False

            rows = session.execute(
                select(ChatMessageRecord).where(ChatMessageRecord.session_id == session_id)
            ).scalars().all()
            for row in rows:
                session.delete(row)

            session.delete(session_row)
            return True


# ---------------------------------------------------------------------------
# Bootstrap — cria tabelas, migra dados e aplica FK constraints
# ---------------------------------------------------------------------------

def _run_migration(engine) -> None:
    """
    Migração idempotente em 3 fases:
      1. Adiciona colunas FK que ainda não existem
      2. Preenche colunas a partir dos payloads JSON e popula teacher_student_links
      3. Remove campos FK do JSON e aplica as constraints formais
    """

    # ── FASE 0 — criar índices nas colunas FK usadas em JOINs ───────────────
    # Necessário caso as tabelas tenham sido criadas antes do ORM declarar index=True.
    index_stmts = [
        "CREATE INDEX IF NOT EXISTS idx_schools_municipio_id        ON public.schools(municipio_id)",
        "CREATE INDEX IF NOT EXISTS idx_teachers_school_id          ON public.teachers(school_id)",
        "CREATE INDEX IF NOT EXISTS idx_students_school_id          ON public.students(school_id)",
        "CREATE INDEX IF NOT EXISTS idx_diary_entries_student_id    ON public.diary_entries(student_id)",
        "CREATE INDEX IF NOT EXISTS idx_pdis_student_id             ON public.pdis(student_id)",
        "CREATE INDEX IF NOT EXISTS idx_tsl_teacher_id              ON public.teacher_student_links(teacher_id)",
        "CREATE INDEX IF NOT EXISTS idx_tsl_student_id              ON public.teacher_student_links(student_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_profiles_role          ON public.user_profiles(role)",
        "CREATE INDEX IF NOT EXISTS idx_user_profiles_school_id     ON public.user_profiles(school_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_profiles_municipio_id  ON public.user_profiles(municipio_id)",
    ]

    # ── FASE 1 — adicionar colunas (IF NOT EXISTS é idempotente) ────────────
    schema_stmts = [
        # schools
        "ALTER TABLE public.schools ADD COLUMN IF NOT EXISTS municipio_id VARCHAR(64)",
        # teachers
        "ALTER TABLE public.teachers ADD COLUMN IF NOT EXISTS school_id VARCHAR(64)",
        # students
        "ALTER TABLE public.students ADD COLUMN IF NOT EXISTS school_id VARCHAR(64)",
        # diary_entries
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS student_id VARCHAR(64)",
        # pdis
        "ALTER TABLE public.pdis ADD COLUMN IF NOT EXISTS student_id VARCHAR(64)",
        # teacher_student_links (pode já existir via SQL script do Supabase)
        """
        CREATE TABLE IF NOT EXISTS public.teacher_student_links (
            id          VARCHAR(64) PRIMARY KEY,
            teacher_id  VARCHAR(64) NOT NULL,
            student_id  VARCHAR(64) NOT NULL,
            created_at  VARCHAR(40) NOT NULL,
            UNIQUE (teacher_id, student_id)
        )
        """,
        # patches históricos de user_profiles
        "ALTER TABLE public.user_profiles DROP CONSTRAINT IF EXISTS user_profiles_id_fkey",
        "ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS password_hash TEXT",
        "ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS full_name TEXT",
    ]

    # ── FASE 2 — backfill das colunas FK a partir do payload JSON ───────────
    backfill_stmts = [
        # schools ← municipio_id
        """
        UPDATE public.schools
        SET    municipio_id = payload->>'municipio_id'
        WHERE  municipio_id IS NULL
        AND    payload->>'municipio_id' IS NOT NULL
        AND    payload->>'municipio_id' <> ''
        AND    EXISTS (
                   SELECT 1 FROM public.municipalities
                   WHERE id = payload->>'municipio_id'
               )
        """,
        # teachers ← school_id
        """
        UPDATE public.teachers
        SET    school_id = payload->>'school_id'
        WHERE  school_id IS NULL
        AND    payload->>'school_id' IS NOT NULL
        AND    payload->>'school_id' <> ''
        AND    EXISTS (
                   SELECT 1 FROM public.schools
                   WHERE id = payload->>'school_id'
               )
        """,
        # students ← school_id
        """
        UPDATE public.students
        SET    school_id = payload->>'school_id'
        WHERE  school_id IS NULL
        AND    payload->>'school_id' IS NOT NULL
        AND    payload->>'school_id' <> ''
        AND    EXISTS (
                   SELECT 1 FROM public.schools
                   WHERE id = payload->>'school_id'
               )
        """,
        # diary_entries ← student_id
        """
        UPDATE public.diary_entries
        SET    student_id = payload->>'student_id'
        WHERE  student_id IS NULL
        AND    payload->>'student_id' IS NOT NULL
        AND    payload->>'student_id' <> ''
        AND    EXISTS (
                   SELECT 1 FROM public.students
                   WHERE id = payload->>'student_id'
               )
        """,
        # pdis ← student_id
        """
        UPDATE public.pdis
        SET    student_id = payload->>'student_id'
        WHERE  student_id IS NULL
        AND    payload->>'student_id' IS NOT NULL
        AND    payload->>'student_id' <> ''
        AND    EXISTS (
                   SELECT 1 FROM public.students
                   WHERE id = payload->>'student_id'
               )
        """,
        # teacher_student_links ← teacher_ids[] do payload de students
        # Usa json_* (não jsonb_*) pois a coluna payload é do tipo json
        """
        INSERT INTO public.teacher_student_links (id, teacher_id, student_id, created_at)
        SELECT
            gen_random_uuid(),
            tid.teacher_id,
            s.id,
            now()
        FROM public.students s,
        LATERAL (
            SELECT json_array_elements_text(
                CASE
                    WHEN json_typeof(s.payload->'teacher_ids') = 'array'
                        THEN s.payload->'teacher_ids'
                    WHEN s.payload->>'teacher_id' IS NOT NULL
                     AND s.payload->>'teacher_id' <> ''
                        THEN json_build_array(s.payload->>'teacher_id')
                    ELSE '[]'::json
                END
            ) AS teacher_id
        ) AS tid
        WHERE tid.teacher_id <> ''
        AND   EXISTS (SELECT 1 FROM public.teachers WHERE id = tid.teacher_id)
        ON CONFLICT (teacher_id, student_id) DO NOTHING
        """,
    ]

    # ── FASE 3a — limpa campos FK dos payloads JSON ─────────────────────────
    # payload é do tipo json (não jsonb): usa cast ::jsonb para os operadores
    # - e ? e depois converte de volta para ::json ao salvar.
    # Não precisa de WHERE pois remover chave inexistente é no-op no jsonb.
    cleanup_stmts = [
        "UPDATE public.schools       SET payload = (payload::jsonb - 'municipio_id')::json",
        "UPDATE public.teachers      SET payload = (payload::jsonb - 'school_id')::json",
        "UPDATE public.students      SET payload = (payload::jsonb - 'school_id' - 'teacher_id' - 'teacher_ids')::json",
        "UPDATE public.diary_entries SET payload = (payload::jsonb - 'student_id')::json",
        "UPDATE public.pdis          SET payload = (payload::jsonb - 'student_id')::json",
    ]

    # ── FASE 3b — nullifica referências órfãs antes de criar constraints ────
    orphan_cleanup_stmts = [
        # user_profiles
        "UPDATE public.user_profiles SET municipio_id = NULL WHERE municipio_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.municipalities WHERE id = user_profiles.municipio_id)",
        "UPDATE public.user_profiles SET school_id    = NULL WHERE school_id    IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.schools        WHERE id = user_profiles.school_id)",
        "UPDATE public.user_profiles SET teacher_id   = NULL WHERE teacher_id   IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.teachers       WHERE id = user_profiles.teacher_id)",
        # chat_sessions
        "UPDATE public.chat_sessions SET municipio_id = NULL WHERE municipio_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.municipalities WHERE id = chat_sessions.municipio_id)",
        "UPDATE public.chat_sessions SET school_id    = NULL WHERE school_id    IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.schools        WHERE id = chat_sessions.school_id)",
        "UPDATE public.chat_sessions SET teacher_id   = NULL WHERE teacher_id   IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.teachers       WHERE id = chat_sessions.teacher_id)",
        "UPDATE public.chat_sessions SET student_id   = NULL WHERE student_id   IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.students       WHERE id = chat_sessions.student_id)",
        # chat_messages
        "UPDATE public.chat_messages SET user_id = NULL WHERE user_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.user_profiles WHERE id = chat_messages.user_id)",
    ]

    # ── FASE 5 — cria colunas individuais (idempotente) ────────────────────
    normalize_schema_stmts = [
        # schools
        "ALTER TABLE public.schools ADD COLUMN IF NOT EXISTS name TEXT",
        "ALTER TABLE public.schools ADD COLUMN IF NOT EXISTS cnpj TEXT",
        "ALTER TABLE public.schools ADD COLUMN IF NOT EXISTS institution_type TEXT",
        "ALTER TABLE public.schools ADD COLUMN IF NOT EXISTS address JSON",
        "ALTER TABLE public.schools ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE public.schools ADD COLUMN IF NOT EXISTS school_registration_completed BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE public.schools ADD COLUMN IF NOT EXISTS registration_answers JSON",
        "ALTER TABLE public.schools ADD COLUMN IF NOT EXISTS anonymized_data JSON",
        # teachers
        "ALTER TABLE public.teachers ADD COLUMN IF NOT EXISTS name TEXT",
        "ALTER TABLE public.teachers ADD COLUMN IF NOT EXISTS email TEXT",
        "ALTER TABLE public.teachers ADD COLUMN IF NOT EXISTS phone TEXT",
        "ALTER TABLE public.teachers ADD COLUMN IF NOT EXISTS specialization TEXT",
        "ALTER TABLE public.teachers ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE public.teachers ADD COLUMN IF NOT EXISTS school_name TEXT",
        "ALTER TABLE public.teachers ADD COLUMN IF NOT EXISTS anonymized_data JSON",
        # students
        "ALTER TABLE public.students ADD COLUMN IF NOT EXISTS name TEXT",
        "ALTER TABLE public.students ADD COLUMN IF NOT EXISTS age TEXT",
        "ALTER TABLE public.students ADD COLUMN IF NOT EXISTS birth_date VARCHAR(20)",
        'ALTER TABLE public.students ADD COLUMN IF NOT EXISTS "class" TEXT',
        "ALTER TABLE public.students ADD COLUMN IF NOT EXISTS grade TEXT",
        "ALTER TABLE public.students ADD COLUMN IF NOT EXISTS school_name TEXT",
        "ALTER TABLE public.students ADD COLUMN IF NOT EXISTS case_study_completed BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE public.students ADD COLUMN IF NOT EXISTS case_study_answers JSON",
        "ALTER TABLE public.students ADD COLUMN IF NOT EXISTS anonymized_data JSON",
        # diary_entries
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS source TEXT",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS status TEXT",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS attendance TEXT",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS diary_date VARCHAR(10)",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS student_name TEXT",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS open_obs TEXT",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS absence_explanation TEXT",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS answers JSON",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS teacher_names JSON",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS teacher_ids JSON",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS parse_warnings JSON",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS anonymized_data JSON",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS deleted_at VARCHAR(40)",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS deleted_by TEXT",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS last_edited_by TEXT",
        "ALTER TABLE public.diary_entries ADD COLUMN IF NOT EXISTS last_edited_at VARCHAR(40)",
        # pdis
        "ALTER TABLE public.pdis ADD COLUMN IF NOT EXISTS student_name TEXT",
        "ALTER TABLE public.pdis ADD COLUMN IF NOT EXISTS student_grade TEXT",
        'ALTER TABLE public.pdis ADD COLUMN IF NOT EXISTS "class" TEXT',
        "ALTER TABLE public.pdis ADD COLUMN IF NOT EXISTS diagnosis TEXT",
        "ALTER TABLE public.pdis ADD COLUMN IF NOT EXISTS birth_date VARCHAR(20)",
        "ALTER TABLE public.pdis ADD COLUMN IF NOT EXISTS guardian_names JSON",
        "ALTER TABLE public.pdis ADD COLUMN IF NOT EXISTS teacher_names JSON",
        "ALTER TABLE public.pdis ADD COLUMN IF NOT EXISTS teacher_ids JSON",
        "ALTER TABLE public.pdis ADD COLUMN IF NOT EXISTS trimesters JSON",
        "ALTER TABLE public.pdis ADD COLUMN IF NOT EXISTS anonymized_data JSON",
        # object_storage_files
        "ALTER TABLE public.object_storage_files ADD COLUMN IF NOT EXISTS student_id VARCHAR(64)",
        "ALTER TABLE public.object_storage_files ADD COLUMN IF NOT EXISTS school_id VARCHAR(64)",
    ]

    # ── FASE 6 — backfill das colunas a partir do payload JSON ───────────────
    # payload é tipo json, então usamos payload->>'campo' para texto e payload->'campo' para json
    normalize_backfill_stmts = [
        # schools
        """
        UPDATE public.schools SET
            name                         = COALESCE(name, payload->>'name'),
            cnpj                         = COALESCE(cnpj, payload->>'cnpj'),
            institution_type             = COALESCE(institution_type, payload->>'institution_type'),
            address                      = COALESCE(address, payload->'address'),
            notes                        = COALESCE(notes, payload->>'notes'),
            school_registration_completed = CASE
                WHEN school_registration_completed = FALSE
                 AND payload->>'school_registration_completed' = 'true'
                THEN TRUE ELSE school_registration_completed END,
            anonymized_data = COALESCE(anonymized_data, json_build_object(
                'school_id', id,
                'municipio_id', COALESCE(municipio_id, ''),
                'institution_type', COALESCE(payload->>'institution_type', '')
            ))
        WHERE payload IS NOT NULL
        """,
        # teachers
        """
        UPDATE public.teachers SET
            name           = COALESCE(name, payload->>'name'),
            email          = COALESCE(email, payload->>'email'),
            phone          = COALESCE(phone, payload->>'phone'),
            specialization = COALESCE(specialization, payload->>'specialization'),
            notes          = COALESCE(notes, payload->>'notes'),
            school_name    = COALESCE(school_name, payload->>'school_name'),
            anonymized_data = COALESCE(anonymized_data, json_build_object(
                'teacher_id', id,
                'school_id', COALESCE(school_id, ''),
                'specialization', COALESCE(payload->>'specialization', '')
            ))
        WHERE payload IS NOT NULL
        """,
        # students
        """
        UPDATE public.students SET
            name                  = COALESCE(name, payload->>'name', payload->>'studentName'),
            age                   = COALESCE(age, payload->>'age', payload->>'studentAge'),
            "class"               = COALESCE("class", payload->>'class', payload->>'className'),
            grade                 = COALESCE(grade, payload->>'grade', payload->>'schoolYear'),
            school_name           = COALESCE(school_name, payload->>'school_name', payload->>'schoolName'),
            case_study_completed  = CASE
                WHEN case_study_completed = FALSE
                 AND payload->>'case_study_completed' = 'true'
                THEN TRUE ELSE case_study_completed END,
            anonymized_data = COALESCE(anonymized_data, json_build_object(
                'student_id', id,
                'school_id', COALESCE(school_id, ''),
                'age', COALESCE(payload->>'age', payload->>'studentAge', ''),
                'grade', COALESCE(payload->>'grade', payload->>'schoolYear', ''),
                'class', COALESCE(payload->>'class', payload->>'className', '')
            ))
        WHERE payload IS NOT NULL
        """,
        # diary_entries
        """
        UPDATE public.diary_entries SET
            source               = COALESCE(source, payload->>'source'),
            status               = COALESCE(status, payload->>'status'),
            attendance           = COALESCE(attendance, payload->>'attendance'),
            diary_date           = COALESCE(diary_date, payload->>'diary_date'),
            student_name         = COALESCE(student_name, payload->>'student_name'),
            open_obs             = COALESCE(open_obs, payload->>'open_obs'),
            absence_explanation  = COALESCE(absence_explanation, payload->>'absence_explanation'),
            answers              = COALESCE(answers, payload->'answers'),
            teacher_names        = COALESCE(teacher_names,
                CASE WHEN json_typeof(payload->'teachers') = 'array' THEN payload->'teachers' ELSE NULL END),
            parse_warnings       = COALESCE(parse_warnings,
                CASE WHEN json_typeof(payload->'parse_warnings') = 'array' THEN payload->'parse_warnings' ELSE '[]'::json END),
            anonymized_data = COALESCE(anonymized_data, json_build_object(
                'student_id', COALESCE(student_id, ''),
                'teacher_ids', '[]'::json,
                'school_id', '',
                'diary_date', COALESCE(payload->>'diary_date', ''),
                'attendance', COALESCE(payload->>'attendance', ''),
                'answers', COALESCE(payload->'answers', '{}'::json),
                'open_obs', COALESCE(payload->>'open_obs', ''),
                'absence_explanation', COALESCE(payload->>'absence_explanation', ''),
                'parse_warnings', COALESCE(CASE WHEN json_typeof(payload->'parse_warnings') = 'array' THEN payload->'parse_warnings' ELSE NULL END, '[]'::json),
                'status', COALESCE(payload->>'status', ''),
                'source', COALESCE(payload->>'source', '')
            ))
        WHERE payload IS NOT NULL
        """,
        # pdis
        """
        UPDATE public.pdis SET
            student_name  = COALESCE(student_name, payload->>'student_name'),
            student_grade = COALESCE(student_grade, payload->>'student_grade', payload->>'grade'),
            "class"       = COALESCE("class", payload->>'class'),
            diagnosis     = COALESCE(diagnosis, payload->>'diagnosis'),
            birth_date    = COALESCE(birth_date, payload->>'birth_date'),
            guardian_names = COALESCE(guardian_names,
                CASE WHEN json_typeof(payload->'guardians') = 'array' THEN payload->'guardians' ELSE NULL END),
            teacher_names  = COALESCE(teacher_names,
                CASE WHEN json_typeof(payload->'teachers') = 'array' THEN payload->'teachers' ELSE NULL END),
            trimesters     = COALESCE(trimesters,
                CASE WHEN json_typeof(payload->'trimesters') = 'object' THEN payload->'trimesters' ELSE NULL END),
            anonymized_data = COALESCE(anonymized_data, json_build_object(
                'student_id', COALESCE(student_id, ''),
                'teacher_ids', '[]'::json,
                'school_id', '',
                'student_grade', COALESCE(payload->>'student_grade', payload->>'grade', ''),
                'class', COALESCE(payload->>'class', ''),
                'diagnosis', COALESCE(payload->>'diagnosis', ''),
                'trimesters', COALESCE(CASE WHEN json_typeof(payload->'trimesters') = 'object' THEN payload->'trimesters' ELSE NULL END, '{}'::json)
            ))
        WHERE payload IS NOT NULL
        """,
        # object_storage_files — vincula student_id pela coluna extra.student_name via students.name
        """
        UPDATE public.object_storage_files osf
        SET student_id = s.id
        FROM public.students s
        WHERE osf.student_id IS NULL
          AND osf.extra->>'student_name' IS NOT NULL
          AND lower(trim(s.name)) = lower(trim(osf.extra->>'student_name'))
        """,
    ]

    # ── FASE 6b — torna payload nullable para que INSERTs funcionem mesmo
    #             que o DROP COLUMN ainda não tenha sido executado ──────────
    make_payload_nullable_stmts = [
        "ALTER TABLE public.schools ALTER COLUMN payload DROP NOT NULL",
        "ALTER TABLE public.teachers ALTER COLUMN payload DROP NOT NULL",
        "ALTER TABLE public.students ALTER COLUMN payload DROP NOT NULL",
        "ALTER TABLE public.diary_entries ALTER COLUMN payload DROP NOT NULL",
        "ALTER TABLE public.pdis ALTER COLUMN payload DROP NOT NULL",
    ]

    # ── FASE 7 — remove colunas payload (após backfill concluído) ─────────
    # Requer que as funções/policies RLS não referenciem mais payload.
    # Rodar scripts/phase2_scope_core_policies.sql e
    # scripts/phase2.5_additional_policies.sql no Supabase antes de reiniciar.
    drop_payload_stmts = [
        "ALTER TABLE public.schools DROP COLUMN IF EXISTS payload",
        "ALTER TABLE public.teachers DROP COLUMN IF EXISTS payload",
        "ALTER TABLE public.students DROP COLUMN IF EXISTS payload",
        "ALTER TABLE public.diary_entries DROP COLUMN IF EXISTS payload",
        "ALTER TABLE public.pdis DROP COLUMN IF EXISTS payload",
    ]

    # ── FASE 3c — cria/recria as FK constraints ──────────────────────────────
    constraint_stmts = [
        # schools
        "ALTER TABLE public.schools DROP CONSTRAINT IF EXISTS fk_schools_municipio",
        "ALTER TABLE public.schools ADD CONSTRAINT fk_schools_municipio FOREIGN KEY (municipio_id) REFERENCES public.municipalities(id) ON DELETE SET NULL",
        # teachers
        "ALTER TABLE public.teachers DROP CONSTRAINT IF EXISTS fk_teachers_school",
        "ALTER TABLE public.teachers ADD CONSTRAINT fk_teachers_school FOREIGN KEY (school_id) REFERENCES public.schools(id) ON DELETE SET NULL",
        # students
        "ALTER TABLE public.students DROP CONSTRAINT IF EXISTS fk_students_school",
        "ALTER TABLE public.students ADD CONSTRAINT fk_students_school FOREIGN KEY (school_id) REFERENCES public.schools(id) ON DELETE SET NULL",
        # teacher_student_links
        "ALTER TABLE public.teacher_student_links DROP CONSTRAINT IF EXISTS fk_tsl_teacher",
        "ALTER TABLE public.teacher_student_links ADD CONSTRAINT fk_tsl_teacher FOREIGN KEY (teacher_id) REFERENCES public.teachers(id) ON DELETE CASCADE",
        "ALTER TABLE public.teacher_student_links DROP CONSTRAINT IF EXISTS fk_tsl_student",
        "ALTER TABLE public.teacher_student_links ADD CONSTRAINT fk_tsl_student FOREIGN KEY (student_id) REFERENCES public.students(id) ON DELETE CASCADE",
        # diary_entries
        "ALTER TABLE public.diary_entries DROP CONSTRAINT IF EXISTS fk_diary_student",
        "ALTER TABLE public.diary_entries ADD CONSTRAINT fk_diary_student FOREIGN KEY (student_id) REFERENCES public.students(id) ON DELETE CASCADE",
        # pdis
        "ALTER TABLE public.pdis DROP CONSTRAINT IF EXISTS fk_pdis_student",
        "ALTER TABLE public.pdis ADD CONSTRAINT fk_pdis_student FOREIGN KEY (student_id) REFERENCES public.students(id) ON DELETE CASCADE",
        # user_profiles
        "ALTER TABLE public.user_profiles DROP CONSTRAINT IF EXISTS fk_user_profiles_municipio",
        "ALTER TABLE public.user_profiles ADD CONSTRAINT fk_user_profiles_municipio FOREIGN KEY (municipio_id) REFERENCES public.municipalities(id) ON DELETE SET NULL",
        "ALTER TABLE public.user_profiles DROP CONSTRAINT IF EXISTS fk_user_profiles_school",
        "ALTER TABLE public.user_profiles ADD CONSTRAINT fk_user_profiles_school FOREIGN KEY (school_id) REFERENCES public.schools(id) ON DELETE SET NULL",
        "ALTER TABLE public.user_profiles DROP CONSTRAINT IF EXISTS fk_user_profiles_teacher",
        "ALTER TABLE public.user_profiles ADD CONSTRAINT fk_user_profiles_teacher FOREIGN KEY (teacher_id) REFERENCES public.teachers(id) ON DELETE SET NULL",
        # chat_sessions
        "ALTER TABLE public.chat_sessions DROP CONSTRAINT IF EXISTS fk_chat_sessions_user",
        "ALTER TABLE public.chat_sessions ADD CONSTRAINT fk_chat_sessions_user FOREIGN KEY (created_by_user_id) REFERENCES public.user_profiles(id) ON DELETE CASCADE",
        "ALTER TABLE public.chat_sessions DROP CONSTRAINT IF EXISTS fk_chat_sessions_municipio",
        "ALTER TABLE public.chat_sessions ADD CONSTRAINT fk_chat_sessions_municipio FOREIGN KEY (municipio_id) REFERENCES public.municipalities(id) ON DELETE SET NULL",
        "ALTER TABLE public.chat_sessions DROP CONSTRAINT IF EXISTS fk_chat_sessions_school",
        "ALTER TABLE public.chat_sessions ADD CONSTRAINT fk_chat_sessions_school FOREIGN KEY (school_id) REFERENCES public.schools(id) ON DELETE SET NULL",
        "ALTER TABLE public.chat_sessions DROP CONSTRAINT IF EXISTS fk_chat_sessions_teacher",
        "ALTER TABLE public.chat_sessions ADD CONSTRAINT fk_chat_sessions_teacher FOREIGN KEY (teacher_id) REFERENCES public.teachers(id) ON DELETE SET NULL",
        "ALTER TABLE public.chat_sessions DROP CONSTRAINT IF EXISTS fk_chat_sessions_student",
        "ALTER TABLE public.chat_sessions ADD CONSTRAINT fk_chat_sessions_student FOREIGN KEY (student_id) REFERENCES public.students(id) ON DELETE SET NULL",
        # chat_messages
        "ALTER TABLE public.chat_messages DROP CONSTRAINT IF EXISTS fk_chat_messages_session",
        "ALTER TABLE public.chat_messages ADD CONSTRAINT fk_chat_messages_session FOREIGN KEY (session_id) REFERENCES public.chat_sessions(id) ON DELETE CASCADE",
        "ALTER TABLE public.chat_messages DROP CONSTRAINT IF EXISTS fk_chat_messages_user",
        "ALTER TABLE public.chat_messages ADD CONSTRAINT fk_chat_messages_user FOREIGN KEY (user_id) REFERENCES public.user_profiles(id) ON DELETE SET NULL",
        # object_storage_files — FKs para student e school
        "ALTER TABLE public.object_storage_files DROP CONSTRAINT IF EXISTS fk_osf_student",
        "ALTER TABLE public.object_storage_files ADD CONSTRAINT fk_osf_student FOREIGN KEY (student_id) REFERENCES public.students(id) ON DELETE SET NULL",
        "ALTER TABLE public.object_storage_files DROP CONSTRAINT IF EXISTS fk_osf_school",
        "ALTER TABLE public.object_storage_files ADD CONSTRAINT fk_osf_school FOREIGN KEY (school_id) REFERENCES public.schools(id) ON DELETE SET NULL",
    ]

    has_payload = False
    try:
        with engine.connect() as conn:
            res = conn.execute(text(
                "SELECT EXISTS ("
                "   SELECT 1 FROM information_schema.columns "
                "   WHERE table_schema='public' "
                "     AND table_name='schools' "
                "     AND column_name='payload'"
                ")"
            )).scalar()
            has_payload = bool(res)
    except Exception as exc:
        print(f"[postgres_repositories] erro ao verificar coluna payload: {exc}")

    def run_batch(stmts, label: str) -> None:
        try:
            with engine.begin() as conn:
                for stmt in stmts:
                    conn.execute(text(stmt))
        except Exception as exc:
            print(f"[postgres_repositories] aviso na fase '{label}': {exc}")

    run_batch(index_stmts,          "indexes")
    run_batch(schema_stmts,         "schema")
    if has_payload:
        run_batch(backfill_stmts,       "backfill")
        run_batch(cleanup_stmts,        "json-cleanup")
    run_batch(normalize_schema_stmts,      "normalize-schema")
    if has_payload:
        run_batch(normalize_backfill_stmts,    "normalize-backfill")
        run_batch(make_payload_nullable_stmts, "payload-nullable")
        run_batch(drop_payload_stmts,          "drop-payload")
    run_batch(orphan_cleanup_stmts, "orphan-cleanup")

    # ── FASE 8 — backfill de anonimização ────────────────────────────────────
    # Corrige registros criados antes da lógica de anonymized_data estar completa.
    anonymization_backfill_stmts = [
        # PDIs: preenche student_id e school_id (via JOIN com students) em anonymized_data
        """
        UPDATE public.pdis p
        SET anonymized_data = (
            jsonb_set(
                jsonb_set(
                    COALESCE(p.anonymized_data::jsonb, '{}'::jsonb),
                    '{student_id}',
                    to_jsonb(COALESCE(p.student_id, ''))
                ),
                '{school_id}',
                to_jsonb(COALESCE(s.school_id, ''))
            )
        )::json
        FROM public.students s
        WHERE s.id = p.student_id
          AND p.anonymized_data IS NOT NULL
          AND (p.anonymized_data->>'student_id' = '' OR p.anonymized_data->>'student_id' IS NULL)
          AND p.student_id IS NOT NULL
        """,
        # Escolas: remove municipio_id de anonymized_data (dado não deve ir para IA)
        """
        UPDATE public.schools
        SET anonymized_data = (anonymized_data::jsonb - 'municipio_id')::json
        WHERE anonymized_data IS NOT NULL
          AND (anonymized_data::jsonb) ? 'municipio_id'
        """,
    ]
    run_batch(anonymization_backfill_stmts, "anonymization-backfill")

    run_batch(constraint_stmts,     "constraints")


class AIUsageRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, AIUsageEventRecord)

    def insert_event(self, event: dict) -> None:
        with self._session() as session:
            record = AIUsageEventRecord(
                id=str(uuid.uuid4()),
                timestamp=event.get('timestamp', ''),
                model=event['model'],
                operation=event.get('operation', 'unspecified'),
                input_tokens=event.get('input_tokens', 0),
                output_tokens=event.get('output_tokens', 0),
                total_tokens=event.get('total_tokens', 0),
                duration_ms=event.get('duration_ms'),
                user_id=event.get('user_id'),
                username=event.get('username'),
            )
            session.add(record)

    def list_events(self, limit: Optional[int] = None) -> List[Dict]:
        with self._session() as session:
            stmt = select(AIUsageEventRecord).order_by(AIUsageEventRecord.timestamp.desc())
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [
                {
                    'timestamp': r.timestamp,
                    'model': r.model,
                    'operation': r.operation,
                    'input_tokens': r.input_tokens,
                    'output_tokens': r.output_tokens,
                    'total_tokens': r.total_tokens,
                    **({'duration_ms': r.duration_ms} if r.duration_ms is not None else {}),
                    **({'user_id': r.user_id} if r.user_id else {}),
                    **({'username': r.username} if r.username else {}),
                }
                for r in rows
            ]


def create_postgres_repositories(database_url: str):
    engine = create_engine(database_url, future=True)
    # Cria tabelas que ainda não existem (idempotente)
    Base.metadata.create_all(engine)
    # Migração: colunas FK, backfill, limpeza de JSON, constraints
    _run_migration(engine)

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    return {
        'auth': PostgresAuthRepository(
            session_factory,
            default_admin_username=os.getenv('AUTH_ADMIN_USERNAME', 'admin'),
            default_admin_password=os.getenv('AUTH_ADMIN_PASSWORD', ''),
        ),
        'municipality': MunicipalityPostgresRepository(session_factory),
        'school': SchoolPostgresRepository(session_factory),
        'student': StudentPostgresRepository(session_factory),
        'teacher': TeacherPostgresRepository(session_factory),
        'diary': DiaryPostgresRepository(session_factory),
        'family_diary': FamilyDiaryPostgresRepository(session_factory),
        'diary_summary': DiarySummaryPostgresRepository(session_factory),
        'pdi': PDIPostgresRepository(session_factory),
        'form_submission': FormSubmissionsPostgresRepository(session_factory),
        'object_metadata': ObjectStorageMetadataPostgresRepository(session_factory),
        'pei': PEIPostgresRepository(session_factory),
        'chat_history': ChatHistoryPostgresRepository(session_factory),
        'usage_events': AIUsageRepository(session_factory),
    }
