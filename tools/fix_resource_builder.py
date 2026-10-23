from pathlib import Path

path = Path("tools/research_os_resource_builder.py")
text = path.read_text(encoding="utf-8")

lines = text.splitlines()

for i, line in enumerate(lines):
    if "explicit = sorted(" in line:
        lines[i:i+1] = [
            "            explicit = sorted(",
            "                value",
            "                for value in identities",
            "                if value != Path(relative).stem.lower()",
            "            )",
            "            identity = explicit[0] if explicit else relative",
        ]
        break
else:
    raise RuntimeError("BROKEN_BUILDER_ANCHOR_NOT_FOUND")

path.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8",
    newline="\n",
)

print("RESOURCE_BUILDER_FIXED")
