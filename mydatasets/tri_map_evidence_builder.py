from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class _HTMLTableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] = []
        self.current_cell: list[str] = []
        self.in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "tr":
            self.current_row = []
        elif tag in {"td", "th"}:
            self.in_cell = True
            self.current_cell = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.in_cell:
            cell_text = " ".join("".join(self.current_cell).split()).strip()
            self.current_row.append(cell_text)
            self.current_cell = []
            self.in_cell = False
        elif tag == "tr" and self.current_row:
            self.rows.append(self.current_row)
            self.current_row = []


class TriMapEvidenceBuilder:
    def __init__(self, cfg: dict[str, Any] | None = None):
        self.cfg = cfg or {}

    def build_from_parsed_document(
        self,
        parsed_document_path: str,
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        parsed_path = Path(parsed_document_path)
        parsed_doc = json.loads(parsed_path.read_text(encoding="utf-8"))
        target_dir = Path(output_dir) if output_dir else parsed_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        doc_id = str(parsed_doc["doc_id"])
        doc_name = str(parsed_doc["doc_name"])

        text_units: list[dict[str, Any]] = []
        image_units: list[dict[str, Any]] = []
        table_units: list[dict[str, Any]] = []

        for page in parsed_doc.get("pages", []):
            page_num = int(page["page"])

            for block in page.get("text_blocks", []):
                text_units.append(
                    {
                        "doc_id": doc_id,
                        "doc_name": doc_name,
                        "block_id": block["id"],
                        "page": page_num,
                        "section": "",
                        "text": block.get("text", ""),
                        "source_type": block.get("role", "paragraph"),
                        "bbox": block.get("bbox", []),
                        "source": block.get("source", "fallback"),
                    }
                )

            for region in page.get("image_regions", []):
                image_units.append(
                    {
                        "doc_id": doc_id,
                        "doc_name": doc_name,
                        "image_id": region["id"],
                        "page": page_num,
                        "type": region.get("role", "figure"),
                        "caption": region.get("caption_text", ""),
                        "summary": "",
                        "image_path": region.get("image_path", ""),
                        "bbox": region.get("bbox", []),
                        "ocr_text": region.get("ocr_text", ""),
                        "source": region.get("source", "fallback"),
                    }
                )

            for region in page.get("table_regions", []):
                rows = self._extract_table_rows(region)
                schema = self._extract_schema(rows)
                table_units.append(
                    {
                        "doc_id": doc_id,
                        "doc_name": doc_name,
                        "table_id": region["id"],
                        "page": page_num,
                        "caption": region.get("caption_text", ""),
                        "summary": "",
                        "schema": schema,
                        "n_rows": max(len(rows) - 1, 0),
                        "rows": rows[1:] if len(rows) > 1 else [],
                        "table_image_path": region.get("table_image_path", ""),
                        "bbox": region.get("bbox", []),
                        "ocr_text": region.get("ocr_text", ""),
                        "html": region.get("html"),
                        "markdown": region.get("markdown"),
                        "sqlite_table_name": "",
                        "source": region.get("source", "fallback"),
                    }
                )

        text_path = target_dir / "text_units.jsonl"
        image_path = target_dir / "image_units.json"
        table_path = target_dir / "table_units.json"

        self._dump_jsonl(text_path, text_units)
        self._dump_json(image_path, image_units)
        self._dump_json(table_path, table_units)

        manifest = {
            "doc_id": doc_id,
            "doc_name": doc_name,
            "parsed_document_path": str(parsed_path),
            "text_units_path": str(text_path),
            "image_units_path": str(image_path),
            "table_units_path": str(table_path),
            "counts": {
                "text_units": len(text_units),
                "image_units": len(image_units),
                "table_units": len(table_units),
            },
        }
        self._dump_json(target_dir / "evidence_manifest.json", manifest)
        return manifest

    def _extract_table_rows(self, region: dict[str, Any]) -> list[list[str]]:
        html = region.get("html")
        if not isinstance(html, str) or not html.strip():
            return []

        parser = _HTMLTableExtractor()
        parser.feed(html)
        return [row for row in parser.rows if any(cell for cell in row)]

    def _extract_schema(self, rows: list[list[str]]) -> list[str]:
        if not rows:
            return []

        schema: list[str] = []
        for idx, cell in enumerate(rows[0], start=1):
            name = " ".join(str(cell).split()).strip() or f"col_{idx}"
            if name in schema:
                name = f"{name}_{idx}"
            schema.append(name)
        return schema

    def _dump_json(self, path: Path, data: Any) -> None:
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _dump_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
