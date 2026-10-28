import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.ingestion.chunker import setup_qdrant_collection, ingest_document


class IngestionPipeline:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        setup_qdrant_collection()

    def ingest_file(
        self,
        file_path: Path,
        allowed_roles: List[str],
        clearance_level: int,
        doc_id: Optional[str] = None,
        source_name: Optional[str] = None,
    ):
        """Read a document and index it with explicit identity and policy metadata."""
        if not file_path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")

        text = file_path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError(f"Refusing to index an empty document: {file_path.name}")

        generated_doc_id = doc_id or f"doc-{file_path.stem}"
        display_name = source_name or file_path.name
        print(f"Processing '{display_name}' [ID: {generated_doc_id}]...")
        ingest_document(
            text=text,
            doc_id=generated_doc_id,
            allowed_roles=allowed_roles,
            clearance_level=clearance_level,
            source_name=display_name,
        )

    def process_manifest(self, manifest_path: Path):
        """Index each file described by a JSON manifest."""
        if not manifest_path.exists():
            print(f"Manifest file missing: {manifest_path}")
            return

        documents_meta: List[Dict[str, Any]] = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        for doc_info in documents_meta:
            file_path = manifest_path.parent / doc_info["filename"]
            self.ingest_file(
                file_path=file_path,
                allowed_roles=doc_info.get("allowed_roles", ["general"]),
                clearance_level=doc_info.get("clearance_level", 1),
                doc_id=doc_info.get("doc_id"),
                source_name=doc_info.get("filename"),
            )

    def run_directory_scan(
        self, default_roles: List[str] = None, default_clearance: int = 1
    ):
        """Ingest a directory using its manifest, or conservative defaults if absent."""
        default_roles = default_roles or ["employee"]
        if not self.data_dir.exists():
            print(f"Directory '{self.data_dir}' does not exist.")
            return

        manifest_file = self.data_dir / "manifest.json"
        if manifest_file.exists():
            print(f"Found manifest file at {manifest_file}. Ingesting via manifest...")
            self.process_manifest(manifest_file)
            return

        for file_path in self.data_dir.glob("**/*"):
            if file_path.is_file() and file_path.suffix.lower() in {".txt", ".md"}:
                self.ingest_file(
                    file_path=file_path,
                    allowed_roles=default_roles,
                    clearance_level=default_clearance,
                )


if __name__ == "__main__":
    pipeline = IngestionPipeline(data_dir="data")
    pipeline.run_directory_scan(default_roles=["engineering"], default_clearance=2)
