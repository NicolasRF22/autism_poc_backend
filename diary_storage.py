"""Armazenamento persistente de Diários de Acompanhamento Individual."""
import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional


class DiaryStorage:
    def __init__(self, storage_dir: str = "./diaries"):
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
    def save_entry(self, student_name: str, teachers: List[str], 
                   diary_date: str, answers: Dict, open_obs: str) -> Dict:
        """Registra uma nova entrada de diário."""
        entry_id = str(uuid.uuid4())
        entry = {
            "id": entry_id,
            "student_name": student_name,
            "teachers": teachers,
            "diary_date": diary_date,
            "answers": answers,
            "open_obs": open_obs,
            "created_at": datetime.now().isoformat(),
        }
        self._index.append(entry)
        self._save_index()
        return entry

    def list_all_students(self) -> List[str]:
        """Retorna lista única de nomes de alunos com diários."""
        students = set(e["student_name"] for e in self._index)
        return sorted(list(students))

    def get_entries_by_student(self, student_name: str) -> List[Dict]:
        """Retorna todas as entradas de um aluno específico."""
        entries = [e for e in self._index if e["student_name"] == student_name]
        # Ordenar por data de diário (mais recente primeiro)
        return sorted(entries, key=lambda x: x["diary_date"], reverse=True)

    def get_entry(self, entry_id: str) -> Optional[Dict]:
        """Retorna uma entrada específica por ID."""
        return next((e for e in self._index if e["id"] == entry_id), None)

    def delete_entry(self, entry_id: str) -> bool:
        """Remove uma entrada do diário."""
        entry = self.get_entry(entry_id)
        if not entry:
            return False
        self._index = [e for e in self._index if e["id"] != entry_id]
        self._save_index()
        return True

    def get_last_teachers(self, student_name: str) -> List[str]:
        """Retorna os professores da última entrada do aluno (para usar como padrão)."""
        entries = self.get_entries_by_student(student_name)
        if entries:
            return entries[0]["teachers"]  # entries já ordenadas por data desc
        return []

    def get_student_summary(self, student_name: str) -> Dict:
        """Retorna resumo de um aluno: nome, última data, últimos professores, total de entradas."""
        entries = self.get_entries_by_student(student_name)
        if not entries:
            return None
        
        last_entry = entries[0]
        return {
            "student_name": student_name,
            "last_date": last_entry["diary_date"],
            "last_teachers": last_entry["teachers"],
            "total_entries": len(entries),
        }

    def list_all_summaries(self) -> List[Dict]:
        """Retorna resumos de todos os alunos com diários."""
        students = self.list_all_students()
        return [self.get_student_summary(s) for s in students]
