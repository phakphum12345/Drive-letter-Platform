from pathlib import Path

# ------------------------------------------------------------
# Fix validator newline handling and import root.
# ------------------------------------------------------------

validator = Path("tools/validate_resource_builder_contract.py")
text = validator.read_text(encoding="utf-8")

text = text.replace(
    'ROOT = Path(".")',
    '''ROOT = Path(__file__).resolve().parent.parent

import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))''',
    1,
)

text = text.replace(
    'newline="\\\\n"',
    'newline="\\n"',
)

validator.write_text(
    text,
    encoding="utf-8",
)

print("VALIDATOR_HARDENED")

# ------------------------------------------------------------
# Resource Translator.
# ------------------------------------------------------------

translator = Path("tools/research_os_resource_translator.py")

source = """from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping


RESOURCE_TRANSLATOR_SCHEMA = "RESEARCH_OS_CANONICAL_RESOURCE_V1"

VALID_KINDS = frozenset({
    "CONTRACT",
    "IMPLEMENTATION",
    "WORKFLOW",
    "TEST",
    "EVIDENCE",
    "MANIFEST",
    "EXTERNAL_TOOL",
    "PROJECT",
    "CONFIGURATION",
    "DOCUMENT",
    "UNKNOWN",
})


@dataclass(frozen=True)
class CanonicalResource:
    resource_id: str
    kind: str
    path: str
    canonical_identity: str
    schema: str = RESOURCE_TRANSLATOR_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_path(value: str) -> str:
    return value.replace("\\\\\\\\", "/").strip()


def normalize_kind(value: str | None) -> str:
    if not value:
        return "UNKNOWN"

    value = value.strip().upper()

    aliases = {
        "CODE": "IMPLEMENTATION",
        "SOURCE": "IMPLEMENTATION",
        "SCRIPT": "IMPLEMENTATION",
        "TESTS": "TEST",
        "TEST_FILE": "TEST",
        "CONTRACTS": "CONTRACT",
        "WORKFLOWS": "WORKFLOW",
        "TOOLS": "EXTERNAL_TOOL",
    }

    value = aliases.get(value, value)

    return value if value in VALID_KINDS else "UNKNOWN"


def normalize_identity(value: str | None, path: str) -> str:
    if value and value.strip():
        return value.strip().lower()

    return Path(path).stem.lower()


def translate_resource(
    resource: Mapping[str, Any],
) -> CanonicalResource:
    path = normalize_path(str(resource.get("path", "")))

    if not path:
        raise ValueError("RESOURCE_PATH_REQUIRED")

    resource_id = str(resource.get("resource_id", "")).strip()

    if not resource_id:
        raise ValueError("RESOURCE_ID_REQUIRED")

    kind = normalize_kind(
        str(resource.get("kind", "")) or None
    )

    identity = normalize_identity(
        resource.get("canonical_identity"),
        path,
    )

    return CanonicalResource(
        resource_id=resource_id,
        kind=kind,
        path=path,
        canonical_identity=identity,
    )


def translate_resources(
    resources: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    translated = [
        translate_resource(resource).to_dict()
        for resource in resources
    ]

    translated.sort(
        key=lambda x: (
            x["kind"],
            x["path"],
            x["resource_id"],
        )
    )

    return translated
"""

translator.write_text(
    source,
    encoding="utf-8",
)

print(f"CREATED {translator}")

# ------------------------------------------------------------
# Translator tests.
# ------------------------------------------------------------

tests = Path("tools/test_research_os_resource_translator.py")

test_source = """import unittest

from tools.research_os_resource_translator import (
    RESOURCE_TRANSLATOR_SCHEMA,
    translate_resource,
    translate_resources,
)


class ResourceTranslatorTests(unittest.TestCase):

    def test_translates_canonical_resource(self):
        resource = translate_resource({
            "resource_id": "abc123",
            "kind": "implementation",
            "path": r"tools\\\\example.py",
            "canonical_identity": "EXAMPLE",
        })

        self.assertEqual(resource.schema, RESOURCE_TRANSLATOR_SCHEMA)
        self.assertEqual(resource.kind, "IMPLEMENTATION")
        self.assertEqual(resource.path, "tools/example.py")
        self.assertEqual(resource.canonical_identity, "example")

    def test_normalizes_known_kind_alias(self):
        resource = translate_resource({
            "resource_id": "abc123",
            "kind": "source",
            "path": "tools/example.py",
            "canonical_identity": "EXAMPLE",
        })

        self.assertEqual(resource.kind, "IMPLEMENTATION")

    def test_unknown_kind_becomes_unknown(self):
        resource = translate_resource({
            "resource_id": "abc123",
            "kind": "something_new",
            "path": "example.txt",
            "canonical_identity": "EXAMPLE",
        })

        self.assertEqual(resource.kind, "UNKNOWN")

    def test_missing_resource_id_fails_closed(self):
        with self.assertRaises(ValueError):
            translate_resource({
                "kind": "implementation",
                "path": "tools/example.py",
            })

    def test_missing_path_fails_closed(self):
        with self.assertRaises(ValueError):
            translate_resource({
                "resource_id": "abc123",
                "kind": "implementation",
            })

    def test_translation_is_deterministic(self):
        resources = [
            {
                "resource_id": "b",
                "kind": "test",
                "path": "tests/b.py",
                "canonical_identity": "B",
            },
            {
                "resource_id": "a",
                "kind": "implementation",
                "path": "tools/a.py",
                "canonical_identity": "A",
            },
        ]

        first = translate_resources(resources)
        second = translate_resources(list(reversed(resources)))

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
"""

tests.write_text(
    test_source,
    encoding="utf-8",
)

print(f"CREATED {tests}")
print("NO_M2_MODIFICATION")
print("NO_COMMIT")
print("NO_PUSH")
