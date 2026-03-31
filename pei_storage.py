"""Armazenamento persistente de PEIs gerados (JSON index + arquivos PDF)."""
import os
import json
import uuid
from typing import List, Dict, Optional

from time_utils import now_brasilia_iso


class PEIStorage:
    def __init__(self, storage_dir: str = "./peis"):
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
    def save(self, student_name: str, school: str,
             markdown_text: str, pdf_path: str) -> Dict:
        """Registra um novo PEI gerado no índice."""
        pei_id = str(uuid.uuid4())
        entry = {
            "id": pei_id,
            "student_name": student_name,
            "school": school,
            "created_at": now_brasilia_iso(),
            "pdf_filename": os.path.basename(pdf_path),
            "markdown": markdown_text,
        }
        self._index.append(entry)
        self._save_index()
        return entry

    def list_all(self) -> List[Dict]:
        """Retorna todos os PEIs (sem o markdown para economizar payload)."""
        return [
            {k: v for k, v in e.items() if k != "markdown"}
            for e in self._index
        ]

    def get(self, pei_id: str) -> Optional[Dict]:
        return next((e for e in self._index if e["id"] == pei_id), None)

    def get_pdf_path(self, pei_id: str) -> Optional[str]:
        entry = self.get(pei_id)
        if not entry:
            return None
        path = os.path.join(self.storage_dir, entry["pdf_filename"])
        return path if os.path.exists(path) else None

    def delete(self, pei_id: str) -> bool:
        entry = self.get(pei_id)
        if not entry:
            return False
        # Remove PDF file
        pdf_path = os.path.join(self.storage_dir, entry["pdf_filename"])
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        self._index = [e for e in self._index if e["id"] != pei_id]
        self._save_index()
        return True
