"""Deterministic validation for AtomicClaimGraph and writing inputs."""

from __future__ import annotations

from .models import AtomicClaimGraph, AtomicClaimNode, WritingContextBundle


def validate_claim_node(
    claim: AtomicClaimNode, context: WritingContextBundle
) -> AtomicClaimNode:
    if claim.project_id != context.project_id:
        raise ValueError("claim project does not match writing context project")
    evidence_ids = {item.evidence_id for item in context.evidence_refs}
    formal_evidence_ids = {
        item.evidence_id
        for item in context.evidence_refs
        if item.verification_status.value in {"source_verified", "human_verified"}
    }
    if context.intended_use == "formal" and not set(claim.evidence_refs).issubset(
        formal_evidence_ids
    ):
        raise ValueError("formal claims require source_verified or human_verified evidence")
    if claim.claim_type.value == "LITERATURE":
        if not claim.evidence_refs or not set(claim.evidence_refs).issubset(evidence_ids):
            raise ValueError("literature claim requires context evidence")
    elif claim.claim_type.value == "RESULT":
        if claim.result_card_ref not in context.validated_result_cards:
            raise ValueError("result claim requires a validated result reference")
    elif claim.claim_type.value == "METHOD":
        if claim.method_ref not in context.approved_study_protocol_refs:
            raise ValueError("method claim requires an approved method reference")
    elif claim.claim_type.value == "INTERPRETATION":
        if not claim.evidence_refs:
            raise ValueError("interpretation claim requires bounded theory evidence")
        if claim.interpretation_boundary_ref is None:
            raise ValueError("interpretation claim requires an interpretation boundary")
        if claim.human_approval_ref is None:
            raise ValueError("interpretation claim requires human approval")
    return claim


def validate_claim_graph(
    graph: AtomicClaimGraph, context: WritingContextBundle
) -> AtomicClaimGraph:
    if graph.project_id != context.project_id:
        raise ValueError("claim graph project does not match writing context project")
    claim_ids: set[str] = set()
    nodes_by_id = {node.claim_id: node for node in graph.nodes}
    for claim in graph.nodes:
        if claim.claim_id in claim_ids:
            raise ValueError("claim IDs must be unique")
        claim_ids.add(claim.claim_id)
        validate_claim_node(claim, context)
        for target_id, _ in claim.relations:
            if target_id == claim.claim_id or target_id not in nodes_by_id:
                raise ValueError("claim relation must target another claim in the same graph")
        if claim.claim_type.value == "INTERPRETATION":
            result_relations = [
                target_id
                for target_id, relation in claim.relations
                if relation.value == "INTERPRETS"
                and nodes_by_id[target_id].claim_type.value == "RESULT"
            ]
            if not result_relations:
                raise ValueError("interpretation claim must interpret a RESULT claim")
    return graph
