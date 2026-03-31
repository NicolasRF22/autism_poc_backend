"""Armazenamento persistente de Cadastros de Docentes."""
import os
import json
import uuid
from typing import List, Dict, Optional

from time_utils import now_brasilia_iso


class TeacherStorage:
    def __init__(self, storage_dir: str = "./teachers"):
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

    def create_teacher(self, teacher_data: Dict) -> Dict:
        teacher_id = str(uuid.uuid4())
        teacher = {
            "id": teacher_id,
            **teacher_data,
            "created_at": now_brasilia_iso(),
            "updated_at": now_brasilia_iso(),
        }
        self._index.append(teacher)
        self._save_index()
        return teacher

    def update_teacher(self, teacher_id: str, teacher_data: Dict) -> Optional[Dict]:
        teacher = self.get_teacher(teacher_id)
        if not teacher:
            return None

        created_at = teacher["created_at"]
        teacher.clear()
        teacher["id"] = teacher_id
        teacher["created_at"] = created_at
        teacher.update(teacher_data)
        teacher["updated_at"] = now_brasilia_iso()

        self._save_index()
        return teacher

    def get_teacher(self, teacher_id: str) -> Optional[Dict]:
        return next((teacher for teacher in self._index if teacher["id"] == teacher_id), None)

    def list_all_teachers(self) -> List[Dict]:
        summaries = []
        for teacher in self._index:
            summaries.append({
                "id": teacher["id"],
                "name": teacher.get("name", ""),
                "school_name": teacher.get("school_name", ""),
                "specialization": teacher.get("specialization", ""),
                "updated_at": teacher["updated_at"],
            })
        return sorted(summaries, key=lambda value: value["name"].lower())

    def delete_teacher(self, teacher_id: str) -> bool:
        teacher = self.get_teacher(teacher_id)
        if not teacher:
            return False

        self._index.remove(teacher)
        self._save_index()
        return True
