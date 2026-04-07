import uuid
from contextlib import contextmanager
from typing import Dict, List, Optional

from sqlalchemy import JSON, Integer, String, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from time_utils import now_brasilia_iso


class Base(DeclarativeBase):
    pass


class SchoolRecord(Base):
    __tablename__ = 'schools'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class StudentRecord(Base):
    __tablename__ = 'students'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class TeacherRecord(Base):
    __tablename__ = 'teachers'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class DiaryEntryRecord(Base):
    __tablename__ = 'diary_entries'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class PDIRecord(Base):
    __tablename__ = 'pdis'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
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


class SchoolPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, SchoolRecord)

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

        with self._session() as session:
            record = SchoolRecord(
                id=school_id,
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

            record.payload = payload
            record.updated_at = now_brasilia_iso()
            return self._to_entity(record)

    def get_school(self, school_id: str) -> Optional[Dict]:
        return self._get(school_id)

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
                'city': school.get('address', {}).get('city', '') if isinstance(school.get('address'), dict) else '',
                'school_registration_completed': bool(school.get('school_registration_completed', False)),
                'updated_at': school['updated_at'],
            })

        return sorted(summaries, key=lambda x: x['name'].lower())

    def delete_school(self, school_id: str) -> bool:
        return self._delete(school_id)


class StudentPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, StudentRecord)

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

        with self._session() as session:
            record = StudentRecord(
                id=student_id,
                payload=payload,
                created_at=created_at,
                updated_at=updated_at,
            )
            session.merge(record)
            return self._to_entity(record)

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

            record.payload = payload
            record.updated_at = now_brasilia_iso()
            return self._to_entity(record)

    def get_student(self, student_id: str) -> Optional[Dict]:
        return self._get(student_id)

    def list_all_students(self) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(select(StudentRecord)).scalars().all()

        summaries = []
        for row in rows:
            student = self._to_entity(row)
            summaries.append({
                'id': student['id'],
                'name': student.get('name', student.get('studentName', '')),
                'age': student.get('age', student.get('studentAge', '')),
                'school_name': student.get('school_name', student.get('schoolName', '')),
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

        matches = []
        for row in rows:
            student = self._to_entity(row)
            student_name = student.get('name') or student.get('studentName') or ''
            if self._normalize_name(student_name) == normalized_candidate:
                matches.append(student)

        return matches

    def _normalize_name(self, value: str) -> str:
        import unicodedata

        normalized = unicodedata.normalize('NFKD', (value or '').strip().lower())
        normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
        return ' '.join(normalized.split())

    def delete_student(self, student_id: str) -> bool:
        return self._delete(student_id)


class TeacherPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, TeacherRecord)

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

        with self._session() as session:
            record = TeacherRecord(
                id=teacher_id,
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

            record.payload = payload
            record.updated_at = now_brasilia_iso()
            return self._to_entity(record)

    def get_teacher(self, teacher_id: str) -> Optional[Dict]:
        return self._get(teacher_id)

    def list_all_teachers(self) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(select(TeacherRecord)).scalars().all()

        summaries = []
        for row in rows:
            teacher = self._to_entity(row)
            summaries.append({
                'id': teacher['id'],
                'name': teacher.get('name', ''),
                'school_name': teacher.get('school_name', ''),
                'specialization': teacher.get('specialization', ''),
                'updated_at': teacher['updated_at'],
            })

        return sorted(summaries, key=lambda value: value['name'].lower())

    def delete_teacher(self, teacher_id: str) -> bool:
        return self._delete(teacher_id)


class DiaryPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, DiaryEntryRecord)

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

        payload = {
            'student_id': student_id,
            'student_name': student_name,
            'teachers': teachers,
            'diary_date': diary_date,
            'answers': answers,
            'open_obs': open_obs,
            'status': status,
            'source': source,
            'parse_warnings': parse_warnings or [],
        }

        with self._session() as session:
            record = DiaryEntryRecord(
                id=entry_id,
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
        entries = [
            entry for entry in self.list_all_entries()
            if self._entry_matches_student(entry, student_id, student_name)
        ]
        return sorted(entries, key=lambda x: x.get('diary_date', ''), reverse=True)

    def has_date_conflict(self, student_id: Optional[str], student_name: str, diary_date: str) -> bool:
        if not diary_date:
            return False

        for entry in self.list_all_entries():
            if not self._entry_matches_student(entry, student_id, student_name):
                continue
            if (entry.get('diary_date') or '') == diary_date:
                return True
        return False

    def update_entry(
        self,
        entry_id: str,
        student_name: str,
        teachers: List[str],
        diary_date: str,
        answers: Dict,
        open_obs: str,
        student_id: Optional[str] = None,
        status: str = 'final',
        source: str = 'manual',
        parse_warnings: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(DiaryEntryRecord, entry_id)
            if not record:
                return None

            record.payload = {
                **dict(record.payload or {}),
                'student_id': student_id,
                'student_name': student_name,
                'teachers': teachers,
                'diary_date': diary_date,
                'answers': answers,
                'open_obs': open_obs,
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
            rows = session.execute(select(DiaryEntryRecord)).scalars().all()
            to_delete = []
            for row in rows:
                entry = self._to_entity(row)
                if self._entry_matches_student(entry, student_id, student_name):
                    to_delete.append(row)

            for row in to_delete:
                session.delete(row)

            return len(to_delete)

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

    def list_all_summaries(self) -> List[Dict]:
        grouped = {}
        for entry in self.list_all_entries():
            student_id = (entry.get('student_id') or '').strip()
            student_name = entry.get('student_name') or ''
            key = f"id:{student_id}" if student_id else f"name:{self._normalize_name(student_name)}"
            if key not in grouped:
                grouped[key] = {
                    'student_id': student_id or None,
                    'student_name': student_name,
                }

        summaries = []
        for group in grouped.values():
            summary = self.get_student_summary(
                group['student_name'],
                student_id=group.get('student_id'),
            )
            if summary:
                summaries.append(summary)

        return sorted(summaries, key=lambda x: (x.get('student_name') or '').lower())

    def link_entries_to_student(self, student_id: str, student_name: str) -> int:
        if not student_id or not student_name:
            return 0

        normalized_name = self._normalize_name(student_name)
        linked_count = 0

        with self._session() as session:
            rows = session.execute(select(DiaryEntryRecord)).scalars().all()
            for row in rows:
                payload = dict(row.payload or {})
                if payload.get('student_id'):
                    continue
                if self._normalize_name(payload.get('student_name', '')) != normalized_name:
                    continue

                payload['student_id'] = student_id
                payload['student_name'] = student_name
                row.payload = payload
                linked_count += 1

        return linked_count


class PDIPostgresRepository(_BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory, PDIRecord)

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
        pdi_id: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        pdi_id = pdi_id or str(uuid.uuid4())
        created_at = created_at or now
        updated_at = updated_at or now

        payload = {
            'student_id': student_id,
            'student_name': student_name,
            'birth_date': birth_date,
            'guardians': guardians,
            'diagnosis': diagnosis,
            'class': class_name,
            'teachers': teachers,
            'trimesters': trimesters,
        }

        with self._session() as session:
            record = PDIRecord(
                id=pdi_id,
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
    ) -> Optional[Dict]:
        with self._session() as session:
            record = session.get(PDIRecord, pdi_id)
            if not record:
                return None

            record.payload = {
                **dict(record.payload or {}),
                'student_id': student_id,
                'student_name': student_name,
                'birth_date': birth_date,
                'guardians': guardians,
                'diagnosis': diagnosis,
                'class': class_name,
                'teachers': teachers,
                'trimesters': trimesters,
            }
            record.updated_at = now_brasilia_iso()
            return self._to_entity(record)

    def get_pdi(self, pdi_id: str) -> Optional[Dict]:
        return self._get(pdi_id)

    def get_pdi_by_student(self, student_name: str, student_id: Optional[str] = None) -> Optional[Dict]:
        pdis = [
            p for p in self.list_all_full_pdis()
            if self._pdi_matches_student(p, student_id, student_name)
        ]
        if pdis:
            return sorted(pdis, key=lambda x: x.get('updated_at', ''), reverse=True)[0]
        return None

    def has_pdi_for_student(self, student_name: str, student_id: Optional[str] = None, exclude_pdi_id: Optional[str] = None) -> bool:
        for pdi in self.list_all_full_pdis():
            if exclude_pdi_id and pdi.get('id') == exclude_pdi_id:
                continue
            if self._pdi_matches_student(pdi, student_id, student_name):
                return True
        return False

    def list_all_full_pdis(self) -> List[Dict]:
        with self._session() as session:
            rows = session.execute(select(PDIRecord)).scalars().all()
        return [self._to_entity(row) for row in rows]

    def list_all_pdis(self) -> List[Dict]:
        summaries = []
        for pdi in self.list_all_full_pdis():
            summaries.append({
                'id': pdi['id'],
                'student_id': pdi.get('student_id'),
                'student_name': pdi.get('student_name', ''),
                'class': pdi.get('class', ''),
                'diagnosis': pdi.get('diagnosis', ''),
                'updated_at': pdi.get('updated_at', ''),
                'teachers': pdi.get('teachers', []),
            })

        return sorted(summaries, key=lambda x: x.get('updated_at', ''), reverse=True)

    def delete_pdi(self, pdi_id: str) -> bool:
        return self._delete(pdi_id)

    def link_pdis_to_student(self, student_id: str, student_name: str) -> int:
        if not student_id or not student_name:
            return 0

        normalized_name = self._normalize_name(student_name)
        linked_count = 0

        with self._session() as session:
            rows = session.execute(select(PDIRecord)).scalars().all()
            for row in rows:
                payload = dict(row.payload or {})
                if payload.get('student_id'):
                    continue
                if self._normalize_name(payload.get('student_name', '')) != normalized_name:
                    continue

                payload['student_id'] = student_id
                payload['student_name'] = student_name
                row.payload = payload
                row.updated_at = now_brasilia_iso()
                linked_count += 1

        return linked_count


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


def create_postgres_repositories(database_url: str):
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    return {
        'school': SchoolPostgresRepository(session_factory),
        'student': StudentPostgresRepository(session_factory),
        'teacher': TeacherPostgresRepository(session_factory),
        'diary': DiaryPostgresRepository(session_factory),
        'pdi': PDIPostgresRepository(session_factory),
        'form_submission': FormSubmissionsPostgresRepository(session_factory),
        'object_metadata': ObjectStorageMetadataPostgresRepository(session_factory),
    }
