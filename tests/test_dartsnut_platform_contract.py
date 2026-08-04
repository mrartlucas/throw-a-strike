"""Contract inspector and committed-evidence tests (standard library only)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.inspect_pydartsnut_wheel import InspectionError, inspect_wheel, main, serialize

ROOT = Path(__file__).parents[1]
CONTRACT = ROOT / "docs/platform/evidence/pydartsnut-1.2.1-contract.json"
WHEEL_HASH = "a207168cf36ba04352d3710933e159a1311948363be18c4bbd81ce4ae5916f4f"
SDIST_HASH = "f3618dc311e77773f6e655b11cb448e94940c59af32ad060e77a9ed616583d8e"


def synthetic_wheel(directory: Path, *, name="pydartsnut", version="1.2.1", source=None) -> Path:
    source = source or '''class Dartsnut:\n    def __init__(self):\n        pass\n    def update_frame_buffer(self, frame):\n        return True\n'''
    path = directory / f"{name}-{version}-py3-none-any.whl"
    dist = f"{name}-{version}.dist-info"
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nRequires-Python: >=3.11\n\nDescription\n"
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr("pydartsnut/__init__.py", source)
        wheel.writestr(f"{dist}/METADATA", metadata)
        wheel.writestr(f"{dist}/RECORD", f"{dist}/METADATA,,\npydartsnut/__init__.py,,\n")
    return path


class InspectorTests(unittest.TestCase):
    def test_rejects_non_wheel_and_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "x.txt"; plain.write_text("x")
            with self.assertRaises(InspectionError): inspect_wheel(plain, "0" * 64)
            wheel = synthetic_wheel(Path(tmp))
            with self.assertRaisesRegex(InspectionError, "mismatch"): inspect_wheel(wheel, "0" * 64)

    def test_rejects_wrong_name_and_version(self):
        for kwargs, message in [({"name": "wrong"}, "name"), ({"version": "9.9"}, "version")]:
            with tempfile.TemporaryDirectory() as tmp:
                wheel = synthetic_wheel(Path(tmp), **kwargs); digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
                with self.assertRaisesRegex(InspectionError, message): inspect_wheel(wheel, digest)

    def test_ast_inventory_is_deterministic_and_has_ranges_hashes_and_record(self):
        marker = Path("/tmp/pydartsnut-wheel-code-must-not-run")
        marker.unlink(missing_ok=True)
        source = "from pathlib import Path\nPath('/tmp/pydartsnut-wheel-code-must-not-run').touch()\nclass Dartsnut:\n def ping(self, value=None): return value\n"
        with tempfile.TemporaryDirectory() as tmp:
            wheel = synthetic_wheel(Path(tmp), source=source); digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            first = inspect_wheel(wheel, digest); second = inspect_wheel(wheel, digest)
        self.assertEqual(first, second); self.assertFalse(marker.exists())
        self.assertIn("Dartsnut", [x["name"] for x in first["inspection"]["public_classes"]])
        method = next(x for x in first["inspection"]["public_methods"] if x["symbol"] == "Dartsnut.ping")
        self.assertGreaterEqual(method["line_end"], method["line_start"])
        self.assertRegex(first["package"]["source_files_inspected"][0]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["inspection"]["record_entries"], sorted(first["inspection"]["record_entries"]))

    def test_serialization_sorted_stable_and_single_newline(self):
        rendered = serialize({"z": [2, 1], "a": 1})
        self.assertTrue(rendered.startswith('{\n  "a"'))
        self.assertTrue(rendered.endswith("\n")); self.assertFalse(rendered.endswith("\n\n"))

    def test_output_check_and_ambiguous_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); wheel = synthetic_wheel(root)
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest(); output = root / "contract.json"
            self.assertEqual(main([str(wheel), "--expected-sha256", digest, "--output", str(output)]), 0)
            self.assertEqual(main([str(wheel), "--expected-sha256", digest, "--check", str(output)]), 0)
            data = json.loads(output.read_text())
            self.assertIsNone(data["main_display"]["encoded_width"])
            output.write_text(output.read_text() + " ")
            self.assertEqual(main([str(wheel), "--expected-sha256", digest, "--check", str(output)]), 1)


class CommittedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(CONTRACT.read_text())

    def test_exact_artifact_and_schema(self):
        self.assertEqual(self.data["schema_version"], 1)
        self.assertEqual((self.data["package"]["name"], self.data["package"]["version"]), ("pydartsnut", "1.2.1"))
        self.assertEqual(self.data["package"]["wheel_sha256"], WHEEL_HASH)
        self.assertEqual(self.data["package"]["sdist_sha256"], SDIST_HASH)

    def test_evidence_pointers_are_unique_and_complete(self):
        evidence = self.data["evidence"]; ids = [x["evidence_id"] for x in evidence]
        self.assertEqual(len(ids), len(set(ids)))
        for item in evidence:
            self.assertTrue(item["archive_path"]); self.assertGreaterEqual(item["line_start"], 1)
            self.assertGreaterEqual(item["line_end"], item["line_start"])
            if item["evidence_level"] == "VERIFIED_PACKAGE_SOURCE": self.assertRegex(item["source_sha256"], r"^[0-9a-f]{64}$")

    def test_unknowns_contradictions_and_secondary_are_conservative(self):
        self.assertTrue(all(x["current_status"] == "UNKNOWN_HARDWARE" for x in self.data["unknowns"]))
        self.assertTrue(all(x["resolution_status"] == "UNRESOLVED" for x in self.data["contradictions"]))
        secondary = self.data["secondary_display"]
        self.assertIn(secondary["status"], {"VERIFIED_PACKAGE_SOURCE", "NOT_FOUND_IN_INSPECTED_PACKAGE", "UNKNOWN_HARDWARE"})
        self.assertIn("does not prove", secondary["caveat"])

    def test_dependency_is_exactly_pinned(self):
        self.assertIn('"pydartsnut==1.2.1"', (ROOT / "pyproject.toml").read_text())
        lock = (ROOT / "uv.lock").read_text()
        self.assertIn(f"sha256:{WHEEL_HASH}", lock); self.assertIn(f"sha256:{SDIST_HASH}", lock)

    def test_markdown_references_existing_evidence_and_all_blockers(self):
        document = (ROOT / "docs/platform/DARTSNUT_PLATFORM_CONTRACT.md").read_text()
        ids = {x["evidence_id"] for x in self.data["evidence"]}
        import re
        self.assertLessEqual(set(re.findall(r"E\d{3}", document)), ids)
        for item in self.data["contradictions"]: self.assertIn(item["contradiction_id"], document)
        for item in self.data["unknowns"]:
            if item["blocks_adapter"] or item["blocks_rendering"] or item["blocks_multiplayer"]: self.assertIn(item["unknown_id"], document)
        self.assertIn(WHEEL_HASH, document); self.assertIn("pydartsnut==1.2.1", document)

    def test_checklist_has_required_categories_and_blanks(self):
        sheet = (ROOT / "docs/platform/DARTSNUT_CABINET_VERIFICATION_CHECKLIST.md").read_text().lower()
        for phrase in ["solid-color", "channel-order", "native-width", "native-height", "corner", "x-axis", "y-axis", "center coordinate", "nine-zone", "twelve dart", "repeated insertion", "duplicate blocking", "re-arm", "simultaneous", "every named button", "debounce", "home", "reserved", "brightness", "display busy", "update-rate", "shutdown", "data-store", "secondary-screen", "audio", "emulator"]:
            self.assertIn(phrase, sheet)
        self.assertIn("actual observation: __________________", sheet)


if __name__ == "__main__":
    unittest.main()
