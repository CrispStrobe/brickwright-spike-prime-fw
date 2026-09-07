# SPDX-License-Identifier: Apache-2.0
"""Black-box tests for tools/source_closure.py."""
from __future__ import annotations
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools/source_closure.py"

class ClosureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = Path(self.temp.name)
        self.root = self.base / "upstream"; self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Test"], check=True)
        (self.root / "main.c").write_text("/* SPDX-License-Identifier: Apache-2.0 */\nint main(void) { return 0; }\n")
        (self.root / "header.h").write_text("#define ANSWER 42\n")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "fixture"], check=True)
        self.commit = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        self.roots = self.base / "roots.json"; self.write_roots("MIT")
        self.dep = self.base / "main.d"; self.dep.write_text(f"main.o: {self.root}/main.c {self.root}/header.h\n")
        self.trace = self.base / "trace"; self.trace.write_text(
            f'3947728 chdir("{self.root}") = 0\n'
            '3947728 openat(AT_FDCWD, ".", O_RDONLY|O_DIRECTORY) = 3\n'
            '3947728 clone(child_stack=NULL, flags=SIGCHLD) = 3948000\n'
            '3948000 fchdir(3) = 0\n'
            '3948000 openat(AT_FDCWD, "main.c", O_RDONLY) = 4\n'
            '3948000 newfstatat(3, "header.h",  <unfinished ...>\n'
            '3947728 access("header.h", F_OK) = 0\n'
            '3948000 <... newfstatat resumed>{st_mode=S_IFREG}, 0) = 0\n'
            f'3948000 execve("{self.root}/main.c", ["main.c"], []) = 0\n'
            '3948000 readlinkat(3, "header.h", "x", 1) = 1\n'
            f'3947728 openat(AT_FDCWD, "{self.root}/ignored.c", O_RDONLY) = -1 ENOENT\n')
        self.manifest = self.base / "manifest.json"; self.sbom = self.base / "sbom.json"

    def tearDown(self): self.temp.cleanup()
    def write_roots(self, license):
        self.roots.write_text(json.dumps({"schema": 1, "roots": [{"name": "nuttx", "path": str(self.root),
            "repository": "https://example.invalid/nuttx", "commit": self.commit,
            "license": license, "role": "kernel"}]}) + "\n")
    def invoke(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(TOOL), *map(str,args)], text=True, capture_output=True)
        if ok and result.returncode: self.fail(result.stderr)
        if not ok and not result.returncode: self.fail("command unexpectedly passed")
        return result
    def generate(self, *extra, ok=True):
        return self.invoke("generate", "--roots", self.roots, "--cwd", self.base,
                        "--strace", self.trace, "--depfile", self.dep,
                        "--output", self.manifest, "--sbom", self.sbom, *extra, ok=ok)

    def test_deterministic_manifest_sbom_and_link_evidence(self):
        obj = self.base / "main.o"; obj.write_bytes(b"object")
        mapfile = self.base / "firmware.map"; mapfile.write_text("LOAD main.o\n")
        evidence = self.base / "evidence.json"
        self.generate("--map", mapfile, "--object", obj, "--evidence", evidence)
        first = (self.manifest.read_bytes(), self.sbom.read_bytes(), evidence.read_bytes())
        self.generate("--map", mapfile, "--object", obj, "--evidence", evidence)
        self.assertEqual(first, (self.manifest.read_bytes(), self.sbom.read_bytes(), evidence.read_bytes()))
        manifest = json.loads(first[0]); self.assertEqual(2, len(manifest["files"]))
        self.assertTrue(all(item["origin"].get("blob") for item in manifest["files"]))
        self.assertEqual("SPDX-2.3", json.loads(first[1])["spdxVersion"])
        linked = json.loads(first[2])["objects"][0]
        self.assertTrue(linked["mentioned_in_map"]); self.assertEqual(["nuttx/header.h", "nuttx/main.c"], linked["sources"])
        self.invoke("verify", "--roots", self.roots, "--cwd", self.base,
                 "--strace", self.trace, "--depfile", self.dep, "--manifest", self.manifest)

    def test_forbidden_and_unknown_licenses_rejected(self):
        for expression in ("GPL-2.0-only", "AGPL-3.0-only", "LGPL-2.1-only", "CC-BY-NC-4.0", "ISC"):
            self.write_roots(expression)
            self.assertIn("unknown, compound, or forbidden license", self.generate(ok=False).stderr)
        self.write_roots("MIT")
        evil = self.root / "evil.c"; evil.write_text("/* SPDX-License-Identifier: GPL-3.0-only */\n")
        self.dep.write_text(f"x: {evil}\n")
        self.assertIn("unknown, compound, or forbidden license", self.generate(ok=False).stderr)
        evil.write_text("/* copyright block */\n" * 2000 + "/* SPDX-License-Identifier: MIT OR Apache-2.0 */\n")
        self.assertIn("unknown, compound, or forbidden license", self.generate(ok=False).stderr)

    def test_missing_escape_and_escaping_symlink_rejected(self):
        self.dep.write_text(f"x: {self.root}/missing.h\n")
        self.assertIn("missing", self.generate(ok=False).stderr)
        outside = self.base / "outside.c"; outside.write_text("x")
        self.dep.write_text(f"x: {outside}\n")
        self.assertIn("escapes declared", self.generate(ok=False).stderr)
        link = self.root / "link.c"; link.symlink_to(outside)
        self.dep.write_text(f"x: {link}\n")
        self.assertIn("symlink escapes", self.generate(ok=False).stderr)

    def test_hash_mismatch_and_unmanifested_file_rejected(self):
        self.generate(); (self.root / "main.c").write_text("changed\n")
        result = self.invoke("verify", "--roots", self.roots, "--cwd", self.base,
                          "--strace", self.trace, "--depfile", self.dep,
                          "--manifest", self.manifest, ok=False)
        self.assertIn("current bytes differ from declared origin blob", result.stderr)
        subprocess.run(["git", "-C", str(self.root), "checkout", "--", "main.c"], check=True)
        new = self.root / "new.c"; new.write_text("/* SPDX-License-Identifier: MIT */\n")
        self.dep.write_text(self.dep.read_text().strip() + f" {new}\n")
        result = self.invoke("verify", "--roots", self.roots, "--cwd", self.base,
                          "--strace", self.trace, "--depfile", self.dep,
                          "--manifest", self.manifest, ok=False)
        self.assertIn("unmanifested", result.stderr)

    def test_manifest_origin_and_role_are_verified(self):
        self.generate(); data = json.loads(self.manifest.read_text())
        data["files"][0]["origin"]["repository"] = "https://attacker.invalid/replaced"
        self.manifest.write_text(json.dumps(data))
        result = self.invoke("verify", "--roots", self.roots, "--cwd", self.base,
                             "--strace", self.trace, "--depfile", self.dep,
                             "--manifest", self.manifest, ok=False)
        self.assertIn("origin mismatch", result.stderr)

    def test_unresolved_relative_pid_and_fchdir_are_rejected(self):
        self.trace.write_text('3948000 openat(AT_FDCWD, "main.c", O_RDONLY) = 3\n')
        # The first observed PID legitimately inherits the explicitly supplied
        # initial cwd, so make a second, uninherited PID the ambiguous one.
        self.trace.write_text(self.trace.read_text() + '3948001 openat(AT_FDCWD, "main.c", O_RDONLY) = 3\n')
        self.assertIn("has no inherited cwd state", self.generate(ok=False).stderr)
        self.trace.write_text('3947728 fchdir(9) = 0\n')
        self.assertIn("successful fchdir has unresolved fd", self.generate(ok=False).stderr)
        self.trace.write_text('3947728 openat(9, "main.c", O_RDONLY) = 4\n')
        self.assertIn("unresolved dirfd 9", self.generate(ok=False).stderr)

    def test_nested_license_boundary_requires_override(self):
        nested = self.root / "vendor"; nested.mkdir()
        (nested / "LICENSE").write_text("different terms\n")
        source = nested / "source.c"; source.write_text("int x;\n")
        self.dep.write_text(f"x: {source}\n")
        self.assertIn("nested license boundary lacks an override", self.generate(ok=False).stderr)

    def test_same_basename_objects_are_not_joined_ambiguously(self):
        first = self.base / "one"; second = self.base / "two"
        first.mkdir(); second.mkdir()
        (first / "same.o").write_bytes(b"one"); (second / "same.o").write_bytes(b"two")
        mapfile = self.base / "firmware.map"; mapfile.write_text("LOAD same.o\n")
        result = self.generate("--map", mapfile, "--object", first / "same.o",
                               "--object", second / "same.o", "--evidence", self.base / "evidence.json",
                               ok=False)
        self.assertIn("ambiguous basename-only map object", result.stderr)

if __name__ == "__main__": unittest.main()
