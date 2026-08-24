"""Build the Physics-STEM chunk-to-PDF locator and optionally update its manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT / "src"))

from stem_sci.knowledge.locator import build_locator_index, write_locator_index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-root", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "data/catalogs/physics_stem/locator.json",
    )
    parser.add_argument("--update-manifest", action="store_true")
    args = parser.parse_args()

    manifest_path = (
        REPOSITORY_ROOT / "data/catalogs/physics_stem/physics_stem_v1.manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit, locator = build_locator_index(
        corpus_id=manifest["corpus_id"],
        corpus_version=manifest["corpus_version"],
        pdf_root=args.pdf_root.resolve(),
        identity_map_path=REPOSITORY_ROOT / manifest["identity_map"]["relative_path"],
        metadata_path=REPOSITORY_ROOT / manifest["vector_metadata"]["relative_path"],
    )
    digest = write_locator_index(locator, args.output.resolve())
    if args.update_manifest:
        relative_output = args.output.resolve().relative_to(REPOSITORY_ROOT).as_posix()
        manifest["locator_index"] = {
            "relative_path": relative_output,
            "sha256": digest,
            "required": True,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(audit.model_dump_json(indent=2))
    print(locator.model_dump_json(include={"paper_count", "chunk_count", "resolved_count", "source_verified_count", "unresolved_count"}, indent=2))
    print(f"locator_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
