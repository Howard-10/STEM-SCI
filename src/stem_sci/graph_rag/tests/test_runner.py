"""Comprehensive test suite for graph_rag.

Run from the graph_rag parent directory:
    cd C:/Users/25946/Desktop/揭榜挂帅比赛
    python -m unittest graph_rag.tests.test_runner -v
"""
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure graph_rag is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from graph_rag.entity_extract import EntityExtractor
from graph_rag.schema import (
    BatchedExtractionResult, ChunkTriples, EntityType,
    ExtractionResult, RelationType, Triple,
)
from graph_rag.prompt_templates import (
    build_batch_user_prompt, build_profile_user_prompt,
)
from graph_rag.cache import ExtractionCache


def _make_ext(**kwargs):
    """Create extractor with mocked OpenAI."""
    with patch("graph_rag.entity_extract.OpenAI") as m:
        client = MagicMock()
        m.return_value = client
        base = {
            "api_base": "http://localhost/v1",
            "api_key": "sk-test",
            "model_id": "test-model",
            "cache_dir": "",
        }
        base.update(kwargs)
        ext = EntityExtractor(**base)
        return ext, client


def _triple(**overrides):
    """Build a Triple with defaults."""
    values = {
        "head": "paper object", "head_type": "Concept",
        "relation": "RELATED_TO", "tail": "another object",
        "tail_type": "Concept",
        "evidence": "The paper explicitly describes the relationship.",
        "confidence": 0.9, "layer": "L2",
    }
    values.update(overrides)
    return Triple(**values)


# ==================================================================
# 1. Self-loop normalization
# ==================================================================
class TestNormalizePaperRelations(unittest.TestCase):

    def test_self_loop_converted_to_paper_edge(self):
        t = _triple(
            head="quasi-experiment", head_type="ResearchMethod",
            relation="USES_METHOD",
            tail="quasi-experiment", tail_type="ResearchMethod",
        )
        EntityExtractor._normalize_paper_relations([t], "10.1234/example")
        self.assertEqual(t.head, "10.1234/example")
        self.assertEqual(t.head_type, "Paper")
        self.assertEqual(t.tail, "quasi-experiment")
        self.assertEqual(t.tail_type, "ResearchMethod")

    def test_non_paper_relation_unchanged(self):
        t = _triple(
            head="ChatGPT", head_type="Technology",
            relation="INTEGRATES_WITH",
            tail="PBL", tail_type="PedagogicalMethod",
        )
        EntityExtractor._normalize_paper_relations([t], "10.1234/example")
        # INTEGRATES_WITH is not a paper relation
        self.assertEqual(t.head, "ChatGPT")

    def test_empty_paper_id_noop(self):
        t = _triple(relation="USES_METHOD")
        EntityExtractor._normalize_paper_relations([t], "")
        self.assertEqual(t.head, "paper object")  # unchanged


# ==================================================================
# 2. Validation rules
# ==================================================================
class TestValidation(unittest.TestCase):

    def test_rejects_self_loop(self):
        t = _triple(head="same", tail="same")
        self.assertFalse(EntityExtractor._validate_triple(t))

    def test_rejects_sentence_as_entity(self):
        t = _triple(
            head="subjective norms significantly influence perceived usefulness.",
            tail="perceived usefulness",
        )
        self.assertFalse(EntityExtractor._validate_triple(t))

    def test_rejects_long_entity(self):
        t = _triple(head="x" * 200, tail="ok")
        self.assertFalse(EntityExtractor._validate_triple(t))

    def test_rejects_many_word_entity(self):
        t = _triple(
            head="a b c d e f g h i j k l m n o p q r s t u v w x y z",
            tail="ok",
        )
        self.assertFalse(EntityExtractor._validate_triple(t))

    def test_rejects_empty_evidence(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            _triple(evidence="")

    def test_rejects_bad_confidence(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            _triple(confidence=2.5)

    def test_rejects_invalid_type(self):
        t = _triple(head_type="NotAType")
        self.assertFalse(EntityExtractor._validate_triple(t))

    def test_rejects_paper_relation_without_paper_head(self):
        t = _triple(
            relation="INVOLVES_POPULATION",
            head="pre-service teachers", head_type="StudentPopulation",
            tail="pre-service teachers", tail_type="StudentPopulation",
        )
        self.assertFalse(EntityExtractor._validate_triple(t))

    def test_accepts_paper_relation_with_correct_head(self):
        t = _triple(
            relation="INVOLVES_POPULATION",
            head="10.1234/paper", head_type="Paper",
            tail="pre-service teachers", tail_type="StudentPopulation",
        )
        self.assertTrue(EntityExtractor._validate_triple(t))

    def test_accepts_valid_cross_entity_relation(self):
        t = _triple(
            relation="INTEGRATES_WITH",
            head="ChatGPT", head_type="Technology",
            tail="PBL", tail_type="PedagogicalMethod",
        )
        self.assertTrue(EntityExtractor._validate_triple(t))

    def test_statistical_value_as_effect_size(self):
        # "d=0.82" is fine as EffectSize; the Claim head should be concise
        t = _triple(
            head="VR instruction improves density understanding",
            tail="d=0.82",
            head_type="Claim", tail_type="EffectSize",
            relation="HAS_EFFECT_SIZE",
        )
        self.assertTrue(EntityExtractor._validate_triple(t))

    def test_sentence_head_rejected(self):
        # A full sentence as head should be rejected
        t = _triple(
            head="VR-based instruction significantly improves conceptual understanding of density",
            tail="d=0.82",
            head_type="Claim", tail_type="EffectSize",
            relation="HAS_EFFECT_SIZE",
        )
        self.assertFalse(EntityExtractor._validate_triple(t))


# ==================================================================
# 3. Sparse profile
# ==================================================================
class TestSparseProfile(unittest.TestCase):

    def test_profile_requires_paper_id(self):
        ext, _ = _make_ext()
        with self.assertRaises(ValueError):
            ext.extract_sparse_profile(paper_id="", title="T", abstract="A")

    def test_profile_returns_profil_mode(self):
        ext, client = _make_ext()
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content=json.dumps({"triples": [
                    {"head": "10.1234/x", "head_type": "Paper",
                     "relation": "STUDIES_DOMAIN", "tail": "physics",
                     "tail_type": "SubjectDomain",
                     "evidence": "study of physics education", "confidence": 1.0, "layer": "L2"},
                ]})
            ))],
            usage=MagicMock(total_tokens=100, prompt_tokens=50, completion_tokens=50),
        )
        result = ext.extract_sparse_profile(
            paper_id="10.1234/x", title="Test", abstract="Test abstract",
        )
        self.assertEqual(result.mode, "PROFILE")
        self.assertGreater(result.total_triples, 0)

    def test_profile_caps_max_triples(self):
        ext, _ = _make_ext()
        many = [
            _triple(relation="USES_METHOD", head="p", head_type="Paper",
                    tail=f"m{i}", tail_type="ResearchMethod", evidence=f"ev{i}")
            for i in range(50)
        ]
        selected = EntityExtractor._select_sparse_triples(many, max_triples=30)
        self.assertEqual(len(selected), 30)

    def test_related_to_capped_at_2(self):
        triples = [_triple(relation="RELATED_TO", head=f"p{i}", tail=f"c{i}") for i in range(10)]
        triples += [_triple(relation="USES_METHOD", head="p", head_type="Paper",
                           tail=f"m{i}", tail_type="ResearchMethod", evidence=f"ev{i}")
                    for i in range(30)]
        selected = EntityExtractor._select_sparse_triples(triples, max_triples=30)
        related = [t for t in selected if t.relation == "RELATED_TO"]
        self.assertLessEqual(len(related), 2)

    def test_claims_capped_at_5(self):
        triples = [_triple(relation="CLAIMS", head="p", head_type="Paper",
                          tail=f"claim {i}", tail_type="Claim", evidence=f"ev{i}")
                   for i in range(10)]
        triples += [_triple(relation="USES_METHOD", head="p", head_type="Paper",
                           tail=f"m{i}", tail_type="ResearchMethod", evidence=f"ev{i}")
                    for i in range(30)]
        selected = EntityExtractor._select_sparse_triples(triples, max_triples=30)
        claims = [t for t in selected if t.relation == "CLAIMS"]
        self.assertLessEqual(len(claims), 5)

    def test_profile_cache_hit(self):
        import tempfile, os, shutil
        tmp = tempfile.mkdtemp()
        try:
            ext, client = _make_ext()
            ext.cache_dir = os.path.join(tmp, "cache.db")
            ext._cache = ExtractionCache(ext.cache_dir)

            # First call (cache miss)
            client.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(
                    content=json.dumps({"triples": [
                        {"head": "10.1234/x", "head_type": "Paper",
                         "relation": "STUDIES_DOMAIN", "tail": "physics",
                         "tail_type": "SubjectDomain",
                         "evidence": "study", "confidence": 1.0, "layer": "L2"},
                    ]})
                ))],
                usage=MagicMock(total_tokens=100, prompt_tokens=50, completion_tokens=50),
            )
            r1 = ext.extract_sparse_profile(
                paper_id="10.1234/x", title="T", abstract="A",
            )
            self.assertEqual(r1.cache_hits, 0)
            self.assertEqual(r1.cache_misses, 1)

            # Second call (cache hit)
            r2 = ext.extract_sparse_profile(
                paper_id="10.1234/x", title="T", abstract="A",
            )
            self.assertEqual(r2.cache_hits, 1)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ==================================================================
# 4. Prompt templates
# ==================================================================
class TestPromptTemplates(unittest.TestCase):

    def test_batch_prompt_includes_paper_id(self):
        prompt = build_batch_user_prompt(
            [{"chunk_id": "chunk_0000", "chunk_index": 0, "text": "A study."}],
            paper_title="Example", paper_id="10.1234/example",
        )
        self.assertIn("paper_id: 10.1234/example", prompt)
        self.assertIn("Never output head == tail", prompt)

    def test_profile_prompt_is_metadata_only(self):
        prompt = build_profile_user_prompt(
            paper_id="10.1234/example",
            title="AI scaffolding in physics modelling",
            abstract="We study modelling performance and transfer.",
            keywords="physics education; generative AI",
        )
        self.assertIn("10.1234/example", prompt)
        self.assertIn("AI scaffolding in physics modelling", prompt)
        self.assertIn("physics education; generative AI", prompt)


# ==================================================================
# 5. Dedup
# ==================================================================
class TestDedup(unittest.TestCase):

    def test_same_triple_merged(self):
        t1 = _triple(head="A", head_type="Technology", relation="IMPROVES",
                     tail="B", tail_type="LearningOutcome", evidence="ev1",
                     confidence=0.8, source_chunk_id="c0", source_chunk_index=0)
        t2 = _triple(head="A", head_type="Technology", relation="IMPROVES",
                     tail="B", tail_type="LearningOutcome", evidence="ev2",
                     confidence=0.9, source_chunk_id="c1", source_chunk_index=1)
        result = EntityExtractor._deduplicate_local([t1, t2])
        self.assertEqual(len(result), 1)
        self.assertIn("ev1", result[0].evidence)
        self.assertIn("ev2", result[0].evidence)
        self.assertEqual(result[0].confidence, 0.9)
        self.assertIn("c0", result[0].source_chunk_ids)
        self.assertIn("c1", result[0].source_chunk_ids)

    def test_sources_sorted(self):
        t1 = _triple(source_chunk_id="c", source_chunk_index=2)
        t2 = _triple(source_chunk_id="a", source_chunk_index=0)
        t3 = _triple(source_chunk_id="b", source_chunk_index=1)
        result = EntityExtractor._deduplicate_local([t1, t2, t3])
        self.assertEqual(result[0].source_chunk_ids, ["a", "b", "c"])
        self.assertEqual(result[0].source_chunk_indices, [0, 1, 2])


# ==================================================================
# 6. Batch provenance
# ==================================================================
class TestBatchProvenance(unittest.TestCase):

    def test_missing_chunk_id_causes_failure(self):
        ext, client = _make_ext(chunks_per_request=2)
        # Return only 1 chunk_id for 2 expected
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content=json.dumps({"results": [
                    {"chunk_id": "doi_chunk_0000", "triples": [
                        {"head": "doi", "head_type": "Paper",
                         "relation": "STUDIES_DOMAIN", "tail": "physics",
                         "tail_type": "SubjectDomain",
                         "evidence": "test", "confidence": 1.0, "layer": "L2"},
                    ]},
                ]})
            ))],
            usage=MagicMock(total_tokens=100, prompt_tokens=50, completion_tokens=50),
        )
        result = ext.extract_from_chunks_batched(
            ["A", "B"], paper_id="doi", batch_size=2, use_cache=False,
        )
        has_failure = len(result.failures) > 0 or any(
            cr.status == "failed" for cr in result.chunks
        )
        self.assertTrue(has_failure, "Missing chunk_id should trigger failure")


# ==================================================================
# 7. Retry count
# ==================================================================
class TestRetryCount(unittest.TestCase):

    def test_first_success_has_retry_zero(self):
        ext, client = _make_ext(max_retries=2, retry_delay=0.01)
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content=json.dumps([{
                    "head": "e0", "head_type": "Concept", "relation": "RELATED_TO",
                    "tail": "e1", "tail_type": "Concept",
                    "evidence": "test", "confidence": 0.9, "layer": "L2",
                }])
            ))],
            usage=MagicMock(total_tokens=50, prompt_tokens=30, completion_tokens=20),
        )
        result = ext.extract_from_chunk("test", use_cache=False)
        self.assertEqual(result.retry_count, 0)

    def test_one_retry_then_success(self):
        from openai import APITimeoutError
        ext, client = _make_ext(max_retries=2, retry_delay=0.01)
        client.chat.completions.create.side_effect = [
            APITimeoutError(request=MagicMock()),
            MagicMock(
                choices=[MagicMock(message=MagicMock(
                    content=json.dumps([{
                        "head": "e0", "head_type": "Concept", "relation": "RELATED_TO",
                        "tail": "e1", "tail_type": "Concept",
                        "evidence": "test", "confidence": 0.9, "layer": "L2",
                    }])
                ))],
                usage=MagicMock(total_tokens=50, prompt_tokens=30, completion_tokens=20),
            ),
        ]
        result = ext.extract_from_chunk("test", use_cache=False)
        self.assertEqual(result.retry_count, 1)


# ==================================================================
# 8. Performance mock
# ==================================================================
class TestPerformanceMock(unittest.TestCase):

    def test_batch_vs_single_call_count(self):
        chunks = [f"Chunk {i} with education research content" for i in range(9)]

        with patch("graph_rag.entity_extract.OpenAI") as m:
            client = MagicMock()
            m.return_value = client

            def batch_side_effect(**kwargs):
                import re
                msg = kwargs["messages"][1]["content"]
                cids = re.findall(r'\[(doi_chunk_\d+)\]', msg)
                results = [{"chunk_id": cid, "triples": [
                    {"head": "doi", "head_type": "Paper", "relation": "STUDIES_DOMAIN",
                     "tail": "physics", "tail_type": "SubjectDomain",
                     "evidence": "test", "confidence": 1.0, "layer": "L2"},
                ]} for cid in cids]
                return MagicMock(
                    choices=[MagicMock(message=MagicMock(content=json.dumps({"results": results})))],
                    usage=MagicMock(total_tokens=100, prompt_tokens=50, completion_tokens=50),
                )

            client.chat.completions.create.side_effect = batch_side_effect

            ext = EntityExtractor(
                api_base="http://localhost/v1", api_key="sk-test",
                model_id="test", chunks_per_request=3, cache_dir="",
            )
            result = ext.extract_from_chunks_batched(
                chunks, paper_id="doi", batch_size=3, use_cache=False,
            )
            self.assertEqual(client.chat.completions.create.call_count, 3)
            self.assertEqual(len(result.chunks), 9)


if __name__ == "__main__":
    unittest.main()
