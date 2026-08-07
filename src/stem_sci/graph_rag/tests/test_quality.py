from ..entity_extract import EntityExtractor
from ..prompt_templates import build_batch_user_prompt, build_profile_user_prompt
from ..schema import EntityType, RelationType, Triple


def make_triple(**overrides) -> Triple:
    values = {
        "head": "paper object",
        "head_type": EntityType.CONCEPT.value,
        "relation": RelationType.RELATED_TO.value,
        "tail": "another object",
        "tail_type": EntityType.CONCEPT.value,
        "evidence": "The paper explicitly describes the relationship.",
        "confidence": 0.9,
        "layer": "L2",
    }
    values.update(overrides)
    return Triple(**values)


def test_old_paper_self_loop_is_normalized_to_paper_edge() -> None:
    triple = make_triple(
        head="quasi-experiment",
        head_type=EntityType.RESEARCH_METHOD.value,
        relation=RelationType.USES_METHOD.value,
        tail="quasi-experiment",
        tail_type=EntityType.RESEARCH_METHOD.value,
    )

    EntityExtractor._normalize_paper_relations([triple], "10.1234/example")

    assert triple.head == "10.1234/example"
    assert triple.head_type == EntityType.PAPER.value
    assert triple.tail == "quasi-experiment"
    assert triple.tail_type == EntityType.RESEARCH_METHOD.value
    assert EntityExtractor._validate_triple(triple)


def test_validator_rejects_self_loop() -> None:
    triple = make_triple(
        relation=RelationType.RELATED_TO.value,
        head="same",
        tail="same",
    )

    assert not EntityExtractor._validate_triple(triple)


def test_validator_rejects_sentence_as_entity() -> None:
    triple = make_triple(
        head="subjective norms significantly influence perceived usefulness.",
        tail="perceived usefulness",
    )

    assert not EntityExtractor._validate_triple(triple)


def test_validator_requires_paper_head_for_paper_relation() -> None:
    triple = make_triple(
        relation=RelationType.INVOLVES_POPULATION.value,
        head="pre-service teachers",
        head_type=EntityType.STUDENT_POPULATION.value,
        tail="pre-service teachers",
        tail_type=EntityType.STUDENT_POPULATION.value,
    )

    assert not EntityExtractor._validate_triple(triple)


def test_batch_prompt_provides_paper_id_and_forbids_self_loop() -> None:
    prompt = build_batch_user_prompt(
        [{"chunk_id": "paper_chunk_0000", "chunk_index": 0, "text": "A study."}],
        paper_title="Example paper",
        paper_id="10.1234/example",
    )

    assert "paper_id: 10.1234/example" in prompt
    assert "Never output head == tail" in prompt


def test_profile_prompt_is_metadata_only() -> None:
    prompt = build_profile_user_prompt(
        paper_id="10.1234/example",
        title="AI scaffolding in physics modelling",
        abstract="We study modelling performance and transfer.",
        keywords="physics education; generative AI",
    )

    assert "10.1234/example" in prompt
    assert "AI scaffolding in physics modelling" in prompt
    assert "physics education; generative AI" in prompt
    assert "modelling performance and transfer" in prompt


def test_sparse_profile_selection_caps_density() -> None:
    triples = [
        make_triple(
            relation=RelationType.RELATED_TO.value,
            head=f"paper {index}",
            tail=f"concept {index}",
        )
        for index in range(10)
    ]
    triples.extend(
        make_triple(
            relation=RelationType.CLAIMS.value,
            head="paper object",
            head_type=EntityType.PAPER.value,
            tail=f"claim {index}",
            tail_type=EntityType.CLAIM.value,
        )
        for index in range(8)
    )
    triples.extend(
        make_triple(
            relation=RelationType.USES_METHOD.value,
            head="paper object",
            head_type=EntityType.PAPER.value,
            tail=f"method {index}",
            tail_type=EntityType.RESEARCH_METHOD.value,
        )
        for index in range(30)
    )

    selected = EntityExtractor._select_sparse_triples(triples, max_triples=30)

    assert len(selected) == 30
    assert sum(t.relation == RelationType.RELATED_TO.value for t in selected) <= 2
    assert sum(t.relation == RelationType.CLAIMS.value for t in selected) <= 5


def test_sparse_profile_returns_profile_result_without_network(monkeypatch) -> None:
    extractor = EntityExtractor(
        api_base="http://localhost:1",
        api_key="test-key",
        model_id="test-model",
        max_retries=0,
    )
    calls: list[str] = []

    def fake_call(prompt: str, *, system_prompt: str):
        calls.append(system_prompt)
        return '{"triples": []}', [
            make_triple(
                relation=RelationType.STUDIES_DOMAIN.value,
                head="paper object",
                head_type=EntityType.PAPER.value,
                tail="physics education",
                tail_type=EntityType.SUBJECT_DOMAIN.value,
            )
        ], 0

    monkeypatch.setattr(extractor, "_call_with_retry", fake_call)
    result = extractor.extract_sparse_profile(
        paper_id="10.1234/example",
        title="A physics education study",
        abstract="The abstract describes the study.",
        keywords="physics education",
    )

    assert result.mode == "PROFILE"
    assert result.total_triples == 1
    assert result.chunks[0].chunk_id == "10.1234/example_profile"
    assert calls and "sparse cross-paper STEM research graph" in calls[0]
