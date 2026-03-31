"""Armazenamento persistente de usuários para autenticação."""
import os
import json
import uuid
from typing import Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash
from time_utils import now_brasilia_iso


VALID_ROLES = {"admin", "editor", "viewer"}


class AuthStorage:
    def __init__(
        self,
        storage_dir: str = "./users",
        default_admin_username: str = "admin",
        default_admin_password: str = "",
    ):
        self.storage_dir = storage_dir
        self.index_path = os.path.join(storage_dir, "index.json")
        self.default_admin_username = default_admin_username
        self.default_admin_password = default_admin_password
        os.makedirs(storage_dir, exist_ok=True)
        self._index: List[Dict] = self._load_index()
        self._ensure_default_admin()

    def _load_index(self) -> List[Dict]:
        if os.path.exists(self.index_path):
            with open(self.index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_index(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)

    def _ensure_default_admin(self):
        has_admin = any(user.get("role") == "admin" for user in self._index)
        if has_admin:
            return

        if not self.default_admin_password:
            raise RuntimeError(
                "AUTH_ADMIN_PASSWORD não configurada. Defina no .env para criar o admin inicial."
            )

        self._index.append(
            {
                "id": str(uuid.uuid4()),
                "username": self.default_admin_username,
                "password_hash": generate_password_hash(self.default_admin_password),
                "role": "admin",
                "is_active": True,
                "created_at": now_brasilia_iso(),
                "updated_at": now_brasilia_iso(),
            }
        )
        self._save_index()

    def _sanitize_user(self, user: Dict) -> Dict:
        return {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "is_active": user.get("is_active", True),
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
        }

    def list_users(self) -> List[Dict]:
        users = [self._sanitize_user(user) for user in self._index]
        return sorted(users, key=lambda item: item["username"].lower())

    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        user = next((u for u in self._index if u["id"] == user_id), None)
        return self._sanitize_user(user) if user else None

    def _get_raw_user_by_id(self, user_id: str) -> Optional[Dict]:
        return next((u for u in self._index if u["id"] == user_id), None)

    def _get_raw_user_by_username(self, username: str) -> Optional[Dict]:
        normalized_username = username.strip().lower()
        return next((u for u in self._index if u["username"].lower() == normalized_username), None)

    def authenticate(self, username: str, password: str) -> Optional[Dict]:
        user = self._get_raw_user_by_username(username)
        if not user or not user.get("is_active", True):
            return None

        if not check_password_hash(user["password_hash"], password):
            return None

        return self._sanitize_user(user)

    def create_user(self, username: str, password: str, role: str) -> Dict:
        username = (username or "").strip()
        if len(username) < 3:
            raise ValueError("Nome de usuário deve ter ao menos 3 caracteres")
        if len(password or "") < 6:
            raise ValueError("Senha deve ter ao menos 6 caracteres")
        if role not in VALID_ROLES:
            raise ValueError("Perfil inválido. Use: admin, editor ou viewer")
        if self._get_raw_user_by_username(username):
            raise ValueError("Nome de usuário já existe")

        now = now_brasilia_iso()
        user = {
            "id": str(uuid.uuid4()),
            "username": username,
            "password_hash": generate_password_hash(password),
            "role": role,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        self._index.append(user)
        self._save_index()
        return self._sanitize_user(user)

    def update_user_role(self, user_id: str, role: str) -> Optional[Dict]:
        if role not in VALID_ROLES:
            raise ValueError("Perfil inválido. Use: admin, editor ou viewer")

        user = self._get_raw_user_by_id(user_id)
        if not user:
            return None

        user["role"] = role
        user["updated_at"] = now_brasilia_iso()
        self._save_index()
        return self._sanitize_user(user)
