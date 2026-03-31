"""Armazenamento persistente de Planos de Desenvolvimento Individual (PDI)."""
import os
import json
import uuid
import unicodedata
from typing import List, Dict, Optional

from time_utils import now_brasilia_iso


class PDIStorage:
    def __init__(self, storage_dir: str = "./pdis"):
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

    def _pdi_matches_student(self, pdi: Dict, student_id: Optional[str], student_name: str) -> bool:
        pdi_student_id = (pdi.get("student_id") or "").strip()
        if student_id and pdi_student_id:
            return pdi_student_id == student_id

        if student_name:
            return self._normalize_name(pdi.get("student_name", "")) == self._normalize_name(student_name)

        return False

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
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
    ) -> Dict:
        """Cria um novo PDI."""
        pdi_id = str(uuid.uuid4())
        pdi = {
            "id": pdi_id,
            "student_id": student_id,
            "student_name": student_name,
            "birth_date": birth_date,
            "guardians": guardians,
            "diagnosis": diagnosis,
            "class": class_name,
            "teachers": teachers,
            "trimesters": trimesters,
            "created_at": now_brasilia_iso(),
            "updated_at": now_brasilia_iso(),
        }
        self._index.append(pdi)
        self._save_index()
        return pdi

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
        """Atualiza um PDI existente."""
        pdi = self.get_pdi(pdi_id)
        if not pdi:
            return None
        
        # Atualiza os campos
        pdi["student_id"] = student_id
        pdi["student_name"] = student_name
        pdi["birth_date"] = birth_date
        pdi["guardians"] = guardians
        pdi["diagnosis"] = diagnosis
        pdi["class"] = class_name
        pdi["teachers"] = teachers
        pdi["trimesters"] = trimesters
        pdi["updated_at"] = now_brasilia_iso()
        
        self._save_index()
        return pdi

    def get_pdi(self, pdi_id: str) -> Optional[Dict]:
        """Retorna um PDI específico por ID."""
        return next((p for p in self._index if p["id"] == pdi_id), None)

    def get_pdi_by_student(self, student_name: str, student_id: Optional[str] = None) -> Optional[Dict]:
        """Retorna o PDI de um aluno específico (espera-se apenas um PDI ativo por aluno)."""
        pdis = [
            p
            for p in self._index
            if self._pdi_matches_student(p, student_id, student_name)
        ]
        # Retorna o mais recente se houver múltiplos
        if pdis:
            return sorted(pdis, key=lambda x: x["updated_at"], reverse=True)[0]
        return None

    def has_pdi_for_student(self, student_name: str, student_id: Optional[str] = None, exclude_pdi_id: Optional[str] = None) -> bool:
        for pdi in self._index:
            if exclude_pdi_id and pdi.get("id") == exclude_pdi_id:
                continue
            if self._pdi_matches_student(pdi, student_id, student_name):
                return True
        return False

    def list_all_pdis(self) -> List[Dict]:
        """Retorna lista de todos os PDIs com informações resumidas."""
        summaries = []
        for pdi in self._index:
            summaries.append({
                "id": pdi["id"],
                "student_id": pdi.get("student_id"),
                "student_name": pdi["student_name"],
                "class": pdi["class"],
                "diagnosis": pdi["diagnosis"],
                "updated_at": pdi["updated_at"],
                "teachers": pdi["teachers"],
            })
        # Ordenar por data de atualização (mais recente primeiro)
        return sorted(summaries, key=lambda x: x["updated_at"], reverse=True)

    def delete_pdi(self, pdi_id: str) -> bool:
        """Remove um PDI."""
        pdi = self.get_pdi(pdi_id)
        if not pdi:
            return False
        self._index = [p for p in self._index if p["id"] != pdi_id]
        self._save_index()
        return True

    def link_pdis_to_student(self, student_id: str, student_name: str) -> int:
        """Vincula PDIs legados sem student_id ao aluno cadastrado pelo nome."""
        if not student_id or not student_name:
            return 0

        normalized_name = self._normalize_name(student_name)
        linked_count = 0

        for pdi in self._index:
            if pdi.get("student_id"):
                continue
            if self._normalize_name(pdi.get("student_name", "")) != normalized_name:
                continue

            pdi["student_id"] = student_id
            pdi["student_name"] = student_name
            pdi["updated_at"] = now_brasilia_iso()
            linked_count += 1

        if linked_count:
            self._save_index()

        return linked_count
