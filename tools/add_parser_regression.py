from pathlib import Path

p = Path("tools/test_research_os_resource_semantic_binding.py")

if not p.exists():
    raise RuntimeError("EXPECTED_EXISTING_TEST_FILE_NOT_FOUND")

text = p.read_text(encoding="utf-8")

test = r'''
    def test_python_type_annotation_is_not_resource_identity(self):
        from tools.research_os_resource_parser import declared_identities

        values = declared_identities(
            "tools/example.py",
            "resource_id: str\ncontract_id: str\n",
        )

        self.assertNotIn("str", values)
        self.assertIn("example", values)

'''

marker = "\nif __name__ == \"__main__\":"

if "test_python_type_annotation_is_not_resource_identity" not in text:
    if marker not in text:
        raise RuntimeError("TEST_MAIN_MARKER_NOT_FOUND")

    text = text.replace(marker, "\n" + test + marker, 1)
    p.write_text(text, encoding="utf-8")
    print("PARSER_REGRESSION_TEST_ADDED")
else:
    print("PARSER_REGRESSION_TEST_ALREADY_PRESENT")
