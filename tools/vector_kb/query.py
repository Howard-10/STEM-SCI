"""Query the local Physics STEM hybrid vector knowledge base.

The index and full-text metadata are local-only. This tool intentionally does
not build, upload, or commit those assets.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
from pathlib import Path
from typing import Any

import dashscope
import faiss
import numpy as np
from dotenv import load_dotenv


TOOL_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = TOOL_DIR.parents[1]
DEFAULT_VECTOR_DB_DIR = REPOSITORY_ROOT / "data" / "local" / "vector_kb" / "vectordb"
TOP_K = 5

load_dotenv(TOOL_DIR / ".env")


def vector_db_dir() -> Path:
    """Return the configured local-only vector database directory."""
    configured = os.getenv("STEM_SCI_VECTOR_DB_DIR")
    return Path(configured).expanduser() if configured else DEFAULT_VECTOR_DB_DIR


def embed_query(text: str) -> np.ndarray:
    """Embed one query with the same model used by the 1024-dimensional index."""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is missing; create tools/vector_kb/.env first.")
    dashscope.api_key = api_key
    response = dashscope.TextEmbedding.call(model="text-embedding-v3", input=[text])
    if response.status_code != 200:
        raise RuntimeError(f"DashScope embedding failed with status {response.status_code}.")
    vector = np.asarray(response.output["embeddings"][0]["embedding"], dtype="float32").reshape(1, -1)
    faiss.normalize_L2(vector)
    return vector


class HybridSearcher:
    """Run vector and BM25 search, then combine both rankings with RRF."""

    def __init__(self, db_dir: Path | None = None) -> None:
        root = db_dir or vector_db_dir()
        index_path = root / "index.faiss"
        bm25_path = root / "bm25.pkl"
        metadata_path = root / "metadata.json"
        missing = [str(path) for path in (index_path, bm25_path, metadata_path) if not path.is_file()]
        if missing:
            raise FileNotFoundError("Missing local vector assets: " + ", ".join(missing))

        self.index = faiss.read_index(str(index_path))
        with bm25_path.open("rb") as handle:
            self.bm25_vectorizer, self.bm25_matrix = pickle.load(handle)
        self.metadata: list[dict[str, Any]] = json.loads(metadata_path.read_text(encoding="utf-8"))
        if self.index.ntotal != len(self.metadata):
            raise ValueError(
                "Vector index / metadata mismatch: "
                f"FAISS has {self.index.ntotal} entries but metadata has {len(self.metadata)}."
            )

    def search_bm25(self, query: str, limit: int) -> list[tuple[int, float]]:
        query_vector = self.bm25_vectorizer.transform([query])
        norm = np.linalg.norm(query_vector.toarray()) + 1e-10
        query_vector = query_vector / norm
        scores = (self.bm25_matrix @ query_vector.T).toarray().ravel()
        ranked = np.argsort(scores)[::-1][:limit]
        return [(int(index), float(scores[index])) for index in ranked if scores[index] > 0]

    def search_vector(self, query: str, limit: int) -> list[tuple[int, float]]:
        query_vector = embed_query(query)
        if query_vector.shape[1] != self.index.d:
            raise ValueError(
                f"Embedding dimension {query_vector.shape[1]} does not match index dimension {self.index.d}."
            )
        scores, indices = self.index.search(query_vector, limit)
        return [
            (int(index), float(score))
            for index, score in zip(indices[0], scores[0], strict=True)
            if index >= 0
        ]

    def search(self, query: str, top_k: int = TOP_K) -> list[tuple[float, dict[str, Any]]]:
        candidate_limit = top_k * 2
        fused: dict[int, float] = {}
        for results in (self.search_vector(query, candidate_limit), self.search_bm25(query, candidate_limit)):
            for rank, (index, _score) in enumerate(results, start=1):
                fused[index] = fused.get(index, 0.0) + 1.0 / (60 + rank)

        results: list[tuple[float, dict[str, Any]]] = []
        shown_text_prefixes: set[str] = set()
        for index, score in sorted(fused.items(), key=lambda item: (-item[1], item[0])):
            metadata = self.metadata[index]
            text_prefix = str(metadata.get("text", ""))[:100]
            if text_prefix in shown_text_prefixes:
                continue
            shown_text_prefixes.add(text_prefix)
            results.append((score, metadata))
            if len(results) == top_k:
                break
        return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Natural-language query")
    parser.add_argument("--top-k", type=int, default=TOP_K)
    args = parser.parse_args()

    for rank, (score, metadata) in enumerate(HybridSearcher().search(args.query, args.top_k), start=1):
        print(f"\n--- #{rank} | RRF score {score:.4f} ---")
        print(f"Paper: {metadata.get('paper_title', 'N/A')}")
        print(f"DOI: {metadata.get('doi', 'N/A')} | Year: {metadata.get('year', 'N/A')}")
        print(f"Section: {metadata.get('section_hint', 'N/A')}")
        print(f"Text: {str(metadata.get('text', '')).replace(chr(10), ' ')[:500]}...")


if __name__ == "__main__":
    main()
