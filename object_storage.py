import os
from typing import Dict, Optional


class ObjectStorageError(Exception):
    pass


class BaseObjectStorage:
    def upload_file(self, bucket: str, object_key: str, content: bytes, content_type: str):
        raise NotImplementedError

    def download_file(self, bucket: str, object_key: str) -> bytes:
        raise NotImplementedError

    def delete_file(self, bucket: str, object_key: str) -> bool:
        raise NotImplementedError


class LocalObjectStorage(BaseObjectStorage):
    def __init__(self, bucket_dirs: Dict[str, str]):
        self.bucket_dirs = dict(bucket_dirs or {})
        for path in self.bucket_dirs.values():
            os.makedirs(path, exist_ok=True)

    def _resolve_path(self, bucket: str, object_key: str) -> str:
        base_dir = self.bucket_dirs.get(bucket)
        if not base_dir:
            raise ObjectStorageError(f'Bucket local não configurado: {bucket}')
        return os.path.join(base_dir, object_key)

    def upload_file(self, bucket: str, object_key: str, content: bytes, content_type: str):
        target_path = self._resolve_path(bucket, object_key)
        with open(target_path, 'wb') as file_obj:
            file_obj.write(content)

    def download_file(self, bucket: str, object_key: str) -> bytes:
        target_path = self._resolve_path(bucket, object_key)
        if not os.path.exists(target_path):
            raise FileNotFoundError(target_path)
        with open(target_path, 'rb') as file_obj:
            return file_obj.read()

    def delete_file(self, bucket: str, object_key: str) -> bool:
        target_path = self._resolve_path(bucket, object_key)
        if not os.path.exists(target_path):
            return False
        os.remove(target_path)
        return True


class SupabaseObjectStorage(BaseObjectStorage):
    def __init__(self, supabase_url: str, service_role_key: str):
        try:
            from supabase import create_client
        except Exception as exc:
            raise ObjectStorageError('Dependência supabase não instalada. Adicione supabase ao requirements.txt') from exc

        self.client = create_client(supabase_url, service_role_key)

    def upload_file(self, bucket: str, object_key: str, content: bytes, content_type: str):
        try:
            self.client.storage.from_(bucket).upload(
                path=object_key,
                file=content,
                file_options={'content-type': content_type, 'upsert': 'true'},
            )
        except Exception as exc:
            raise ObjectStorageError(f'Falha ao enviar arquivo para Supabase Storage: {exc}') from exc

    def download_file(self, bucket: str, object_key: str) -> bytes:
        try:
            return self.client.storage.from_(bucket).download(path=object_key)
        except Exception as exc:
            raise FileNotFoundError(f'Arquivo não encontrado no Supabase Storage: {bucket}/{object_key}') from exc

    def delete_file(self, bucket: str, object_key: str) -> bool:
        try:
            self.client.storage.from_(bucket).remove([object_key])
            return True
        except Exception:
            return False


def build_object_storage(
    backend: str,
    local_bucket_dirs: Optional[Dict[str, str]] = None,
    supabase_url: Optional[str] = None,
    supabase_service_role_key: Optional[str] = None,
) -> BaseObjectStorage:
    backend_mode = (backend or 'local').strip().lower()

    if backend_mode == 'supabase':
        if not supabase_url or not supabase_service_role_key:
            raise ObjectStorageError('SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY são obrigatórios para OBJECT_STORAGE_BACKEND=supabase')
        return SupabaseObjectStorage(supabase_url=supabase_url, service_role_key=supabase_service_role_key)

    return LocalObjectStorage(bucket_dirs=local_bucket_dirs or {})
