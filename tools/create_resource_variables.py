from pathlib import Path

p = Path("tools/research_os_resource_variables.py")

p.write_text(
'''from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping

RESOURCE_VARIABLE_SCHEMA = "RESEARCH_OS_RESOURCE_VARIABLE_V1"

VALID_TYPES = frozenset({
    "STRING",
    "INTEGER",
    "NUMBER",
    "BOOLEAN",
    "PATH",
    "IDENTITY",
    "RESOURCE_ID",
    "JSON",
})


@dataclass(frozen=True)
class ResourceVariable:
    name: str
    type: str
    value: Any = None
    source: str = "declared"
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("RESOURCE_VARIABLE_NAME_REQUIRED")
    return value


def normalize_type(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in VALID_TYPES:
        raise ValueError(
            f"INVALID_RESOURCE_VARIABLE_TYPE:{value}"
        )
    return normalized


def create_variable(
    name: str,
    variable_type: str,
    value: Any = None,
    source: str = "declared",
    required: bool = False,
) -> ResourceVariable:
    name = normalize_name(name)
    variable_type = normalize_type(variable_type)

    if required and value is None:
        raise ValueError(
            f"REQUIRED_RESOURCE_VARIABLE_MISSING:{name}"
        )

    return ResourceVariable(
        name=name,
        type=variable_type,
        value=value,
        source=source.strip() or "declared",
        required=bool(required),
    )


def variables_from_mapping(
    values: Mapping[str, Mapping[str, Any]],
) -> list[ResourceVariable]:
    result = []

    for name, definition in values.items():
        if not isinstance(definition, Mapping):
            raise ValueError(
                f"INVALID_RESOURCE_VARIABLE:{name}"
            )

        result.append(
            create_variable(
                name,
                str(definition.get("type", "STRING")),
                definition.get("value"),
                str(definition.get("source", "declared")),
                bool(definition.get("required", False)),
            )
        )

    return validate_variables(result)


def validate_variables(
    variables: list[ResourceVariable],
) -> list[ResourceVariable]:
    seen = set()

    for variable in variables:
        if variable.name in seen:
            raise ValueError(
                f"DUPLICATE_RESOURCE_VARIABLE:{variable.name}"
            )

        seen.add(variable.name)

        if variable.type not in VALID_TYPES:
            raise ValueError(
                f"INVALID_RESOURCE_VARIABLE_TYPE:{variable.type}"
            )

        if variable.required and variable.value is None:
            raise ValueError(
                f"REQUIRED_RESOURCE_VARIABLE_MISSING:{variable.name}"
            )

    return sorted(variables, key=lambda x: x.name)


def variable_dict(
    variable: ResourceVariable,
) -> dict[str, Any]:
    return variable.to_dict()
''',
    encoding="utf-8",
)

print("RESOURCE_VARIABLE_MODULE_CREATED")


t = Path("tools/test_research_os_resource_variables.py")

t.write_text(
'''import unittest

from tools.research_os_resource_variables import (
    RESOURCE_VARIABLE_SCHEMA,
    create_variable,
    validate_variables,
    variables_from_mapping,
)


class ResourceVariableTests(unittest.TestCase):

    def test_create_variable(self):
        value = create_variable(
            "API_PORT",
            "integer",
            8787,
        )
        self.assertEqual(value.type, "INTEGER")
        self.assertEqual(value.value, 8787)

    def test_required_missing_fails_closed(self):
        with self.assertRaises(ValueError):
            create_variable(
                "API_PORT",
                "INTEGER",
                required=True,
            )

    def test_invalid_type_fails_closed(self):
        with self.assertRaises(ValueError):
            create_variable(
                "X",
                "INVALID",
            )

    def test_duplicate_names_fail_closed(self):
        values = [
            create_variable("X", "STRING", "a"),
            create_variable("X", "STRING", "b"),
        ]

        with self.assertRaises(ValueError):
            validate_variables(values)

    def test_mapping_is_deterministic(self):
        values = {
            "Z": {"type": "STRING", "value": "z"},
            "A": {"type": "PATH", "value": "a"},
        }

        a = variables_from_mapping(values)
        b = variables_from_mapping(
            dict(reversed(list(values.items())))
        )

        self.assertEqual(a, b)
        self.assertEqual(
            [x.name for x in a],
            ["A", "Z"],
        )

    def test_schema_exists(self):
        self.assertTrue(
            RESOURCE_VARIABLE_SCHEMA.endswith("_V1")
        )


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

print("RESOURCE_VARIABLE_TESTS_CREATED")
