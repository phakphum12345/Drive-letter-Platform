from pathlib import Path

root = Path("tools")

module = root / "research_os_resource_instance.py"
test = root / "test_research_os_resource_instance.py"

module.write_text(
'''from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


RESOURCE_INSTANCE_SCHEMA = "RESEARCH_OS_RESOURCE_INSTANCE_V1"


def normalize_path(path: str | Path) -> str:
    value = str(path).replace("\\\\", "/").strip()
    if not value:
        raise ValueError("RESOURCE_INSTANCE_PATH_REQUIRED")
    return value


def normalize_resource_id(resource_id: str) -> str:
    value = str(resource_id).strip()
    if not value:
        raise ValueError("RESOURCE_INSTANCE_RESOURCE_ID_REQUIRED")
    return value


def content_fingerprint(content: bytes) -> str:
    if not isinstance(content, bytes):
        raise TypeError("RESOURCE_INSTANCE_CONTENT_MUST_BE_BYTES")
    return hashlib.sha256(content).hexdigest()


def instance_fingerprint(
    resource_id: str,
    path: str,
    content_sha256: str,
) -> str:
    resource_id = normalize_resource_id(resource_id)
    path = normalize_path(path)

    if not content_sha256:
        raise ValueError("RESOURCE_INSTANCE_CONTENT_SHA256_REQUIRED")

    payload = {
        "resource_id": resource_id,
        "path": path,
        "content_sha256": content_sha256,
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ResourceInstance:
    resource_id: str
    path: str
    content_sha256: str
    instance_sha256: str

    @classmethod
    def create(
        cls,
        resource_id: str,
        path: str,
        content: bytes,
    ) -> "ResourceInstance":
        resource_id = normalize_resource_id(resource_id)
        path = normalize_path(path)

        content_sha = content_fingerprint(content)
        instance_sha = instance_fingerprint(
            resource_id,
            path,
            content_sha,
        )

        return cls(
            resource_id=resource_id,
            path=path,
            content_sha256=content_sha,
            instance_sha256=instance_sha,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "schema": RESOURCE_INSTANCE_SCHEMA,
            "resource_id": self.resource_id,
            "path": self.path,
            "content_sha256": self.content_sha256,
            "instance_sha256": self.instance_sha256,
        }


def instance_from_file(
    resource_id: str,
    path: str | Path,
) -> ResourceInstance:
    normalized = normalize_path(path)
    source = Path(path)

    if not source.is_file():
        raise FileNotFoundError(
            f"RESOURCE_INSTANCE_FILE_NOT_FOUND:{normalized}"
        )

    return ResourceInstance.create(
        resource_id=resource_id,
        path=normalized,
        content=source.read_bytes(),
    )
''',
    encoding="utf-8",
)

test.write_text(
'''import unittest

from tools.research_os_resource_instance import (
    RESOURCE_INSTANCE_SCHEMA,
    ResourceInstance,
    content_fingerprint,
    instance_fingerprint,
)


class ResourceInstanceTests(unittest.TestCase):

    def test_content_fingerprint_is_deterministic(self):
        first = content_fingerprint(b"research-os")
        second = content_fingerprint(b"research-os")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_different_content_changes_fingerprint(self):
        first = content_fingerprint(b"a")
        second = content_fingerprint(b"b")

        self.assertNotEqual(first, second)

    def test_instance_is_deterministic(self):
        first = ResourceInstance.create(
            "RESOURCE:001",
            "tools/example.py",
            b"content",
        )
        second = ResourceInstance.create(
            "RESOURCE:001",
            "tools/example.py",
            b"content",
        )

        self.assertEqual(first, second)
        self.assertEqual(first.instance_sha256, second.instance_sha256)

    def test_path_normalization_is_deterministic(self):
        first = ResourceInstance.create(
            "RESOURCE:001",
            r"tools\\example.py",
            b"content",
        )
        second = ResourceInstance.create(
            "RESOURCE:001",
            "tools/example.py",
            b"content",
        )

        self.assertEqual(first, second)

    def test_metadata_changes_instance_fingerprint(self):
        first = ResourceInstance.create(
            "RESOURCE:001",
            "tools/example.py",
            b"content",
        )
        second = ResourceInstance.create(
            "RESOURCE:002",
            "tools/example.py",
            b"content",
        )

        self.assertNotEqual(
            first.instance_sha256,
            second.instance_sha256,
        )

    def test_missing_resource_id_fails_closed(self):
        with self.assertRaises(ValueError):
            ResourceInstance.create(
                "",
                "tools/example.py",
                b"content",
            )

    def test_missing_path_fails_closed(self):
        with self.assertRaises(ValueError):
            ResourceInstance.create(
                "RESOURCE:001",
                "",
                b"content",
            )

    def test_schema_is_present(self):
        instance = ResourceInstance.create(
            "RESOURCE:001",
            "tools/example.py",
            b"content",
        )

        data = instance.to_dict()

        self.assertEqual(
            data["schema"],
            RESOURCE_INSTANCE_SCHEMA,
        )


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

print("RESOURCE_INSTANCE_CREATED")
print(module)
print(test)
print("M2_NOT_MODIFIED")
print("NO_COMMIT")
print("NO_PUSH")
