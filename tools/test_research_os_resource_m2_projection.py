from __future__ import annotations

import unittest

from tools.research_os_relationship_registry import validate_relationships
from tools.research_os_resource_m2_projection import (
    M2_RELATION_MAP,
    project_binding,
    project_bindings,
)
from tools.research_os_semantic_binding import BindingResult


SHA = "4a38e1cd596bbe334315e981435a2a3b845ca7f4"


def binding(
    relation: str,
    targets: tuple[str, ...],
    *,
    tier: str = "EXPLICIT_PATH",
    ambiguous: bool = False,
    unresolved: bool = False,
) -> BindingResult:
    return BindingResult(
        relation=relation,
        targets=targets,
        tier=tier,
        ambiguous=ambiguous,
        unresolved=unresolved,
        candidates=targets,
    )


class ResourceM2ProjectionTests(unittest.TestCase):

    def test_projection_composes_with_canonical_relationship_registry(self):
        canonical_relationships = validate_relationships(
            [
                project_binding(
                    source_sha=SHA,
                    resource_id="RESOURCE:r1",
                    kind="CONTRACT",
                    path="current/example.json",
                    binding=binding(
                        "VERIFIED_BY",
                        ("TEST:resource-foundation",),
                    ),
                )[0],
                project_binding(
                    source_sha=SHA,
                    resource_id="RESOURCE:r1",
                    kind="CONTRACT",
                    path="current/example.json",
                    binding=binding(
                        "SUPPORTED_BY",
                        ("EVIDENCE:resource-foundation",),
                    ),
                )[0],
            ]
        )

        self.assertEqual(
            [(row.relation, row.target) for row in canonical_relationships],
            [
                ("SUPPORTED_BY", "EVIDENCE:resource-foundation"),
                ("VERIFIED_BY", "TEST:resource-foundation"),
            ],
        )

        projected = project_bindings(
            source_sha=SHA,
            resource_id="RESOURCE:r1",
            kind="CONTRACT",
            path="current/example.json",
            bindings=(
                binding(
                    "BOUND_TO",
                    ("FINAL_GATE:UNIFIED",),
                ),
                binding(
                    "VERIFIED_BY",
                    ("TEST:resource-foundation",),
                ),
                binding(
                    "SUPPORTED_BY",
                    ("EVIDENCE:resource-foundation",),
                ),
            ),
        )

        self.assertEqual(
            [(row.relation, row.target) for row in projected],
            [
                ("BINDS_TO", "FINAL_GATE:UNIFIED"),
                ("SUPPORTED_BY", "EVIDENCE:resource-foundation"),
                ("VERIFIED_BY", "TEST:resource-foundation"),
            ],
        )

        self.assertTrue(
            all(row.source == "RESOURCE:r1" for row in projected)
        )

        self.assertTrue(
            all(SHA in (row.evidence or "") for row in projected)
        )

    def test_all_relations_have_explicit_mapping(self):
        self.assertEqual(
            set(M2_RELATION_MAP),
            {
                "BOUND_TO",
                "ENFORCED_BY",
                "DISPATCHED_BY",
                "VERIFIED_BY",
                "SUPPORTED_BY",
            },
        )

    def test_resource_id_is_preserved(self):
        result = project_binding(
            source_sha=SHA,
            resource_id="resource-123",
            kind="IMPLEMENTATION",
            path="tools/example.py",
            binding=binding(
                "BOUND_TO",
                ("FINAL_GATE:UNIFIED",),
            ),
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source, "resource-123")

    def test_bound_to_maps_to_bins_to(self):
        result = project_binding(
            source_sha=SHA,
            resource_id="r1",
            kind="IMPLEMENTATION",
            path="tools/example.py",
            binding=binding(
                "BOUND_TO",
                ("FINAL_GATE:UNIFIED",),
            ),
        )

        self.assertEqual(result[0].relation, "BINDS_TO")

    def test_enforced_by_maps_to_enforces_or_references(self):
        result = project_binding(
            source_sha=SHA,
            resource_id="r1",
            kind="IMPLEMENTATION",
            path="tools/example.py",
            binding=binding(
                "ENFORCED_BY",
                ("IMPLEMENTATION:x",),
            ),
        )

        self.assertEqual(
            result[0].relation,
            "ENFORCES_OR_REFERENCES",
        )

    def test_dispatched_by_maps_to_dispatches_or_references(self):
        result = project_binding(
            source_sha=SHA,
            resource_id="r1",
            kind="CONTRACT",
            path="current/example.json",
            binding=binding(
                "DISPATCHED_BY",
                ("WORKFLOW:x",),
            ),
        )

        self.assertEqual(
            result[0].relation,
            "DISPATCHES_OR_REFERENCES",
        )

    def test_verified_and_supported_are_preserved(self):
        for relation in ("VERIFIED_BY", "SUPPORTED_BY"):
            result = project_binding(
                source_sha=SHA,
                resource_id="r1",
                kind="CONTRACT",
                path="current/example.json",
                binding=binding(
                    relation,
                    ("TEST:x",),
                ),
            )

            self.assertEqual(result[0].relation, relation)

    def test_ambiguous_binding_creates_no_edge(self):
        result = project_binding(
            source_sha=SHA,
            resource_id="r1",
            kind="CONTRACT",
            path="current/example.json",
            binding=binding(
                "BOUND_TO",
                (),
                ambiguous=True,
            ),
        )

        self.assertEqual(result, [])

    def test_unresolved_binding_creates_no_edge(self):
        result = project_binding(
            source_sha=SHA,
            resource_id="r1",
            kind="CONTRACT",
            path="current/example.json",
            binding=binding(
                "BOUND_TO",
                (),
                unresolved=True,
            ),
        )

        self.assertEqual(result, [])

    def test_source_sha_is_preserved_as_evidence(self):
        result = project_binding(
            source_sha=SHA,
            resource_id="r1",
            kind="CONTRACT",
            path="current/example.json",
            binding=binding(
                "BOUND_TO",
                ("FINAL_GATE:UNIFIED",),
            ),
        )

        self.assertIn(SHA, result[0].evidence)

    def test_output_is_deterministic(self):
        a = project_binding(
            source_sha=SHA,
            resource_id="r1",
            kind="CONTRACT",
            path="current/example.json",
            binding=binding(
                "SUPPORTED_BY",
                ("TEST:b", "TEST:a"),
            ),
        )

        b = project_binding(
            source_sha=SHA,
            resource_id="r1",
            kind="CONTRACT",
            path="current/example.json",
            binding=binding(
                "SUPPORTED_BY",
                ("TEST:a", "TEST:b"),
            ),
        )

        self.assertEqual(a, b)

    def test_single_cardinality_multiple_targets_are_rejected(self):
        with self.assertRaises(ValueError):
            project_bindings(
                source_sha=SHA,
                resource_id="r1",
                kind="CONTRACT",
                path="current/example.json",
                bindings=(
                    binding(
                        "BOUND_TO",
                        (
                            "IMPLEMENTATION:a",
                            "IMPLEMENTATION:b",
                        ),
                    ),
                ),
            )


if __name__ == "__main__":
    unittest.main()
