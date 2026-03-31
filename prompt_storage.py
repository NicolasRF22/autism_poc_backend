"""Armazenamento persistente dos prompts customizáveis de PEI e Chat."""
import json
import os
from typing import Dict

from prompts import SYSTEM_PROMPT_CHAT, SYSTEM_PROMPT_PEI
from time_utils import now_brasilia_iso


class PromptStorage:
    def __init__(self, storage_dir: str = "./prompts"):
        self.storage_dir = storage_dir
        self.pei_prompt_path = os.path.join(storage_dir, "pei_prompt.json")
        self.chat_prompt_path = os.path.join(storage_dir, "chat_prompt.json")
        os.makedirs(storage_dir, exist_ok=True)
        self._ensure_prompt_file(self.pei_prompt_path, SYSTEM_PROMPT_PEI)
        self._ensure_prompt_file(self.chat_prompt_path, SYSTEM_PROMPT_CHAT)

    def _ensure_prompt_file(self, path: str, default_prompt: str):
        if os.path.exists(path):
            return
        now = now_brasilia_iso()
        payload = {
            "base_prompt": default_prompt,
            "current_prompt": default_prompt,
            "base_updated_at": now,
            "updated_at": now,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _read_payload(self, path: str, default_prompt: str) -> Dict:
        self._ensure_prompt_file(path, default_prompt)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Compatibilidade com versão antiga {prompt, updated_at}
        if "base_prompt" not in data or "current_prompt" not in data:
            now = now_brasilia_iso()
            legacy_prompt = (data.get("prompt") or default_prompt).strip()
            migrated = {
                "base_prompt": default_prompt,
                "current_prompt": legacy_prompt,
                "base_updated_at": now,
                "updated_at": data.get("updated_at") or now,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(migrated, f, ensure_ascii=False, indent=2)
            return migrated

        return data

    def _write_payload(self, path: str, payload: Dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def get_pei_prompt(self) -> Dict:
        data = self._read_payload(self.pei_prompt_path, SYSTEM_PROMPT_PEI)
        base_prompt = (data.get("base_prompt") or SYSTEM_PROMPT_PEI).strip() or SYSTEM_PROMPT_PEI
        current_prompt = (data.get("current_prompt") or base_prompt).strip() or base_prompt

        return {
            "prompt": current_prompt,
            "base_prompt": base_prompt,
            "is_custom": current_prompt != base_prompt,
            "updated_at": data.get("updated_at"),
            "base_updated_at": data.get("base_updated_at"),
        }

    def save_pei_prompt(self, prompt: str) -> Dict:
        clean_prompt = (prompt or "").strip()
        data = self._read_payload(self.pei_prompt_path, SYSTEM_PROMPT_PEI)
        data["current_prompt"] = clean_prompt
        data["updated_at"] = now_brasilia_iso()
        self._write_payload(self.pei_prompt_path, data)
        return self.get_pei_prompt()

    def reset_pei_prompt_to_base(self) -> Dict:
        data = self._read_payload(self.pei_prompt_path, SYSTEM_PROMPT_PEI)
        data["current_prompt"] = (data.get("base_prompt") or SYSTEM_PROMPT_PEI).strip() or SYSTEM_PROMPT_PEI
        data["updated_at"] = now_brasilia_iso()
        self._write_payload(self.pei_prompt_path, data)
        return self.get_pei_prompt()

    def get_chat_prompt(self) -> Dict:
        data = self._read_payload(self.chat_prompt_path, SYSTEM_PROMPT_CHAT)
        base_prompt = (data.get("base_prompt") or SYSTEM_PROMPT_CHAT).strip() or SYSTEM_PROMPT_CHAT
        current_prompt = (data.get("current_prompt") or base_prompt).strip() or base_prompt

        return {
            "prompt": current_prompt,
            "base_prompt": base_prompt,
            "is_custom": current_prompt != base_prompt,
            "updated_at": data.get("updated_at"),
            "base_updated_at": data.get("base_updated_at"),
        }

    def save_chat_prompt(self, prompt: str) -> Dict:
        clean_prompt = (prompt or "").strip()
        data = self._read_payload(self.chat_prompt_path, SYSTEM_PROMPT_CHAT)
        data["current_prompt"] = clean_prompt
        data["updated_at"] = now_brasilia_iso()
        self._write_payload(self.chat_prompt_path, data)
        return self.get_chat_prompt()

    def reset_chat_prompt_to_base(self) -> Dict:
        data = self._read_payload(self.chat_prompt_path, SYSTEM_PROMPT_CHAT)
        data["current_prompt"] = (data.get("base_prompt") or SYSTEM_PROMPT_CHAT).strip() or SYSTEM_PROMPT_CHAT
        data["updated_at"] = now_brasilia_iso()
        self._write_payload(self.chat_prompt_path, data)
        return self.get_chat_prompt()