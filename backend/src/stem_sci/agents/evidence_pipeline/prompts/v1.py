"""Version 1 prompts for the evidence pipeline."""

from ...runtime import PromptRegistry

SYSTEM_PROMPT = (
    "Use only the supplied project evidence. Every factual field must preserve valid "
    "evidence IDs. Leave unsupported fields empty and return only the requested schema."
)


def register_evidence_prompts(registry: PromptRegistry) -> None:
    registry.register(
        name="paper_cards",
        version="evidence-review-v1",
        system_prompt=SYSTEM_PROMPT,
        user_prompt_template="Extract PaperCards from this bounded corpus JSON: {payload}",
    )
    registry.register(
        name="evidence_matrix",
        version="evidence-review-v1",
        system_prompt=SYSTEM_PROMPT,
        user_prompt_template="Build an evidence matrix from these PaperCards JSON: {payload}",
    )
    registry.register(
        name="conflicts_gaps",
        version="evidence-review-v1",
        system_prompt=SYSTEM_PROMPT,
        user_prompt_template=(
            "Identify conflicts and corpus-limited gaps from this evidence matrix JSON: {payload}"
        ),
    )
    registry.register(
        name="bounded_synthesis",
        version="evidence-review-v1",
        system_prompt=SYSTEM_PROMPT,
        user_prompt_template=(
            "Synthesize only the bounded evidence and state corpus limitations: {payload}"
        ),
    )
