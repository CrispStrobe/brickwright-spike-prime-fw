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
        for expression, expected in (
            ("GPL-2.0-only", "forbidden license"),
            ("AGPL-3.0-only", "forbidden license"),
            ("LGPL-2.1-only", "forbidden license"),
            ("CC-BY-NC-4.0", "forbidden license"),
            ("ISC", "unknown or unadmitted license"),
        ):
            self.write_roots(expression)
            self.assertIn(expected, self.generate(ok=False).stderr)
        self.write_roots("MIT")
        evil = self.root / "evil.c"; evil.write_text("/* SPDX-License-Identifier: GPL-3.0-only */\n")
        self.dep.write_text(f"x: {evil}\n")
        self.assertIn("forbidden license", self.generate(ok=False).stderr)
        # A dual-licensed input is still refused: the declarer must record which
        # license was taken, not hand the gate the choice.
        evil.write_text("/* copyright block */\n" * 2000 + "/* SPDX-License-Identifier: MIT OR Apache-2.0 */\n")
        self.assertIn("dual-licensed expression must be resolved", self.generate(ok=False).stderr)

    def test_license_expressions_are_parsed_not_substring_matched(self):
        """The substring rule rejected an expression for NAMING its exception.

        The rest of this file is black-box on purpose.  check_license is a pure
        function and the cases below are cheap to state directly, so this one
        imports it rather than paying a subprocess per expression.
        """
        sys.path.insert(0, str(TOOL.parent))
        import source_closure as closure

        # Admitted: the GCC runtime pair this build links, and the newlib aggregate.
        closure.check_license("GPL-3.0-or-later WITH GCC-exception-3.1")
        closure.check_license("BSD-2-Clause AND BSD-3-Clause AND BSD-4-Clause-UC")
        closure.check_license("MIT")
        # Refused, each for its own reason.
        for expression, expected in (
            ("GPL-3.0-or-later", "forbidden license"),
            ("AGPL-3.0-or-later", "forbidden license"),
            ("GPL-3.0-or-later WITH Autoconf-exception-3.0", "exception that is not admitted"),
            ("MIT OR Apache-2.0", "dual-licensed"),
            ("(MIT AND BSD-2-Clause)", "parenthesised"),
            ("Nonsense-9.9", "unknown or unadmitted"),
            ("MIT AND GPL-2.0-only", "forbidden license"),
            ("MIT WITH Foo WITH Bar", "more than one WITH"),
        ):
            with self.assertRaises(SystemExit) as refusal:
                closure.check_license(expression)
            self.assertIn(expected, str(refusal.exception), expression)

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

    def test_vfork_child_before_parent_resume_and_removed_chdir(self):
        removed = self.root / "removed-build-directory"
        self.trace.write_text(
            f'3947728 chdir("{removed}") = 0\n'
            '3947728 vfork( <unfinished ...>\n'
            f'3948000 execve("{self.root}/main.c", ["main.c"], []) = 0\n'
            '3947728 <... vfork resumed>) = 3948000\n'
        )
        self.dep.write_text(f'x: {self.root}/main.c\n')
        self.generate()
        files = json.loads(self.manifest.read_text())["files"]
        self.assertEqual(["main.c"], [item["path"] for item in files])

    def test_fcntl_directory_descriptor_duplication(self):
        self.trace.write_text(
            f'3947728 openat(AT_FDCWD, "{self.root}", O_RDONLY|O_DIRECTORY) = 3\n'
            '3947728 fcntl(3, F_DUPFD_CLOEXEC, 10) = 10\n'
            '3947728 openat(10, "main.c", O_RDONLY) = 4\n'
        )
        self.dep.write_text(f'x: {self.root}/main.c\n')
        self.generate()

    def test_unfinished_dot_directory_open_supports_fchdir(self):
        self.trace.write_text(
            f'3947728 chdir("{self.root}") = 0\n'
            '3947728 openat(AT_FDCWD, ".", O_RDONLY|O_CLOEXEC <unfinished ...>\n'
            '3947728 <... openat resumed>) = 3\n'
            '3947728 chdir("removed") = 0\n'
            '3947728 fchdir(3) = 0\n'
            '3947728 openat(AT_FDCWD, "main.c", O_RDONLY) = 4\n'
        )
        self.dep.write_text(f'x: {self.root}/main.c\n')
        self.generate()

    def test_generated_and_directory_paths_are_not_source(self):
        output = self.root / "generated.o"
        output.write_bytes(b"generated")
        self.trace.write_text(
            f'3947728 openat(AT_FDCWD, "{self.root}", O_RDONLY|O_DIRECTORY) = 3\n'
            f'3947728 openat(AT_FDCWD, "{output}", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 4\n'
            f'3947728 openat(AT_FDCWD, "{output}", O_RDONLY) = 4\n'
            f'3947728 openat(AT_FDCWD, "{self.root}/main.c", O_RDONLY) = 4\n'
        )
        self.dep.write_text(f'x: {self.root}/main.c\n')
        self.generate()
        files = json.loads(self.manifest.read_text())["files"]
        self.assertEqual(["main.c"], [item["path"] for item in files])

    def test_rename_destination_inherits_the_source_proof(self):
        # CMake writes `X.tmpNNNN` with O_CREAT and renames it onto `X`. The
        # destination is a build product although it was never opened with a
        # creating flag; the protected build produced 84 such files, and the
        # audit reported every one as a path needing classification.
        product = self.root / "generated.cmake"
        temporary = self.root / "generated.cmake.tmp9f2"
        self.trace.write_text(
            f'11 openat(AT_FDCWD, "{temporary}", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 4\n'
            f'11 rename("{temporary}", "{product}") = 0\n'
            f'11 openat(AT_FDCWD, "{product}", O_RDONLY) = 4\n'
            f'11 openat(AT_FDCWD, "{self.root}/main.c", O_RDONLY) = 4\n'
        )
        self.dep.write_text(f"x: {self.root}/main.c\n")
        self.generate()
        files = json.loads(self.manifest.read_text())["files"]
        self.assertEqual(["main.c"], [item["path"] for item in files])

    def test_rename_cannot_launder_an_unproved_source(self):
        # The destination inherits the SOURCE'S proof and nothing more, so a
        # rename from a path the trace never proved generated leaves the
        # destination unproved and the closure still fails closed on it.
        source = self.root / "unproved.h"
        source.write_text("int y;\n")
        destination = self.root / "renamed.h"
        self.trace.write_text(
            f'11 rename("{source}", "{destination}") = 0\n'
            f'11 openat(AT_FDCWD, "{destination}", O_RDONLY) = 4\n'
            f'11 openat(AT_FDCWD, "{self.root}/main.c", O_RDONLY) = 4\n'
        )
        self.dep.write_text(f"x: {self.root}/main.c\n")
        result = self.generate(ok=False)
        self.assertIn("renamed.h", result.stderr)

    def test_descriptor_alias_is_not_a_source_file(self):
        # A shell process substitution hands `/dev/fd/63` to a child, which
        # opens it to read a pipe. That is consumption of a descriptor, never
        # of a source file, and it cannot be classified as either a generated
        # product or a required input.
        self.trace.write_text(
            f'11 openat(AT_FDCWD, "/dev/fd/63", O_RDONLY) = 4\n'
            f'11 openat(AT_FDCWD, "{self.root}/main.c", O_RDONLY) = 4\n'
        )
        self.dep.write_text(f"x: {self.root}/main.c\n")
        self.generate()
        files = json.loads(self.manifest.read_text())["files"]
        self.assertEqual(["main.c"], [item["path"] for item in files])

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
