import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import toml  # type: ignore[import-untyped]

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mydatasets.tri_map_evidence_builder import TriMapEvidenceBuilder
from mydatasets.tri_map_parser import TriMapParser

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_template(value: str, context: dict[str, Any]) -> str:
    resolved = value
    for _ in range(5):
        next_value = resolved.format(**context)
        if next_value == resolved:
            return next_value
        resolved = next_value
    return resolved


def _to_namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _to_namespace(val) for key, val in value.items()})
    return value


def _build_context(cfg: dict[str, Any], dataset_name: str, run_name: str) -> dict[str, Any]:
    raw_context = {
        "run_args": dict(cfg.get("run_args", {})),
        "dataset": dict(cfg.get("dataset", {})),
        "retrieval": dict(cfg.get("retrieval", {})),
    }
    raw_context["run_args"]["work_dir"] = str(PROJECT_ROOT)
    raw_context["run_args"]["run_name"] = run_name
    raw_context["dataset"]["name"] = dataset_name
    return {key: _to_namespace(value) for key, value in raw_context.items()}


def _get_document_path(cfg: dict[str, Any], dataset_name: str, run_name: str) -> Path:
    context = _build_context(cfg, dataset_name=dataset_name, run_name=run_name)
    template = str(cfg.get("dataset", {}).get("document_path", "data/{dataset.name}/documents"))
    return Path(_resolve_template(template, context))


def _load_doc_ids(cfg: dict[str, Any], dataset_name: str, run_name: str) -> list[str]:
    context = _build_context(cfg, dataset_name=dataset_name, run_name=run_name)
    template = str(cfg.get("dataset", {}).get("sample_path", "data/{dataset.name}/samples.json"))
    sample_path = Path(_resolve_template(template, context))

    rows = json.loads(sample_path.read_text(encoding="utf-8"))
    seen_doc_ids: list[str] = []
    seen_set: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        doc_id = str(row.get("doc_id", "")).strip()
        if not doc_id or doc_id in seen_set:
            continue
        seen_set.add(doc_id)
        seen_doc_ids.append(doc_id)
    return seen_doc_ids


def parse_one_document(
    parser: TriMapParser,
    evidence_builder: TriMapEvidenceBuilder,
    document_root: Path,
    dataset_name: str,
    doc_id: str,
    output_root: Path,
    page_limit: int | None,
) -> None:
    doc_name = Path(doc_id).stem
    pdf_path = str(document_root / doc_id)
    output_dir = output_root / dataset_name / "parsed" / doc_name
    parser.parse_document(
        pdf_path=pdf_path,
        doc_id=doc_id,
        output_dir=str(output_dir),
        page_limit=page_limit,
    )
    manifest = evidence_builder.build_from_parsed_document(
        parsed_document_path=str(output_dir / "parsed_document.json"),
        output_dir=str(output_dir / "evidence"),
    )
    print(f"parsed: {doc_id} -> {output_dir}")
    print(f"evidence counts: {manifest['counts']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build Tri-Map parsed evidence")
    ap.add_argument(
        "--config",
        type=str,
        default="config/tri_map_config.toml",
    )
    ap.add_argument("--dataset-name", type=str, required=True)
    ap.add_argument("--run-name", type=str, default="tri_map")
    ap.add_argument("--doc-id", type=str, default="")
    ap.add_argument("--page-limit", type=int, default=-1)
    ap.add_argument("--sample-limit", type=int, default=5)
    ap.add_argument("--output-root", type=str, default="tmp/tri_map")
    ap.add_argument("--mineru-root", type=str, default="")
    args = ap.parse_args()

    config_path = PROJECT_ROOT / args.config
    with open(config_path, "r", encoding="utf-8") as f:
        dq_cfg = toml.load(f)

    mineru_cfg = dq_cfg.get("tri_map", {}).get("mineru", {})
    mineru_root = args.mineru_root or mineru_cfg.get("output_root", "")
    if mineru_root and not Path(mineru_root).is_absolute():
        mineru_root = str((PROJECT_ROOT / mineru_root).resolve())
    document_root = _get_document_path(
        dq_cfg,
        dataset_name=args.dataset_name,
        run_name=args.run_name,
    )
    parser = TriMapParser(
        {
            "backend": "mineru",
            "mineru_root": mineru_root,
            "copy_visual_assets": mineru_cfg.get("copy_visual_assets", True),
            "ignored_types": mineru_cfg.get("ignored_types", []),
        }
    )
    evidence_builder = TriMapEvidenceBuilder()

    page_limit = args.page_limit if args.page_limit > 0 else None
    output_root = Path(args.output_root)

    if args.doc_id:
        parse_one_document(
            parser=parser,
            evidence_builder=evidence_builder,
            document_root=document_root,
            dataset_name=args.dataset_name,
            doc_id=args.doc_id,
            output_root=output_root,
            page_limit=page_limit,
        )
        return

    doc_count = 0
    for doc_id in _load_doc_ids(
        dq_cfg,
        dataset_name=args.dataset_name,
        run_name=args.run_name,
    ):
        parse_one_document(
            parser=parser,
            evidence_builder=evidence_builder,
            document_root=document_root,
            dataset_name=args.dataset_name,
            doc_id=doc_id,
            output_root=output_root,
            page_limit=page_limit,
        )
        doc_count += 1
        if doc_count >= args.sample_limit:
            break


if __name__ == "__main__":
    main()
