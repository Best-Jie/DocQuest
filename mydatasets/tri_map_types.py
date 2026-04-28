from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RawTextBlock:
    id: str
    page: int
    bbox: list[float]
    text: str
    role: str = "paragraph"
    source: str = "fallback"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RawImageRegion:
    id: str
    page: int
    bbox: list[float]
    image_path: str
    caption_text: str = ""
    ocr_text: str = ""
    role: str = "figure"
    source: str = "fallback"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RawTableRegion:
    id: str
    page: int
    bbox: list[float]
    table_image_path: str
    caption_text: str = ""
    ocr_text: str = ""
    html: str | None = None
    markdown: str | None = None
    role: str = "table"
    source: str = "fallback"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedPage:
    page: int
    width: int | None
    height: int | None
    page_image_path: str
    text_path: str
    text_blocks: list[RawTextBlock] = field(default_factory=list)
    image_regions: list[RawImageRegion] = field(default_factory=list)
    table_regions: list[RawTableRegion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "width": self.width,
            "height": self.height,
            "page_image_path": self.page_image_path,
            "text_path": self.text_path,
            "text_blocks": [item.to_dict() for item in self.text_blocks],
            "image_regions": [item.to_dict() for item in self.image_regions],
            "table_regions": [item.to_dict() for item in self.table_regions],
        }


@dataclass
class ParsedDocument:
    doc_id: str
    doc_name: str
    pdf_path: str
    output_dir: str
    parser_backend: str
    pages: list[ParsedPage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "pdf_path": self.pdf_path,
            "output_dir": self.output_dir,
            "parser_backend": self.parser_backend,
            "pages": [page.to_dict() for page in self.pages],
        }
