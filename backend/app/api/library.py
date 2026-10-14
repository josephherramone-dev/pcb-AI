from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import library_dep
from app.library.catalog import all_parts
from app.library.service import LibraryService, PartUnavailable
from app.render.pcb import footprint_render
from app.render.schematic import symbol_render
from app.templates.circuits import template_summaries

router = APIRouter(prefix="/api", tags=["library"])


@router.get("/library/status")
def library_status(lib: LibraryService = Depends(library_dep)):
    return lib.status()


@router.get("/library/parts")
def list_parts(q: str | None = None, category: str | None = None, lib: LibraryService = Depends(library_dep)):
    return {"parts": lib.list_parts(q, category),
            "categories": sorted({p.category for p in all_parts()})}


@router.get("/library/parts/{part_id}")
def get_part(part_id: str, lib: LibraryService = Depends(library_dep)):
    try:
        resolved = lib.resolve(part_id)
    except PartUnavailable as e:
        raise HTTPException(404, str(e)) from e
    data = resolved.to_detail()
    data["symbol"] = symbol_render(resolved.symbol)
    data["footprint_render"] = footprint_render(resolved.footprint) if resolved.footprint else None
    return data


@router.get("/templates")
def templates():
    return template_summaries()
