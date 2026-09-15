import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
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
            doc_id: Optional[str] = None
    ):
        """Reads a single file and runs it through the ingestion pipeline."""
        if not file_path.exists():
            print(f"Error: File not found at {file_path}")
            return

        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        if not text.strip():
            print(f"Skipping empty file: {file_path.name}")
            return

        generated_doc_id = doc_id or f"doc-{file_path.stem}"

        print(f"Processing '{file_path.name}' [ID: {generated_doc_id}]...")
        ingest_document(
            text=text,
            doc_id=generated_doc_id,
            allowed_roles=allowed_roles,
            clearance_level=clearance_level,
            source_name=file_path.name
        )

    def process_manifest(self, manifest_path: Path):
        """
        Processes a JSON manifest containing file metadata & RBAC policies.
        Example manifest format:
        [
          {
            "filename": "q3_financials.txt",
            "doc_id": "doc-fin-001",
            "allowed_roles": ["finance", "executive"],
            "clearance_level": 5
          }
        ]
        """
        if not manifest_path.exists():
            print(f"Manifest file missing: {manifest_path}")
            return

        with open(manifest_path, "r", encoding="utf-8") as f:
            documents_meta: List[Dict[str, Any]] = json.load(f)

        for doc_info in documents_meta:
            file_path = manifest_path.parent / doc_info["filename"]
            self.ingest_file(
                file_path=file_path,
                allowed_roles=doc_info.get("allowed_roles", ["general"]),
                clearance_level=doc_info.get("clearance_level", 1),
                doc_id=doc_info.get("doc_id")
            )

    def run_directory_scan(self, default_roles: List[str] = None, default_clearance: int = 1):
        """Scans the data directory for text files and ingests them with default RBAC fallback."""
        if default_roles is None:
            default_roles = ["employee"]

        if not self.data_dir.exists():
            print(f"Directory '{self.data_dir}' does not exist.")
            return

        manifest_file = self.data_dir / "manifest.json"
        if manifest_file.exists():
            print(f"Found manifest file at {manifest_file}. Ingesting via manifest...")
            self.process_manifest(manifest_file)
            return

        # Fallback: Batch ingest all .txt and .md files in the directory
        for file_path in self.data_dir.glob("**/*"):
            if file_path.suffix in [".txt", ".md"]:
                self.ingest_file(
                    file_path=file_path,
                    allowed_roles=default_roles,
                    clearance_level=default_clearance
                )


if __name__ == "__main__":
    # Instantiate and run directory ingestion
    pipeline = IngestionPipeline(data_dir="data")
    pipeline.run_directory_scan(default_roles=["engineering"], default_clearance=2)