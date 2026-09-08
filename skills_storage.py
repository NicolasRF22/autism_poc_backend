"""Armazenamento persistente de Skills (tarefas pré-definidas com prompt)."""
import json
import os
import uuid
from contextlib import contextmanager
from typing import Dict, List, Optional

from sqlalchemy import Boolean, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

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
            self._engine = create_engine(self.database_url, future=True)
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
