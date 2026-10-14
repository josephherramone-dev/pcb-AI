"""File storage abstraction. Local filesystem today; S3-compatible storage can implement the same interface."""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path, PurePosixPath

from app.core.config import get_settings


class Storage(ABC):
    @abstractmethod
    def put_file(self, key: str, source: Path) -> int:
        """Store a local file under ``key``; returns its size in bytes."""

    @abstractmethod
    def local_path(self, key: str) -> Path:
        """Path to a local copy of the object (downloads it first for remote backends)."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete_prefix(self, prefix: str) -> None: ...


def _safe_key(key: str) -> PurePosixPath:
    p = PurePosixPath(key)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise ValueError(f"invalid storage key {key!r}")
    return p


class LocalStorage(Storage):
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root.joinpath(*_safe_key(key).parts)

    def put_file(self, key: str, source: Path) -> int:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        return dest.stat().st_size

    def local_path(self, key: str) -> Path:
        return self._path(key)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete_prefix(self, prefix: str) -> None:
        shutil.rmtree(self._path(prefix), ignore_errors=True)


@lru_cache
def get_storage() -> Storage:
    return LocalStorage(get_settings().storage_root)
