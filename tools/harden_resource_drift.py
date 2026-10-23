from pathlib import Path

module = Path("tools/research_os_resource_drift.py")
test = Path("tools/test_research_os_resource_drift.py")

module.write_text(
'''from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from tools.research_os_resource_instance import ResourceInstance


RESOURCE_DRIFT_SCHEMA = "RESEARCH_OS_RESOURCE_DRIFT_V1"


DRIFT_STATES = frozenset(
    {
        "UNCHANGED",
        "CONTENT_DRIFT",
        "PATH_DRIFT",
        "RESOURCE_ID_DRIFT",
        "ADDED",
        "REMOVED",
    }
)


def _value(mapping: Mapping, key: str) -> str:
    value = mapping.get(key)
    if value is None:
        raise ValueError(f"RESOURCE_DRIFT_FIELD_REQUIRED:{key}")

    value = str(value).strip()
    if not value:
        raise ValueError(f"RESOURCE_DRIFT_FIELD_REQUIRED:{key}")

    return value


def _instance_fields(instance: ResourceInstance) -> tuple[str, str, str]:
    return (
        _value(instance.to_dict(), "resource_id"),
        _value(instance.to_dict(), "path"),
        _value(instance.to_dict(), "content_sha256"),
    )


@dataclass(frozen=True)
class ResourceDrift:
    resource_id: str
    state: str
    baseline_path: str | None
    current_path: str | None
    baseline_content_sha256: str | None
    current_content_sha256: str | None

    def to_dict(self) -> dict:
        if self.state not in DRIFT_STATES:
            raise ValueError(
                f"RESOURCE_DRIFT_INVALID_STATE:{self.state}"
            )

        return {
            "schema": RESOURCE_DRIFT_SCHEMA,
            "resource_id": self.resource_id,
            "state": self.state,
            "baseline_path": self.baseline_path,
            "current_path": self.current_path,
            "baseline_content_sha256": self.baseline_content_sha256,
            "current_content_sha256": self.current_content_sha256,
        }


def compare_instances(
    baseline: ResourceInstance,
    current: ResourceInstance,
) -> ResourceDrift:
    baseline_id, baseline_path, baseline_sha = _instance_fields(baseline)
    current_id, current_path, current_sha = _instance_fields(current)

    if baseline_id != current_id:
        state = "RESOURCE_ID_DRIFT"
    elif baseline_path != current_path:
        state = "PATH_DRIFT"
    elif baseline_sha != current_sha:
        state = "CONTENT_DRIFT"
    else:
        state = "UNCHANGED"

    return ResourceDrift(
        resource_id=current_id,
        state=state,
        baseline_path=baseline_path,
        current_path=current_path,
        baseline_content_sha256=baseline_sha,
        current_content_sha256=current_sha,
    )


def compare_resource_sets(
    baseline: Mapping[str, ResourceInstance],
    current: Mapping[str, ResourceInstance],
) -> list[ResourceDrift]:
    baseline_ids = set(baseline)
    current_ids = set(current)

    results: list[ResourceDrift] = []

    for resource_id in sorted(current_ids - baseline_ids):
        instance = current[resource_id]
        _, path, sha = _instance_fields(instance)
        results.append(
            ResourceDrift(
                resource_id=resource_id,
                state="ADDED",
                baseline_path=None,
                current_path=path,
                baseline_content_sha256=None,
                current_content_sha256=sha,
            )
        )

    for resource_id in sorted(baseline_ids - current_ids):
        instance = baseline[resource_id]
        _, path, sha = _instance_fields(instance)
        results.append(
            ResourceDrift(
                resource_id=resource_id,
                state="REMOVED",
                baseline_path=path,
                current_path=None,
                baseline_content_sha256=sha,
                current_content_sha256=None,
            )
        )

    for resource_id in sorted(baseline_ids & current_ids):
        results.append(
            compare_instances(
                baseline[resource_id],
                current[resource_id],
            )
        )

    return results


def diff_paths(
    previous: Iterable[str],
    current: Iterable[str],
) -> dict[str, list[str]]:
    old = {str(value).replace("\\\\", "/") for value in previous}
    new = {str(value).replace("\\\\", "/") for value in current}

    return {
        "added": sorted(new - old),
        "removed": sorted(old - new),
        "unchanged": sorted(old & new),
    }


def resource_changed(old: Mapping, new: Mapping) -> bool:
    old_sha = old.get("content_sha256", old.get("sha256"))
    new_sha = new.get("content_sha256", new.get("sha256"))

    old_identity = old.get("resource_id", old.get("canonical_identity"))
    new_identity = new.get("resource_id", new.get("canonical_identity"))

    return old_sha != new_sha or old_identity != new_identity


def detect_orphans(
    manifest_paths: Iterable[str],
    actual_paths: Iterable[str],
) -> dict[str, list[str]]:
    return diff_paths(manifest_paths, actual_paths)
''',
    encoding="utf-8",
)

test.write_text(
'''import unittest

from tools.research_os_resource_drift import (
    RESOURCE_DRIFT_SCHEMA,
    compare_instances,
    compare_resource_sets,
)
from tools.research_os_resource_instance import ResourceInstance


def make(resource_id, path, content):
    return ResourceInstance.create(
        resource_id,
        path,
        content,
    )


class ResourceDriftTests(unittest.TestCase):

    def test_identical_instances_are_unchanged(self):
        baseline = make("R1", "tools/a.py", b"a")
        current = make("R1", "tools/a.py", b"a")

        result = compare_instances(baseline, current)

        self.assertEqual(result.state, "UNCHANGED")

    def test_content_change_is_detected(self):
        baseline = make("R1", "tools/a.py", b"a")
        current = make("R1", "tools/a.py", b"b")

        result = compare_instances(baseline, current)

        self.assertEqual(result.state, "CONTENT_DRIFT")

    def test_path_change_is_detected(self):
        baseline = make("R1", "tools/a.py", b"a")
        current = make("R1", "tools/b.py", b"a")

        result = compare_instances(baseline, current)

        self.assertEqual(result.state, "PATH_DRIFT")

    def test_resource_id_change_is_detected(self):
        baseline = make("R1", "tools/a.py", b"a")
        current = make("R2", "tools/a.py", b"a")

        result = compare_instances(baseline, current)

        self.assertEqual(result.state, "RESOURCE_ID_DRIFT")

    def test_added_resource_is_detected(self):
        result = compare_resource_sets(
            {},
            {"R1": make("R1", "tools/a.py", b"a")},
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].state, "ADDED")

    def test_removed_resource_is_detected(self):
        result = compare_resource_sets(
            {"R1": make("R1", "tools/a.py", b"a")},
            {},
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].state, "REMOVED")

    def test_results_are_deterministic(self):
        baseline = {
            "R2": make("R2", "tools/b.py", b"b"),
            "R1": make("R1", "tools/a.py", b"a"),
        }
        current = {
            "R1": make("R1", "tools/a.py", b"changed"),
            "R3": make("R3", "tools/c.py", b"c"),
        }

        first = compare_resource_sets(baseline, current)
        second = compare_resource_sets(baseline, current)

        self.assertEqual(first, second)
        self.assertEqual(
            [item.resource_id for item in first],
            ["R1", "R2", "R3"],
        )

    def test_schema_is_present(self):
        result = compare_instances(
            make("R1", "tools/a.py", b"a"),
            make("R1", "tools/a.py", b"a"),
        )

        self.assertEqual(
            result.to_dict()["schema"],
            RESOURCE_DRIFT_SCHEMA,
        )

    def test_missing_instance_fields_fail_closed(self):
        class Broken:
            def to_dict(self):
                return {"resource_id": "R1"}

        with self.assertRaises(ValueError):
            compare_instances(Broken(), Broken())


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

print("RESOURCE_DRIFT_HARDENED")
print("RESOURCE_DRIFT_TEST_CREATED")
print("M2_NOT_MODIFIED")
print("NO_COMMIT")
print("NO_PUSH")
