from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from mydatasets.tri_map_types import (
    ParsedDocument,
    ParsedPage,
    RawImageRegion,
    RawTableRegion,
    RawTextBlock,
)


class TriMapParser:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.backend = str(cfg.get("backend", "mineru"))
        self.copy_visual_assets = bool(cfg.get("copy_visual_assets", True))

        mineru_root = str(cfg.get("mineru_root", "")).strip()
        self.mineru_root = Path(mineru_root).expanduser() if mineru_root else None

        ignored_types = cfg.get(
            "ignored_types",
            [
                "aside_text",
                "page_footnote",
                "page_header",
                "page_footer",
                "page_number",
            ],
        )
        self.ignored_types = {str(item).strip() for item in ignored_types if str(item).strip()}

    def parse_document(
        self,
        pdf_path: str,
        doc_id: str,
        output_dir: str,
        page_limit: int | None = None,
    ) -> ParsedDocument:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        content_list_path = self._resolve_content_list_path(doc_id)
        payload = json.loads(content_list_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"MinerU content list must be a list: {content_list_path}")

        pages_by_number: dict[int, ParsedPage] = {}
        counters: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for page_num, block in self._iter_blocks(payload):
            if page_limit is not None and page_num > page_limit:
                continue

            page = pages_by_number.setdefault(
                page_num,
                ParsedPage(
                    page=page_num,
                    width=None,
                    height=None,
                    page_image_path="",
                    text_path=str(content_list_path),
                ),
            )

            block_type = str(block.get("type", "")).strip()
            if not block_type or block_type in self.ignored_types:
                continue

            if block_type in {"text", "title", "paragraph"}:
                text_value = self._extract_text_value(block)
                if not text_value:
                    continue

                item_id = self._next_id(counters, page_num, "text")
                role = self._get_text_role(block)
                page.text_blocks.append(
                    RawTextBlock(
                        id=f"mineru_text_p{page_num}_b{item_id}",
                        page=page_num,
                        bbox=self._normalize_bbox(block.get("bbox")),
                        text=text_value,
                        role=role,
                        source="mineru_vlm",
                    )
                )
                continue

            if block_type == "list":
                text_value = self._extract_list_value(block)
                if not text_value:
                    continue

                item_id = self._next_id(counters, page_num, "text")
                page.text_blocks.append(
                    RawTextBlock(
                        id=f"mineru_text_p{page_num}_b{item_id}",
                        page=page_num,
                        bbox=self._normalize_bbox(block.get("bbox")),
                        text=text_value,
                        role="list",
                        source="mineru_vlm",
                    )
                )
                continue

            if block_type == "image":
                item_id = self._next_id(counters, page_num, "image")
                image_path = self._materialize_visual_asset(
                    img_path=self._extract_image_path(block),
                    output_dir=output_path,
                    page_num=page_num,
                    branch="img",
                    item_id=item_id,
                    content_list_dir=content_list_path.parent,
                )
                if image_path is None:
                    continue

                page.image_regions.append(
                    RawImageRegion(
                        id=f"mineru_img_p{page_num}_b{item_id}",
                        page=page_num,
                        bbox=self._normalize_bbox(block.get("bbox")),
                        image_path=str(image_path),
                        caption_text=self._extract_image_caption(block),
                        ocr_text=self._extract_image_footnote(block),
                        role="figure",
                        source="mineru_vlm",
                    )
                )
                continue

            if block_type == "table":
                item_id = self._next_id(counters, page_num, "table")
                table_path = self._materialize_visual_asset(
                    img_path=self._extract_table_path(block),
                    output_dir=output_path,
                    page_num=page_num,
                    branch="table",
                    item_id=item_id,
                    content_list_dir=content_list_path.parent,
                )
                if table_path is None:
                    continue

                page.table_regions.append(
                    RawTableRegion(
                        id=f"mineru_table_p{page_num}_b{item_id}",
                        page=page_num,
                        bbox=self._normalize_bbox(block.get("bbox")),
                        table_image_path=str(table_path),
                        caption_text=self._extract_table_caption(block),
                        ocr_text=self._extract_table_footnote(block),
                        html=self._extract_table_html(block),
                        markdown=self._extract_table_markdown(block),
                        role="table",
                        source="mineru_vlm",
                    )
                )

        parsed = ParsedDocument(
            doc_id=doc_id,
            doc_name=Path(doc_id).stem,
            pdf_path=pdf_path,
            output_dir=str(output_path),
            parser_backend=self.backend,
            pages=[pages_by_number[page_num] for page_num in sorted(pages_by_number)],
        )
        self._dump_parsed_document(parsed, output_path / "parsed_document.json")
        return parsed

    def _resolve_content_list_path(self, doc_id: str) -> Path:
        if self.mineru_root is None:
            raise ValueError("TriMapParser requires `mineru_root` for MinerU parsing.")

        if self.mineru_root.is_file():
            return self.mineru_root

        doc_name = Path(doc_id).stem
        target_names = [
            f"{doc_name}_content_list_v2.json",
            f"{doc_name}_content_list.json",
        ]

        candidates: list[Path] = []
        for target_name in target_names:
            candidates.extend(self.mineru_root.rglob(target_name))
            if candidates:
                break

        if not candidates:
            raise FileNotFoundError(
                f"No MinerU content list found for doc `{doc_id}` under {self.mineru_root}"
            )

        return sorted(
            {path.resolve() for path in candidates},
            key=lambda path: self._candidate_sort_key(path=path, doc_name=doc_name),
        )[0]

    def _candidate_sort_key(self, path: Path, doc_name: str) -> tuple[int, int, int, str]:
        parent_name = path.parent.name
        grandparent_name = path.parent.parent.name if path.parent.parent != path.parent else ""
        return (
            0 if parent_name == "vlm" else 1,
            0 if grandparent_name == doc_name else 1,
            len(path.parts),
            str(path),
        )

    def _iter_blocks(self, payload: list[Any]) -> list[tuple[int, dict[str, Any]]]:
        blocks: list[tuple[int, dict[str, Any]]] = []
        for page_idx, item in enumerate(payload):
            if isinstance(item, list):
                for block in item:
                    if isinstance(block, dict):
                        blocks.append((page_idx + 1, block))
                continue

            if isinstance(item, dict):
                raw_page_idx = item.get("page_idx")
                if raw_page_idx is None:
                    continue
                blocks.append((int(raw_page_idx) + 1, item))
        return blocks

    def _normalize_bbox(self, bbox: Any) -> list[float]:
        if not isinstance(bbox, list) or len(bbox) != 4:
            return []
        try:
            x1, y1, x2, y2 = [float(value) for value in bbox]
        except (TypeError, ValueError):
            return []
        if x2 <= x1 or y2 <= y1:
            return []
        return [x1, y1, x2, y2]

    def _normalize_text(self, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.split()).strip()

    def _normalize_list_items(self, value: Any) -> str:
        if not isinstance(value, list):
            return ""
        items = [self._normalize_text(item) for item in value if self._normalize_text(item)]
        return "\n".join(items)

    def _get_text_role(self, block: dict[str, Any]) -> str:
        block_type = str(block.get("type", "")).strip()
        if block_type == "title":
            return "title"
        if block_type == "text" and block.get("text_level"):
            return "title"
        return "paragraph"

    def _extract_text_value(self, block: dict[str, Any]) -> str:
        block_type = str(block.get("type", "")).strip()
        if block_type == "text":
            return self._normalize_text(block.get("text", ""))
        if block_type == "title":
            return self._flatten_v2_fragments(
                block.get("content", {}).get("title_content", [])
            )
        if block_type == "paragraph":
            return self._flatten_v2_fragments(
                block.get("content", {}).get("paragraph_content", [])
            )
        return ""

    def _extract_list_value(self, block: dict[str, Any]) -> str:
        if "list_items" in block:
            return self._normalize_list_items(block.get("list_items", []))

        content = block.get("content", {})
        if not isinstance(content, dict):
            return ""

        parts: list[str] = []
        for item in content.get("list_items", []):
            if not isinstance(item, dict):
                continue
            text = self._flatten_v2_fragments(item.get("item_content", []))
            if text:
                parts.append(text)
        return "\n".join(parts)

    def _join_text_parts(self, value: Any) -> str:
        if isinstance(value, list):
            parts = [self._normalize_text(item) for item in value if self._normalize_text(item)]
            return " ".join(parts).strip()
        return self._normalize_text(value)

    def _flatten_v2_fragments(self, value: Any) -> str:
        if not isinstance(value, list):
            return ""
        parts: list[str] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            text = self._normalize_text(item.get("content", ""))
            if text:
                parts.append(text)
        return " ".join(parts).strip()

    def _extract_image_path(self, block: dict[str, Any]) -> str:
        if "img_path" in block:
            return str(block.get("img_path", ""))
        return str(
            block.get("content", {})
            .get("image_source", {})
            .get("path", "")
        )

    def _extract_table_path(self, block: dict[str, Any]) -> str:
        if "img_path" in block:
            return str(block.get("img_path", ""))
        return str(
            block.get("content", {})
            .get("image_source", {})
            .get("path", "")
        )

    def _extract_image_caption(self, block: dict[str, Any]) -> str:
        if "image_caption" in block:
            return self._join_text_parts(block.get("image_caption"))
        return self._flatten_v2_fragments(
            block.get("content", {}).get("image_caption", [])
        )

    def _extract_image_footnote(self, block: dict[str, Any]) -> str:
        if "image_footnote" in block:
            return self._join_text_parts(block.get("image_footnote"))
        return self._flatten_v2_fragments(
            block.get("content", {}).get("image_footnote", [])
        )

    def _extract_table_caption(self, block: dict[str, Any]) -> str:
        if "table_caption" in block:
            return self._join_text_parts(block.get("table_caption"))
        return self._flatten_v2_fragments(
            block.get("content", {}).get("table_caption", [])
        )

    def _extract_table_footnote(self, block: dict[str, Any]) -> str:
        if "table_footnote" in block:
            return self._join_text_parts(block.get("table_footnote"))
        return self._flatten_v2_fragments(
            block.get("content", {}).get("table_footnote", [])
        )

    def _extract_table_html(self, block: dict[str, Any]) -> str | None:
        if "table_body" in block:
            return self._normalize_text(block.get("table_body", "")) or None
        return self._normalize_text(block.get("content", {}).get("html", "")) or None

    def _extract_table_markdown(self, block: dict[str, Any]) -> str | None:
        if "table_markdown" in block:
            return self._normalize_text(block.get("table_markdown", "")) or None
        return self._normalize_text(block.get("content", {}).get("markdown", "")) or None

    def _materialize_visual_asset(
        self,
        img_path: Any,
        output_dir: Path,
        page_num: int,
        branch: str,
        item_id: int,
        content_list_dir: Path,
    ) -> Path | None:
        if not isinstance(img_path, str) or not img_path.strip():
            return None

        raw_path = Path(img_path)
        source_path = raw_path if raw_path.is_absolute() else (content_list_dir / raw_path)
        source_path = source_path.resolve()
        if not source_path.exists():
            return None

        if not self.copy_visual_assets:
            return source_path

        suffix = source_path.suffix or ".png"
        stem = self._safe_token(source_path.stem)
        target_path = output_dir / f"raw_{branch}_p{page_num}_b{item_id}_{stem}{suffix}"
        shutil.copy2(source_path, target_path)
        return target_path

    def _next_id(
        self,
        counters: dict[int, dict[str, int]],
        page_num: int,
        branch: str,
    ) -> int:
        counters[page_num][branch] += 1
        return counters[page_num][branch]

    def _dump_parsed_document(self, parsed: ParsedDocument, output_path: Path) -> None:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(parsed.to_dict(), f, ensure_ascii=False, indent=2)

    def _safe_token(self, text: str) -> str:
        token = re.sub(r"[^A-Za-z0-9_]+", "_", text.strip())
        token = token.strip("_")
        return token or "region"
