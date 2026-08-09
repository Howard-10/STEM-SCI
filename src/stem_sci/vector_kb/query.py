"""
混合检索：向量语义 + BM25 关键词
"""
import json
import os
import pickle
import numpy as np
from dotenv import load_dotenv
load_dotenv()

import dashscope
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
import faiss

INDEX_PATH = "vectordb/index.faiss"
BM25_PATH = "vectordb/bm25.pkl"
META_PATH = "vectordb/metadata.json"
TOP_K = 5


def embed_query(text):
    resp = dashscope.TextEmbedding.call(model="text-embedding-v3", input=[text])
    if resp.status_code == 200:
        vec = np.array(resp.output['embeddings'][0]['embedding']).astype('float32')
        vec = vec.reshape(1, -1)
        faiss.normalize_L2(vec)
        return vec
    return None


class HybridSearcher:
    def __init__(self):
        self.index = faiss.read_index(INDEX_PATH)
        with open(BM25_PATH, 'rb') as f:
            self.bm25_vec, self.bm25_matrix = pickle.load(f)
        with open(META_PATH, 'r', encoding='utf-8') as f:
            self.metadata = json.load(f)

    def search_bm25(self, query, k=TOP_K * 2):
        q_vec = self.bm25_vec.transform([query])
        q_vec = q_vec / (np.linalg.norm(q_vec.toarray()) + 1e-10)
        scores = (self.bm25_matrix @ q_vec.T).toarray().flatten()
        top = np.argsort(scores)[::-1][:k]
        return [(int(i), float(scores[i])) for i in top if scores[i] > 0]

    def search_vector(self, query, k=TOP_K * 2):
        q_emb = embed_query(query)
        if q_emb is None:
            return []
        scores, indices = self.index.search(q_emb, k)
        return [(int(i), float(s)) for i, s in zip(indices[0], scores[0])]

    def search(self, query, top_k=TOP_K):
        vec_results = self.search_vector(query, top_k * 2)
        bm25_results = self.search_bm25(query, top_k * 2)

        # Reciprocal Rank Fusion: 合并两路结果
        scores = {}
        rrf_k = 60
        for rank, (idx, _) in enumerate(vec_results):
            scores[idx] = scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)
        for rank, (idx, _) in enumerate(bm25_results):
            scores[idx] = scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)

        sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        shown_texts = set()
        for idx, score in sorted_ids:
            meta = self.metadata[idx]
            text_hash = meta['text'][:100]
            # 去重：避免同一篇论文的几乎相同段落霸榜
            if text_hash in shown_texts:
                continue
            shown_texts.add(text_hash)
            results.append((idx, score, meta))
        return results[:top_k]


def search(query, top_k=5):
    searcher = HybridSearcher()
    results = searcher.search(query, top_k)

    # safe print
    def safe(s):
        return s.encode('gbk', errors='replace').decode('gbk')

    print(f"\nQuery: \"{safe(query)}\"")
    print(f"{'='*70}")
    for rank, (idx, score, meta) in enumerate(results):
        text = safe(meta['text'][:500].replace('\n', ' '))
        title = safe(meta['paper_title'][:120])
        section = safe(meta['section_hint'])
        doi = meta.get('doi') or 'N/A'
        year = meta.get('year') or '?'
        print(f"\n--- #{rank+1} (score: {score:.4f}) ---")
        print(f"Paper: {title}")
        print(f"Year: {year} | DOI: {doi}")
        print(f"Section: {section}")
        print(f"Text: {text}...")
    print(f"\n{'='*70}")


if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else \
        "What is the definition of STEM education"
    search(query)
