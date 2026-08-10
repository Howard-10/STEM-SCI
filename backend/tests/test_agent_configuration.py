from stem_sci.agents import EvidenceReviewAgent, PaperWritingAgent
from stem_sci.api import _configured_agent_registry


def test_api_keeps_scaffold_agents_without_local_key(monkeypatch) -> None:
    monkeypatch.delenv("STEM_SCI_LLM_API_KEY", raising=False)

    registry = _configured_agent_registry()

    evidence = registry.get("evidence_review")
    writing = registry.get("paper_writing")
    assert isinstance(evidence, EvidenceReviewAgent)
    assert isinstance(writing, PaperWritingAgent)
    assert evidence.pipeline is None
    assert writing.pipeline is None


def test_api_injects_gpt_pipelines_when_local_key_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("STEM_SCI_LLM_PROVIDER", "gpt")
    monkeypatch.setenv("STEM_SCI_LLM_BASE_URL", "https://gpt.invalid/v1")
    monkeypatch.setenv("STEM_SCI_LLM_API_KEY", "local-only-test-key")
    monkeypatch.setenv("STEM_SCI_LLM_MODEL", "gpt-test")
    monkeypatch.setenv("STEM_SCI_LLM_TIMEOUT_SECONDS", "5")

    registry = _configured_agent_registry()

    evidence = registry.get("evidence_review")
    writing = registry.get("paper_writing")
    assert isinstance(evidence, EvidenceReviewAgent)
    assert isinstance(writing, PaperWritingAgent)
    assert evidence.pipeline is not None
    assert writing.pipeline is not None
