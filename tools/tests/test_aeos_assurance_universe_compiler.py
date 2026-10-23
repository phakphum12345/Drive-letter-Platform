from __future__ import annotations

import unittest

from tools.aeos_assurance_universe_compiler import (
    ASSURANCE_FAMILIES,
    ASSURANCE_FAMILY_ALIASES,
    DIMENSIONS,
    LIFECYCLE,
    NEVER_PASS,
    assertion_id,
    compile_addresses,
    compile_catalog,
    validate_observation,
)


class AssuranceUniverseCompilerTests(unittest.TestCase):
    def test_catalog_dimensions_are_exact_and_unique(self):
        self.assertEqual(len(ASSURANCE_FAMILIES), 100)
        self.assertEqual(len(set(ASSURANCE_FAMILIES)), 100)
        self.assertEqual(len(DIMENSIONS), 100)
        self.assertEqual(len(set(DIMENSIONS)), 100)
        self.assertTrue(LIFECYCLE)

    def test_extra_assurance_concepts_are_preserved_as_explicit_aliases(self):
        expected = {
            "common_mode_resistance",
            "assurance_completeness",
            "assurance_of_assurance",
            "constitutional_integrity",
            "knowledge_lifecycle_integrity",
        }
        self.assertEqual(set(ASSURANCE_FAMILY_ALIASES), expected)
        self.assertEqual(len(ASSURANCE_FAMILIES), 100)
        for mapping in ASSURANCE_FAMILY_ALIASES.values():
            self.assertTrue(mapping["families"])
            self.assertLessEqual(set(mapping["families"]), set(ASSURANCE_FAMILIES))
            self.assertTrue(mapping["dimensions"])
            self.assertLessEqual(set(mapping["dimensions"]), set(DIMENSIONS))
        self.assertEqual(ASSURANCE_FAMILY_ALIASES["assurance_of_assurance"]["domains"], ("D113",))
        self.assertEqual(ASSURANCE_FAMILY_ALIASES["knowledge_lifecycle_integrity"]["domains"], ("D120",))

    def test_assertion_id_is_deterministic_and_domain_bound(self):
        first = assertion_id("api", "source_integrity", "source_sha", "VERIFY")
        self.assertEqual(first, assertion_id("api", "source_integrity", "source_sha", "VERIFY"))
        self.assertNotEqual(first, assertion_id("worker", "source_integrity", "source_sha", "VERIFY"))

    def test_compile_addresses_are_deterministic_and_cover_lifecycle(self):
        first = compile_addresses(["api"], lifecycle=("VERIFY", "RECOVER"))
        second = compile_addresses(["api"], lifecycle=("VERIFY", "RECOVER"))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 100 * 100 * 2)
        self.assertEqual({item.lifecycle for item in first}, {"VERIFY", "RECOVER"})
        self.assertTrue(all(item.domain_id == "api" for item in first))

    def test_invalid_catalog_and_domains_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "exactly 100"):
            compile_addresses(["api"], families=("only_one",))
        with self.assertRaisesRegex(ValueError, "non-empty strings"):
            compile_addresses([""])
        with self.assertRaisesRegex(ValueError, "non-empty strings"):
            compile_addresses([])

    def test_catalog_summary_is_bound_to_generated_addresses(self):
        catalog = compile_catalog(["api"])
        self.assertEqual(catalog["contract"], "research-os-aeos-assurance-universe-100x/v1")
        self.assertTrue(catalog["generated"])
        self.assertEqual(catalog["domain_count"], 1)
        self.assertEqual(catalog["family_count"], 100)
        self.assertEqual(catalog["dimension_count"], 100)
        self.assertEqual(catalog["lifecycle_count"], len(LIFECYCLE))
        self.assertEqual(catalog["address_count"], 100 * 100 * len(LIFECYCLE))
        self.assertEqual(len(catalog["address_digest"]), 64)
        self.assertEqual(catalog["never_pass"], sorted(NEVER_PASS))
        self.assertNotIn("status", catalog)

    def test_non_passing_or_unknown_observations_are_rejected(self):
        for state in NEVER_PASS:
            with self.subTest(state=state):
                with self.assertRaisesRegex(ValueError, "non-passing"):
                    validate_observation({"state": state})
        with self.assertRaisesRegex(ValueError, "unknown assurance state"):
            validate_observation({"state": "PASS"})
        validate_observation({"state": "INDEPENDENTLY_VERIFIED"})


if __name__ == "__main__":
    unittest.main()
