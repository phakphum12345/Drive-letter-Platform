from pathlib import Path

p = Path("tools/research_os_resource_parser.py")
text = p.read_text(encoding="utf-8")

old = '''    for match in VALUE_RE.finditer(text):
        value = next((x for x in match.groups() if x is not None), None)
        if value:
            values.add(normalize_identity(value))

    return values
'''

new = '''    # YAML-style identity declarations are only valid for
    # YAML/YML resources. Never apply this grammar to Python,
    # PowerShell, Dart, JS, or other programming languages because
    # constructs such as `resource_id: str` are type annotations,
    # not resource identities.
    suffix = Path(path).suffix.lower()

    if suffix in {".yaml", ".yml"}:
        for match in VALUE_RE.finditer(text):
            value = next(
                (x for x in match.groups() if x is not None),
                None,
            )
            if value:
                values.add(normalize_identity(value))

    return values
'''

if old not in text:
    raise RuntimeError("PARSER_IDENTITY_BLOCK_NOT_FOUND")

p.write_text(
    text.replace(old, new, 1),
    encoding="utf-8",
)

print("PARSER_FALSE_POSITIVE_GUARD_ADDED")
print("CODE_FILES_NO_LONGER_USE_YAML_IDENTITY_REGEX")
print("M2_NOT_MODIFIED")
