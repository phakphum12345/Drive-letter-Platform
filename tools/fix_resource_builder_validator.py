from pathlib import Path

path = Path("tools/validate_resource_builder_contract.py")
text = path.read_text(encoding="utf-8")

anchor = 'ROOT = Path(".")'

replacement = '''ROOT = Path(__file__).resolve().parent.parent
'''

if anchor not in text:
    raise RuntimeError("VALIDATOR_ROOT_ANCHOR_NOT_FOUND")

text = text.replace(anchor, replacement, 1)

path.write_text(
    text,
    encoding="utf-8",
    newline="\\n",
)

print("VALIDATOR_ROOT_FIXED")
