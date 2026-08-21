"""Hash-checked manifests for local-only retrieval assets."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .models import AssetCheck, AssetRef, CorpusManifest, CorpusReadiness


def repository_root() -> Path:
    """Locate the repository without exposing that path through an API."""

    configured = os.getenv("STEM_SCI_REPOSITORY_ROOT")
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[4]


class CorpusRegistry:
    """Load and validate declared shared-corpus assets before retrieval."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or repository_root()).resolve()

    def manifest_path(self, corpus_id: str) -> Path:
        if corpus_id != "physics_stem_v1":
            raise ValueError(f"Unsupported shared corpus: {corpus_id}")
        return self.root / "data" / "catalogs" / "physics_stem" / "physics_stem_v1.manifest.json"

    def load_manifest(self, corpus_id: str = "physics_stem_v1") -> CorpusManifest:
        return CorpusManifest.model_validate_json(self.manifest_path(corpus_id).read_text(encoding="utf-8"))

    def readiness(self, corpus_id: str = "physics_stem_v1") -> CorpusReadiness:
        """Validate required discovery assets and report formal-locator readiness separately."""

        manifest = self.load_manifest(corpus_id)
        checks = [self._check(asset) for asset in self._required_assets(manifest)]
        pdf_root = self.pdf_root_path(manifest)
        if not pdf_root.is_dir():
            checks.append(
                AssetCheck(
                    relative_path=manifest.pdf_root_relative_path,
                    state="MISSING",
                    required=True,
                )
            )
        checks.extend(self._content_checks(manifest))
        base_risks = [
            f"asset_{check.state.lower()}:{check.relative_path}"
            for check in checks
            if check.state != "READY" and check.required
        ]
        discovery_ready = not base_risks
        formal_ready = discovery_ready and manifest.locator_index is not None
        risks = list(base_risks)
        if manifest.locator_index is None:
            risks.append("formal_locator_index_unavailable")
        elif self._check(manifest.locator_index).state != "READY":
            formal_ready = False
            risks.append("formal_locator_index_invalid")
        return CorpusReadiness(
            corpus_id=manifest.corpus_id,
            corpus_version=manifest.corpus_version,
            discovery_ready=discovery_ready,
            formal_evidence_ready=formal_ready,
            checks=checks,
            risk_flags=sorted(set(risks)),
        )

    def asset_path(self, reference: AssetRef) -> Path:
        """Resolve a manifest asset, allowing ignored local corpus roots."""

        relative_path = reference.relative_path.replace("\\", "/")
        vector_root = os.getenv("STEM_SCI_VECTOR_KB_ROOT", "").strip()
        if vector_root and relative_path.startswith("data/local/vector_kb/"):
            return (
                Path(vector_root).expanduser().resolve()
                / relative_path.removeprefix("data/local/vector_kb/")
            ).resolve()
        candidate = (self.root / relative_path).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            raise ValueError("Manifest asset escapes repository root")
        return candidate

    def pdf_root_path(self, manifest: CorpusManifest) -> Path:
        """Resolve the local PDF root used by a deployment."""

        configured = os.getenv("STEM_SCI_PDF_ROOT", "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return (self.root / manifest.pdf_root_relative_path).resolve()

    def _check(self, reference: AssetRef) -> AssetCheck:
        path = self.asset_path(reference)
        if not path.is_file():
            return AssetCheck(relative_path=reference.relative_path, state="MISSING", required=reference.required)
        if self._sha256(path) != reference.sha256:
            return AssetCheck(
                relative_path=reference.relative_path,
                state="HASH_MISMATCH",
                required=reference.required,
            )
        return AssetCheck(relative_path=reference.relative_path, state="READY", required=reference.required)

    def _content_checks(self, manifest: CorpusManifest) -> list[AssetCheck]:
        """Validate declared record counts without exposing corpus text through an API."""

        checks: list[AssetCheck] = []
        checks.append(
            self._json_count_check(
                manifest.identity_map,
                expected=manifest.paper_count,
                list_key="papers",
                declared_count_key="paper_count",
            )
        )
        checks.append(
            self._graph_check(manifest)
        )
        checks.append(
            self._json_count_check(
                manifest.vector_metadata,
                expected=manifest.vector_chunk_count,
                list_key=None,
                declared_count_key=None,
            )
        )
        pdf_root = self.pdf_root_path(manifest)
        if pdf_root.is_dir():
            count = len(list(pdf_root.rglob("*.pdf")))
            checks.append(
                AssetCheck(
                    relative_path=manifest.pdf_root_relative_path,
                    state="READY" if count == manifest.paper_count else "CONTENT_MISMATCH",
                    required=True,
                )
            )
        return checks

    def _json_count_check(
        self,
        reference: AssetRef,
        *,
        expected: int,
        list_key: str | None,
        declared_count_key: str | None,
    ) -> AssetCheck:
        """Confirm a JSON list or nested list has the manifest's expected count."""

        path = self.asset_path(reference)
        if not path.is_file() or self._sha256(path) != reference.sha256:
            return AssetCheck(relative_path=reference.relative_path, state="READY", required=reference.required)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            records = data[list_key] if list_key else data
            valid = isinstance(records, list) and len(records) == expected
            if declared_count_key:
                valid = valid and data.get(declared_count_key) == expected
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            valid = False
        return AssetCheck(
            relative_path=f"{reference.relative_path}#content",
            state="READY" if valid else "CONTENT_MISMATCH",
            required=reference.required,
        )

    def _graph_check(self, manifest: CorpusManifest) -> AssetCheck:
        """Check graph cardinality and graph status before graph navigation is enabled."""

        reference = manifest.graph_artifact
        path = self.asset_path(reference)
        if not path.is_file() or self._sha256(path) != reference.sha256:
            return AssetCheck(relative_path=reference.relative_path, state="READY", required=reference.required)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            papers = data["papers"]
            triple_count = sum(len(paper["triples"]) for paper in papers)
            valid = (
                data.get("artifact_type") == manifest.graph_artifact_type
                and data.get("paper_count") == manifest.graph_paper_count
                and len(papers) == manifest.graph_paper_count
                and data.get("total_triples") == manifest.graph_triple_count
                and triple_count == manifest.graph_triple_count
                and data.get("source_status") == "model_generated_unverified"
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            valid = False
        return AssetCheck(
            relative_path=f"{reference.relative_path}#content",
            state="READY" if valid else "CONTENT_MISMATCH",
            required=reference.required,
        )

    @staticmethod
    def _required_assets(manifest: CorpusManifest) -> tuple[AssetRef, ...]:
        return (
            manifest.identity_map,
            manifest.graph_artifact,
            manifest.vector_metadata,
            manifest.vector_index,
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
