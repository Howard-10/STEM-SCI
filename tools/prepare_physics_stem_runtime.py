"""Validate and prepare local Physics-STEM assets for the full workflow."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/catalogs/physics_stem/physics_stem_v1.manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-root", type=Path, required=True)
    parser.add_argument("--vector-root", type=Path, required=True)
    parser.add_argument("--neo4j-password", required=True)
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7688")
    parser.add_argument("--neo4j-username", default="neo4j")
    parser.add_argument("--neo4j-database", default="neo4j")
    args = parser.parse_args()

    pdf_root = args.pdf_root.expanduser().resolve()
    vector_root = args.vector_root.expanduser().resolve()
    vector_dir = vector_root / "vectordb"
    required = {
        "PDF root": pdf_root,
        "vector metadata": vector_dir / "metadata.json",
        "FAISS index": vector_dir / "index.faiss",
    }
    missing = [f"{label}: {path}" for label, path in required.items() if not path.exists()]
    if missing:
        print("Local Physics-STEM assets are incomplete:")
        print("\n".join(f"- {item}" for item in missing))
        return 2

    env = os.environ.copy()
    env["STEM_SCI_VECTOR_KB_ROOT"] = str(vector_root)
    locator_cmd = [
        sys.executable,
        str(ROOT / "backend/scripts/build_physics_stem_locator.py"),
        "--pdf-root",
        str(pdf_root),
        "--metadata",
        str(vector_dir / "metadata.json"),
        "--update-manifest",
    ]
    subprocess.run(locator_cmd, cwd=ROOT, env=env, check=True)

    import_cmd = [
        sys.executable,
        str(ROOT / "tools/neo4j_import_sparse_graph.py"),
        "--uri",
        args.neo4j_uri,
        "--username",
        args.neo4j_username,
        "--database",
        args.neo4j_database,
        "--password",
        args.neo4j_password,
    ]
    subprocess.run(import_cmd, cwd=ROOT, check=True)
    print("Physics-STEM runtime preparation completed.")
    print("Next: restart the backend and verify GET /api/v1/corpora.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
