from pathlib import Path

p = Path("tools/research_os_resource_manifest.py")
text = p.read_text(encoding="utf-8")

old = '''        if any(x.get("resource_id") == resource_id for x in self.resources):
            return
        self.resources.append(dict(resource))
'''

new = '''        candidate = dict(resource)

        for existing in self.resources:
            if existing.get("resource_id") != resource_id:
                continue

            if existing == candidate:
                return

            raise ValueError(
                f"RESOURCE_ID_COLLISION:{resource_id}"
            )

        self.resources.append(candidate)
'''

if old not in text:
    raise RuntimeError("MANIFEST_ADD_BLOCK_NOT_FOUND")

p.write_text(
    text.replace(old, new, 1),
    encoding="utf-8",
)

print("MANIFEST_COLLISION_HARDENED")
print("M2_NOT_MODIFIED")
