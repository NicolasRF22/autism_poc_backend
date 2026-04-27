#!/usr/bin/env python3
"""Sincroniza os cadastros locais com o Supabase/PostgreSQL.

O objetivo é manter o Render consistente com os arquivos versionados no repositório.
O script é idempotente: pode ser executado em todo deploy/startup.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from object_storage import build_object_storage
from postgres_repositories import create_postgres_repositories
from school_storage import SchoolStorage
from municipality_storage import MunicipalityStorage
from student_storage import StudentStorage
from teacher_storage import TeacherStorage
from diary_storage import DiaryStorage
from pdi_storage import PDIStorage


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _iter_items(value: Any) -> Iterable[Dict]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def _normalize_index_item(item: Dict) -> Dict:
    payload = dict(item)
    payload.pop("id", None)
    payload.pop("created_at", None)
    payload.pop("updated_at", None)
    return payload


def _mirror_entities(
    *,
    repo,
    local_items: List[Dict],
    remote_items: List[Dict],
    get_local_id: Callable[[Dict], str],
    get_remote_id: Callable[[Dict], str],
    upsert_one: Callable[[Dict], None],
    delete_remote: Callable[[str], bool],
) -> Tuple[int, int]:
    local_ids = {item_id for item_id in (get_local_id(item) for item in local_items) if item_id}
    remote_ids = {item_id for item_id in (get_remote_id(item) for item in remote_items) if item_id}

    deleted = 0
    for remote_id in sorted(remote_ids - local_ids):
        if delete_remote(remote_id):
            deleted += 1

    synced = 0
    for item in local_items:
        item_id = get_local_id(item)
        if not item_id:
            continue
        upsert_one(item)
        synced += 1

    return synced, deleted


def main() -> int:
    load_dotenv()

    database_url = _env("DATABASE_URL")
    if not database_url:
        print("[sync] DATABASE_URL ausente; nada a sincronizar.")
        return 0

    backend_dir = BACKEND_DIR
    source_dir = backend_dir

    repositories = create_postgres_repositories(database_url)

    municipalities = list(_iter_items(_read_json(source_dir / "municipalities" / "index.json", [])))
    schools = list(_iter_items(_read_json(source_dir / "schools" / "index.json", [])))
    teachers = list(_iter_items(_read_json(source_dir / "teachers" / "index.json", [])))
    students = list(_iter_items(_read_json(source_dir / "students" / "index.json", [])))
    users = list(_iter_items(_read_json(source_dir / "users" / "index.json", [])))
    diaries = list(_iter_items(_read_json(source_dir / "diaries" / "index.json", [])))
    pdis = list(_iter_items(_read_json(source_dir / "pdis" / "index.json", [])))

    users_synced, users_deleted = _mirror_entities(
        repo=repositories["auth"],
        local_items=users,
        remote_items=repositories["auth"].list_users(),
        get_local_id=lambda item: str(item.get("id") or "").strip(),
        get_remote_id=lambda item: str(item.get("id") or "").strip(),
        upsert_one=lambda item: repositories["auth"].upsert_user(
            user_id=str(item.get("id") or "").strip(),
            username=str(item.get("username") or "").strip(),
            password_hash=str(item.get("password_hash") or "").strip() or None,
            role=str(item.get("role") or "viewer").strip(),
            name=str(item.get("name") or "").strip(),
            municipio_id=str(item.get("municipio_id") or "").strip(),
            school_id=str(item.get("school_id") or "").strip(),
            teacher_id=str(item.get("teacher_id") or "").strip(),
            is_active=bool(item.get("is_active", True)),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        ),
        delete_remote=lambda entity_id: repositories["auth"].delete_user(entity_id),
    )

    municipalities_synced, municipalities_deleted = _mirror_entities(
        repo=repositories["municipality"],
        local_items=municipalities,
        remote_items=repositories["municipality"].list_all_municipalities(),
        get_local_id=lambda item: str(item.get("id") or item.get("municipio_id") or "").strip(),
        get_remote_id=lambda item: str(item.get("id") or "").strip(),
        upsert_one=lambda item: (
            repositories["municipality"].update_municipality(
                municipio_id=str(item.get("id") or item.get("municipio_id") or "").strip(),
                name=str(item.get("name") or "").strip(),
                created_at=item.get("created_at"),
                updated_at=item.get("updated_at"),
            )
            if repositories["municipality"].get_municipality(str(item.get("id") or item.get("municipio_id") or "").strip())
            else repositories["municipality"].create_municipality(
                municipio_id=str(item.get("id") or item.get("municipio_id") or "").strip(),
                name=str(item.get("name") or "").strip(),
                created_at=item.get("created_at"),
                updated_at=item.get("updated_at"),
            )
        ),
        delete_remote=lambda entity_id: repositories["municipality"].delete_municipality(entity_id),
    )

    schools_synced, schools_deleted = _mirror_entities(
        repo=repositories["school"],
        local_items=schools,
        remote_items=repositories["school"].list_all_schools(),
        get_local_id=lambda item: str(item.get("id") or "").strip(),
        get_remote_id=lambda item: str(item.get("id") or "").strip(),
        upsert_one=lambda item: repositories["school"].create_school(
            _normalize_index_item(item),
            school_id=str(item.get("id") or "").strip(),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        ),
        delete_remote=lambda entity_id: repositories["school"].delete_school(entity_id),
    )

    teachers_synced, teachers_deleted = _mirror_entities(
        repo=repositories["teacher"],
        local_items=teachers,
        remote_items=repositories["teacher"].list_all_teachers(),
        get_local_id=lambda item: str(item.get("id") or "").strip(),
        get_remote_id=lambda item: str(item.get("id") or "").strip(),
        upsert_one=lambda item: repositories["teacher"].create_teacher(
            _normalize_index_item(item),
            teacher_id=str(item.get("id") or "").strip(),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        ),
        delete_remote=lambda entity_id: repositories["teacher"].delete_teacher(entity_id),
    )

    students_synced, students_deleted = _mirror_entities(
        repo=repositories["student"],
        local_items=students,
        remote_items=repositories["student"].list_all_students(),
        get_local_id=lambda item: str(item.get("id") or "").strip(),
        get_remote_id=lambda item: str(item.get("id") or "").strip(),
        upsert_one=lambda item: repositories["student"].create_student(
            _normalize_index_item(item),
            student_id=str(item.get("id") or "").strip(),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        ),
        delete_remote=lambda entity_id: repositories["student"].delete_student(entity_id),
    )

    diaries_synced, diaries_deleted = _mirror_entities(
        repo=repositories["diary"],
        local_items=diaries,
        remote_items=repositories["diary"].list_all_entries(),
        get_local_id=lambda item: str(item.get("id") or "").strip(),
        get_remote_id=lambda item: str(item.get("id") or "").strip(),
        upsert_one=lambda item: repositories["diary"].save_entry(
            student_name=str(item.get("student_name") or ""),
            teachers=list(item.get("teachers") or []),
            diary_date=str(item.get("diary_date") or ""),
            answers=dict(item.get("answers") or {}),
            open_obs=str(item.get("open_obs") or ""),
            student_id=(str(item.get("student_id") or "").strip() or None),
            status=str(item.get("status") or "draft"),
            source=str(item.get("source") or "manual"),
            parse_warnings=list(item.get("parse_warnings") or []),
            entry_id=str(item.get("id") or "").strip(),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        ),
        delete_remote=lambda entity_id: repositories["diary"].delete_entry(entity_id),
    )

    pdis_synced, pdis_deleted = _mirror_entities(
        repo=repositories["pdi"],
        local_items=pdis,
        remote_items=repositories["pdi"].list_all_full_pdis(),
        get_local_id=lambda item: str(item.get("id") or "").strip(),
        get_remote_id=lambda item: str(item.get("id") or "").strip(),
        upsert_one=lambda item: repositories["pdi"].save_pdi(
            student_name=str(item.get("student_name") or ""),
            birth_date=str(item.get("birth_date") or ""),
            guardians=list(item.get("guardians") or []),
            diagnosis=str(item.get("diagnosis") or ""),
            class_name=str(item.get("class") or ""),
            teachers=list(item.get("teachers") or []),
            trimesters=dict(item.get("trimesters") or {}),
            student_id=(str(item.get("student_id") or "").strip() or None),
            pdi_id=str(item.get("id") or "").strip(),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        ),
        delete_remote=lambda entity_id: repositories["pdi"].delete_pdi(entity_id),
    )

    print(
        "[sync] concluído: "
        f"users={users_synced} (del={users_deleted}), "
        f"municipalities={municipalities_synced} (del={municipalities_deleted}), "
        f"schools={schools_synced} (del={schools_deleted}), "
        f"teachers={teachers_synced} (del={teachers_deleted}), "
        f"students={students_synced} (del={students_deleted}), "
        f"diaries={diaries_synced} (del={diaries_deleted}), "
        f"pdis={pdis_synced} (del={pdis_deleted})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
