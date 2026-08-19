"""Armazenamento persistente dos prompts customizáveis de PEI e Chat."""
import json
import os
import uuid
from contextlib import contextmanager
from typing import Dict, List, Optional

from sqlalchemy import Boolean, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from prompts import SYSTEM_PROMPT_CHAT, SYSTEM_PROMPT_DIARY_SUMMARY, SYSTEM_PROMPT_PEI
from time_utils import now_brasilia_iso


class PromptBase(DeclarativeBase):
    pass


class PromptRecord(PromptBase):
    __tablename__ = 'prompt_templates'
    __table_args__ = (
        UniqueConstraint('scope', 'name', name='uq_prompt_templates_scope_name'),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class PromptStorage:
    def __init__(self, storage_dir: str = './prompts', database_url: str = ''):
        self.storage_dir = storage_dir
        self.database_url = (database_url or os.getenv('DATABASE_URL') or '').strip()
        self.pei_prompt_path = os.path.join(storage_dir, 'pei_prompt.json')
        self.chat_prompt_path = os.path.join(storage_dir, 'chat_prompt.json')
        self.diary_summary_prompt_path = os.path.join(storage_dir, 'diary_summary_prompt.json')
        os.makedirs(storage_dir, exist_ok=True)
        self._engine = None
        self._session_factory = None
        self._use_database = bool(self.database_url)

        if self._use_database:
            self._engine = create_engine(self.database_url, future=True)
            self._session_factory = sessionmaker(bind=self._engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
            PromptBase.metadata.create_all(self._engine)
            self._seed_database_defaults()
        else:
            self._ensure_scope_file('pei')
            self._ensure_scope_file('chat')
            self._ensure_scope_file('diary_summary')

    def _scope_default_content(self, scope: str) -> str:
        if scope == 'chat':
            return SYSTEM_PROMPT_CHAT
        if scope == 'pei':
            return SYSTEM_PROMPT_PEI
        if scope == 'diary_summary':
            return SYSTEM_PROMPT_DIARY_SUMMARY
        raise ValueError('Escopo inválido')

    def _scope_default_name(self, scope: str) -> str:
        if scope == 'chat':
            return 'Prompt base do Chat'
        if scope == 'diary_summary':
            return 'Prompt base do Resumo Diário'
        return 'Prompt base do PEI'

    def _scope_path(self, scope: str) -> str:
        scope = self._normalize_scope(scope)
        if scope == 'chat':
            return self.chat_prompt_path
        if scope == 'diary_summary':
            return self.diary_summary_prompt_path
        return self.pei_prompt_path

    def _normalize_scope(self, scope: str) -> str:
        normalized = (scope or '').strip().lower()
        if normalized not in {'chat', 'pei', 'diary_summary'}:
            raise ValueError('Escopo inválido')
        return normalized

    def _new_prompt_dict(
        self,
        *,
        prompt_id: Optional[str] = None,
        scope: str,
        name: str,
        description: str,
        content: str,
        is_default: bool = False,
        is_active: bool = False,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> Dict:
        now = now_brasilia_iso()
        return {
            'id': str(prompt_id or uuid.uuid4()),
            'scope': self._normalize_scope(scope),
            'name': (name or '').strip() or self._scope_default_name(scope),
            'description': (description or '').strip(),
            'content': (content or '').strip(),
            'is_default': bool(is_default),
            'is_active': bool(is_active),
            'created_at': created_at or now,
            'updated_at': updated_at or now,
        }

    def _sorted_prompts(self, prompts: List[Dict]) -> List[Dict]:
        return sorted(
            prompts,
            key=lambda item: (
                not bool(item.get('is_active')),
                not bool(item.get('is_default')),
                item.get('updated_at') or '',
                item.get('name') or '',
            ),
            reverse=False,
        )

    def _scope_file_payload(self, scope: str) -> Dict:
        scope = self._normalize_scope(scope)
        path = self._scope_path(scope)
        default_content = self._scope_default_content(scope)
        default_prompt = self._new_prompt_dict(
            prompt_id=f'{scope}-default',
            scope=scope,
            name=self._scope_default_name(scope),
            description='Prompt inicial do sistema',
            content=default_content,
            is_default=True,
            is_active=True,
        )

        if not os.path.exists(path):
            payload = {
                'scope': scope,
                'active_prompt_id': default_prompt['id'],
                'prompts': [default_prompt],
                'updated_at': default_prompt['updated_at'],
            }
            self._write_scope_file(scope, payload)
            return payload

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f) or {}

        prompts = data.get('prompts') or []
        if prompts:
            normalized_prompts = []
            active_prompt_id = (data.get('active_prompt_id') or data.get('current_prompt_id') or '').strip()
            for item in prompts:
                prompt_id = str(item.get('id') or '').strip() or str(uuid.uuid4())
                normalized_prompts.append({
                    'id': prompt_id,
                    'scope': scope,
                    'name': (item.get('name') or self._scope_default_name(scope)).strip(),
                    'description': (item.get('description') or '').strip(),
                    'content': (item.get('content') or '').strip(),
                    'is_default': bool(item.get('is_default')),
                    'is_active': bool(item.get('is_active')),
                    'created_at': item.get('created_at') or now_brasilia_iso(),
                    'updated_at': item.get('updated_at') or now_brasilia_iso(),
                })
            if active_prompt_id:
                for item in normalized_prompts:
                    item['is_active'] = item['id'] == active_prompt_id
            elif normalized_prompts:
                normalized_prompts[0]['is_active'] = True
                active_prompt_id = normalized_prompts[0]['id']
            payload = {
                'scope': scope,
                'active_prompt_id': active_prompt_id or (normalized_prompts[0]['id'] if normalized_prompts else default_prompt['id']),
                'prompts': normalized_prompts,
                'updated_at': data.get('updated_at') or now_brasilia_iso(),
            }
            self._write_scope_file(scope, payload)
            return payload

        base_prompt = (data.get('base_prompt') or default_content).strip() or default_content
        current_prompt = (data.get('current_prompt') or base_prompt).strip() or base_prompt
        base_updated_at = data.get('base_updated_at') or now_brasilia_iso()
        current_updated_at = data.get('updated_at') or now_brasilia_iso()

        prompts = [
            self._new_prompt_dict(
                prompt_id=f'{scope}-default',
                scope=scope,
                name=self._scope_default_name(scope),
                description='Prompt base',
                content=base_prompt,
                is_default=True,
                is_active=current_prompt == base_prompt,
                created_at=base_updated_at,
                updated_at=base_updated_at,
            )
        ]
        active_prompt_id = prompts[0]['id']

        if current_prompt != base_prompt:
            custom_prompt = self._new_prompt_dict(
                prompt_id=f'{scope}-custom',
                scope=scope,
                name='Prompt atual',
                description='Prompt migrado da versão antiga',
                content=current_prompt,
                is_default=False,
                is_active=True,
                created_at=current_updated_at,
                updated_at=current_updated_at,
            )
            prompts.append(custom_prompt)
            active_prompt_id = custom_prompt['id']
            prompts[0]['is_active'] = False

        payload = {
            'scope': scope,
            'active_prompt_id': active_prompt_id,
            'prompts': prompts,
            'updated_at': current_updated_at,
        }
        self._write_scope_file(scope, payload)
        return payload

    def _write_scope_file(self, scope: str, payload: Dict):
        scope = self._normalize_scope(scope)
        with open(self._scope_path(scope), 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    @contextmanager
    def _session(self):
        if not self._session_factory:
            raise RuntimeError('Storage em modo arquivo')
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _prompt_to_dict(self, prompt: PromptRecord | Dict) -> Dict:
        if isinstance(prompt, dict):
            return dict(prompt)
        return {
            'id': prompt.id,
            'scope': prompt.scope,
            'name': prompt.name,
            'description': prompt.description or '',
            'content': prompt.content,
            'is_default': bool(prompt.is_default),
            'is_active': bool(prompt.is_active),
            'created_at': prompt.created_at,
            'updated_at': prompt.updated_at,
        }

    def _get_default_prompt(self, scope: str) -> Dict:
        prompts = self.list_prompts(scope)
        for prompt in prompts:
            if prompt.get('is_default'):
                return prompt
        if prompts:
            return prompts[0]
        scope = self._normalize_scope(scope)
        content = self._scope_default_content(scope)
        return self._new_prompt_dict(
            prompt_id=f'{scope}-default',
            scope=scope,
            name=self._scope_default_name(scope),
            description='Prompt base',
            content=content,
            is_default=True,
            is_active=True,
        )

    def _bundle_from_prompts(self, scope: str, prompts: List[Dict]) -> Dict:
        scope = self._normalize_scope(scope)
        ordered = self._sorted_prompts(prompts)
        active_prompt = next((prompt for prompt in ordered if prompt.get('is_active')), None)
        default_prompt = next((prompt for prompt in ordered if prompt.get('is_default')), None)
        if active_prompt is None and ordered:
            active_prompt = ordered[0]
        if default_prompt is None and ordered:
            default_prompt = ordered[0]

        active_prompt = active_prompt or self._new_prompt_dict(
            prompt_id=f'{scope}-default',
            scope=scope,
            name=self._scope_default_name(scope),
            description='Prompt base',
            content=self._scope_default_content(scope),
            is_default=True,
            is_active=True,
        )
        default_prompt = default_prompt or active_prompt

        return {
            'scope': scope,
            'prompt': active_prompt.get('content') or '',
            'base_prompt': default_prompt.get('content') or '',
            'is_custom': active_prompt.get('id') != default_prompt.get('id') or (active_prompt.get('content') or '') != (default_prompt.get('content') or ''),
            'updated_at': active_prompt.get('updated_at'),
            'base_updated_at': default_prompt.get('updated_at'),
            'current_prompt_id': active_prompt.get('id'),
            'current_prompt_name': active_prompt.get('name') or '',
            'current_prompt_description': active_prompt.get('description') or '',
            'available_prompts': ordered,
        }

    def _ensure_scope_file(self, scope: str):
        self._scope_file_payload(scope)

    def _seed_database_defaults(self):
        for scope in ('pei', 'chat', 'diary_summary'):
            self._ensure_database_scope(scope)

    def _ensure_database_scope(self, scope: str):
        scope = self._normalize_scope(scope)
        with self._session() as session:
            existing = session.execute(select(PromptRecord).where(PromptRecord.scope == scope)).scalars().all()
            if existing:
                return

            payload = self._scope_file_payload(scope)
            prompts = payload.get('prompts') or []
            if not prompts:
                default_content = self._scope_default_content(scope)
                prompts = [self._new_prompt_dict(
                    prompt_id=f'{scope}-default',
                    scope=scope,
                    name=self._scope_default_name(scope),
                    description='Prompt base',
                    content=default_content,
                    is_default=True,
                    is_active=True,
                )]

            for prompt in prompts:
                session.add(PromptRecord(
                    id=prompt['id'],
                    scope=scope,
                    name=prompt['name'],
                    description=prompt.get('description') or '',
                    content=prompt['content'],
                    is_default=bool(prompt.get('is_default')),
                    is_active=bool(prompt.get('is_active')),
                    created_at=prompt.get('created_at') or now_brasilia_iso(),
                    updated_at=prompt.get('updated_at') or now_brasilia_iso(),
                ))
            session.flush()

    def _db_list_prompts(self, scope: str) -> List[Dict]:
        scope = self._normalize_scope(scope)
        with self._session() as session:
            rows = session.execute(select(PromptRecord).where(PromptRecord.scope == scope)).scalars().all()
        prompts = [self._prompt_to_dict(row) for row in rows]
        return self._sorted_prompts(prompts)

    def _db_get_prompt(self, prompt_id: str) -> Optional[Dict]:
        prompt_id = str(prompt_id or '').strip()
        if not prompt_id:
            return None
        with self._session() as session:
            row = session.get(PromptRecord, prompt_id)
            return self._prompt_to_dict(row) if row else None

    def _db_get_prompt_by_scope(self, scope: str, prompt_id: str) -> Optional[Dict]:
        scope = self._normalize_scope(scope)
        prompt_id = str(prompt_id or '').strip()
        if not prompt_id:
            return None
        with self._session() as session:
            row = session.execute(
                select(PromptRecord).where(PromptRecord.scope == scope, PromptRecord.id == prompt_id)
            ).scalar_one_or_none()
            return self._prompt_to_dict(row) if row else None

    def _db_bundle(self, scope: str) -> Dict:
        return self._bundle_from_prompts(scope, self._db_list_prompts(scope))

    def _db_set_active_prompt(self, scope: str, prompt_id: str) -> Dict:
        scope = self._normalize_scope(scope)
        prompt_id = str(prompt_id or '').strip()
        if not prompt_id:
            raise ValueError('Prompt não encontrado')
        with self._session() as session:
            row = session.execute(
                select(PromptRecord).where(PromptRecord.scope == scope, PromptRecord.id == prompt_id)
            ).scalar_one_or_none()
            if not row:
                raise ValueError('Prompt não encontrado')
            session.execute(
                select(PromptRecord).where(PromptRecord.scope == scope, PromptRecord.id != prompt_id)
            )
            for other in session.execute(select(PromptRecord).where(PromptRecord.scope == scope)).scalars().all():
                other.is_active = other.id == prompt_id
                if other.id == prompt_id:
                    other.updated_at = now_brasilia_iso()
            session.flush()
        return self._db_get_prompt(prompt_id) or {}

    def _db_create_prompt(self, scope: str, name: str, description: str, content: str, activate: bool = False) -> Dict:
        scope = self._normalize_scope(scope)
        now = now_brasilia_iso()
        prompt = PromptRecord(
            id=str(uuid.uuid4()),
            scope=scope,
            name=(name or '').strip() or self._scope_default_name(scope),
            description=(description or '').strip(),
            content=(content or '').strip(),
            is_default=False,
            is_active=bool(activate),
            created_at=now,
            updated_at=now,
        )
        with self._session() as session:
            if activate:
                for other in session.execute(select(PromptRecord).where(PromptRecord.scope == scope)).scalars().all():
                    other.is_active = False
            session.add(prompt)
            session.flush()
            if activate:
                prompt.is_active = True
        return self._prompt_to_dict(prompt)

    def _db_update_prompt(self, prompt_id: str, name: Optional[str], description: Optional[str], content: Optional[str], activate: Optional[bool] = None) -> Dict:
        prompt_id = str(prompt_id or '').strip()
        if not prompt_id:
            raise ValueError('Prompt não encontrado')
        with self._session() as session:
            row = session.get(PromptRecord, prompt_id)
            if not row:
                raise ValueError('Prompt não encontrado')
            if name is not None:
                row.name = (name or '').strip() or row.name
            if description is not None:
                row.description = (description or '').strip()
            if content is not None:
                row.content = (content or '').strip()
            row.updated_at = now_brasilia_iso()
            if activate is True:
                for other in session.execute(select(PromptRecord).where(PromptRecord.scope == row.scope)).scalars().all():
                    other.is_active = other.id == row.id
                row.is_active = True
            session.flush()
            return self._prompt_to_dict(row)

    def _db_delete_prompt(self, prompt_id: str) -> Dict:
        prompt_id = str(prompt_id or '').strip()
        if not prompt_id:
            raise ValueError('Prompt não encontrado')
        with self._session() as session:
            row = session.get(PromptRecord, prompt_id)
            if not row:
                raise ValueError('Prompt não encontrado')
            if row.is_default:
                raise ValueError('Não é permitido remover o prompt base')
            deleted = self._prompt_to_dict(row)
            scope = row.scope
            session.delete(row)
            session.flush()
            remaining = session.execute(select(PromptRecord).where(PromptRecord.scope == scope)).scalars().all()
            if remaining and not any(item.is_active for item in remaining):
                default_row = next((item for item in remaining if item.is_default), None)
                fallback = default_row or remaining[0]
                for item in remaining:
                    item.is_active = item.id == fallback.id
            session.flush()
            return deleted

    def _db_reset_scope_to_base(self, scope: str) -> Dict:
        scope = self._normalize_scope(scope)
        with self._session() as session:
            rows = session.execute(select(PromptRecord).where(PromptRecord.scope == scope)).scalars().all()
            default_row = next((item for item in rows if item.is_default), None)
            if not default_row:
                raise ValueError('Prompt base não encontrado')
            for item in rows:
                item.is_active = item.id == default_row.id
            default_row.updated_at = now_brasilia_iso()
            session.flush()
        return self._db_bundle(scope)

    def list_prompts(self, scope: str) -> List[Dict]:
        scope = self._normalize_scope(scope)
        if self._use_database:
            return self._db_list_prompts(scope)
        payload = self._scope_file_payload(scope)
        return self._sorted_prompts(payload.get('prompts') or [])

    def get_prompt(self, prompt_id: str) -> Optional[Dict]:
        prompt_id = str(prompt_id or '').strip()
        if not prompt_id:
            return None
        if self._use_database:
            return self._db_get_prompt(prompt_id)
        for scope in ('chat', 'pei', 'diary_summary'):
            payload = self._scope_file_payload(scope)
            for prompt in payload.get('prompts') or []:
                if prompt.get('id') == prompt_id:
                    return dict(prompt)
        return None

    def get_prompt_bundle(self, scope: str) -> Dict:
        scope = self._normalize_scope(scope)
        if self._use_database:
            return self._db_bundle(scope)
        payload = self._scope_file_payload(scope)
        return self._bundle_from_prompts(scope, payload.get('prompts') or [])

    def create_prompt(self, scope: str, name: str, description: str, content: str, activate: bool = False) -> Dict:
        scope = self._normalize_scope(scope)
        if not (content or '').strip():
            raise ValueError('Prompt é obrigatório')
        if self._use_database:
            return self._db_create_prompt(scope, name, description, content, activate=activate)
        payload = self._scope_file_payload(scope)
        prompts = payload.get('prompts') or []
        new_prompt = self._new_prompt_dict(
            scope=scope,
            name=name,
            description=description,
            content=content,
            is_default=False,
            is_active=bool(activate),
        )
        if activate:
            for item in prompts:
                item['is_active'] = False
            payload['active_prompt_id'] = new_prompt['id']
        prompts.append(new_prompt)
        payload['prompts'] = prompts
        payload['updated_at'] = now_brasilia_iso()
        self._write_scope_file(scope, payload)
        return new_prompt

    def update_prompt(self, prompt_id: str, scope: Optional[str] = None, name: Optional[str] = None, description: Optional[str] = None, content: Optional[str] = None, activate: Optional[bool] = None) -> Dict:
        prompt_id = str(prompt_id or '').strip()
        if not prompt_id:
            raise ValueError('Prompt não encontrado')
        if self._use_database:
            return self._db_update_prompt(prompt_id, name, description, content, activate=activate)
        for current_scope in ('chat', 'pei', 'diary_summary'):
            if scope and self._normalize_scope(scope) != current_scope:
                continue
            payload = self._scope_file_payload(current_scope)
            prompts = payload.get('prompts') or []
            for item in prompts:
                if item.get('id') != prompt_id:
                    continue
                if name is not None:
                    item['name'] = (name or '').strip() or item['name']
                if description is not None:
                    item['description'] = (description or '').strip()
                if content is not None:
                    item['content'] = (content or '').strip()
                if activate is True:
                    for other in prompts:
                        other['is_active'] = other.get('id') == prompt_id
                    payload['active_prompt_id'] = prompt_id
                item['updated_at'] = now_brasilia_iso()
                payload['updated_at'] = item['updated_at']
                self._write_scope_file(current_scope, payload)
                return dict(item)
        raise ValueError('Prompt não encontrado')

    def delete_prompt(self, prompt_id: str) -> Dict:
        prompt_id = str(prompt_id or '').strip()
        if not prompt_id:
            raise ValueError('Prompt não encontrado')
        if self._use_database:
            return self._db_delete_prompt(prompt_id)
        for scope in ('chat', 'pei', 'diary_summary'):
            payload = self._scope_file_payload(scope)
            prompts = payload.get('prompts') or []
            target = next((item for item in prompts if item.get('id') == prompt_id), None)
            if not target:
                continue
            if target.get('is_default'):
                raise ValueError('Não é permitido remover o prompt base')
            prompts = [item for item in prompts if item.get('id') != prompt_id]
            if target.get('is_active') and prompts:
                fallback = next((item for item in prompts if item.get('is_default')), prompts[0])
                for item in prompts:
                    item['is_active'] = item.get('id') == fallback.get('id')
                payload['active_prompt_id'] = fallback.get('id')
            payload['prompts'] = prompts
            payload['updated_at'] = now_brasilia_iso()
            self._write_scope_file(scope, payload)
            return target
        raise ValueError('Prompt não encontrado')

    def activate_prompt(self, prompt_id: str) -> Dict:
        prompt_id = str(prompt_id or '').strip()
        if not prompt_id:
            raise ValueError('Prompt não encontrado')
        if self._use_database:
            prompt = self._db_get_prompt(prompt_id)
            if not prompt:
                raise ValueError('Prompt não encontrado')
            return self._db_set_active_prompt(prompt['scope'], prompt_id)
        for scope in ('chat', 'pei', 'diary_summary'):
            payload = self._scope_file_payload(scope)
            prompts = payload.get('prompts') or []
            target = next((item for item in prompts if item.get('id') == prompt_id), None)
            if not target:
                continue
            for item in prompts:
                item['is_active'] = item.get('id') == prompt_id
                if item.get('id') == prompt_id:
                    item['updated_at'] = now_brasilia_iso()
            payload['active_prompt_id'] = prompt_id
            payload['updated_at'] = now_brasilia_iso()
            self._write_scope_file(scope, payload)
            return dict(target)
        raise ValueError('Prompt não encontrado')

    def save_scope_prompt(self, scope: str, prompt: str) -> Dict:
        scope = self._normalize_scope(scope)
        prompt = (prompt or '').strip()
        if not prompt:
            raise ValueError('Prompt é obrigatório')
        bundle = self.get_prompt_bundle(scope)
        current_prompt_id = bundle.get('current_prompt_id')
        if current_prompt_id:
            updated = self.update_prompt(current_prompt_id, scope=scope, content=prompt)
            return self.get_prompt_bundle(scope)
        created = self.create_prompt(scope, self._scope_default_name(scope), '', prompt, activate=True)
        return self.get_prompt_bundle(scope)

    def reset_scope_prompt_to_base(self, scope: str) -> Dict:
        scope = self._normalize_scope(scope)
        if self._use_database:
            return self._db_reset_scope_to_base(scope)
        payload = self._scope_file_payload(scope)
        prompts = payload.get('prompts') or []
        default_prompt = next((item for item in prompts if item.get('is_default')), None)
        if not default_prompt:
            raise ValueError('Prompt base não encontrado')
        for item in prompts:
            item['is_active'] = item.get('id') == default_prompt.get('id')
        payload['active_prompt_id'] = default_prompt.get('id')
        payload['updated_at'] = now_brasilia_iso()
        self._write_scope_file(scope, payload)
        return self.get_prompt_bundle(scope)

    def get_pei_prompt(self) -> Dict:
        return self.get_prompt_bundle('pei')

    def save_pei_prompt(self, prompt: str) -> Dict:
        return self.save_scope_prompt('pei', prompt)

    def reset_pei_prompt_to_base(self) -> Dict:
        return self.reset_scope_prompt_to_base('pei')

    def get_chat_prompt(self) -> Dict:
        return self.get_prompt_bundle('chat')

    def save_chat_prompt(self, prompt: str) -> Dict:
        return self.save_scope_prompt('chat', prompt)

    def reset_chat_prompt_to_base(self) -> Dict:
        return self.reset_scope_prompt_to_base('chat')

    def get_diary_summary_prompt(self) -> Dict:
        return self.get_prompt_bundle('diary_summary')

    def save_diary_summary_prompt(self, prompt: str) -> Dict:
        return self.save_scope_prompt('diary_summary', prompt)

    def reset_diary_summary_prompt_to_base(self) -> Dict:
        return self.reset_scope_prompt_to_base('diary_summary')
