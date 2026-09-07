from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMPORTER = ROOT / "tools" / "import_ti_service_pack.py"


def synthetic_bts(*payloads: bytes) -> bytes:
    records = [struct.pack("<HH", index + 1, len(payload)) + payload for index, payload in enumerate(payloads)]
    return b"BTSB" + bytes(28) + b"".join(records)


class ImportTiServicePackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ti-import-test-")
        self.root = Path(self.temp.name)
        self.data = synthetic_bts(b"synthetic command", b"synthetic event")
        self.sha256 = hashlib.sha256(self.data).hexdigest()
        self.license_data = b"synthetic TI-like test licence; not TI material\n"
        self.license_sha256 = hashlib.sha256(self.license_data).hexdigest()
        self.license = self.root / "LICENSE"
        self.license.write_bytes(self.license_data)
        self.allowlist = self.root / "allowlist.json"
        self.allowlist.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "source": {
                        "repository": "https://invalid.example/test.git",
                        "commit": "0" * 40,
                        "bts_path": "initscripts/synthetic.bts",
                        "license_path": "LICENSE",
                        "license_sha256": self.license_sha256,
                    },
                    "files": {
                        self.sha256: {
                            "device": "TEST",
                            "rom": "0",
                            "service_pack": "synthetic",
                            "kind": "test-only",
                            "filename": "synthetic.bts",
                            "size": len(self.data),
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self.output = self.root / "output"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_import(self, source: Path, *, with_license: bool = True) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(IMPORTER),
            str(source),
            "--allowlist",
            str(self.allowlist),
            "--output-dir",
            str(self.output),
        ]
        if with_license:
            command.extend(["--license", str(self.license)])
        return subprocess.run(command, check=False, text=True, capture_output=True)

    def test_imports_allowlisted_file_without_changing_bytes(self) -> None:
        source = self.root / "synthetic.bts"
        source.write_bytes(self.data)
        result = self.run_import(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / "synthetic.bts").read_bytes(), self.data)
        generated = (self.output / "ti_bts_local_payload.h").read_text()
        self.assertIn(f"SHA-256: {self.sha256}", generated)
        encoded = bytes(
            int(token, 16)
            for token in re.findall(r"0x([0-9a-f]{2})", generated)
        )
        self.assertEqual(encoded, self.data)
        executable = self.root / "payload-test"
        compile_result = subprocess.run(
            [
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-DEXPECT_LOCAL_PAYLOAD=1", f"-I{self.output}",
                f"-I{ROOT / 'apps/btsensor'}",
                f"-I{ROOT / 'bluetooth/zephyr_compat/include'}",
                str(ROOT / "apps/btsensor/btsensor_ti_payload.c"),
                str(ROOT / "apps/btsensor/test/test_ti_payload.c"),
                "-o", str(executable),
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
        self.assertEqual(subprocess.run([executable], check=False).returncode, 0)
        manifest = json.loads((self.output / "import-manifest.json").read_text())
        self.assertEqual(manifest["sha256"], self.sha256)
        self.assertEqual(manifest["actions"], 2)
        self.assertEqual(manifest["licence"]["sha256"], self.license_sha256)
        self.assertEqual((self.output / "LICENSE.ti").read_bytes(), self.license_data)

    def test_finds_allowlisted_file_in_zip_without_extracting_archive(self) -> None:
        archive = self.root / "official-package.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("nested/ignored.bts", synthetic_bts(b"other"))
            output.writestr("nested/synthetic.bts", self.data)
        result = self.run_import(archive)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / "synthetic.bts").read_bytes(), self.data)

    def test_rejects_unknown_hash(self) -> None:
        source = self.root / "unknown.bts"
        source.write_bytes(synthetic_bts(b"not allowlisted"))
        result = self.run_import(source)
        self.assertEqual(result.returncode, 2)
        self.assertIn("no allowlisted BTS file", result.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_missing_accompanying_licence(self) -> None:
        source = self.root / "synthetic.bts"
        source.write_bytes(self.data)
        self.license.unlink()
        result = self.run_import(source, with_license=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("accompanying TI LICENSE was not found", result.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_wrong_accompanying_licence(self) -> None:
        source = self.root / "synthetic.bts"
        source.write_bytes(self.data)
        self.license.write_bytes(b"wrong licence")
        result = self.run_import(source)
        self.assertEqual(result.returncode, 2)
        self.assertIn("licence hash is not allowlisted", result.stderr)
        self.assertFalse(self.output.exists())

    def test_fetches_pinned_file_and_licence_from_git_source(self) -> None:
        repository = self.root / "official-source"
        (repository / "initscripts").mkdir(parents=True)
        (repository / "initscripts" / "synthetic.bts").write_bytes(self.data)
        (repository / "LICENSE").write_bytes(self.license_data)
        subprocess.run(["git", "init", "--quiet", repository], check=True)
        subprocess.run(["git", "-C", repository, "config", "user.email",
                        "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", repository, "config", "user.name",
                        "Synthetic Test"], check=True)
        subprocess.run(["git", "-C", repository, "add", "."], check=True)
        subprocess.run(["git", "-C", repository, "commit", "--quiet", "-m",
                        "fixture"], check=True)
        commit = subprocess.check_output(
            ["git", "-C", repository, "rev-parse", "HEAD"], text=True
        ).strip()
        document = json.loads(self.allowlist.read_text())
        document["source"]["repository"] = str(repository)
        document["source"]["commit"] = commit
        self.allowlist.write_text(json.dumps(document), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(IMPORTER), "--from-ti", "--allowlist",
             str(self.allowlist), "--output-dir", str(self.output)],
            check=False, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / "synthetic.bts").read_bytes(), self.data)
        self.assertEqual((self.output / "LICENSE.ti").read_bytes(), self.license_data)

    def test_rejects_truncated_allowlisted_container(self) -> None:
        malformed = b"BTSB" + bytes(28) + struct.pack("<HH", 1, 20) + b"short"
        malformed_hash = hashlib.sha256(malformed).hexdigest()
        document = json.loads(self.allowlist.read_text())
        document["files"] = {
            malformed_hash: {
                "device": "TEST",
                "rom": "0",
                "service_pack": "synthetic",
                "kind": "test-only",
                "filename": "synthetic.bts",
                "size": len(malformed),
            }
        }
        self.allowlist.write_text(json.dumps(document), encoding="utf-8")
        source = self.root / "synthetic.bts"
        source.write_bytes(malformed)
        result = self.run_import(source)
        self.assertEqual(result.returncode, 2)
        self.assertIn("truncated BTS action payload", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
