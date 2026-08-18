"""Conservative paper identity resolution for shared corpus assets."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .models import CanonicalPaper
from .normalization import normalize_doi, normalize_text


class _CatalogPaper(BaseModel):
    """Projection of a checked-in identity catalog record."""

    model_config = ConfigDict(extra="ignore")

    paper_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_filename: str = Field(min_length=1)
    vector_filename: str = Field(min_length=1)
    doi: str | None = None
    journal: str | None = None
    year: int | None = None


class _IdentityCatalog(BaseModel):
    """Projection of a checked-in identity catalog."""

    model_config = ConfigDict(extra="ignore")

    paper_count: int = Field(ge=0)
    papers: list[_CatalogPaper]


class PaperIdentityResolver:
    """Resolve exact identifiers without unsafe fuzzy automatic merging."""

    def __init__(self, papers: list[CanonicalPaper]) -> None:
        self._papers = papers
        self._by_canonical = {paper.canonical_paper_id: paper for paper in papers}
        self._by_graph = {paper.graph_paper_id: paper for paper in papers}
        self._by_filename = {normalize_text(paper.source_filename): paper for paper in papers}
        self._by_vector_filename = {normalize_text(paper.vector_filename): paper for paper in papers}
        self._by_doi = {
            paper.normalized_doi: paper for paper in papers if paper.normalized_doi is not None
        }
        self._by_exact_title_year = {
            (normalize_text(paper.title), paper.year): paper for paper in papers
        }

    @classmethod
    def from_catalog_path(cls, path: Path) -> "PaperIdentityResolver":
        """Load a checked-in map and create stable paper IDs independent of file hashes."""

        catalog = _IdentityCatalog.model_validate_json(path.read_text(encoding="utf-8"))
        if catalog.paper_count != len(catalog.papers):
            raise ValueError("Identity catalog paper_count does not match records")
        papers = [cls._canonical(record) for record in catalog.papers]
        if len({paper.canonical_paper_id for paper in papers}) != len(papers):
            raise ValueError("Identity catalog contains duplicate canonical paper identities")
        return cls(papers)

    @staticmethod
    def _canonical(record: _CatalogPaper) -> CanonicalPaper:
        # The existing controlled corpus predates CanonicalPaper. Bootstrap a
        # stable identity from its curated graph paper ID, never from the PDF
        # hash or a title similarity heuristic. New imported papers receive a
        # generated ID at CanonicalPaper creation time.
        identity_key = f"physics_stem_v1\x00{record.paper_id}"
        canonical_id = f"cp_{sha256(identity_key.encode('utf-8')).hexdigest()[:20]}"
        return CanonicalPaper(
            canonical_paper_id=canonical_id,
            graph_paper_id=record.paper_id,
            title=record.title,
            normalized_doi=normalize_doi(record.doi),
            year=record.year,
            journal=record.journal,
            source_filename=record.source_filename,
            vector_filename=record.vector_filename,
        )

    @property
    def papers(self) -> list[CanonicalPaper]:
        """Return a defensive ordered copy of the catalog records."""

        return list(self._papers)

    def by_canonical_id(self, canonical_paper_id: str) -> CanonicalPaper | None:
        return self._by_canonical.get(canonical_paper_id)

    def by_graph_paper_id(self, graph_paper_id: str) -> CanonicalPaper | None:
        return self._by_graph.get(graph_paper_id)

    def resolve(
        self,
        *,
        filename: str | None = None,
        doi: str | None = None,
        title: str | None = None,
        year: int | None = None,
    ) -> CanonicalPaper | None:
        """Resolve in exact-identifier order; title similarity never auto-merges."""

        if filename:
            normalized_filename = normalize_text(filename)
            found = self._by_filename.get(normalized_filename) or self._by_vector_filename.get(
                normalized_filename
            )
            if found is not None:
                return found
        normalized_doi = normalize_doi(doi)
        if normalized_doi:
            found = self._by_doi.get(normalized_doi)
            if found is not None:
                return found
        if title is not None:
            return self._by_exact_title_year.get((normalize_text(title), year))
        return None
