"""Armazenamento persistente de Cadastros de Escolas."""
import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional


class SchoolStorage:
    def __init__(self, storage_dir: str = "./schools"):
        self.storage_dir = storage_dir
        self.index_path = os.path.join(storage_dir, "index.json")
        os.makedirs(storage_dir, exist_ok=True)
        self._index: List[Dict] = self._load_index()

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------
    def _load_index(self) -> List[Dict]:
        if os.path.exists(self.index_path):
            with open(self.index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_index(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create_school(self, school_data: Dict) -> Dict:
        """Cria um novo cadastro de escola."""
        school_id = str(uuid.uuid4())
        school = {
            "id": school_id,
            **school_data,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._index.append(school)
        self._save_index()
        return school

    def update_school(self, school_id: str, school_data: Dict) -> Optional[Dict]:
        """Atualiza um cadastro de escola existente."""
        school = self.get_school(school_id)
        if not school:
            return None

        # Atualiza de forma não-destrutiva para preservar campos do cadastro completo
        school.update(school_data)
        school["updated_at"] = datetime.now().isoformat()
        
        self._save_index()
        return school

    def get_school(self, school_id: str) -> Optional[Dict]:
        """Retorna um cadastro de escola específico por ID."""
        return next((s for s in self._index if s["id"] == school_id), None)

    def list_all_schools(self) -> List[Dict]:
        """Retorna lista de todas as escolas com informações resumidas."""
        summaries = []
        for school in self._index:
            summaries.append({
                "id": school["id"],
                "name": school.get("name", ""),
                "cnpj": school.get("cnpj", ""),
                "institution_type": school.get("institution_type", ""),
                "city": school.get("address", {}).get("city", "") if isinstance(school.get("address"), dict) else "",
                "updated_at": school["updated_at"],
            })
        # Ordenar por nome
        return sorted(summaries, key=lambda x: x["name"].lower())

    def delete_school(self, school_id: str) -> bool:
        """Remove um cadastro de escola."""
        school = self.get_school(school_id)
        if not school:
            return False
        
        self._index.remove(school)
        self._save_index()
        return True
