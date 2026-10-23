from pathlib import Path
import subprocess
import sys

ROOT = Path(r"E:\ResearchOS_Main")
FILES = {
    "tools/research_os_resource_parser.py": """from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

IDENTITY_FIELDS = ("contract", "contract_id", "capability_id", "component_id", "resource_id")
VALUE_RE = re.compile(
    r'''^\\s*(?:contract|contract_id|capability_id|component_id|resource_id)\\s*:\\s*(?:"([^"]+)"|'([^']+)'|([^#\\s]+))\\s*(?:#.*)?$''',
    re.IGNORECASE | re.MULTILINE,
)

def normalize_path(value: str) -> str:
    return value.replace("\\\\", "/").strip()

def normalize_identity(value: str) -> str:
    return value.strip().strip('"').strip("'").lower()

def parse_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None

def declared_identities(path: str, text: str) -> set[str]:
    values = {Path(path).stem.lower()}
    obj = parse_json(text)
    if obj:
        for field in IDENTITY_FIELDS:
            value = obj.get(field)
            if isinstance(value, str) and value.strip():
                values.add(normalize_identity(value))
    for match in VALUE_RE.finditer(text):
        value = next((x for x in match.groups() if x is not None), None)
        if value:
            values.add(normalize_identity(value))
    return values

def structured_bindings(text: str) -> dict[str, Any] | None:
    obj = parse_json(text)
    if not obj:
        return None
    for key in ("bindings", "semantic_bindings", "relationships"):
        value = obj.get(key)
        if isinstance(value, dict):
            return value
    return None
""",

    "tools/research_os_identity_registry.py": """from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib
from typing import Iterable

@dataclass(frozen=True)
class ResourceIdentity:
    resource_id: str
    kind: str
    path: str
    canonical_identity: str

def make_resource_id(kind: str, identity: str) -> str:
    key = f"{kind.upper()}:{identity.strip().lower()}".encode()
    return hashlib.sha256(key).hexdigest()[:24]

def identity_for(kind: str, path: str, identity: str | None = None) -> ResourceIdentity:
    canonical = (identity or path).strip().lower()
    return ResourceIdentity(
        make_resource_id(kind, canonical),
        kind.upper(),
        path.replace("\\\\", "/"),
        canonical,
    )

def index(resources: Iterable[ResourceIdentity]) -> dict[str, ResourceIdentity]:
    result = {}
    for resource in resources:
        previous = result.get(resource.resource_id)
        if previous is not None and previous != resource:
            raise ValueError(f"RESOURCE_ID_COLLISION:{resource.resource_id}")
        result[resource.resource_id] = resource
    return result

def to_dict(resource: ResourceIdentity) -> dict:
    return asdict(resource)
""",

    "tools/research_os_relationship_registry.py": """from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable

MULTI_RELATIONS = frozenset({"VERIFIED_BY", "SUPPORTED_BY"})
SINGLE_RELATIONS = frozenset({"BOUND_TO", "ENFORCED_BY", "DISPATCHED_BY"})
RELATIONS = MULTI_RELATIONS | SINGLE_RELATIONS

@dataclass(frozen=True)
class Relationship:
    source: str
    relation: str
    target: str
    tier: str | None = None
    evidence: str | None = None

def validate_relationships(items: Iterable[Relationship]) -> list[Relationship]:
    rows = list(items)
    for item in rows:
        if item.relation not in RELATIONS:
            raise ValueError(f"INVALID_RELATION:{item.relation}")
    for item in rows:
        if item.relation in SINGLE_RELATIONS:
            targets = {
                x.target for x in rows
                if x.source == item.source and x.relation == item.relation
            }
            if len(targets) > 1:
                raise ValueError(f"AMBIGUOUS_BINDING:{item.source}:{item.relation}")
    return sorted(rows, key=lambda x: (x.source, x.relation, x.target))

def relationship_dict(item: Relationship) -> dict:
    return asdict(item)
""",

    "tools/research_os_code_identity.py": """from __future__ import annotations
import ast
from pathlib import Path
from typing import Any

def extract_python_identities(path: str, text: str) -> dict[str, Any]:
    tree = ast.parse(text, filename=path)
    constants = {}
    symbols = []
    calls = []
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    constants[target.id] = node.value.value
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")

    return {
        "path": Path(path).as_posix(),
        "constants": constants,
        "symbols": sorted(set(symbols)),
        "calls": sorted(set(calls)),
        "imports": sorted(set(imports)),
    }
""",

    "tools/research_os_code_discovery.py": """from __future__ import annotations
from pathlib import Path
from tools.research_os_code_identity import extract_python_identities

CODE_SUFFIXES = frozenset({
    ".py", ".ps1", ".sh", ".dart", ".js", ".ts", ".cs", ".cpp", ".h"
})

def discover_code(root: Path) -> list[str]:
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in CODE_SUFFIXES
        and ".git" not in p.parts
    )

def inspect_python(root: Path, paths: list[str]) -> list[dict]:
    result = []
    for relative in paths:
        path = root / relative
        if path.suffix.lower() == ".py":
            result.append(
                extract_python_identities(
                    relative,
                    path.read_text(encoding="utf-8"),
                )
            )
    return result
""",

    "tools/research_os_resource_manifest.py": """from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable
import hashlib
import json

@dataclass
class ResourceManifest:
    schema: str = "RESEARCH_OS_RESOURCE_MANIFEST_V1"
    source_sha256: str = ""
    resources: list[dict[str, Any]] = field(default_factory=list)

    def add(self, resource: dict[str, Any]) -> None:
        resource_id = resource.get("resource_id")
        if not resource_id:
            raise ValueError("resource_id required")
        if any(x.get("resource_id") == resource_id for x in self.resources):
            return
        self.resources.append(dict(resource))

    def canonical(self) -> str:
        payload = asdict(self)
        payload["resources"] = sorted(
            payload["resources"],
            key=lambda x: (
                x.get("kind", ""),
                x.get("path", ""),
                x.get("resource_id", ""),
            ),
        )
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()

def build_manifest(
    source_sha256: str,
    resources: Iterable[dict[str, Any]],
) -> ResourceManifest:
    manifest = ResourceManifest(source_sha256=source_sha256)
    for resource in resources:
        manifest.add(resource)
    return manifest
""",

    "tools/research_os_resource_drift.py": """from __future__ import annotations
from typing import Iterable

def diff_paths(previous: Iterable[str], current: Iterable[str]) -> dict[str, list[str]]:
    old = set(previous)
    new = set(current)
    return {
        "added": sorted(new - old),
        "removed": sorted(old - new),
        "unchanged": sorted(old & new),
    }

def resource_changed(old: dict, new: dict) -> bool:
    return (
        old.get("sha256") != new.get("sha256")
        or old.get("canonical_identity") != new.get("canonical_identity")
    )

def detect_orphans(
    manifest_paths: Iterable[str],
    actual_paths: Iterable[str],
) -> dict[str, list[str]]:
    return diff_paths(manifest_paths, actual_paths)
""",

    "tools/research_os_resource_builder.py": """from __future__ import annotations
from pathlib import Path
from typing import Any
from tools.research_os_code_discovery import discover_code
from tools.research_os_identity_registry import identity_for
from tools.research_os_resource_manifest import ResourceManifest
from tools.research_os_resource_parser import declared_identities

class ResourceBuilder:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def discover(self) -> list[dict[str, Any]]:
        resources = []
        for relative in discover_code(self.root):
            path = self.root / relative
            text = path.read_text(encoding="utf-8", errors="ignore")
            name = Path(relative).name
            kind = (
                "TEST"
                if relative.startswith("tests/")
                or name.startswith("test_")
                else "IMPLEMENTATION"
            )
            identities = declared_identities(relative, text)
            identity = sorted(identities)[0] if identities else relative
            resource = identity_for(kind, relative, identity)
            resources.append({
                "resource_id": resource.resource_id,
                "kind": resource.kind,
                "path": resource.path,
                "canonical_identity": resource.canonical_identity,
            })
        return resources

    def build(self, existing: ResourceManifest | None = None) -> ResourceManifest:
        manifest = existing or ResourceManifest()
        for resource in self.discover():
            manifest.add(resource)
        return manifest

def build_resources(
    root: str | Path,
    existing: ResourceManifest | None = None,
) -> ResourceManifest:
    return ResourceBuilder(Path(root)).build(existing)
""",

    "tools/research_os_semantic_binding.py": """from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence
from tools.research_os_resource_parser import (
    declared_identities,
    normalize_path,
    structured_bindings,
)

SEMANTIC_ASSURANCE_RELATIONS = frozenset({
    "VERIFIED_BY",
    "SUPPORTED_BY",
    "BOUND_TO",
    "ENFORCED_BY",
    "DISPATCHED_BY",
})

MULTI_CARDINALITY_RELATIONS = frozenset({
    "VERIFIED_BY",
    "SUPPORTED_BY",
})

SINGLE_CARDINALITY_RELATIONS = frozenset({
    "BOUND_TO",
    "ENFORCED_BY",
    "DISPATCHED_BY",
})

@dataclass(frozen=True)
class BindingResult:
    relation: str
    targets: tuple[str, ...]
    tier: str | None
    ambiguous: bool
    unresolved: bool
    candidates: tuple[str, ...]
    evidence: tuple[str, ...] = ()

def _explicit_path(target: str, candidate: str, text: str) -> bool:
    binding = structured_bindings(text) or {}
    paths = binding.get("paths", [])
    if isinstance(paths, str):
        paths = [paths]
    normalized = {normalize_path(str(x)) for x in paths}
    return normalize_path(candidate) in normalized

def _explicit_reference(target: str, text: str) -> bool:
    target = normalize_path(target)
    normalized = normalize_path(text)
    return target in normalized or Path(target).name in normalized

def _semantic(target: str, candidate: str, texts: Mapping[str, str]) -> bool:
    target_ids = declared_identities(target, texts.get(target, ""))
    candidate_ids = declared_identities(candidate, texts.get(candidate, ""))
    overlap = {
        value for value in target_ids & candidate_ids
        if value and value != Path(target).stem.lower()
    }
    return bool(overlap)

def resolve_semantic_binding(
    *,
    target: str,
    relation: str,
    candidates: Sequence[str],
    texts: Mapping[str, str],
) -> BindingResult:
    if relation not in SEMANTIC_ASSURANCE_RELATIONS:
        raise ValueError(f"INVALID_RELATION:{relation}")

    normalized_target = normalize_path(target)
    candidates = tuple(sorted({
        normalize_path(value)
        for value in candidates
        if normalize_path(value) != normalized_target
    }))

    tiers: list[tuple[str, list[str]]] = []

    explicit_paths = [
        value for value in candidates
        if _explicit_path(target, value, texts.get(target, ""))
    ]
    if explicit_paths:
        tiers.append(("EXPLICIT_PATH", explicit_paths))

    explicit_refs = [
        value for value in candidates
        if _explicit_reference(target, texts.get(value, ""))
    ]
    if explicit_refs:
        tiers.append(("EXPLICIT_CONTRACT_REFERENCE", explicit_refs))

    semantic = [
        value for value in candidates
        if _semantic(target, value, texts)
    ]
    if semantic:
        tiers.append(("UNIQUE_SEMANTIC_IDENTITY", semantic))

    if not tiers:
        return BindingResult(
            relation, (), None, False, True, candidates
        )

    tier, winners = tiers[0]

    if (
        relation in SINGLE_CARDINALITY_RELATIONS
        and len(winners) != 1
    ):
        return BindingResult(
            relation, (), tier, True, False, tuple(winners)
        )

    return BindingResult(
        relation,
        tuple(winners),
        tier,
        False,
        False,
        tuple(winners),
        tuple(winners),
    )
""",

    "tools/test_research_os_resource_platform.py": """import tempfile
import unittest
from pathlib import Path

from tools.research_os_code_identity import extract_python_identities
from tools.research_os_identity_registry import identity_for
from tools.research_os_resource_builder import build_resources
from tools.research_os_resource_drift import diff_paths
from tools.research_os_resource_manifest import ResourceManifest
from tools.research_os_resource_parser import declared_identities
from tools.research_os_relationship_registry import Relationship, validate_relationships
from tools.research_os_semantic_binding import resolve_semantic_binding

class ResourcePlatformTests(unittest.TestCase):
    def test_parser_quote_variants(self):
        text = (
            'contract_id: "CANONICAL_X"\\n'
            "capability_id: 'CAP_X'\\n"
            "component_id: COMP_X\\n"
        )
        identities = declared_identities("unrelated.py", text)
        self.assertIn("canonical_x", identities)
        self.assertIn("cap_x", identities)
        self.assertIn("comp_x", identities)

    def test_identity_deterministic(self):
        self.assertEqual(
            identity_for("contract", "a", "X"),
            identity_for("other", "b", "X"),
        )

    def test_builder_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text(
                'CONTRACT_ID="X"\\n',
                encoding="utf-8",
            )
            first = build_resources(root)
            second = build_resources(root, first)
            self.assertEqual(first.canonical(), second.canonical())

    def test_python_ast(self):
        result = extract_python_identities("x.py", 'VALUE="ABC"\\n')
        self.assertEqual(result["constants"]["VALUE"], "ABC")

    def test_single_relation_fail_closed(self):
        rows = [
            Relationship("C", "BOUND_TO", "A"),
            Relationship("C", "BOUND_TO", "B"),
        ]
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_BINDING"):
            validate_relationships(rows)

    def test_semantic_ambiguity(self):
        texts = {
            "c.json": '{"contract_id":"X"}',
            "a.py": 'CONTRACT_ID="X"',
            "b.py": 'CONTRACT_ID="X"',
        }
        result = resolve_semantic_binding(
            target="c.json",
            relation="ENFORCED_BY",
            candidates=["a.py", "b.py"],
            texts=texts,
        )
        self.assertTrue(result.ambiguous)

    def test_explicit_reference_priority(self):
        texts = {
            "c.json": '{"contract_id":"X"}',
            "a.py": 'CONTRACT_ID="X"',
            "b.py": 'uses c.json',
        }
        result = resolve_semantic_binding(
            target="c.json",
            relation="ENFORCED_BY",
            candidates=["a.py", "b.py"],
            texts=texts,
        )
        self.assertEqual(result.tier, "EXPLICIT_CONTRACT_REFERENCE")
        self.assertEqual(result.targets, ("b.py",))

    def test_drift(self):
        result = diff_paths(["a", "b"], ["b", "c"])
        self.assertEqual(result["added"], ["c"])

if __name__ == "__main__":
    unittest.main()
"""
}

for rel, content in FILES.items():
    path = ROOT / rel
    if path.exists():
        print("REFUSE_OVERWRITE", rel)
        raise SystemExit(2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    print("CREATED", rel)

print("\n=== VALIDATE AST / COMPILE ===")
for rel in FILES:
    path = ROOT / rel
    subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        check=True,
    )
print("PY_COMPILE=OK")

print("\n=== IMPORT SMOKE ===")
subprocess.run(
    [
        sys.executable,
        "-c",
        "import tools.research_os_resource_parser;"
        "import tools.research_os_identity_registry;"
        "import tools.research_os_relationship_registry;"
        "import tools.research_os_code_identity;"
        "import tools.research_os_code_discovery;"
        "import tools.research_os_resource_manifest;"
        "import tools.research_os_resource_drift;"
        "import tools.research_os_resource_builder;"
        "import tools.research_os_semantic_binding;"
    ],
    check=True,
)
print("IMPORT=OK")

print("\n=== RESOURCE PLATFORM TESTS ===")
subprocess.run(
    [
        sys.executable,
        "-m",
        "unittest",
        "tools.test_research_os_resource_platform",
        "-v",
    ],
    cwd=ROOT,
    check=True,
)
print("\nRESOURCE PLATFORM = PASS")
print("M2 has NOT been modified.")
print("No commit / push / merge performed.")
