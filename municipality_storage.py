"""Armazenamento persistente de municipios."""
import json
import os
from typing import Dict, List, Optional

from time_utils import now_brasilia_iso


class MunicipalityStorage:
    def __init__(self, storage_dir: str = "./municipalities"):
        self.storage_dir = storage_dir
        self.index_path = os.path.join(storage_dir, "index.json")
        os.makedirs(storage_dir, exist_ok=True)
        self._index: List[Dict] = self._load_index()

    def _load_index(self) -> List[Dict]:
        if os.path.exists(self.index_path):
            with open(self.index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_index(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)

    def get_municipality(self, municipio_id: str) -> Optional[Dict]:
        municipio_id = str(municipio_id or "").strip()
        if not municipio_id:
            return None
        return next((m for m in self._index if (m.get("id") or "") == municipio_id), None)

    def list_all_municipalities(self) -> List[Dict]:
        return sorted(
            [dict(item) for item in self._index],
            key=lambda value: (value.get("name") or "").lower(),
        )

    def create_municipality(self, municipio_id: str, name: str) -> Dict:
        municipio_id = str(municipio_id or "").strip()
        name = str(name or "").strip()
        if not municipio_id:
            raise ValueError("municipio_id é obrigatório")
        if not name:
            raise ValueError("Nome do município é obrigatório")
        if self.get_municipality(municipio_id):
            raise ValueError("Municipio já existe")

        now = now_brasilia_iso()
        municipality = {
            "id": municipio_id,
            "name": name,
            "created_at": now,
            "updated_at": now,
        }
        self._index.append(municipality)
        self._save_index()
        return municipality
