"""Armazenamento append-only de eventos de auditoria."""
import json
import os
from typing import Dict, List, Optional

from time_utils import now_brasilia_iso


class AuditStorage:
    def __init__(self, storage_dir: str = "./audit_logs"):
        self.storage_dir = storage_dir
        self.events_path = os.path.join(storage_dir, "events.jsonl")
        os.makedirs(storage_dir, exist_ok=True)

        if not os.path.exists(self.events_path):
            with open(self.events_path, "w", encoding="utf-8") as f:
                f.write("")

    def log_event(
        self,
        action: str,
        status_code: int,
        path: str,
        method: str,
        user: Optional[Dict] = None,
        details: Optional[Dict] = None,
    ):
        event = {
            "timestamp": now_brasilia_iso(),
            "action": action,
            "path": path,
            "method": method,
            "status_code": status_code,
            "outcome": "success" if status_code < 400 else "error",
            "user": user or {},
            "details": details or {},
        }

        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def list_events(self, limit: int = 200) -> List[Dict]:
        limit = max(1, min(limit, 2000))

        with open(self.events_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        events = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        events.reverse()
        return events
