"""Component library service: curated catalog + data read from KiCad libraries."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings
from app.library.catalog import CatalogPart, all_parts, get_part
from app.library.footprints import FootprintDef, FootprintLibrary, FootprintNotFound
from app.library.symbols import SymbolDef, SymbolLibrary, SymbolNotFound


class PartUnavailable(LookupError):
    pass


@dataclass
class ResolvedPart:
    part: CatalogPart
    symbol: SymbolDef
    footprint: FootprintDef | None

    def to_summary(self) -> dict:
        p = self.part
        return {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "lib_symbol": p.lib_symbol,
            "footprint": p.footprint,
            "ref_prefix": p.ref_prefix,
            "default_value": p.default_value,
            "value_editable": p.value_editable,
            "in_bom": p.in_bom,
            "on_board": p.on_board,
            "description": self.symbol.description,
            "keywords": self.symbol.keywords,
            "datasheet": self.symbol.datasheet,
            "footprint_description": self.footprint.description if self.footprint else None,
            "notes": p.notes,
            "source": "KiCad official libraries (symbol/footprint metadata read from installed library files)",
        }

    def to_detail(self) -> dict:
        data = self.to_summary()
        data["pins"] = [
            {"number": pin.number, "name": pin.name, "electrical_type": pin.electrical_type, "unit": pin.unit}
            for pin in self.symbol.pins
        ]
        data["pads"] = sorted(self.footprint.pad_numbers) if self.footprint else []
        return data


class LibraryService:
    def __init__(self, symbols: SymbolLibrary, footprints: FootprintLibrary):
        self.symbols = symbols
        self.footprints = footprints

    def status(self) -> dict:
        return {
            "symbol_dir": str(self.symbols.root),
            "symbol_libraries_available": self.symbols.available(),
            "footprint_dir": str(self.footprints.root),
            "footprint_libraries_available": self.footprints.available(),
        }

    def resolve(self, part_id: str) -> ResolvedPart:
        part = get_part(part_id)
        if part is None:
            raise PartUnavailable(f"unknown part id {part_id!r}")
        try:
            symbol = self.symbols.get(part.lib_symbol)
        except SymbolNotFound as e:
            raise PartUnavailable(str(e)) from e
        fp = None
        if part.footprint:
            try:
                fp = self.footprints.get(part.footprint)
            except FootprintNotFound as e:
                raise PartUnavailable(str(e)) from e
        return ResolvedPart(part=part, symbol=symbol, footprint=fp)

    def list_parts(self, query: str | None = None, category: str | None = None) -> list[dict]:
        out = []
        q = (query or "").lower().strip()
        for part in all_parts():
            if category and part.category != category:
                continue
            try:
                resolved = self.resolve(part.id)
            except PartUnavailable as e:
                out.append({"id": part.id, "name": part.name, "category": part.category,
                            "available": False, "error": str(e)})
                continue
            summary = resolved.to_summary()
            haystack = " ".join(
                str(summary.get(k) or "") for k in ("id", "name", "category", "description", "keywords",
                                                    "lib_symbol", "footprint")
            ).lower()
            if q and not all(tok in haystack for tok in q.split()):
                continue
            summary["available"] = True
            out.append(summary)
        return out


@lru_cache
def get_library_service() -> LibraryService:
    s = get_settings()
    return LibraryService(SymbolLibrary(s.symbol_dir()), FootprintLibrary(s.footprint_dir()))
