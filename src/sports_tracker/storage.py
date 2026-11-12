"""Immutable raw-snapshot storage contracts and local/cloud adapters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ModuleNotFoundError:  # pragma: no cover - exercised by the optional-dependency guard
    boto3 = None
    BotoConfig = None

from .config import ObjectStorageSettings, OpenLigaDBSettings, load_object_storage_settings
from .openligadb import OpenLigaDBResponse
from .snapshots import RawSnapshot, save_raw_snapshot


class SnapshotStorageError(RuntimeError):
    """Raised when an immutable snapshot cannot be stored or verified."""


@dataclass(frozen=True)
class SnapshotBlob:
    """Verified bytes and metadata retrieved from a snapshot store."""

    key: str
    body: bytes
    metadata: dict[str, object]
    metadata_bytes: bytes | None = None


class SnapshotStore(Protocol):
    """Provider-neutral contract for immutable raw response storage."""

    def put(self, key: str, body: bytes, metadata: dict[str, object]) -> None: ...

    def get(self, key: str) -> SnapshotBlob: ...


class LocalSnapshotStore:
    """Filesystem adapter retaining the existing response.json/metadata.json layout."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, key: str, body: bytes, metadata: dict[str, object]) -> None:
        directory = self.root / key
        digest = hashlib.sha256(body).hexdigest()
        declared_digest = str(metadata.get("sha256", "")).lower()
        if declared_digest != digest:
            raise SnapshotStorageError("snapshot metadata SHA-256 does not match response bytes")
        directory.parent.mkdir(parents=True, exist_ok=True)
        if directory.exists():
            raise SnapshotStorageError(f"immutable snapshot already exists: {directory}")

        with TemporaryDirectory(prefix=f".{directory.name}.", dir=directory.parent) as temporary:
            staging = Path(temporary)
            response_path = staging / "response.json"
            metadata_path = staging / "metadata.json"
            with response_path.open("xb") as response_file:
                response_file.write(body)
            with metadata_path.open("x", encoding="utf-8", newline="\n") as metadata_file:
                json.dump(metadata, metadata_file, indent=2, ensure_ascii=False)
                metadata_file.write("\n")
            try:
                staging.rename(directory)
            except FileExistsError as exc:
                raise SnapshotStorageError(
                    f"immutable snapshot already exists: {directory}"
                ) from exc

    def get(self, key: str) -> SnapshotBlob:
        directory = self.root / key
        try:
            body = (directory / "response.json").read_bytes()
            metadata_bytes = (directory / "metadata.json").read_bytes()
            metadata = json.loads(metadata_bytes)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SnapshotStorageError(f"could not read immutable snapshot: {directory}") from exc
        if hashlib.sha256(body).hexdigest() != str(metadata.get("sha256", "")).lower():
            raise SnapshotStorageError(f"snapshot hash verification failed: {directory}")
        return SnapshotBlob(
            key=key,
            body=body,
            metadata=metadata,
            metadata_bytes=metadata_bytes,
        )

    def capture(
        self,
        response: OpenLigaDBResponse,
        settings: OpenLigaDBSettings,
        matchday: int,
    ) -> RawSnapshot:
        """Capture through the established writer; raw bytes remain unmodified."""

        return save_raw_snapshot(response, settings, matchday)


def build_snapshot_object_key(
    settings: ObjectStorageSettings,
    *,
    shortcut: str,
    season: int,
    matchday: int,
    retrieved_at_utc: str,
    sha256: str,
) -> str:
    """Build a deterministic key that separates retrievals while addressing content."""

    try:
        timestamp = datetime.fromisoformat(retrieved_at_utc.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotStorageError("snapshot retrieval time is not valid ISO-8601") from exc
    if timestamp.tzinfo is None:
        raise SnapshotStorageError("snapshot retrieval time must be timezone-aware")
    safe_timestamp = timestamp.astimezone(UTC).strftime("%Y%m%dT%H%M%S.%fZ").replace(".", "")
    digest = sha256.lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise SnapshotStorageError("snapshot SHA-256 must be a 64-character hexadecimal value")
    return f"{settings.prefix}/{shortcut}/{season}/matchday-{matchday}/{safe_timestamp}_{digest}"


class NeonS3SnapshotStore:
    """Private S3-compatible store with immutable, hash-verified snapshot objects."""

    def __init__(
        self,
        settings: ObjectStorageSettings | None = None,
        *,
        client: object | None = None,
    ) -> None:
        self.settings = settings or load_object_storage_settings()
        if client is not None:
            self.client = client
        else:
            if boto3 is None or BotoConfig is None:
                raise SnapshotStorageError(
                    "cloud snapshot storage requires the optional cloud dependency"
                )
            self.client = boto3.client(
                "s3",
                endpoint_url=self.settings.endpoint_url,
                region_name=self.settings.region,
                aws_access_key_id=self.settings.access_key_id,
                aws_secret_access_key=self.settings.secret_access_key,
                config=BotoConfig(
                    signature_version="s3v4",
                    connect_timeout=self.settings.connect_timeout_seconds,
                    read_timeout=self.settings.read_timeout_seconds,
                    retries={"mode": "standard", "max_attempts": 3},
                ),
            )

    @property
    def bucket(self) -> str:
        return self.settings.bucket

    def _object_key(self, key: str, filename: str) -> str:
        clean_key = key.strip("/")
        if not clean_key or ".." in clean_key or "\\" in clean_key:
            raise SnapshotStorageError("snapshot object key is not safe")
        return f"{clean_key}/{filename}"

    def _read_object(self, object_key: str) -> bytes | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        except Exception as exc:
            if self._is_missing(exc):
                return None
            raise SnapshotStorageError(
                f"could not read object {object_key}: {type(exc).__name__}"
            ) from exc
        try:
            return response["Body"].read()
        except Exception as exc:
            raise SnapshotStorageError(
                f"could not read object body {object_key}: {type(exc).__name__}"
            ) from exc

    @staticmethod
    def _is_missing(exc: BaseException) -> bool:
        response = getattr(exc, "response", None)
        if not isinstance(response, dict):
            return False
        error = response.get("Error")
        if not isinstance(error, dict):
            return False
        return str(error.get("Code", "")) in {"404", "NoSuchKey", "NotFound"}

    @staticmethod
    def _is_precondition_failure(exc: BaseException) -> bool:
        response = getattr(exc, "response", None)
        if not isinstance(response, dict):
            return False
        error = response.get("Error")
        if not isinstance(error, dict):
            return False
        return str(error.get("Code", "")) in {"PreconditionFailed", "412"}

    def _put_if_absent_or_equal(
        self,
        object_key: str,
        body: bytes,
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> bool:
        existing = self._read_object(object_key)
        if existing is not None:
            if existing != body:
                raise SnapshotStorageError(f"immutable object content mismatch: {object_key}")
            return False
        arguments: dict[str, object] = {
            "Bucket": self.bucket,
            "Key": object_key,
            "Body": body,
            "ContentType": content_type,
            "IfNoneMatch": "*",
        }
        if metadata:
            arguments["Metadata"] = metadata
        try:
            self.client.put_object(**arguments)
        except Exception as exc:
            if not self._is_precondition_failure(exc):
                raise SnapshotStorageError(
                    f"could not store object {object_key}: {type(exc).__name__}"
                ) from exc
            existing = self._read_object(object_key)
            if existing != body:
                raise SnapshotStorageError(
                    f"immutable object content mismatch after concurrent upload: {object_key}"
                ) from exc
            return False
        return True

    def put_files(
        self,
        key: str,
        body: bytes,
        metadata_bytes: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> None:
        """Store exact response and metadata bytes, allowing safe idempotent retries."""

        digest = hashlib.sha256(body).hexdigest()
        declared_digest = expected_sha256 or ""
        if declared_digest and declared_digest.lower() != digest:
            raise SnapshotStorageError("snapshot SHA-256 does not match response bytes")
        try:
            metadata = json.loads(metadata_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SnapshotStorageError("snapshot metadata is not valid UTF-8 JSON") from exc
        if not isinstance(metadata, dict) or str(metadata.get("sha256", "")).lower() != digest:
            raise SnapshotStorageError("snapshot metadata SHA-256 does not match response bytes")
        if metadata.get("byte_count") is not None:
            try:
                declared_byte_count = int(metadata["byte_count"])
            except (TypeError, ValueError) as exc:
                raise SnapshotStorageError("snapshot metadata byte_count is invalid") from exc
            if declared_byte_count != len(body):
                raise SnapshotStorageError(
                    "snapshot metadata byte_count does not match response bytes"
                )
        response_key = self._object_key(key, "response.json")
        metadata_key = self._object_key(key, "metadata.json")
        response_created = False
        try:
            response_created = self._put_if_absent_or_equal(
                response_key,
                body,
                content_type=str(metadata.get("content_type") or "application/json"),
                metadata={"sha256": digest},
            )
            self._put_if_absent_or_equal(
                metadata_key,
                metadata_bytes,
                content_type="application/json",
                metadata={"sha256": digest},
            )
            stored_body = self._read_object(response_key)
            stored_metadata = self._read_object(metadata_key)
            if stored_body != body or stored_metadata != metadata_bytes:
                raise SnapshotStorageError(f"snapshot read-after-write verification failed: {key}")
        except SnapshotStorageError:
            if response_created:
                try:
                    self.client.delete_object(Bucket=self.bucket, Key=response_key)
                except Exception as cleanup_error:
                    raise SnapshotStorageError(
                        f"snapshot upload failed and cleanup failed for {key}: "
                        f"{type(cleanup_error).__name__}"
                    ) from cleanup_error
            raise

    def put(self, key: str, body: bytes, metadata: dict[str, object]) -> None:
        """Serialize metadata in the same stable form as the local snapshot writer."""

        metadata_bytes = json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        self.put_files(
            key,
            body,
            metadata_bytes,
            expected_sha256=str(metadata.get("sha256", "")),
        )

    def get(self, key: str) -> SnapshotBlob:
        response_key = self._object_key(key, "response.json")
        metadata_key = self._object_key(key, "metadata.json")
        body = self._read_object(response_key)
        metadata_bytes = self._read_object(metadata_key)
        if body is None or metadata_bytes is None:
            raise SnapshotStorageError(f"snapshot objects are incomplete: {key}")
        try:
            metadata = json.loads(metadata_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SnapshotStorageError(f"snapshot metadata is invalid: {key}") from exc
        if not isinstance(metadata, dict):
            raise SnapshotStorageError(f"snapshot metadata must be an object: {key}")
        digest = hashlib.sha256(body).hexdigest()
        if digest != str(metadata.get("sha256", "")).lower():
            raise SnapshotStorageError(f"snapshot hash verification failed: {key}")
        if metadata.get("byte_count") is not None:
            try:
                byte_count = int(metadata["byte_count"])
            except (TypeError, ValueError) as exc:
                raise SnapshotStorageError(
                    f"snapshot byte-count verification failed: {key}"
                ) from exc
            if byte_count != len(body):
                raise SnapshotStorageError(f"snapshot byte-count verification failed: {key}")
        return SnapshotBlob(
            key=key,
            body=body,
            metadata=metadata,
            metadata_bytes=metadata_bytes,
        )


class CloudSnapshotStoreUnavailable:
    """Compatibility adapter for deployments that intentionally have no cloud store."""

    def put(self, key: str, body: bytes, metadata: dict[str, object]) -> None:
        del key, body, metadata
        raise SnapshotStorageError(
            "private cloud snapshot storage is not configured; local disk is not durable in Render"
        )

    def get(self, key: str) -> SnapshotBlob:
        del key
        raise SnapshotStorageError("private cloud snapshot storage is not configured")
