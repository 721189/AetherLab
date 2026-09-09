"""Object storage service for satellite products and large rasters.

PostgreSQL holds metadata, provenance, results and hashes.
The object store holds the actual GeoTIFF/NetCDF assets — multi-GB files
that should never live inside the relational database.

Configuration
-------------
All values are optional. When OBJECT_STORE_ENDPOINT is empty the service
is disabled and every operation raises ObjectStoreDisabledError.

Object key scheme
-----------------
    satellite_products/{source}/{scene_id}/{band_or_product}.{ext}

Immutability
------------
Uploaded objects are immutable. The same checksum maps to the same key —
re-uploading identical content returns the existing key instead of creating
a duplicate. This makes re-processing idempotent across Celery retries.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path, PurePath
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from app.core.config import settings


class ObjectStoreDisabledError(Exception):
    """Raised when an operation is requested but no object store is configured."""


class ObjectStoreError(Exception):
    """Wrapped storage backend error."""


def _safe_basename(name: str) -> str:
    """Sanitise a filename component so it cannot escape the object key."""
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
    return safe or "unnamed"


def satellite_product_key(
    source: str,
    scene_id: str,
    sub_key: str = "",
    ext: str = "tif",
) -> str:
    """Build a deterministic, hierarchical object key.

    Args:
        source: provider/source name, e.g. "sentinel2", "sentinel5p".
        scene_id: catalogued scene id, e.g.
            "S2A_MSIL1C_20260801T045621_N0510_R094_T30TVK_20260801T064955".
        sub_key: optional sub-path within the scene folder, e.g.
            "ndvi" or "B04". Empty means top of scene folder.
        ext: filename extension (no leading dot). Defaults to "tif".
    """
    source = _safe_basename(source.strip().lower())
    scene_id = _safe_basename(scene_id.strip())
    if sub_key:
        sub_key = _safe_basename(sub_key.strip())
        filename = f"{sub_key}.{ext}"
    else:
        filename = f"{scene_id[:16]}.{ext}"

    return f"satellite_products/{source}/{scene_id}/{filename}"


class _LocalStore:
    """Filesystem-backed store used when OBJECT_STORE_ENDPOINT is empty.

    Root directory is derived from settings.BASE_DIR so it is predictable
    and doesn't pollute the repo.
    """

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _full_path(self, key: str) -> Path:
        if key.startswith("satellite_products/"):
            rel = key[len("satellite_products/") :]
        else:
            rel = key
        return self.root / "object_store" / rel

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        path = self._full_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        path = self._full_path(key)
        if not path.is_file():
            raise FileNotFoundError(f"No object at {key}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._full_path(key).is_file()

    def delete(self, key: str) -> None:
        path = self._full_path(key)
        if path.is_file():
            path.unlink()

    def list(self, prefix: str = "") -> List[str]:
        base = self.root / "object_store"
        if prefix:
            base = base / prefix
        if not base.is_dir():
            return []
        out: List[str] = []
        for p in base.rglob("*"):
            if p.is_file():
                rel = p.relative_to(base.parent)
                out.append(str(rel).replace(os.sep, "/"))
        return sorted(out)

    def checksum(self, key: str) -> str:
        return hashlib.sha256(self.get(key)).hexdigest()

    def presigned_download_url(
        self,
        key: str,
        *,
        expires_in: int = 3600,
    ) -> Optional[str]:
        path = self._full_path(key)
        if not path.is_file():
            return None
        encoded = quote(str(path.resolve()), safe="")
        return f"file://{encoded}"


class _S3Store:
    """S3-compatible backend using boto3.

    Requires boto3 to be installed. The dependency is optional so the
    application still starts when object storage is disabled or boto3 is absent
    (operations then raise ObjectStoreDisabledError or a clear error).
    """

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "",
        secure: bool = True,
    ) -> None:
        try:
            import boto3
            from botocore.config import Config as BotoConfig
            from botocore.exceptions import ClientError
        except ImportError as exc:
            raise RuntimeError(
                "Object storage is enabled but boto3 is not installed. "
                "Install it with: pip install boto3"
            ) from exc

        self._boto3 = boto3
        self._ClientError = ClientError
        self._bucket = bucket

        config_kwargs: Dict[str, Any] = {
            "region_name": region or "us-east-1",
            "config": BotoConfig(
                signature_version="s3v4",
                max_pool_connections=10,
            ),
            "endpoint_url": endpoint if endpoint else None,
            "aws_access_key_id": access_key or "",
            "aws_secret_access_key": secret_key or "",
        }
        if not secure:
            config_kwargs["use_ssl"] = False

        self._client = self._boto3.client("s3", **config_kwargs)

    @staticmethod
    def _sha256_hex(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": data,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        if metadata:
            kwargs["Metadata"] = {str(k): str(v) for k, v in metadata.items()}

        try:
            self._client.put_object(**kwargs)
        except self._ClientError as exc:
            raise ObjectStoreError(str(exc)) from exc
        return key

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except self._ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "NoSuchKey":
                raise FileNotFoundError(f"No object at {key}") from exc
            raise ObjectStoreError(str(exc)) from exc
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except self._ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey"):
                return False
            raise ObjectStoreError(str(exc)) from exc
        return True

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except self._ClientError as exc:
            raise ObjectStoreError(str(exc)) from exc

    def list(self, prefix: str = "") -> List[str]:
        out: List[str] = []
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            page_iter = paginator.paginate(
                Bucket=self._bucket, Prefix=prefix or None
            )
            for page in page_iter:
                for obj in page.get("Contents", []):
                    k = obj.get("Key", "")
                    if k and not k.endswith("/"):  # skip folder placeholders
                        out.append(k)
        except self._ClientError as exc:
            raise ObjectStoreError(str(exc)) from exc
        return sorted(out)

    def checksum(self, key: str) -> str:
        return self._sha256_hex(self.get(key))

    def presigned_download_url(
        self,
        key: str,
        *,
        expires_in: int = 3600,
    ) -> Optional[str]:
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except self._ClientError:
            return None



class ObjectStoreService:
    """High-level object storage service.

    Usage::

        store = ObjectStoreService.get()          # singleton-ish, config-driven
        key = store.put(product_bytes, source=..., scene_id=..., ext="tif")
        data = store.get(key)
        url = store.presigned_download_url(key)
    """

    _instance: Optional[Any] = None  # lazily created backend

    @classmethod
    def get(cls) -> Any:
        """Return the configured backend, creating it on first call.

        Returns None when object storage is disabled (no endpoint configured).
        """
        if cls._instance is None:
            cls._instance = cls._build()
        return cls._instance

    @classmethod
    def _build(cls) -> Any:
        if not settings.OBJECT_STORE_ENDPOINT:
            return None

        # S3-compatible takes precedence when an endpoint is configured.
        if settings.OBJECT_STORE_ACCESS_KEY or settings.OBJECT_STORE_SECRET_KEY:
            return _S3Store(
                endpoint=settings.OBJECT_STORE_ENDPOINT,
                bucket=settings.OBJECT_STORE_BUCKET,
                access_key=settings.OBJECT_STORE_ACCESS_KEY,
                secret_key=settings.OBJECT_STORE_SECRET_KEY,
                region=settings.OBJECT_STORE_REGION,
                secure=settings.OBJECT_STORE_SECURE,
            )

        # Fall back to local filesystem when only a bucket name (or nothing) is
        # configured. This is convenient for local development without S3.
        return _LocalStore(root=str(settings.BASE_DIR))

    @staticmethod
    def _require_backend() -> Any:
        backend = ObjectStoreService.get()
        if backend is None:
            raise ObjectStoreDisabledError(
                "Object storage is not configured. "
                "Set OBJECT_STORE_ENDPOINT (or use a local dev path)."
            )
        return backend

    @staticmethod
    def put(
        data: bytes,
        *,
        source: str = "satellite",
        scene_id: str = "",
        sub_key: str = "",
        ext: str = "tif",
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        make_immutable: bool = True,
    ) -> str:
        """Upload data and return the object key.

        When make_immutable=True the same content is never stored twice:
        if an object with an identical SHA-256 already exists the existing key
        is returned instead of uploading a duplicate. Disabling enables testing.
        """
        backend = ObjectStoreService._require_backend()
        key = satellite_product_key(
            source=_safe_basename(source),
            scene_id=_safe_basename(scene_id) if scene_id else "",
            sub_key=sub_key,
            ext=ext,
        )
        sha = hashlib.sha256(data).hexdigest()

        if make_immutable and backend.exists(key):
            existing_sha = backend.checksum(key)
            if existing_sha == sha:
                return key
            raise ObjectStoreError(
                f"Key already exists with a different checksum: {key}"
            )

        return backend.put(
            key,
            data,
            content_type=content_type,
            metadata=(metadata or {}) | {"sha256": sha, "uploaded_at": str(time.time())},
        )

    @staticmethod
    def get(key: str) -> bytes:
        backend = ObjectStoreService._require_backend()
        return backend.get(key)

    @staticmethod
    def exists(key: str) -> bool:
        backend = ObjectStoreService._require_backend()
        return backend.exists(key)

    @staticmethod
    def delete(key: str) -> None:
        backend = ObjectStoreService._require_backend()
        backend.delete(key)

    @staticmethod
    def list(prefix: str = "") -> List[str]:
        backend = ObjectStoreService._require_backend()
        return backend.list(prefix)

    @staticmethod
    def checksum(key: str) -> str:
        backend = ObjectStoreService._require_backend()
        return backend.checksum(key)

    @staticmethod
    def presigned_download_url(
        key: str,
        *,
        expires_in: int = 3600,
    ) -> Optional[str]:
        backend = ObjectStoreService._require_backend()
        return backend.presigned_download_url(key, expires_in=expires_in)

    @staticmethod
    def put_satellite_band(
        data: bytes,
        source: str,
        scene_id: str,
        band: str,
        *,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload a single satellite band (e.g. B04, B08) for a scene."""
        return ObjectStoreService.put(
            data, source=source, scene_id=scene_id,
            sub_key=band, ext="tif", content_type=content_type,
        )

    @staticmethod
    def put_satellite_product(
        data: bytes,
        source: str,
        scene_id: str,
        product_name: str,
        *,
        content_type: Optional[str] = None,
        ext: str = "tif",
    ) -> str:
        """Upload a derived product (e.g. NDVI, NO2 aggregation)."""
        return ObjectStoreService.put(
            data, source=source, scene_id=scene_id,
            sub_key=product_name, ext=ext, content_type=content_type,
        )

    @staticmethod
    def get_satellite_band(key: str) -> bytes:
        """Retrieve a band/product bytes by its full key."""
        return ObjectStoreService.get(key)

