import uuid
import os
from contextlib import contextmanager
from typing import Dict, List, Optional

from sqlalchemy import (
    JSON, ForeignKey, Integer, String, Text,
    UniqueConstraint, create_engine, delete, select, text,
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
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
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
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
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
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
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
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


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
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
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
    reference_id é uma referência polimórfica (depende de doc_type),
    portanto não possui FK formal — mantido como está.
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
    extra_json: Mapped[dict] = mapped_column('extra', JSON, nullable=False, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


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
# Schools  (FK: municipio_id → municipalities)
# ---------------------------------------------------------------------------

class SchoolPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, SchoolRecord)

    def _to_entity(self, record: SchoolRecord) -> Dict:
        """municipio_id vem da coluna, não do payload."""
        entity = dict(record.payload or {})
        entity['id'] = record.id
        entity['municipio_id'] = record.municipio_id or ''
        entity['created_at'] = record.created_at
        entity['updated_at'] = record.updated_at
        return entity

    def create_school(
        self,
        school_data: Dict,
        school_id: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        school_id = school_id or str(uuid.uuid4())
        created_at = created_at or now
        updated_at = updated_at or now

        payload = dict(school_data)
        payload.pop('id', None)
        payload.pop('created_at', None)
        payload.pop('updated_at', None)
        # Extrai FK do payload para a coluna própria
        municipio_id = payload.pop('municipio_id', None) or None

        with self._session() as session:
            record = SchoolRecord(
                id=school_id,
                municipio_id=municipio_id,
                payload=payload,
                created_at=created_at,
                updated_at=updated_at,
            )
            session.merge(record)
            return self._to_entity(record)

    def update_school(self, school_id: str, school_data: Dict) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(SchoolRecord, school_id)
            if not record:
                return None

            payload = dict(record.payload or {})
            payload.update(dict(school_data))
            payload.pop('id', None)
            payload.pop('created_at', None)
            payload.pop('updated_at', None)
            # Extrai FK
            municipio_id = payload.pop('municipio_id', None)
            if municipio_id is not None:
                record.municipio_id = municipio_id or None

            record.payload = payload
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
    def _student_entity(record: StudentRecord, teacher_ids: List[str]) -> Dict:
        """Constrói o dict de entidade com colunas FK explícitas."""
        entity = dict(record.payload or {})
        entity['id'] = record.id
        entity['school_id'] = record.school_id or ''
        entity['teacher_ids'] = teacher_ids
        entity['teacher_id'] = teacher_ids[0] if teacher_ids else ''
        entity['created_at'] = record.created_at
        entity['updated_at'] = record.updated_at
        return entity

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
        created_at = created_at or now
        updated_at = updated_at or now

        payload = dict(student_data)
        payload.pop('id', None)
        payload.pop('created_at', None)
        payload.pop('updated_at', None)
        # Extrai FKs do payload para colunas próprias
        school_id = payload.pop('school_id', None) or None
        raw_teacher_ids = payload.pop('teacher_ids', []) or []
        # Remove campos legados de teacher do payload
        payload.pop('teacher_id', None)

        with self._session() as session:
            record = StudentRecord(
                id=student_id,
                school_id=school_id,
                payload=payload,
                created_at=created_at,
                updated_at=updated_at,
            )
            session.merge(record)
            session.flush()
            teacher_ids = [str(t) for t in raw_teacher_ids if t]
            self._sync_teacher_links(session, student_id, teacher_ids)
            return self._student_entity(record, teacher_ids)

    def update_student(self, student_id: str, student_data: Dict) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(StudentRecord, student_id)
            if not record:
                return None

            payload = dict(record.payload or {})
            payload.update(dict(student_data))
            payload.pop('id', None)
            payload.pop('created_at', None)
            payload.pop('updated_at', None)
            # Extrai FKs
            school_id = payload.pop('school_id', None)
            raw_teacher_ids = payload.pop('teacher_ids', None)
            payload.pop('teacher_id', None)

            if school_id is not None:
                record.school_id = school_id or None
            record.payload = payload
            record.updated_at = now_brasilia_iso()
            session.flush()

            if raw_teacher_ids is not None:
                teacher_ids = [str(t) for t in raw_teacher_ids if t]
                self._sync_teacher_links(session, student_id, teacher_ids)
            else:
                teacher_ids = self._get_teacher_ids(session, student_id)

            return self._student_entity(record, teacher_ids)

    def get_student(self, student_id: str) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(StudentRecord, student_id)
            if not record:
                return None
            teacher_ids = self._get_teacher_ids(session, student_id)
            return self._student_entity(record, teacher_ids)

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

        teacher_ids_map: Dict[str, List[str]] = {}
        for link in link_rows:
            teacher_ids_map.setdefault(link.student_id, []).append(link.teacher_id)

        summaries = []
        for row in rows:
            teacher_ids = teacher_ids_map.get(row.id, [])
            student = self._student_entity(row, teacher_ids)
            summaries.append({
                'id': student['id'],
                'name': student.get('name', student.get('studentName', '')),
                'age': student.get('age', student.get('studentAge', '')),
                'school_id': student.get('school_id', ''),
                'school_name': student.get('school_name', student.get('schoolName', '')),
                'teacher_ids': teacher_ids,
                'teacher_id': teacher_ids[0] if teacher_ids else '',
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
                        .distinct())
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

        teacher_ids_map: Dict[str, List[str]] = {}
        for link in link_rows:
            teacher_ids_map.setdefault(link.student_id, []).append(link.teacher_id)

        summaries = []
        for row in rows:
            t_ids = teacher_ids_map.get(row.id, [])
            student = self._student_entity(row, t_ids)
            summaries.append({
                'id': student['id'],
                'name': student.get('name', student.get('studentName', '')),
                'age': student.get('age', student.get('studentAge', '')),
                'school_id': student.get('school_id', ''),
                'school_name': student.get('school_name', student.get('schoolName', '')),
                'teacher_ids': t_ids,
                'teacher_id': t_ids[0] if t_ids else '',
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

            # Batch de links
            student_ids = [r.id for r in rows]
            link_rows = session.execute(
                select(TeacherStudentLinkRecord).where(
                    TeacherStudentLinkRecord.student_id.in_(student_ids)
                )
            ).scalars().all()

        teacher_ids_map: Dict[str, List[str]] = {}
        for link in link_rows:
            teacher_ids_map.setdefault(link.student_id, []).append(link.teacher_id)

        matches = []
        for row in rows:
            student_name = dict(row.payload or {}).get('name') or dict(row.payload or {}).get('studentName') or ''
            if self._normalize_name(student_name) == normalized_candidate:
                teacher_ids = teacher_ids_map.get(row.id, [])
                matches.append(self._student_entity(row, teacher_ids))

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
        """school_id vem da coluna, não do payload."""
        entity = dict(record.payload or {})
        entity['id'] = record.id
        entity['school_id'] = record.school_id or ''
        entity['created_at'] = record.created_at
        entity['updated_at'] = record.updated_at
        return entity

    def create_teacher(
        self,
        teacher_data: Dict,
        teacher_id: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        teacher_id = teacher_id or str(uuid.uuid4())
        created_at = created_at or now
        updated_at = updated_at or now

        payload = dict(teacher_data)
        payload.pop('id', None)
        payload.pop('created_at', None)
        payload.pop('updated_at', None)
        # Extrai FK
        school_id = payload.pop('school_id', None) or None

        with self._session() as session:
            record = TeacherRecord(
                id=teacher_id,
                school_id=school_id,
                payload=payload,
                created_at=created_at,
                updated_at=updated_at,
            )
            session.merge(record)
            return self._to_entity(record)

    def update_teacher(self, teacher_id: str, teacher_data: Dict) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(TeacherRecord, teacher_id)
            if not record:
                return None

            payload = dict(teacher_data)
            payload.pop('id', None)
            payload.pop('created_at', None)
            payload.pop('updated_at', None)
            # Extrai FK
            school_id = payload.pop('school_id', None)
            if school_id is not None:
                record.school_id = school_id or None

            record.payload = payload
            record.updated_at = now_brasilia_iso()
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
        """student_id vem da coluna, não do payload."""
        entity = dict(record.payload or {})
        entity['id'] = record.id
        entity['student_id'] = record.student_id or ''
        entity['created_at'] = record.created_at
        entity['updated_at'] = record.updated_at
        return entity

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
        created_at = created_at or now

        # student_id fica na coluna; demais dados ficam no payload
        payload = {
            'student_name': student_name,
            'teachers': teachers,
            'diary_date': diary_date,
            'answers': answers,
            'open_obs': open_obs,
            'attendance': attendance,
            'absence_explanation': absence_explanation,
            'status': status,
            'source': source,
            'parse_warnings': parse_warnings or [],
        }

        with self._session() as session:
            record = DiaryEntryRecord(
                id=entry_id,
                student_id=student_id or None,
                payload=payload,
                created_at=created_at,
                updated_at=updated_at,
            )
            session.merge(record)
            return self._to_entity(record)

    def get_entry(self, entry_id: str) -> Optional[Dict]:
        return self._get(entry_id)

    def list_all_entries(self) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(select(DiaryEntryRecord)).scalars().all()
        return [self._to_entity(row) for row in rows]

    def get_entries_by_student(self, student_name: str, student_id: Optional[str] = None) -> List[Dict]:
        with self._session() as session:
            if student_id:
                # Caminho rápido: usa o índice da coluna FK student_id
                rows = session.execute(
                    select(DiaryEntryRecord).where(DiaryEntryRecord.student_id == student_id)
                ).scalars().all()
                entries = [self._to_entity(row) for row in rows]
            else:
                # Fallback por nome: full scan (student_id não disponível)
                rows = session.execute(select(DiaryEntryRecord)).scalars().all()
                entities = [self._to_entity(row) for row in rows]
                entries = [e for e in entities
                           if self._entry_matches_student(e, None, student_name)]

        return sorted(entries, key=lambda x: x.get('diary_date', ''), reverse=True)

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
    ) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(DiaryEntryRecord, entry_id)
            if not record:
                return None

            # Atualiza coluna FK
            if student_id is not None:
                record.student_id = student_id or None

            record.payload = {
                **dict(record.payload or {}),
                'student_name': student_name,
                'teachers': teachers,
                'diary_date': diary_date,
                'answers': answers,
                'open_obs': open_obs,
                'attendance': attendance,
                'absence_explanation': absence_explanation,
                'status': status,
                'source': source,
                'parse_warnings': parse_warnings or [],
            }
            record.updated_at = now_brasilia_iso()
            return self._to_entity(record)

    def delete_entry(self, entry_id: str) -> bool:
        return self._delete(entry_id)

    def delete_entries_by_student(self, student_name: str, student_id: Optional[str] = None) -> int:
        with self._session() as session:
            if student_id:
                # Caminho rápido: usa índice FK
                rows = session.execute(
                    select(DiaryEntryRecord).where(DiaryEntryRecord.student_id == student_id)
                ).scalars().all()
            else:
                # Fallback por nome
                all_rows = session.execute(select(DiaryEntryRecord)).scalars().all()
                rows = [r for r in all_rows
                        if self._entry_matches_student(self._to_entity(r), None, student_name)]

            for row in rows:
                session.delete(row)

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
            stmt = select(DiaryEntryRecord)

            if role == 'admin':
                pass  # sem filtro
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
                        .distinct())
            else:
                return []

            rows = session.execute(stmt).scalars().all()

        return self._group_into_summaries([self._to_entity(row) for row in rows])

    def link_entries_to_student(self, student_id: str, student_name: str) -> int:
        """
        Vincula entradas sem student_id à coluna FK correta (não mais ao payload).
        """
        if not student_id or not student_name:
            return 0

        normalized_name = self._normalize_name(student_name)
        linked_count = 0

        with self._session() as session:
            rows = session.execute(select(DiaryEntryRecord)).scalars().all()
            for row in rows:
                if row.student_id:
                    continue
                payload = dict(row.payload or {})
                if self._normalize_name(payload.get('student_name', '')) != normalized_name:
                    continue

                row.student_id = student_id
                # Mantém student_name atualizado no payload
                payload['student_name'] = student_name
                row.payload = payload
                linked_count += 1

        return linked_count


# ---------------------------------------------------------------------------
# PDI  (FK: student_id → students CASCADE)
# ---------------------------------------------------------------------------

class PDIPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, PDIRecord)

    def _to_entity(self, record: PDIRecord) -> Dict:
        """student_id vem da coluna, não do payload."""
        entity = dict(record.payload or {})
        entity['id'] = record.id
        entity['student_id'] = record.student_id or ''
        entity['created_at'] = record.created_at
        entity['updated_at'] = record.updated_at
        return entity

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
        guardians: List[str],
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
        created_at = created_at or now
        updated_at = updated_at or now

        # student_id fica na coluna; demais dados ficam no payload
        payload = {
            'student_name': student_name,
            'birth_date': birth_date,
            'guardians': guardians,
            'diagnosis': diagnosis,
            'class': class_name,
            'teachers': teachers,
            'student_grade': student_grade or '',
            'trimesters': normalize_trimesters(
                trimesters,
                subject_ids=get_pdi_subject_ids_for_grade(student_grade),
            ),
        }

        with self._session() as session:
            record = PDIRecord(
                id=pdi_id,
                student_id=student_id or None,
                payload=payload,
                created_at=created_at,
                updated_at=updated_at,
            )
            session.merge(record)
            return self._to_entity(record)

    def update_pdi(
        self,
        pdi_id: str,
        student_name: str,
        birth_date: str,
        guardians: List[str],
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

            # Atualiza coluna FK
            if student_id is not None:
                record.student_id = student_id or None

            payload = dict(record.payload or {})
            payload.update({
                'student_name': student_name,
                'birth_date': birth_date,
                'guardians': guardians,
                'diagnosis': diagnosis,
                'class': class_name,
                'teachers': teachers,
                'student_grade': student_grade or payload.get('student_grade') or '',
                'trimesters': normalize_trimesters(
                    trimesters,
                    subject_ids=get_pdi_subject_ids_for_grade(student_grade or payload.get('student_grade')),
                ),
            })
            record.payload = payload
            record.updated_at = now_brasilia_iso()
            return self._to_entity(record)

    def normalize_existing_pdis(self) -> int:
        updated_count = 0
        with self._session() as session:
            rows = session.execute(select(PDIRecord)).scalars().all()
            for row in rows:
                payload = dict(row.payload or {})
                normalized_trimesters = normalize_trimesters(
                    payload.get('trimesters'),
                    subject_ids=get_pdi_subject_ids_for_grade(payload.get('student_grade')),
                )
                if normalized_trimesters == payload.get('trimesters'):
                    continue

                payload['trimesters'] = normalized_trimesters
                row.payload = payload
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
                        .distinct())
            else:
                return []

            rows = session.execute(stmt).scalars().all()

        summaries = [self._pdi_to_summary(self._to_entity(row)) for row in rows]
        return sorted(summaries, key=lambda x: x.get('updated_at', ''), reverse=True)

    def delete_pdi(self, pdi_id: str) -> bool:
        return self._delete(pdi_id)

    def link_pdis_to_student(self, student_id: str, student_name: str) -> int:
        """
        Vincula PDIs sem student_id à coluna FK correta (não mais ao payload).
        """
        if not student_id or not student_name:
            return 0

        normalized_name = self._normalize_name(student_name)
        linked_count = 0

        with self._session() as session:
            rows = session.execute(select(PDIRecord)).scalars().all()
            for row in rows:
                if row.student_id:
                    continue
                payload = dict(row.payload or {})
                if self._normalize_name(payload.get('student_name', '')) != normalized_name:
                    continue

                row.student_id = student_id
                payload['student_name'] = student_name
                row.payload = payload
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
    ]

    def run_batch(stmts, label: str) -> None:
        try:
            with engine.begin() as conn:
                for stmt in stmts:
                    conn.execute(text(stmt))
        except Exception as exc:
            print(f"[postgres_repositories] aviso na fase '{label}': {exc}")

    run_batch(index_stmts,        "indexes")
    run_batch(schema_stmts,       "schema")
    run_batch(backfill_stmts,     "backfill")
    run_batch(cleanup_stmts,      "json-cleanup")
    run_batch(orphan_cleanup_stmts, "orphan-cleanup")
    run_batch(constraint_stmts,   "constraints")


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
        'pdi': PDIPostgresRepository(session_factory),
        'form_submission': FormSubmissionsPostgresRepository(session_factory),
        'object_metadata': ObjectStorageMetadataPostgresRepository(session_factory),
        'chat_history': ChatHistoryPostgresRepository(session_factory),
    }
