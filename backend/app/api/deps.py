from __future__ import annotations

from app.library.service import LibraryService, get_library_service


def library_dep() -> LibraryService:
    return get_library_service()
