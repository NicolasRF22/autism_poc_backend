"""Armazenamento persistente de Skills (tarefas pré-definidas com prompt)
e de Resultados Salvos de Skills."""
import json
import os
import uuid
from contextlib import contextmanager
from typing import Dict, List, Optional

from sqlalchemy import Boolean, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import NullPool

from time_utils import now_brasilia_iso


class SkillBase(DeclarativeBase):
    pass


class SkillRecord(SkillBase):
    __tablename__ = 'skills'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


def _record_to_dict(record: SkillRecord) -> Dict:
    return {
        'id': record.id,
        'title': record.title,
        'description': record.description or '',
        'prompt': record.prompt,
        'created_by': record.created_by or '',
        'created_at': record.created_at,
        'updated_at': record.updated_at,
        'is_active': record.is_active,
    }


class SkillsStorage:
    """Armazena Skills em PostgreSQL ou arquivo JSON local como fallback."""

    _JSON_PATH_DEFAULT = './skills.json'

    def __init__(self, storage_dir: str = '.', database_url: str = ''):
        self.database_url = (database_url or os.getenv('DATABASE_URL') or '').strip()
        self._json_path = os.path.join(storage_dir, 'skills.json')
        self._engine = None
        self._session_factory = None
        self._use_database = bool(self.database_url)

        if self._use_database:
            self._engine = create_engine(self.database_url, future=True, poolclass=NullPool)
            self._session_factory = sessionmaker(
                bind=self._engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
                future=True,
            )
            SkillBase.metadata.create_all(self._engine)

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

    # ------------------------------------------------------------------ #
    # JSON fallback helpers                                                #
    # ------------------------------------------------------------------ #

    def _read_json(self) -> List[Dict]:
        if not os.path.exists(self._json_path):
            return []
        try:
            with open(self._json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _write_json(self, skills: List[Dict]):
        with open(self._json_path, 'w', encoding='utf-8') as f:
            json.dump(skills, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def list_skills(self, include_inactive: bool = False) -> List[Dict]:
        if self._use_database:
            with self._session() as session:
                stmt = select(SkillRecord)
                if not include_inactive:
                    stmt = stmt.where(SkillRecord.is_active == True)  # noqa: E712
                stmt = stmt.order_by(SkillRecord.created_at.asc())
                rows = session.execute(stmt).scalars().all()
                return [_record_to_dict(r) for r in rows]
        else:
            skills = self._read_json()
            if not include_inactive:
                skills = [s for s in skills if s.get('is_active', True)]
            return skills

    def get_skill(self, skill_id: str) -> Optional[Dict]:
        if self._use_database:
            with self._session() as session:
                record = session.get(SkillRecord, skill_id)
                return _record_to_dict(record) if record else None
        else:
            return next((s for s in self._read_json() if s.get('id') == skill_id), None)

    def create_skill(self, title: str, prompt: str, description: str = '', created_by: str = '') -> Dict:
        now = now_brasilia_iso()
        skill_id = str(uuid.uuid4())
        skill = {
            'id': skill_id,
            'title': title.strip(),
            'description': description.strip(),
            'prompt': prompt.strip(),
            'created_by': created_by,
            'created_at': now,
            'updated_at': now,
            'is_active': True,
        }
        if self._use_database:
            with self._session() as session:
                record = SkillRecord(
                    id=skill_id,
                    title=skill['title'],
                    description=skill['description'] or None,
                    prompt=skill['prompt'],
                    created_by=created_by or None,
                    created_at=now,
                    updated_at=now,
                    is_active=True,
                )
                session.add(record)
                session.flush()
                return _record_to_dict(record)
        else:
            skills = self._read_json()
            skills.append(skill)
            self._write_json(skills)
            return skill

    def update_skill(self, skill_id: str, title: str = None, prompt: str = None,
                     description: str = None) -> Optional[Dict]:
        now = now_brasilia_iso()
        if self._use_database:
            with self._session() as session:
                record = session.get(SkillRecord, skill_id)
                if not record:
                    return None
                if title is not None:
                    record.title = title.strip()
                if prompt is not None:
                    record.prompt = prompt.strip()
                if description is not None:
                    record.description = description.strip() or None
                record.updated_at = now
                session.flush()
                return _record_to_dict(record)
        else:
            skills = self._read_json()
            for s in skills:
                if s.get('id') == skill_id:
                    if title is not None:
                        s['title'] = title.strip()
                    if prompt is not None:
                        s['prompt'] = prompt.strip()
                    if description is not None:
                        s['description'] = description.strip()
                    s['updated_at'] = now
                    self._write_json(skills)
                    return s
            return None

    def delete_skill(self, skill_id: str) -> bool:
        """Soft delete — marca is_active = False."""
        now = now_brasilia_iso()
        if self._use_database:
            with self._session() as session:
                record = session.get(SkillRecord, skill_id)
                if not record:
                    return False
                record.is_active = False
                record.updated_at = now
                return True
        else:
            skills = self._read_json()
            for s in skills:
                if s.get('id') == skill_id:
                    s['is_active'] = False
                    s['updated_at'] = now
                    self._write_json(skills)
                    return True
            return False


# ============================================================================
# SavedSkillResult — resultados salvos manualmente pelo usuário
# ============================================================================

class SavedSkillResultRecord(SkillBase):
    __tablename__ = 'saved_skill_results'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    skill_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    skill_title: Mapped[str] = mapped_column(Text, nullable=False)
    student_id: Mapped[str] = mapped_column(String(64), nullable=False)
    student_name: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    saved_by_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    saved_by_username: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


def _saved_record_to_dict(record: SavedSkillResultRecord) -> Dict:
    return {
        'id': record.id,
        'skill_id': record.skill_id or '',
        'skill_title': record.skill_title,
        'student_id': record.student_id,
        'student_name': record.student_name,
        'response': record.response,
        'session_id': record.session_id or '',
        'saved_by_user_id': record.saved_by_user_id or '',
        'saved_by_username': record.saved_by_username,
        'created_at': record.created_at,
    }


class SavedSkillsStorage:
    """Armazena resultados salvos de Skills em PostgreSQL ou JSON local."""

    def __init__(self, storage_dir: str = '.', database_url: str = ''):
        self.database_url = (database_url or os.getenv('DATABASE_URL') or '').strip()
        self._json_path = os.path.join(storage_dir, 'saved_skill_results.json')
        self._engine = None
        self._session_factory = None
        self._use_database = bool(self.database_url)

        if self._use_database:
            # Reutiliza o mesmo engine se já foi criado — mas como esta classe é
            # instanciada separadamente, cria um novo com a mesma URL.
            self._engine = create_engine(self.database_url, future=True, poolclass=NullPool)
            self._session_factory = sessionmaker(
                bind=self._engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
                future=True,
            )
            # Cria a tabela se não existir (idempotente)
            SkillBase.metadata.create_all(self._engine, tables=[SavedSkillResultRecord.__table__])

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

    # ------------------------------------------------------------------ #
    # JSON fallback helpers                                                #
    # ------------------------------------------------------------------ #

    def _read_json(self) -> List[Dict]:
        if not os.path.exists(self._json_path):
            return []
        try:
            with open(self._json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _write_json(self, records: List[Dict]):
        with open(self._json_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def list_results(
        self,
        student_ids: Optional[List[str]] = None,
        start_date: str = '',
        end_date: str = '',
    ) -> List[Dict]:
        """Lista resultados salvos, do mais recente ao mais antigo.
        student_ids: se passado, filtra apenas esses alunos.
        start_date / end_date: strings ISO date 'YYYY-MM-DD' (inclusivos).
        """
        end_prefix = (end_date + 'T23:59:59') if end_date else ''
        if self._use_database:
            with self._session() as session:
                stmt = select(SavedSkillResultRecord).order_by(
                    SavedSkillResultRecord.created_at.desc()
                )
                if student_ids is not None:
                    stmt = stmt.where(SavedSkillResultRecord.student_id.in_(student_ids))
                if start_date:
                    stmt = stmt.where(SavedSkillResultRecord.created_at >= start_date)
                if end_prefix:
                    stmt = stmt.where(SavedSkillResultRecord.created_at <= end_prefix)
                rows = session.execute(stmt).scalars().all()
                return [_saved_record_to_dict(r) for r in rows]
        else:
            records = self._read_json()
            records = sorted(records, key=lambda r: r.get('created_at', ''), reverse=True)
            if student_ids is not None:
                records = [r for r in records if r.get('student_id') in student_ids]
            if start_date:
                records = [r for r in records if r.get('created_at', '') >= start_date]
            if end_prefix:
                records = [r for r in records if r.get('created_at', '') <= end_prefix]
            return records

    def save_result(
        self,
        skill_id: str,
        skill_title: str,
        student_id: str,
        student_name: str,
        response: str,
        saved_by_user_id: str = '',
        saved_by_username: str = '',
        session_id: str = '',
    ) -> Dict:
        now = now_brasilia_iso()
        record_id = str(uuid.uuid4())
        record = {
            'id': record_id,
            'skill_id': skill_id or '',
            'skill_title': skill_title,
            'student_id': student_id,
            'student_name': student_name,
            'response': response,
            'session_id': session_id or '',
            'saved_by_user_id': saved_by_user_id or '',
            'saved_by_username': saved_by_username,
            'created_at': now,
        }
        if self._use_database:
            with self._session() as session:
                db_record = SavedSkillResultRecord(
                    id=record_id,
                    skill_id=skill_id or None,
                    skill_title=skill_title,
                    student_id=student_id,
                    student_name=student_name,
                    response=response,
                    session_id=session_id or None,
                    saved_by_user_id=saved_by_user_id or None,
                    saved_by_username=saved_by_username,
                    created_at=now,
                )
                session.add(db_record)
                session.flush()
                return _saved_record_to_dict(db_record)
        else:
            records = self._read_json()
            records.append(record)
            self._write_json(records)
            return record

    def delete_result(self, result_id: str) -> bool:
        """Hard delete."""
        if self._use_database:
            with self._session() as session:
                record = session.get(SavedSkillResultRecord, result_id)
                if not record:
                    return False
                session.delete(record)
                return True
        else:
            records = self._read_json()
            new_records = [r for r in records if r.get('id') != result_id]
            if len(new_records) == len(records):
                return False
            self._write_json(new_records)
            return True

    def get_result(self, result_id: str) -> Optional[Dict]:
        if self._use_database:
            with self._session() as session:
                record = session.get(SavedSkillResultRecord, result_id)
                return _saved_record_to_dict(record) if record else None
        else:
            return next((r for r in self._read_json() if r.get('id') == result_id), None)


# ============================================================================
# SavedPeiStructured — PEIs gerados e salvos pelo usuário na página PEI
# ============================================================================

class SavedPeiStructuredRecord(SkillBase):
    __tablename__ = 'saved_peis_structured'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), nullable=False)
    student_name: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    saved_by_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    saved_by_username: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


def _pei_record_to_dict(record: SavedPeiStructuredRecord) -> Dict:
    return {
        'id': record.id,
        'student_id': record.student_id,
        'student_name': record.student_name,
        'response': record.response,
        'session_id': record.session_id or '',
        'saved_by_user_id': record.saved_by_user_id or '',
        'saved_by_username': record.saved_by_username,
        'created_at': record.created_at,
    }


class SavedPeiStructuredStorage:
    """Armazena PEIs salvos na página PEI Estruturado."""

    def __init__(self, storage_dir: str = '.', database_url: str = ''):
        self.database_url = (database_url or os.getenv('DATABASE_URL') or '').strip()
        self._json_path = os.path.join(storage_dir, 'saved_peis_structured.json')
        self._engine = None
        self._session_factory = None
        self._use_database = bool(self.database_url)

        if self._use_database:
            self._engine = create_engine(self.database_url, future=True, poolclass=NullPool)
            self._session_factory = sessionmaker(
                bind=self._engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
                future=True,
            )
            SkillBase.metadata.create_all(self._engine, tables=[SavedPeiStructuredRecord.__table__])

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

    def _read_json(self) -> List[Dict]:
        if not os.path.exists(self._json_path):
            return []
        try:
            with open(self._json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _write_json(self, records: List[Dict]):
        with open(self._json_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def list_results(
        self,
        student_ids: Optional[List[str]] = None,
        start_date: str = '',
        end_date: str = '',
    ) -> List[Dict]:
        end_prefix = (end_date + 'T23:59:59') if end_date else ''
        if self._use_database:
            with self._session() as session:
                stmt = select(SavedPeiStructuredRecord).order_by(
                    SavedPeiStructuredRecord.created_at.desc()
                )
                if student_ids is not None:
                    stmt = stmt.where(SavedPeiStructuredRecord.student_id.in_(student_ids))
                if start_date:
                    stmt = stmt.where(SavedPeiStructuredRecord.created_at >= start_date)
                if end_prefix:
                    stmt = stmt.where(SavedPeiStructuredRecord.created_at <= end_prefix)
                rows = session.execute(stmt).scalars().all()
                return [_pei_record_to_dict(r) for r in rows]
        else:
            records = self._read_json()
            records = sorted(records, key=lambda r: r.get('created_at', ''), reverse=True)
            if student_ids is not None:
                records = [r for r in records if r.get('student_id') in student_ids]
            if start_date:
                records = [r for r in records if r.get('created_at', '') >= start_date]
            if end_prefix:
                records = [r for r in records if r.get('created_at', '') <= end_prefix]
            return records

    def save_result(
        self,
        student_id: str,
        student_name: str,
        response: str,
        saved_by_user_id: str = '',
        saved_by_username: str = '',
        session_id: str = '',
    ) -> Dict:
        now = now_brasilia_iso()
        record_id = str(uuid.uuid4())
        record = {
            'id': record_id,
            'student_id': student_id,
            'student_name': student_name,
            'response': response,
            'session_id': session_id or '',
            'saved_by_user_id': saved_by_user_id or '',
            'saved_by_username': saved_by_username,
            'created_at': now,
        }
        if self._use_database:
            with self._session() as session:
                db_record = SavedPeiStructuredRecord(
                    id=record_id,
                    student_id=student_id,
                    student_name=student_name,
                    response=response,
                    session_id=session_id or None,
                    saved_by_user_id=saved_by_user_id or None,
                    saved_by_username=saved_by_username,
                    created_at=now,
                )
                session.add(db_record)
                session.flush()
                return _pei_record_to_dict(db_record)
        else:
            records = self._read_json()
            records.append(record)
            self._write_json(records)
            return record

    def update_result(self, result_id: str, response: str) -> Optional[Dict]:
        """Atualiza o conteúdo (response) de um PEI salvo."""
        if self._use_database:
            with self._session() as session:
                record = session.get(SavedPeiStructuredRecord, result_id)
                if not record:
                    return None
                record.response = response
                session.flush()
                return _pei_record_to_dict(record)
        else:
            records = self._read_json()
            for r in records:
                if r.get('id') == result_id:
                    r['response'] = response
                    self._write_json(records)
                    return dict(r)
            return None

    def delete_result(self, result_id: str) -> bool:
        if self._use_database:
            with self._session() as session:
                record = session.get(SavedPeiStructuredRecord, result_id)
                if not record:
                    return False
                session.delete(record)
                return True
        else:
            records = self._read_json()
            new_records = [r for r in records if r.get('id') != result_id]
            if len(new_records) == len(records):
                return False
            self._write_json(new_records)
            return True
