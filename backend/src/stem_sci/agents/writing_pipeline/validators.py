"""Deterministic validation for AtomicClaimGraph and writing inputs."""

from __future__ import annotations

from .models import AtomicClaimGraph, AtomicClaimNode, WritingContextBundle


def validate_claim_node(
    claim: AtomicClaimNode, context: WritingContextBundle
) -> AtomicClaimNode:
    if claim.project_id != context.project_id:
        raise ValueError("claim project does not match writing context project")
    evidence_ids = {item.evidence_id for item in context.evidence_refs}
    if claim.claim_type.value == "LITERATURE":
        if not claim.evidence_refs or not set(claim.evidence_refs).issubset(evidence_ids):
            raise ValueError("literature claim requires context evidence")
    elif claim.claim_type.value == "RESULT":
        if claim.result_card_ref not in context.validated_result_cards:
            raise ValueError("result claim requires a validated result reference")
    elif claim.claim_type.value == "METHOD":
        if claim.method_ref not in context.approved_study_protocol_refs:
            raise ValueError("method claim requires an approved method reference")
    elif claim.claim_type.value == "INTERPRETATION" and claim.result_card_ref is None and not claim.relations:
        raise ValueError("interpretation claim requires a result relation")
    return claim


def validate_claim_graph(
    graph: AtomicClaimGraph, context: WritingContextBundle
) -> AtomicClaimGraph:
    if graph.project_id != context.project_id:
        raise ValueError("claim graph project does not match writing context project")
    claim_ids: set[str] = set()
    for claim in graph.nodes:
        if claim.claim_id in claim_ids:
            raise ValueError("claim IDs must be unique")
        claim_ids.add(claim.claim_id)
        validate_claim_node(claim, context)
    return graph
