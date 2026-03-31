"""Armazenamento persistente de Diários de Acompanhamento Individual."""
import os
import json
import uuid
import unicodedata
from typing import List, Dict, Optional

from time_utils import now_brasilia_iso


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

    def _normalize_name(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", (value or "").strip().lower())
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return " ".join(normalized.split())

    def _entry_matches_student(self, entry: Dict, student_id: Optional[str], student_name: str) -> bool:
        entry_student_id = (entry.get("student_id") or "").strip()
        if student_id and entry_student_id:
            return entry_student_id == student_id

        if student_name:
            return self._normalize_name(entry.get("student_name", "")) == self._normalize_name(student_name)

        return False

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def save_entry(
        self,
        student_name: str,
        teachers: List[str],
        diary_date: str,
        answers: Dict,
        open_obs: str,
        student_id: Optional[str] = None,
        status: str = "final",
        source: str = "manual",
        parse_warnings: Optional[List[str]] = None,
    ) -> Dict:
        """Registra uma nova entrada de diário."""
        entry_id = str(uuid.uuid4())
        entry = {
            "id": entry_id,
            "student_id": student_id,
            "student_name": student_name,
            "teachers": teachers,
            "diary_date": diary_date,
            "answers": answers,
            "open_obs": open_obs,
            "status": status,
            "source": source,
            "parse_warnings": parse_warnings or [],
            "created_at": now_brasilia_iso(),
        }
        self._index.append(entry)
        self._save_index()
        return entry

    def list_all_students(self) -> List[str]:
        """Retorna lista única de nomes de alunos com diários."""
        students = set(e["student_name"] for e in self._index)
        return sorted(list(students))

    def get_entries_by_student(self, student_name: str, student_id: Optional[str] = None) -> List[Dict]:
        """Retorna todas as entradas de um aluno específico."""
        entries = [
            e
            for e in self._index
            if self._entry_matches_student(e, student_id, student_name)
        ]
        # Ordenar por data de diário (mais recente primeiro)
        return sorted(entries, key=lambda x: x["diary_date"], reverse=True)

    def has_date_conflict(self, student_id: Optional[str], student_name: str, diary_date: str) -> bool:
        if not diary_date:
            return False

        for entry in self._index:
            if not self._entry_matches_student(entry, student_id, student_name):
                continue
            if (entry.get("diary_date") or "") == diary_date:
                return True
        return False

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

    def update_entry(
        self,
        entry_id: str,
        student_name: str,
        teachers: List[str],
        diary_date: str,
        answers: Dict,
        open_obs: str,
        student_id: Optional[str] = None,
        status: str = "final",
        source: str = "manual",
        parse_warnings: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        """Atualiza uma entrada existente do diário."""
        entry = self.get_entry(entry_id)
        if not entry:
            return None

        entry.update({
            "student_id": student_id,
            "student_name": student_name,
            "teachers": teachers,
            "diary_date": diary_date,
            "answers": answers,
            "open_obs": open_obs,
            "status": status,
            "source": source,
            "parse_warnings": parse_warnings or [],
            "updated_at": now_brasilia_iso(),
        })
        self._save_index()
        return entry

    def delete_entries_by_student(self, student_name: str, student_id: Optional[str] = None) -> int:
        """Remove todas as entradas de diário de um aluno."""
        original_count = len(self._index)
        self._index = [
            entry
            for entry in self._index
            if not self._entry_matches_student(entry, student_id, student_name)
        ]

        removed_count = original_count - len(self._index)
        if removed_count > 0:
            self._save_index()

        return removed_count

    def get_last_teachers(self, student_name: str, student_id: Optional[str] = None) -> List[str]:
        """Retorna os professores da última entrada do aluno (para usar como padrão)."""
        entries = self.get_entries_by_student(student_name, student_id=student_id)
        if entries:
            return entries[0]["teachers"]  # entries já ordenadas por data desc
        return []

    def get_student_summary(self, student_name: str, student_id: Optional[str] = None) -> Dict:
        """Retorna resumo de um aluno: nome, última data, últimos professores, total de entradas."""
        entries = self.get_entries_by_student(student_name, student_id=student_id)
        if not entries:
            return None
        
        last_entry = entries[0]
        return {
            "student_id": last_entry.get("student_id"),
            "student_name": student_name,
            "last_date": last_entry["diary_date"],
            "last_teachers": last_entry["teachers"],
            "total_entries": len(entries),
        }

    def list_all_summaries(self) -> List[Dict]:
        """Retorna resumos de todos os alunos com diários."""
        grouped = {}

        for entry in self._index:
            student_id = (entry.get("student_id") or "").strip()
            student_name = entry.get("student_name") or ""
            key = f"id:{student_id}" if student_id else f"name:{self._normalize_name(student_name)}"
            if key not in grouped:
                grouped[key] = {
                    "student_id": student_id or None,
                    "student_name": student_name,
                }

        summaries = []
        for group in grouped.values():
            summary = self.get_student_summary(
                group["student_name"],
                student_id=group.get("student_id"),
            )
            if summary:
                summaries.append(summary)

        return sorted(summaries, key=lambda x: (x.get("student_name") or "").lower())

    def link_entries_to_student(self, student_id: str, student_name: str) -> int:
        """Vincula entradas legadas sem student_id a um aluno cadastrado."""
        if not student_id or not student_name:
            return 0

        normalized_name = self._normalize_name(student_name)
        linked_count = 0

        for entry in self._index:
            if entry.get("student_id"):
                continue
            if self._normalize_name(entry.get("student_name", "")) != normalized_name:
                continue

            entry["student_id"] = student_id
            entry["student_name"] = student_name
            linked_count += 1

        if linked_count:
            self._save_index()

        return linked_count
