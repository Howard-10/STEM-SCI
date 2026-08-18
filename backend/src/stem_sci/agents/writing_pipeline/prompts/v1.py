"""Version 1 prompts for claim-safe writing."""

from ...runtime import PromptRegistry

SYSTEM_PROMPT = (
    "Use only the supplied AtomicClaimGraph and approved context. Do not create "
    "citations, numbers, results, analyses, or stronger causal language. Return only JSON."
)


def register_writing_prompts(registry: PromptRegistry) -> None:
    registry.register(
        name="claim_graph",
        version="paper-writing-v1",
        system_prompt=SYSTEM_PROMPT,
        user_prompt_template="Build one typed AtomicClaimGraph from this context: {payload}",
    )
    registry.register(
        name="outline",
        version="paper-writing-v1",
        system_prompt=SYSTEM_PROMPT,
        user_prompt_template="Build an IMRaD outline using only these claims: {payload}",
    )
    registry.register(
        name="draft_zh",
        version="paper-writing-v1",
        system_prompt=SYSTEM_PROMPT,
        user_prompt_template="Render the Chinese manuscript from this graph and outline: {payload}",
    )
    registry.register(
        name="draft_en",
        version="paper-writing-v1",
        system_prompt=SYSTEM_PROMPT,
        user_prompt_template="Render the English manuscript from this graph and outline: {payload}",
    )
