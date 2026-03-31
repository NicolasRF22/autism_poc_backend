"""Armazenamento persistente de Cadastros de Alunos."""
import os
import json
import uuid
import unicodedata
from typing import List, Dict, Optional

from time_utils import now_brasilia_iso


class StudentStorage:
    def __init__(self, storage_dir: str = "./students"):
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
    def create_student(self, student_data: Dict) -> Dict:
        """Cria um novo cadastro de aluno."""
        student_id = str(uuid.uuid4())
        student = {
            "id": student_id,
            **student_data,
            "created_at": now_brasilia_iso(),
            "updated_at": now_brasilia_iso(),
        }
        self._index.append(student)
        self._save_index()
        return student

    def update_student(self, student_id: str, student_data: Dict) -> Optional[Dict]:
        """Atualiza um cadastro de aluno existente."""
        student = self.get_student(student_id)
        if not student:
            return None

        # Atualiza de forma não-destrutiva para preservar campos do cadastro completo
        student.update(student_data)
        student["updated_at"] = now_brasilia_iso()
        
        self._save_index()
        return student

    def get_student(self, student_id: str) -> Optional[Dict]:
        """Retorna um cadastro de aluno específico por ID."""
        return next((s for s in self._index if s["id"] == student_id), None)

    def list_all_students(self) -> List[Dict]:
        """Retorna lista de todos os alunos com informações resumidas."""
        summaries = []
        for student in self._index:
            summaries.append({
                "id": student["id"],
                "name": self._student_name(student),
                "age": student.get("age", student.get("studentAge", "")),
                "school_name": student.get("school_name", student.get("schoolName", "")),
                "class": student.get("class", student.get("className", "")),
                "grade": student.get("grade", student.get("schoolYear", "")),
                "updated_at": student["updated_at"],
            })
        # Ordenar por nome
        return sorted(summaries, key=lambda x: x["name"].lower())

    def find_students_by_name(self, candidate_name: str) -> List[Dict]:
        """Busca alunos por nome normalizado (match exato)."""
        normalized_candidate = self._normalize_name(candidate_name)
        if not normalized_candidate:
            return []

        matches = []
        for student in self._index:
            student_name = self._student_name(student)
            if self._normalize_name(student_name) == normalized_candidate:
                matches.append(student)

        return matches

    def _student_name(self, student: Dict) -> str:
        return student.get("name") or student.get("studentName") or ""

    def _normalize_name(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", (value or "").strip().lower())
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return " ".join(normalized.split())

    def delete_student(self, student_id: str) -> bool:
        """Remove um cadastro de aluno."""
        student = self.get_student(student_id)
        if not student:
            return False
        
        self._index.remove(student)
        self._save_index()
        return True
