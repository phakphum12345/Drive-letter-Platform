from pathlib import Path

p = Path("tools/research_os_resource_identity_allocator.py")

p.write_text(
'''from __future__ import annotations

import hashlib
from dataclasses import dataclass


RESOURCE_IDENTITY_ALLOCATOR_SCHEMA = (
    "RESEARCH_OS_RESOURCE_IDENTITY_ALLOCATOR_V1"
)


@dataclass(frozen=True)
class ResourceKey:
    kind: str
    canonical_identity: str
    path: str

    def normalized(self) -> "ResourceKey":
        return ResourceKey(
            kind=self.kind.strip().upper(),
            canonical_identity=self.canonical_identity.strip().lower(),
            path=self.path.replace("\\\\", "/").strip(),
        )


def make_resource_key(
    kind: str,
    canonical_identity: str,
    path: str,
) -> ResourceKey:
    key = ResourceKey(
        kind=kind,
        canonical_identity=canonical_identity,
        path=path,
    ).normalized()

    if not key.kind:
        raise ValueError("RESOURCE_KIND_REQUIRED")

    if not key.canonical_identity:
        raise ValueError("RESOURCE_IDENTITY_REQUIRED")

    if not key.path:
        raise ValueError("RESOURCE_PATH_REQUIRED")

    return key


def make_resource_id(key: ResourceKey) -> str:
    key = key.normalized()

    payload = (
        f"{key.kind}:"
        f"{key.canonical_identity}:"
        f"{key.path}"
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()[:24]


def allocate_resource_ids(
    resources: list[dict],
) -> list[dict]:
    result = []

    for resource in resources:
        key = make_resource_key(
            str(resource.get("kind", "")),
            str(resource.get("canonical_identity", "")),
            str(resource.get("path", "")),
        )

        candidate = dict(resource)
        candidate["kind"] = key.kind
        candidate["canonical_identity"] = (
            key.canonical_identity
        )
        candidate["path"] = key.path
        candidate["resource_id"] = make_resource_id(key)

        result.append(candidate)

    return sorted(
        result,
        key=lambda x: (
            x["kind"],
            x["canonical_identity"],
            x["path"],
            x["resource_id"],
        ),
    )
''',
    encoding="utf-8",
)

print("RESOURCE_IDENTITY_ALLOCATOR_CREATED")


t = Path(
    "tools/test_research_os_resource_identity_allocator.py"
)

t.write_text(
'''import unittest

from tools.research_os_resource_identity_allocator import (
    allocate_resource_ids,
    make_resource_id,
    make_resource_key,
)


class ResourceIdentityAllocatorTests(unittest.TestCase):

    def test_same_identity_different_paths_are_distinct(self):
        a = make_resource_key(
            "IMPLEMENTATION",
            "EXAMPLE",
            "tools/a.py",
        )
        b = make_resource_key(
            "IMPLEMENTATION",
            "EXAMPLE",
            "tools/b.py",
        )

        self.assertNotEqual(
            make_resource_id(a),
            make_resource_id(b),
        )

    def test_normalization_is_deterministic(self):
        a = make_resource_key(
            "implementation",
            "EXAMPLE",
            r"tools\\a.py",
        )
        b = make_resource_key(
            "IMPLEMENTATION",
            "example",
            "tools/a.py",
        )

        self.assertEqual(
            make_resource_id(a),
            make_resource_id(b),
        )

    def test_missing_kind_fails_closed(self):
        with self.assertRaises(ValueError):
            make_resource_key(
                "",
                "EXAMPLE",
                "a.py",
            )

    def test_missing_identity_fails_closed(self):
        with self.assertRaises(ValueError):
            make_resource_key(
                "IMPLEMENTATION",
                "",
                "a.py",
            )

    def test_missing_path_fails_closed(self):
        with self.assertRaises(ValueError):
            make_resource_key(
                "IMPLEMENTATION",
                "EXAMPLE",
                "",
            )

    def test_allocation_is_deterministic(self):
        values = [
            {
                "kind": "IMPLEMENTATION",
                "canonical_identity": "B",
                "path": "b.py",
            },
            {
                "kind": "IMPLEMENTATION",
                "canonical_identity": "A",
                "path": "a.py",
            },
        ]

        self.assertEqual(
            allocate_resource_ids(values),
            allocate_resource_ids(list(reversed(values))),
        )


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

print("RESOURCE_IDENTITY_ALLOCATOR_TESTS_CREATED")
