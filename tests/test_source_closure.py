# SPDX-License-Identifier: Apache-2.0
"""Black-box tests for tools/source_closure.py."""
from __future__ import annotations
import hashlib, json, subprocess, sys, tempfile, unittest
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
        (self.root / "build.mk").write_text("# build input\n")
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
            '3948000 fcntl(3</fixture>, F_DUPFD_CLOEXEC, 0) = 5\n'
            '3948000 close(5</fixture>) = 0\n'
            '3948000 openat(AT_FDCWD</fixture>, "main.c", O_RDONLY) = 4\n'
            '3948000 close(4</fixture/main.c>) = 0\n'
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

    def test_capture_depfiles_use_recorded_cwd_and_exclude_proved_generated(self):
        sub = self.root / "sub"; sub.mkdir(); generated = sub / "generated.h"
        generated.write_text("generated\n")
        capture = self.base / "capture"; (capture / "compiles").mkdir(parents=True)
        depfile = capture / "one.d"; depfile.write_text("one.o: ../main.c generated.h\n")
        (capture / "compiles/one.json").write_text(json.dumps({"cwd": str(sub), "depfile": str(depfile)}))
        trace = self.base / "generated.trace"
        trace.write_text(f'1 openat(AT_FDCWD, "{generated}", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 3\n')
        self.invoke("generate", "--roots", self.roots, "--cwd", self.base,
                    "--strace", trace, "--capture", capture,
                    "--output", self.manifest, "--sbom", self.sbom)
        self.assertEqual(["main.c"], [x["path"] for x in json.loads(self.manifest.read_text())["files"]])

    def test_repository_trace_adds_build_inputs_but_not_host_tools(self):
        trace = self.base / "build.trace"
        trace.write_text(
            f'1 openat(AT_FDCWD, "{self.root / "build.mk"}", O_RDONLY) = 3\n'
            '1 openat(AT_FDCWD, "/usr/bin/make", O_RDONLY) = 4\n'
        )
        self.invoke(
            "generate", "--roots", self.roots, "--cwd", self.base,
            "--repository", self.base, "--repository-trace", trace,
            "--depfile", self.dep, "--output", self.manifest,
            "--sbom", self.sbom,
        )
        self.assertEqual(
            ["build.mk", "header.h", "main.c"],
            [item["path"] for item in json.loads(self.manifest.read_text())["files"]],
        )

    def test_stat_only_unlinked_license_is_not_source_content(self):
        unused = self.root / "unused.c"
        unused.write_text("/* SPDX-License-Identifier: OAR */\n")
        trace = self.base / "metadata.trace"
        trace.write_text(
            f'1 newfstatat(AT_FDCWD, "{unused}", '
            '{st_mode=S_IFREG|0644}, 0) = 0\n'
            f'1 stat("{unused}", {{st_mode=S_IFREG|0644}}) = 0\n'
            f'1 statx(AT_FDCWD, "{unused}", 0, STATX_MODE, '
            '{stx_mode=S_IFREG|0644}) = 0\n'
            f'1 access("{unused}", F_OK) = 0\n'
        )
        self.invoke(
            "generate", "--roots", self.roots, "--cwd", self.base,
            "--repository", self.base, "--repository-trace", trace,
            "--depfile", self.dep, "--output", self.manifest,
            "--sbom", self.sbom,
        )
        self.assertNotIn(
            "unused.c",
            [item["path"] for item in json.loads(self.manifest.read_text())["files"]],
        )

    def test_opened_or_depfile_input_still_enforces_license(self):
        consumed = self.root / "consumed.c"
        consumed.write_text("/* SPDX-License-Identifier: OAR */\n")
        for mode in ("open", "depfile"):
            trace = self.base / f"{mode}.trace"
            trace.write_text(
                f'1 openat(AT_FDCWD, "{consumed}", O_RDONLY) = 3\n'
                if mode == "open" else ""
            )
            depfile = self.base / f"{mode}.d"
            depfile.write_text(f"x: {consumed}\n" if mode == "depfile" else "x:\n")
            result = self.invoke(
                "generate", "--roots", self.roots, "--cwd", self.base,
                "--repository", self.base, "--repository-trace", trace,
                "--depfile", depfile, "--output", self.manifest,
                "--sbom", self.sbom, ok=False,
            )
            self.assertIn("unknown, compound, or forbidden license expression: OAR", result.stderr)

    def test_capture_proved_compiler_output_is_not_source(self):
        obj = self.root / "main.o"
        obj.write_bytes(b"object")
        trace = self.base / "build.trace"
        trace.write_text(f'1 openat(AT_FDCWD, "{obj}", O_RDONLY) = 3\n')
        capture = self.base / "capture"
        (capture / "compiles").mkdir(parents=True)
        (capture / "compiles/one.json").write_text(json.dumps({
            "cwd": str(self.root), "output": "main.o",
            "output_sha256": hashlib.sha256(b"object").hexdigest(),
        }))
        self.invoke(
            "generate", "--roots", self.roots, "--cwd", self.base,
            "--repository", self.base, "--repository-trace", trace,
            "--capture", capture, "--depfile", self.dep,
            "--output", self.manifest, "--sbom", self.sbom,
        )
        self.assertNotIn(
            "main.o",
            [item["path"] for item in json.loads(self.manifest.read_text())["files"]],
        )

    def test_unverifiable_capture_output_cannot_hide_consumed_file(self):
        for case in ("mismatch", "missing"):
            with self.subTest(case=case):
                obj = self.root / f"{case}.o"
                if case == "mismatch":
                    obj.write_bytes(b"current")
                trace = self.base / f"{case}.trace"
                trace.write_text(f'1 openat(AT_FDCWD, "{obj}", O_RDONLY) = 3\n')
                capture = self.base / f"capture-{case}"
                (capture / "compiles").mkdir(parents=True)
                (capture / "compiles/one.json").write_text(json.dumps({
                    "cwd": str(self.root), "output": obj.name,
                    "output_sha256": hashlib.sha256(b"recorded").hexdigest(),
                }))
                result = self.invoke(
                    "generate", "--roots", self.roots, "--cwd", self.base,
                    "--repository", self.base, "--repository-trace", trace,
                    "--capture", capture, "--depfile", self.dep,
                    "--output", self.manifest, "--sbom", self.sbom, ok=False,
                )
                self.assertRegex(result.stderr, "consumed file is missing|file absent from declared origin")

    def test_dangling_symlink_metadata_is_not_source_consumption(self):
        link = self.root / "optional"
        link.symlink_to("missing-target")
        trace = self.base / "symlink.trace"
        trace.write_text(
            f'1 newfstatat(AT_FDCWD, "{link}", '
            '{st_mode=S_IFLNK|0777}, AT_SYMLINK_NOFOLLOW) = 0\n'
        )
        self.dep.write_text(f"main.o: {self.root}/main.c\n")
        self.invoke(
            "generate", "--roots", self.roots, "--cwd", self.base,
            "--strace", trace, "--depfile", self.dep,
            "--output", self.manifest, "--sbom", self.sbom,
        )
        self.assertEqual(
            ["main.c"],
            [item["path"] for item in json.loads(self.manifest.read_text())["files"]],
        )

    def test_removed_object_reachable_through_archive_member_is_retained(self):
        capture=self.base/"capture"; (capture/"compiles").mkdir(parents=True)
        dep=capture/"gone.d"; dep.write_text(f"gone.o: {self.root}/main.c\n")
        (capture/"compiles/gone.json").write_text(json.dumps({"cwd":str(self.base),"depfile":str(dep),"output":"gone.o"}))
        trace=self.base/"empty.trace"; trace.write_text("")
        archive=self.base/"libfirmware.a"; archive.write_bytes(b"archive")
        import hashlib
        (capture/"archives").mkdir(); (capture/"archives/a.json").write_text(json.dumps({"cwd":str(self.base),
            "argv":["rcs","libfirmware.a","gone.o"],"output_sha256":hashlib.sha256(b"archive").hexdigest()}))
        mapfile=self.base/"firmware.map"; mapfile.write_text(f"{archive}(gone.o)\n")
        self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,
                    "--capture",capture,"--map",mapfile,"--output",self.manifest,"--sbom",self.sbom)
        self.assertIn("main.c",[x["path"] for x in json.loads(self.manifest.read_text())["files"]])

    def test_incremental_archive_updates_retain_earlier_member_source(self):
        capture = self.base / "capture"
        (capture / "compiles").mkdir(parents=True)
        (capture / "archives").mkdir()
        archive = self.base / "libapps.a"; archive.write_bytes(b"final")
        staged_archive = self.base / "staging" / "libapps.a"
        staged_archive.parent.mkdir()
        staged_archive.write_bytes(b"final")
        for name, source in (("first.o", "main.c"), ("second.o", "header.h")):
            object_path = self.base / name
            object_path.write_bytes(name.encode())
            dep = capture / f"{name}.d"
            dep.write_text(f"{name}: {self.root / source}\n")
            (capture / "compiles" / f"{name}.json").write_text(json.dumps({
                "cwd": str(self.base), "depfile": str(dep), "output": name,
                "output_sha256": hashlib.sha256(name.encode()).hexdigest(),
            }))
        (self.base / "second_1.o").write_bytes(b"second.o")
        (capture / "archives/first.json").write_text(json.dumps({
            "cwd": str(self.base), "argv": ["rcs", "libapps.a", "first.o"],
            "output": str(archive), "output_sha256": hashlib.sha256(b"partial").hexdigest(),
        }))
        (capture / "archives/second.json").write_text(json.dumps({
            "cwd": str(self.base), "argv": ["rcs", "libapps.a", "second_1.o"],
            "output": str(archive), "output_sha256": hashlib.sha256(b"final").hexdigest(),
        }))
        mapfile = self.base / "firmware.map"
        mapfile.write_text(
            f"{staged_archive}(first.o)\n{staged_archive}(second_1.o)\n"
        )
        trace = self.base / "empty.trace"; trace.write_text("")
        self.invoke(
            "generate", "--roots", self.roots, "--cwd", self.base,
            "--strace", trace, "--capture", capture, "--map", mapfile,
            "--output", self.manifest, "--sbom", self.sbom,
        )
        self.assertEqual(
            ["header.h", "main.c"],
            [item["path"] for item in json.loads(self.manifest.read_text())["files"]],
        )

    def test_compiler_evidence_is_mandatory(self):
        result = self.invoke("generate", "--roots", self.roots, "--cwd", self.base,
                             "--strace", self.trace, "--output", self.manifest,
                             "--sbom", self.sbom, ok=False)
        self.assertIn("compiler evidence requires", result.stderr)

    def test_explicit_generated_input_requires_hash_and_generator(self):
        generated = self.base / "generated.h"; generated.write_text("generated\n")
        self.dep.write_text(f"main.o: {self.root}/main.c {generated}\n")
        declaration = self.base / "generated.json"
        import hashlib
        relative=generated.relative_to(self.base).as_posix()
        declaration.write_text(json.dumps({"schema":"brickwright/generated-build-inputs/v1","files":[{
            "path":relative, "sha256":hashlib.sha256(generated.read_bytes()).hexdigest(), "generator_argv":["fixture"]}]}))
        self.generate("--repository",self.base,"--generated", declaration.name)
        data=json.loads(self.manifest.read_text()); self.assertEqual(relative,data["generated_inputs"][0]["path"])
        self.assertIn("generated/"+relative,[x["fileName"] for x in json.loads(self.sbom.read_text())["files"]])
        generated.write_text("drift\n")
        self.assertIn("hash mismatch", self.generate("--repository",self.base,"--generated", declaration.name, ok=False).stderr)

    def test_external_boundary_is_exact_and_not_vendored(self):
        external = self.base / "toolchain"; external.mkdir(); header=external / "stdint.h"; header.write_text("tool\n")
        import hashlib
        lock=self.base/"lock"; lock.write_text("lock\n")
        declaration=self.base/"external.json"; declaration.write_text(json.dumps({"schema":"brickwright/external-build-inputs/v1",
          "boundary":"arm-toolchain","lock":{"path":"lock","sha256":hashlib.sha256(lock.read_bytes()).hexdigest()},"files":[{"path":"stdint.h","sha256":hashlib.sha256(header.read_bytes()).hexdigest()}]}))
        self.dep.write_text(f"main.o: {self.root}/main.c {external}/stdint.h\n")
        self.generate("--repository",self.base,"--external",declaration.name,"--external-root",f"arm-toolchain={external}"); data=json.loads(self.manifest.read_text())
        self.assertEqual(["header.h","main.c"],[x["path"] for x in data["files"]]); self.assertEqual("stdint.h",data["external_inputs"][0]["path"])
        header.write_text("drift\n")
        self.assertIn("external-input hash mismatch",self.generate("--repository",self.base,"--external",declaration.name,"--external-root",f"arm-toolchain={external}",ok=False).stderr)

    def test_external_lock_and_generated_generator_fail_closed(self):
        generated=self.base/"generated.h"; generated.write_text("x")
        import hashlib
        declaration=self.base/"generated.json"; declaration.write_text(json.dumps({"schema":"brickwright/generated-build-inputs/v1","files":[{"path":"generated.h","sha256":hashlib.sha256(b"x").hexdigest()}]}))
        self.dep.write_text(f"x.o: {generated}\n")
        self.assertIn("lacks generator",self.generate("--repository",self.base,"--generated",declaration.name,ok=False).stderr)
        external=self.base/"external"; external.mkdir(); (external/"h").write_text("h")
        declaration.write_text(json.dumps({"schema":"brickwright/external-build-inputs/v1","boundary":"host-tool","lock":{"path":"../escape","sha256":"0"*64},"files":[]}))
        self.assertIn("lock escapes",self.generate("--repository",self.base,"--external",declaration.name,"--external-root",f"host-tool={external}",ok=False).stderr)

    def test_forbidden_and_unknown_licenses_rejected(self):
        for expression in ("GPL-2.0-only", "AGPL-3.0-only", "LGPL-2.1-only", "CC-BY-NC-4.0", "ISC"):
            self.write_roots(expression)
            self.assertIn("unknown, compound, or forbidden license", self.generate(ok=False).stderr)
        self.write_roots("MIT")
        evil = self.root / "evil.c"; evil.write_text("/* SPDX-License-Identifier: GPL-3.0-only */\n")
        self.dep.write_text(f"x: {evil}\n")
        self.assertIn("unknown, compound, or forbidden license", self.generate(ok=False).stderr)
        evil.write_text("/* copyright block */\n" * 2000 + "/* SPDX-License-Identifier: MIT OR Apache-2.0 */\n")
        self.write_roots("BSD-3-Clause")
        self.assertIn("unknown, compound, or forbidden license", self.generate(ok=False).stderr)

    def test_bsd_2_clause_is_allowed_as_permissive(self):
        self.write_roots("BSD-2-Clause")
        self.generate()
        manifest = json.loads(self.manifest.read_text())
        self.assertIn("BSD-2-Clause", manifest["allowed_licenses"])
        header = next(item for item in manifest["files"] if item["path"] == "header.h")
        self.assertEqual("BSD-2-Clause", header["license"])

    def test_deprecated_freebsd_identifier_is_allowed_and_preserved(self):
        self.write_roots("BSD-2-Clause-FreeBSD")
        self.generate()
        manifest = json.loads(self.manifest.read_text())
        header = next(item for item in manifest["files"] if item["path"] == "header.h")
        self.assertEqual("BSD-2-Clause-FreeBSD", header["license"])
        sbom = json.loads(self.sbom.read_text())
        sbom_header = next(item for item in sbom["files"]
                           if item["fileName"] == "nuttx/header.h")
        self.assertEqual(["BSD-2-Clause-FreeBSD"], sbom_header["licenseInfoInFiles"])

    def test_missing_escape_and_escaping_symlink_rejected(self):
        self.dep.write_text(f"x: {self.root}/missing.h\n")
        self.assertIn("missing", self.generate(ok=False).stderr)
        outside = self.base / "outside.c"; outside.write_text("x")
        self.dep.write_text(f"x: {outside}\n")
        self.assertIn("escapes declared", self.generate(ok=False).stderr)
        link = self.root / "link.c"; link.symlink_to(outside)
        self.dep.write_text(f"x: {link}\n")
        self.assertIn("escapes declared source roots", self.generate(ok=False).stderr)

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

    def test_opened_directory_is_not_source_content(self):
        stat_trace = self.base / "directory-stat.trace"
        stat_trace.write_text(
            f'1 newfstatat(AT_FDCWD, "{self.root}", '
            '{st_mode=S_IFDIR|0755}, 0) = 0\n'
        )
        open_trace = self.base / "directory-open.trace"
        open_trace.write_text(
            f'1 openat(AT_FDCWD, "{self.root}", O_RDONLY) = 3\n'
        )
        self.invoke(
            "generate", "--roots", self.roots, "--cwd", self.base,
            "--repository", self.base,
            "--repository-trace", stat_trace,
            "--repository-trace", open_trace,
            "--depfile", self.dep, "--output", self.manifest,
            "--sbom", self.sbom,
        )
        self.assertEqual(
            ["header.h", "main.c"],
            [item["path"] for item in json.loads(self.manifest.read_text())["files"]],
        )

    def test_opened_directory_symlink_is_not_silently_dropped(self):
        directory = self.root / "directory"; directory.mkdir()
        link = self.root / "directory-link"; link.symlink_to(directory)
        trace = self.base / "directory-link.trace"
        trace.write_text(f'1 openat(AT_FDCWD, "{link}", O_RDONLY) = 3\n')
        result = self.invoke(
            "generate", "--roots", self.roots, "--cwd", self.base,
            "--repository", self.base, "--repository-trace", trace,
            "--depfile", self.dep, "--output", self.manifest,
            "--sbom", self.sbom, ok=False,
        )
        self.assertIn("consumed path is not a file", result.stderr)

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

    def test_required_spdx_accepts_block_comment_interior(self):
        nested = self.root / "vendor"; nested.mkdir()
        (nested / "LICENSE").write_text("Apache License, Version 2.0\n")
        source = nested / "source.c"
        source.write_text("/*\n * SPDX-License-Identifier: Apache-2.0\n */\nint x;\n")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "vendor"], check=True)
        document = json.loads(self.roots.read_text())
        document["roots"][0]["commit"] = subprocess.check_output(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True,
        ).strip()
        document["roots"][0]["license_overrides"] = [{
            "path": "vendor", "license": "Apache-2.0", "require_spdx": True,
        }]
        self.roots.write_text(json.dumps(document))
        self.dep.write_text(f"x: {source}\n")
        self.generate()

    def test_required_spdx_rejects_prose_and_near_miss(self):
        nested = self.root / "vendor"; nested.mkdir()
        (nested / "LICENSE").write_text("Apache License, Version 2.0\n")
        source = nested / "source.c"
        document = json.loads(self.roots.read_text())
        document["roots"][0]["license_overrides"] = [{
            "path": "vendor", "license": "Apache-2.0", "require_spdx": True,
        }]
        self.roots.write_text(json.dumps(document))
        self.dep.write_text(f"x: {source}\n")
        for text in (
            "SPDX-License-Identifier: Apache-2.0\n",
            "/*\n * SPDX-License-Identifer: Apache-2.0\n */\n",
        ):
            source.write_text(text)
            self.assertIn("SPDX identifier required", self.generate(ok=False).stderr)

    def test_alternate_license_concludes_declared_root_choice(self):
        source = self.root / "dual.c"
        source.write_text("/* SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later */\n")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "dual"], check=True)
        document = json.loads(self.roots.read_text())
        document["roots"][0]["commit"] = subprocess.check_output(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True,
        ).strip()
        document["roots"][0]["license"] = "Apache-2.0"
        self.roots.write_text(json.dumps(document))
        self.dep.write_text(f"x: {source}\n")
        self.generate()
        entry = json.loads(self.manifest.read_text())["files"][0]
        self.assertEqual("Apache-2.0", entry["license"])
        self.assertEqual("Apache-2.0 OR GPL-2.0-or-later", entry["declared_license"])
        sbom_entry = json.loads(self.sbom.read_text())["files"][0]
        self.assertEqual("Apache-2.0", sbom_entry["licenseConcluded"])
        self.assertEqual(["Apache-2.0 OR GPL-2.0-or-later"], sbom_entry["licenseInfoInFiles"])

    def test_compound_license_selection_fails_closed(self):
        cases = {
            "and.c": "Apache-2.0 AND MIT",
            "parenthesized.c": "(Apache-2.0 OR GPL-2.0-or-later)",
            "no_allowed.c": "GPL-2.0-or-later OR OAR",
            "ambiguous.c": "MIT OR BSD-3-Clause",
        }
        for name, expression in cases.items():
            (self.root / name).write_text(f"/* SPDX-License-Identifier: {expression} */\n")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "compounds"], check=True)
        document = json.loads(self.roots.read_text())
        document["roots"][0]["commit"] = subprocess.check_output(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True,
        ).strip()
        document["roots"][0]["license"] = "Apache-2.0"
        self.roots.write_text(json.dumps(document))
        for name in cases:
            self.dep.write_text(f"x: {self.root / name}\n")
            self.assertIn(
                "unknown, compound, or forbidden license expression",
                self.generate(ok=False).stderr,
            )

    def test_exact_nuttx_search_public_domain_override_is_preserved(self):
        include = self.root / "include"; include.mkdir()
        source = include / "search.h"
        source.write_text(
            "/*\n * SPDX-License-Identifier: LicenseRef-NuttX-PublicDomain\n"
            " * Written by J.T. Conklin <jtc@netbsd.org>\n * Public domain.\n */\n"
        )
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "search"], check=True)
        document = json.loads(self.roots.read_text())
        document["roots"][0]["commit"] = subprocess.check_output(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True,
        ).strip()
        document["roots"][0]["license_overrides"] = [{
            "path": "include/search.h",
            "license": "LicenseRef-NuttX-PublicDomain",
            "require_spdx": True,
        }]
        self.roots.write_text(json.dumps(document))
        self.dep.write_text(f"x: {source}\n")
        self.generate()
        entry = next(item for item in json.loads(self.manifest.read_text())["files"]
                     if item["path"] == "include/search.h")
        self.assertEqual("LicenseRef-NuttX-PublicDomain", entry["license"])
        sbom = json.loads(self.sbom.read_text())
        notice = "Written by J.T. Conklin <jtc@netbsd.org>\nPublic domain."
        sbom_file = next(item for item in sbom["files"]
                         if item["fileName"] == "nuttx/include/search.h")
        self.assertEqual(notice, sbom_file["copyrightText"])
        self.assertEqual("LicenseRef-NuttX-PublicDomain",
                         sbom["hasExtractedLicensingInfos"][0]["licenseId"])
        self.assertEqual(notice, sbom["hasExtractedLicensingInfos"][0]["extractedText"])

    def test_public_domain_reference_outside_exact_override_fails(self):
        source = self.root / "other.h"
        source.write_text("/* SPDX-License-Identifier: LicenseRef-NuttX-PublicDomain */\n")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "other"], check=True)
        document = json.loads(self.roots.read_text())
        document["roots"][0]["commit"] = subprocess.check_output(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True,
        ).strip()
        self.roots.write_text(json.dumps(document))
        self.dep.write_text(f"x: {source}\n")
        self.assertIn("unknown, compound, or forbidden license expression",
                      self.generate(ok=False).stderr)

    def test_exact_public_domain_override_rejects_notice_drift(self):
        include = self.root / "include"; include.mkdir()
        source = include / "search.h"
        source.write_text(
            "/*\n * SPDX-License-Identifier: LicenseRef-NuttX-PublicDomain\n"
            " * Public domain.\n */\n"
        )
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "search"], check=True)
        document = json.loads(self.roots.read_text())
        document["roots"][0]["commit"] = subprocess.check_output(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True,
        ).strip()
        document["roots"][0]["license_overrides"] = [{
            "path": "include/search.h",
            "license": "LicenseRef-NuttX-PublicDomain",
            "require_spdx": True,
        }]
        self.roots.write_text(json.dumps(document))
        self.dep.write_text(f"x: {source}\n")
        self.assertIn("reviewed license notice mismatch", self.generate(ok=False).stderr)

    def test_public_domain_reference_cannot_be_overridden_elsewhere(self):
        document = json.loads(self.roots.read_text())
        document["roots"][0]["license_overrides"] = [{
            "path": "other.h", "license": "LicenseRef-NuttX-PublicDomain",
            "require_spdx": True,
        }]
        self.roots.write_text(json.dumps(document))
        self.assertIn("unknown, compound, or forbidden license expression",
                      self.generate(ok=False).stderr)

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
