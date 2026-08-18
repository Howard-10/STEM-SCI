"""Orchestration for claim-safe bilingual manuscript drafting."""

from __future__ import annotations

from stem_sci.agents.contracts import AgentInput
from stem_sci.agents.runtime import PromptRegistry, StructuredGenerator

from .bilingual import compare_bilingual_drafts
from .models import (
    AtomicClaimGraph,
    BilingualConsistencyStatus,
    WritingContextBundle,
    WritingPackage,
    WritingSufficiencyStatus,
)
from .prompts import register_writing_prompts
from .stages import (
    audit_writing_inputs,
    build_claim_graph,
    build_manuscript_outline,
    normalize_draft,
    render_manuscript,
    validate_manuscript,
)
from .validators import validate_claim_graph, validate_claim_node


class PaperWritingPipeline:
    def __init__(
        self,
        *,
        generator: StructuredGenerator,
        model: str,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self.generator = generator
        self.model = model
        self.prompt_registry = prompt_registry or PromptRegistry()
        register_writing_prompts(self.prompt_registry)

    def run(self, context: WritingContextBundle, agent_input: AgentInput) -> WritingPackage:
        del agent_input
        sufficiency = audit_writing_inputs(context)
        risks: list[str] = []
        metadata_refs: list[str] = []
        if not context.validated_result_cards:
            risks.append("INCOMPLETE_RESULT_INPUT")

        graph_stage = build_claim_graph(
            context, self.generator, self.prompt_registry, self.model
        )
        metadata_refs.append(graph_stage.metadata_ref)
        valid_nodes = []
        for node in graph_stage.value.nodes:
            if not context.validated_result_cards and node.claim_type.value == "RESULT":
                risks.append("INCOMPLETE_RESULT_INPUT")
                continue
            try:
                validate_claim_node(node, context)
            except ValueError:
                risks.append("INVALID_CLAIM_REFERENCE")
                continue
            valid_nodes.append(node)
        graph = AtomicClaimGraph(
            project_id=context.project_id,
            nodes=valid_nodes,
            graph_hash=graph_stage.value.graph_hash,
        )
        try:
            validate_claim_graph(graph, context)
        except ValueError:
            # A malformed claim graph is never rendered as a manuscript.  The
            # Controller may route this candidate back for bounded rework.
            risks.append("INVALID_CLAIM_GRAPH")
            graph = AtomicClaimGraph(project_id=context.project_id, nodes=[])

        outline_stage = build_manuscript_outline(
            context, graph, self.generator, self.prompt_registry, self.model
        )
        metadata_refs.append(outline_stage.metadata_ref)
        graph_ids = {node.claim_id for node in graph.nodes}
        outline = outline_stage.value.model_copy(
            update={
                "project_id": context.project_id,
                "section_claim_ids": {
                    section: [claim_id for claim_id in claim_ids if claim_id in graph_ids]
                    for section, claim_ids in outline_stage.value.section_claim_ids.items()
                },
            }
        )
        chinese_stage = render_manuscript(
            "zh-CN", context, graph, outline, self.generator, self.prompt_registry, self.model
        )
        english_stage = render_manuscript(
            "en-US", context, graph, outline, self.generator, self.prompt_registry, self.model
        )
        metadata_refs.extend([chinese_stage.metadata_ref, english_stage.metadata_ref])
        chinese = normalize_draft(chinese_stage.value, graph)
        english = normalize_draft(english_stage.value, graph)
        chinese_issues = validate_manuscript(chinese, graph, context)
        english_issues = validate_manuscript(english, graph, context)
        risks.extend(chinese_issues + english_issues)
        consistency = compare_bilingual_drafts(chinese, english, graph)
        risks.extend(consistency.risk_flags)
        if consistency.status is BilingualConsistencyStatus.BLOCKED:
            risks.append("BILINGUAL_MISMATCH")
        if risks:
            sufficiency = sufficiency.model_copy(update={"status": WritingSufficiencyStatus.INCOMPLETE})
        return WritingPackage(
            project_id=context.project_id,
            claim_graph=graph,
            outline=outline,
            chinese=chinese,
            english=english,
            consistency=consistency,
            sufficiency=sufficiency,
            risk_flags=list(dict.fromkeys(risks)),
            generation_metadata_refs=metadata_refs,
        )
