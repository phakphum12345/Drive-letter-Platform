from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from tools.research_os_relationship_registry import (
    Relationship,
    validate_relationships,
)
from tools.research_os_semantic_binding import BindingResult


M2_RELATION_MAP = {
    "BOUND_TO": "BINDS_TO",
    "ENFORCED_BY": "ENFORCES_OR_REFERENCES",
    "DISPATCHED_BY": "DISPATCHES_OR_REFERENCES",
    "VERIFIED_BY": "VERIFIED_BY",
    "SUPPORTED_BY": "SUPPORTED_BY",
}


@dataclass(frozen=True)
class ResourceM2Projection:
    source_sha: str
    resource_id: str
    kind: str
    path: str


def project_binding(
    *,
    source_sha: str,
    resource_id: str,
    kind: str,
    path: str,
    binding: BindingResult,
) -> list[Relationship]:
    if not source_sha:
        raise ValueError("SOURCE_SHA_REQUIRED")
    if not resource_id:
        raise ValueError("RESOURCE_ID_REQUIRED")
    if not path:
        raise ValueError("RESOURCE_PATH_REQUIRED")

    relation = M2_RELATION_MAP.get(binding.relation)
    if relation is None:
        raise ValueError(f"UNSUPPORTED_RESOURCE_RELATION:{binding.relation}")

    # Fail closed: unresolved or ambiguous bindings produce no edge.
    if binding.ambiguous or binding.unresolved:
        return []

    rows = [
        Relationship(
            source=resource_id,
            relation=relation,
            target=target,
            tier=binding.tier,
            evidence=f"{source_sha}:{path}",
        )
        for target in binding.targets
    ]

    return sorted(
        rows,
        key=lambda x: (x.source, x.relation, x.target),
    )


def project_bindings(
    *,
    source_sha: str,
    resource_id: str,
    kind: str,
    path: str,
    bindings: Iterable[BindingResult],
) -> list[Relationship]:
    binding_items = tuple(bindings)

    # Validate canonical Resource relations BEFORE projecting
    # them into the M2 relation vocabulary.
    canonical_rows: list[Relationship] = []

    for binding in binding_items:
        if binding.ambiguous or binding.unresolved:
            continue

        if binding.relation not in M2_RELATION_MAP:
            raise ValueError(
                f"UNSUPPORTED_RESOURCE_RELATION:{binding.relation}"
            )

        canonical_rows.extend(
            Relationship(
                source=resource_id,
                relation=binding.relation,
                target=target,
                tier=binding.tier,
                evidence=f"{source_sha}:{path}",
            )
            for target in binding.targets
        )

    # Canonical registry remains the cardinality authority.
    validate_relationships(canonical_rows)

    projected_rows: list[Relationship] = []

    for binding in binding_items:
        projected_rows.extend(
            project_binding(
                source_sha=source_sha,
                resource_id=resource_id,
                kind=kind,
                path=path,
                binding=binding,
            )
        )

    return sorted(
        projected_rows,
        key=lambda x: (x.source, x.relation, x.target),
    )
