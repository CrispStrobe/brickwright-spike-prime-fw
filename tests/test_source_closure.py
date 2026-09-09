# SPDX-License-Identifier: Apache-2.0
"""Black-box tests for tools/source_closure.py."""
from __future__ import annotations
import argparse, hashlib, json, runpy, subprocess, sys, tempfile, unittest
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

    def test_trace_cache_returns_defensive_copies_and_observes_replacement(self):
        module=runpy.run_path(str(TOOL)); cached=module["cached_trace_paths"]
        arguments=argparse.Namespace(); first,_=cached(arguments,self.trace,self.base); expected=set(first); first.clear()
        second,_=cached(arguments,self.trace,self.base); self.assertEqual(expected,second)
        self.trace.write_text(f'1 openat(AT_FDCWD, "{self.root / "build.mk"}", O_RDONLY) = 3\n')
        third,_=cached(arguments,self.trace,self.base); self.assertEqual({self.root/"build.mk"},third)

    def test_child_create_before_resumed_vfork_is_deferred_and_excluded(self):
        product=self.root/"temporary.ddc"; product.write_bytes(b"generated")
        trace=self.base/"vfork-create.trace"; trace.write_text(
            f'1 chdir("{self.root}") = 0\n'
            '1 openat(AT_FDCWD, ".", O_RDONLY|O_DIRECTORY) = 5\n'
            '1 vfork( <unfinished ...>\n'
            '2 openat(5, "temporary.ddc", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 3\n'
            '1 <... vfork resumed>) = 2\n'
            '2 openat(AT_FDCWD, "temporary.ddc", O_RDONLY) = 4\n'
            '2 unlink("temporary.ddc") = 0\n'
        )
        self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,"--depfile",self.dep,"--output",self.manifest,"--sbom",self.sbom)
        self.assertNotIn("temporary.ddc",[item["path"] for item in json.loads(self.manifest.read_text())["files"]])

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

    def test_repository_tool_root_excludes_only_repository_trace(self):
        tools=self.base/".local/toolchain"; tools.mkdir(parents=True); executable=tools/"compiler"; executable.write_bytes(b"host tool")
        trace=self.base/"tool.trace"; trace.write_text(f'1 openat(AT_FDCWD, "{executable}", O_RDONLY) = 3\n')
        arguments=("--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--repository-tool-root",f"toolchain={tools}","--depfile",self.dep,"--output",self.manifest,"--sbom",self.sbom)
        self.invoke("generate",*arguments,"--repository-trace",trace)
        report=json.loads(self.manifest.read_text()); self.assertEqual([{"label":"toolchain","path":".local/toolchain","count":1,"scope":"repository-trace-only"}],report["repository_tool_roots"]); self.assertNotIn(str(self.base),self.manifest.read_text())
        self.assertIn("escapes declared",self.invoke("generate",*arguments,"--strace",trace,ok=False).stderr)
        dep=self.base/"tool.d"; dep.write_text(f'x: {self.root / "main.c"} {executable}\n')
        self.assertIn("escapes declared",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--repository-tool-root",f"toolchain={tools}","--repository-trace",trace,"--depfile",dep,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)

    def test_repository_tool_root_rejects_missing_escape_overlap_and_duplicates(self):
        valid=self.base/"tools"; valid.mkdir(); outside=self.base.parent
        common=("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--repository-trace",self.trace,"--depfile",self.dep,"--output",self.manifest,"--sbom",self.sbom)
        self.assertIn("missing",self.invoke(*common,"--repository-tool-root","missing=absent",ok=False).stderr)
        self.assertIn("strictly beneath",self.invoke(*common,"--repository-tool-root",f"outside={outside}",ok=False).stderr)
        self.assertIn("overlaps declared",self.invoke(*common,"--repository-tool-root",f"source={self.root}",ok=False).stderr)
        self.assertIn("duplicate",self.invoke(*common,"--repository-tool-root",f"same={valid}","--repository-tool-root",f"same={valid}",ok=False).stderr)

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
        archive=self.base/"libfirmware.a"; archive.write_bytes(b"archive")
        trace=self.base/"empty.trace"; trace.write_text(
            f'1 openat(AT_FDCWD, "{archive}", O_RDONLY) = 3\n'
        )
        import hashlib
        (capture/"archives").mkdir(); (capture/"archives/a.json").write_text(json.dumps({"cwd":str(self.base),
            "argv":["rcs","libfirmware.a","gone.o"],"output":"libfirmware.a","output_sha256":hashlib.sha256(b"archive").hexdigest()}))
        mapfile=self.base/"firmware.map"; mapfile.write_text(f"{archive}(gone.o)\n")
        self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,
                    "--capture",capture,"--map",mapfile,"--output",self.manifest,"--sbom",self.sbom)
        self.assertIn("main.c",[x["path"] for x in json.loads(self.manifest.read_text())["files"]])

    def test_opened_archive_without_mapped_producer_is_not_excluded(self):
        archive=self.base/"unproved.a"; archive.write_bytes(b"archive")
        trace=self.base/"archive.trace"; trace.write_text(
            f'1 openat(AT_FDCWD, "{archive}", O_RDONLY) = 3\n'
        )
        self.assertIn("escapes declared source roots", self.invoke(
            "generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,
            "--depfile",self.dep,"--output",self.manifest,"--sbom",self.sbom,
            ok=False).stderr)

    def test_stale_linked_archive_producer_is_rejected(self):
        capture=self.base/"capture"; (capture/"compiles").mkdir(parents=True); (capture/"archives").mkdir()
        obj=self.base/"one.o"; obj.write_bytes(b"object")
        dep=capture/"one.d"; dep.write_text(f"one.o: {self.root}/main.c\n")
        (capture/"compiles/one.json").write_text(json.dumps({"cwd":str(self.base),"depfile":str(dep),"output":"one.o","output_sha256":hashlib.sha256(b"object").hexdigest()}))
        producer=self.base/"producer.a"; producer.write_bytes(b"stale")
        mapped=self.base/"mapped.a"; mapped.write_bytes(b"final")
        (capture/"archives/a.json").write_text(json.dumps({"cwd":str(self.base),"argv":["rcs","producer.a","one.o"],"output":"producer.a","output_sha256":hashlib.sha256(b"final").hexdigest()}))
        mapfile=self.base/"map"; mapfile.write_text(f"{mapped}(one.o)\n")
        trace=self.base/"empty"; trace.write_text("")
        self.assertIn("missing or stale",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,"--capture",capture,"--map",mapfile,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)

    def test_mapped_archive_without_captured_producer_is_rejected(self):
        capture=self.base/"capture"; (capture/"compiles").mkdir(parents=True); (capture/"archives").mkdir()
        archive=self.base/"mapped.a"; archive.write_bytes(b"archive")
        mapfile=self.base/"map"; mapfile.write_text(f"{archive}(one.o)\n")
        trace=self.base/"empty"; trace.write_text("")
        self.assertIn("no unique recorded final producer",self.invoke(
            "generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,
            "--capture",capture,"--map",mapfile,"--repository",self.base,
            "--output",self.manifest,
            "--sbom",self.sbom,ok=False).stderr)

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

    def test_only_exact_root_git_administration_is_excluded(self):
        github=self.root/".github"; github.write_text("ordinary\n"); gitignore=self.root/".gitignore"; gitignore.write_text("ordinary\n"); subprocess.run(["git","-C",self.root,"add","."],check=True); subprocess.run(["git","-C",self.root,"commit","-qm","dotfiles"],check=True); self.commit=subprocess.check_output(["git","-C",self.root,"rev-parse","HEAD"],text=True).strip(); self.write_roots("MIT")
        trace=self.base/"git.trace"; trace.write_text(f'1 openat(AT_FDCWD, "{self.root}/.git", O_RDONLY) = 3\n1 openat(AT_FDCWD, "{self.root}/.git/config", O_RDONLY) = 4\n1 openat(AT_FDCWD, "{github}", O_RDONLY) = 5\n1 openat(AT_FDCWD, "{gitignore}", O_RDONLY) = 6\n'); self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,"--depfile",self.dep,"--output",self.manifest,"--sbom",self.sbom); data=json.loads(self.manifest.read_text()); audit=data["vcs_administration"][0]; self.assertEqual(("directory",2),(audit["kind"],audit["count"])); serialized=json.dumps(data); self.assertNotIn(str(self.base),serialized); self.assertNotIn("worktrees",serialized); self.assertNotIn("modules",serialized); self.assertNotIn(".git/config",serialized); self.assertTrue({".github",".gitignore"}.issubset({x["path"] for x in data["files"]}))
        nested=self.root/"src/.git"; nested.mkdir(parents=True); trace.write_text(f'1 openat(AT_FDCWD, "{nested}", O_RDONLY) = 3\n'); self.assertIn("not a file",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,"--depfile",self.dep,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)

    def test_capture_relocation_replays_only_old_repository_prefix(self):
        old=self.base.parent/"captured-old"; trace=self.base/"relocated.trace"; dep=self.base/"relocated.d"; trace.write_text(f'1 openat(AT_FDCWD, "{old}/upstream/main.c", O_RDONLY) = 3\n'); dep.write_text(f'x: {old}/upstream/header.h\n')
        self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--captured-repository-root",old,"--strace",trace,"--depfile",dep,"--output",self.manifest,"--sbom",self.sbom); data=json.loads(self.manifest.read_text()); self.assertEqual({"enabled":True,"source_identity":"captured-repository-root"},data["capture_relocation"]); self.assertNotIn(str(old),json.dumps(data)); self.assertEqual(["header.h","main.c"],[x["path"] for x in data["files"]])
        self.assertIn("missing",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--strace",trace,"--depfile",dep,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)
        link=self.base/"configured"; link.symlink_to(self.root,target_is_directory=True); declaration=self.base/"generated.json"; declaration.write_text(json.dumps({"schema":"brickwright/generated-build-inputs/v1","files":[],"symlinks":[{"path":"configured","target":"upstream","target_type":"directory"}]})); trace.write_text(f'1 readlink("{old}/configured", "upstream", 1023) = 8\n'); self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--captured-repository-root",old,"--strace",trace,"--depfile",dep,"--generated",declaration.name,"--output",self.manifest,"--sbom",self.sbom); self.assertEqual("configured",json.loads(self.manifest.read_text())["generated_symlinks"][0]["path"])
        self.assertIn("non-root",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--captured-repository-root","/","--strace",trace,"--depfile",dep,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)
        self.assertIn("overlap",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--captured-repository-root",self.base,"--strace",trace,"--depfile",dep,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)
        trace.write_text(f'1 openat(AT_FDCWD, "{old}ish/upstream/main.c", O_RDONLY) = 3\n'); self.assertIn("missing",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--captured-repository-root",old,"--strace",trace,"--depfile",dep,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)

    def test_root_git_file_excluded_but_git_symlinks_are_not(self):
        root=self.base/"patched"; root.mkdir(); source=root/"source.c"; source.write_text("/* SPDX-License-Identifier: MIT */\n"); admin=root/".git"; admin.write_text("gitdir: /secret/host/path\n")
        roots=self.base/"patched-roots.json"; roots.write_text(json.dumps({"schema":1,"roots":[{"name":"patched","path":str(root),"repository":"x","commit":"tree-id","license":"MIT","role":"fixture","provenance":"patched-tree","patch_policy":"fixture"}]})); dep=self.base/"patched.d"; dep.write_text(f"x: {source}\n"); trace=self.base/"patched.trace"; trace.write_text(f'1 openat(AT_FDCWD, "{admin}", O_RDONLY) = 3\n'); self.invoke("generate","--roots",roots,"--cwd",self.base,"--strace",trace,"--depfile",dep,"--output",self.manifest,"--sbom",self.sbom); data=json.loads(self.manifest.read_text()); self.assertEqual("file",data["vcs_administration"][0]["kind"]); self.assertNotIn("secret",json.dumps(data)); self.assertNotIn(str(self.base),json.dumps(data))
        outside=self.base/"outside-dot"; outside.write_text("/* SPDX-License-Identifier: MIT */\n"); admin.unlink(); admin.symlink_to(outside); trace.write_text(f'1 readlink("{admin}", "x", 1023) = 1\n'); self.assertIn("generated symlink sets differ",self.invoke("generate","--roots",roots,"--cwd",self.base,"--strace",trace,"--depfile",dep,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)
        admin.unlink(); gitfoo=root/".gitfoo"; gitfoo.symlink_to(outside); trace.write_text(f'1 readlink("{gitfoo}", "x", 1023) = 1\n'); self.assertIn("generated symlink sets differ",self.invoke("generate","--roots",roots,"--cwd",self.base,"--strace",trace,"--depfile",dep,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)

    def test_capture_relocation_does_not_rewrite_external_boundary(self):
        old=self.base.parent/"old-repo"; external=self.base/"toolchain-fixture"; external.mkdir(); header=external/"h"; header.write_bytes(b"external"); lock=self.base/"lock"; lock.write_bytes(b"lock"); declaration=self.base/"external.json"; declaration.write_text(json.dumps({"schema":"brickwright/external-build-inputs/v1","boundary":"host-tool","lock":{"path":"lock","sha256":hashlib.sha256(b"lock").hexdigest()},"files":[{"path":"h","sha256":hashlib.sha256(b"external").hexdigest()}]})); trace=self.base/"external.trace"; trace.write_text(f'1 openat(AT_FDCWD, "{header}", O_RDONLY) = 3\n'); dep=self.base/"external.d"; dep.write_text(f'x: {old}/upstream/main.c\n'); self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--captured-repository-root",old,"--strace",trace,"--depfile",dep,"--external",declaration.name,"--external-root",f"host-tool={external}","--output",self.manifest,"--sbom",self.sbom); data=json.loads(self.manifest.read_text()); self.assertEqual("h",data["external_inputs"][0]["path"]); self.assertNotIn(str(external),json.dumps(data))

    def test_capture_relocation_emits_canonical_link_evidence(self):
        old=self.base.parent/"old-capture"; obj=self.base/"main.o"; obj.write_bytes(b"object"); capture=self.base/"capture"; (capture/"compiles").mkdir(parents=True); dep=capture/"main.d"; dep.write_text(f"{old}/main.o: {old}/upstream/main.c\n"); (capture/"compiles/main.json").write_text(json.dumps({"cwd":str(old),"depfile":str(dep),"output":str(old/"main.o"),"output_sha256":hashlib.sha256(b"object").hexdigest()})); mapfile=self.base/"firmware.map"; mapfile.write_text(str(old/"main.o")+"\n"); trace=self.base/"empty.trace"; trace.write_text(""); evidence=self.base/"link.json"
        encoded=str(old).replace("/","."); current_encoded=str(self.base).replace("/","."); mapfile.write_text(str(old/"main.o")+f"\nlibapps.a(prefix{encoded}.apps.demo.o)\nlibnuttx.a(prefix{current_encoded}.nuttx.demo.o)\nlibsame.a(prefix{encoded}.same.o)\nlibsame.a(prefix{current_encoded}.same.o)\n")
        self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--captured-repository-root",old,"--strace",trace,"--capture",capture,"--map",mapfile,"--object",obj,"--output",self.manifest,"--sbom",self.sbom,"--evidence",evidence)
        linked=json.loads(evidence.read_text()); row=linked["objects"][0]; self.assertEqual("main.o",row["path"]); self.assertEqual(["nuttx/main.c"],row["sources"]); self.assertTrue(row["mentioned_in_map"]); self.assertIn("libapps.a(prefix.repository.apps.demo.o)",linked["map_objects"]); self.assertIn("libnuttx.a(prefix.repository.nuttx.demo.o)",linked["map_objects"]); self.assertEqual(1,linked["map_objects"].count("libsame.a(prefix.repository.same.o)"))
        emitted=self.manifest.read_text()+evidence.read_text(); self.assertNotIn(str(old),emitted); self.assertNotIn(str(self.base),emitted); self.assertNotIn(encoded,emitted); self.assertNotIn(current_encoded,emitted)
        mapfile.write_text(f"libapps.a(prefix{encoded}ish.apps.demo.o)\n")
        self.assertIn("repository path material",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--captured-repository-root",old,"--strace",trace,"--capture",capture,"--map",mapfile,"--object",obj,"--output",self.manifest,"--sbom",self.sbom,"--evidence",evidence,ok=False).stderr)

    def test_distinct_objects_cannot_collapse_to_one_public_identity(self):
        old=self.base.parent/"old-capture"; encoded=str(old).replace("/","."); current_encoded=str(self.base).replace("/",".")
        first=self.base/f"prefix{encoded}.same.o"; second=self.base/f"prefix{current_encoded}.same.o"; first.write_bytes(b"first"); second.write_bytes(b"second")
        trace=self.base/"empty.trace"; trace.write_text(""); evidence=self.base/"link.json"
        self.assertIn("collapse",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--captured-repository-root",old,"--strace",trace,"--depfile",self.dep,"--object",first,"--object",second,"--output",self.manifest,"--sbom",self.sbom,"--evidence",evidence,ok=False).stderr)

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

    def test_unconsumed_generated_diagnostic_is_logical_and_bounded(self):
        first=self.base/"first.generated"; second=self.base/"second.generated"; first.write_bytes(b"first"); second.write_bytes(b"second")
        declaration=self.base/"generated.json"; declaration.write_text(json.dumps({"schema":"brickwright/generated-build-inputs/v1","files":[{"path":first.name,"sha256":hashlib.sha256(first.read_bytes()).hexdigest(),"generator_argv":["fixture"]},{"path":second.name,"sha256":hashlib.sha256(second.read_bytes()).hexdigest(),"generator_argv":["fixture"]}]}))
        trace=self.base/"generated-read.trace"; trace.write_text(f'1 openat(AT_FDCWD, "{first}", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 3\n1 openat(AT_FDCWD, "{first}", O_RDONLY) = 4\n')
        result=self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--strace",trace,"--depfile",self.dep,"--generated",declaration.name,"--output",self.manifest,"--sbom",self.sbom,ok=False)
        self.assertIn('count=1, paths=["second.generated"]',result.stderr); self.assertNotIn(str(self.base),result.stderr)
        document=json.loads(declaration.read_text())
        for index in range(34):
            path=self.base/f"extra-{index:02}.generated"; path.write_bytes(b"extra")
            document["files"].append({"path":path.name,"sha256":hashlib.sha256(b"extra").hexdigest(),"generator_argv":["fixture"]})
        declaration.write_text(json.dumps(document)); result=self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--strace",trace,"--depfile",self.dep,"--generated",declaration.name,"--output",self.manifest,"--sbom",self.sbom,ok=False)
        self.assertIn("count=35",result.stderr); self.assertIn("omitted=3",result.stderr); self.assertNotIn("extra-33.generated",result.stderr)

    def test_generated_symlink_is_structured_and_escape_fails(self):
        link=self.base/"configured"; link.symlink_to(self.root,target_is_directory=True)
        trace=self.base/"symlink.trace"; trace.write_text(f'1 newfstatat(AT_FDCWD, "{link}", {{st_mode=S_IFLNK|0777}}, AT_SYMLINK_NOFOLLOW) = 0\n1 readlink("{link}", "upstream", 1023) = 8\n1 newfstatat(AT_FDCWD, "{link}", {{st_mode=S_IFDIR|0755}}, 0) = 0\n')
        declaration=self.base/"generated.json"
        item={"path":"configured","target":"upstream","target_type":"directory","evidence":"fixture"}
        declaration.write_text(json.dumps({"schema":"brickwright/generated-build-inputs/v1","files":[],"symlinks":[item]}))
        self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,"--depfile",self.dep,"--repository",self.base,"--generated",declaration.name,"--output",self.manifest,"--sbom",self.sbom)
        self.assertEqual([item],json.loads(self.manifest.read_text())["generated_symlinks"])
        declaration.write_text(json.dumps({"schema":"brickwright/generated-build-inputs/v1","files":[],"symlinks":[]}))
        self.assertIn("sets differ",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,"--depfile",self.dep,"--repository",self.base,"--generated",declaration.name,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)
        declaration.write_text(json.dumps({"schema":"brickwright/generated-build-inputs/v1","files":[],"symlinks":[item]}))
        extra=self.base/"extra"; extra.symlink_to(self.root,target_is_directory=True)
        declaration.write_text(json.dumps({"schema":"brickwright/generated-build-inputs/v1","files":[],"symlinks":[item,{"path":"extra","target":"upstream","target_type":"directory"}]}))
        self.assertIn("sets differ",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,"--depfile",self.dep,"--repository",self.base,"--generated",declaration.name,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)
        item["target"]="../escape"; declaration.write_text(json.dumps({"schema":"brickwright/generated-build-inputs/v1","files":[],"symlinks":[item]}))
        self.assertIn("escapes",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,"--depfile",self.dep,"--repository",self.base,"--generated",declaration.name,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)

    def test_generated_file_and_symlink_collision_fails_at_generation(self):
        target=self.base/"target"; target.write_bytes(b"target")
        link=self.base/"same"; link.symlink_to(target)
        declaration=self.base/"generated.json"; digest=hashlib.sha256(target.read_bytes()).hexdigest()
        declaration.write_text(json.dumps({"schema":"brickwright/generated-build-inputs/v1","files":[{"path":"same","sha256":digest,"generator_argv":["fixture"]}],"symlinks":[{"path":"same","target":"target","target_type":"file"}]}))
        trace=self.base/"collision.trace"; trace.write_text(f'1 readlink("{link}", "target", 1023) = 6\n')
        self.assertIn("collide",self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--strace",trace,"--depfile",self.dep,"--repository",self.base,"--generated",declaration.name,"--output",self.manifest,"--sbom",self.sbom,ok=False).stderr)

    def test_consumed_file_symlink_manifests_its_target(self):
        link=self.base/"Make.defs"; link.symlink_to(self.root/"build.mk")
        declaration=self.base/"generated.json"; declaration.write_text(json.dumps({"schema":"brickwright/generated-build-inputs/v1","files":[],"symlinks":[{"path":"Make.defs","target":"upstream/build.mk","target_type":"file"}]}))
        trace=self.base/"file-link.trace"; trace.write_text(f'1 openat(AT_FDCWD, "{link}", O_RDONLY) = 3\n')
        self.invoke("generate","--roots",self.roots,"--cwd",self.base,"--repository",self.base,"--strace",trace,"--depfile",self.dep,"--generated",declaration.name,"--output",self.manifest,"--sbom",self.sbom)
        self.assertIn("build.mk",[item["path"] for item in json.loads(self.manifest.read_text())["files"]])

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

    def test_twistedsnmp_is_allowed_and_preserved(self):
        self.write_roots("TwistedSNMP"); self.generate()
        manifest=json.loads(self.manifest.read_text())
        header=next(item for item in manifest["files"] if item["path"]=="header.h")
        self.assertEqual("TwistedSNMP",header["license"])
        sbom=json.loads(self.sbom.read_text())
        item=next(item for item in sbom["files"] if item["fileName"]=="nuttx/header.h")
        self.assertEqual(["TwistedSNMP"],item["licenseInfoInFiles"])

    def test_exact_mnemofs_spdx_anomaly_is_reviewed_and_drift_fails(self):
        source = self.root / "fs/mnemofs/Make.defs"; source.parent.mkdir(parents=True)
        canonical = Path(__file__).resolve().parents[1] / "nuttx/fs/mnemofs/Make.defs"
        source.write_bytes(canonical.read_bytes())
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "mnemofs"], check=True)
        document=json.loads(self.roots.read_text()); document["roots"][0]["commit"]=subprocess.check_output(
            ["git","-C",str(self.root),"rev-parse","HEAD"],text=True).strip(); self.roots.write_text(json.dumps(document))
        self.dep.write_text(f"x: {source}\n"); self.generate()
        entry=next(item for item in json.loads(self.manifest.read_text())["files"] if item["path"]=="fs/mnemofs/Make.defs")
        self.assertEqual("BSD-3-Clause",entry["license"]); self.assertEqual(2,len(entry["license_audit"]["raw_tags"]))
        self.invoke("verify", "--roots", self.roots, "--cwd", self.base,
                    "--strace", self.trace, "--depfile", self.dep,
                    "--manifest", self.manifest)
        manifest=json.loads(self.manifest.read_text())
        next(item for item in manifest["files"] if item["path"]=="fs/mnemofs/Make.defs")["license_audit"]["raw_tags"]=[]
        self.manifest.write_text(json.dumps(manifest))
        self.assertIn("license_audit mismatch", self.invoke("verify", "--roots", self.roots,
            "--cwd", self.base, "--strace", self.trace, "--depfile", self.dep,
            "--manifest", self.manifest, ok=False).stderr)
        source.write_bytes(source.read_bytes()+b"# drift\n")
        self.assertIn("reviewed SPDX anomaly drift",self.generate(ok=False).stderr)

    def test_multiple_spdx_outside_reviewed_anomaly_fails(self):
        source=self.root/"multiple.c"; source.write_text("/* SPDX-License-Identifier: MIT */\n/* SPDX-License-Identifier: BSD-3-Clause */\n")
        self.dep.write_text(f"x: {source}\n")
        self.assertIn("multiple SPDX expressions",self.generate(ok=False).stderr)

    def test_exact_uc_bsd_override_is_hash_pinned(self):
        source=self.root/"libs/libc/search/hash_func.c"; source.parent.mkdir(parents=True)
        source.write_bytes((Path(__file__).resolve().parents[1]/"nuttx/libs/libc/search/hash_func.c").read_bytes())
        subprocess.run(["git","-C",self.root,"add","."],check=True); subprocess.run(["git","-C",self.root,"commit","-qm","uc"],check=True)
        self.commit=subprocess.check_output(["git","-C",self.root,"rev-parse","HEAD"],text=True).strip(); d=json.loads(self.roots.read_text()); d["roots"][0]["commit"]=self.commit; d["roots"][0]["license_overrides"]=[{"path":"libs/libc/search/hash_func.c","license":"BSD-3-Clause-UC","require_spdx":True}]; self.roots.write_text(json.dumps(d)); self.dep.write_text(f"x: {source}\n"); self.generate()
        source.write_bytes(source.read_bytes()+b"drift\n"); self.assertIn("file drift",self.generate(ok=False).stderr)
        other=self.root/"other.c"; other.write_text("/* SPDX-License-Identifier: BSD-3-Clause-UC */\n"); self.dep.write_text(f"x: {other}\n"); self.assertIn("unknown",self.generate(ok=False).stderr)

    def test_exact_isc_override_is_hash_pinned(self):
        source=self.root/"libs/libc/string/lib_timingsafe_bcmp.c"; source.parent.mkdir(parents=True)
        source.write_bytes((Path(__file__).resolve().parents[1]/"nuttx/libs/libc/string/lib_timingsafe_bcmp.c").read_bytes())
        subprocess.run(["git","-C",self.root,"add","."],check=True); subprocess.run(["git","-C",self.root,"commit","-qm","isc"],check=True)
        self.commit=subprocess.check_output(["git","-C",self.root,"rev-parse","HEAD"],text=True).strip(); d=json.loads(self.roots.read_text()); d["roots"][0]["commit"]=self.commit; d["roots"][0]["license_overrides"]=[{"path":"libs/libc/string/lib_timingsafe_bcmp.c","license":"ISC","require_spdx":True}]; self.roots.write_text(json.dumps(d)); self.dep.write_text(f"x: {source}\n"); self.generate()
        source.write_bytes(source.read_bytes()+b"drift\n"); self.assertIn("file drift",self.generate(ok=False).stderr)
        other=self.root/"other.c"; other.write_text("/* SPDX-License-Identifier: ISC */\n"); self.dep.write_text(f"x: {other}\n"); self.assertIn("unknown",self.generate(ok=False).stderr)

    def test_second_exact_uc_bsd_override_is_hash_pinned(self):
        source=self.root/"libs/libc/stdlib/lib_wctomb.c"; source.parent.mkdir(parents=True); source.write_bytes((Path(__file__).resolve().parents[1]/"nuttx/libs/libc/stdlib/lib_wctomb.c").read_bytes())
        subprocess.run(["git","-C",self.root,"add","."],check=True); subprocess.run(["git","-C",self.root,"commit","-qm","wctomb"],check=True); commit=subprocess.check_output(["git","-C",self.root,"rev-parse","HEAD"],text=True).strip()
        d=json.loads(self.roots.read_text()); d["roots"][0]["commit"]=commit; d["roots"][0]["license_overrides"]=[{"path":"libs/libc/stdlib/lib_wctomb.c","license":"BSD-3-Clause-UC","require_spdx":True}]; self.roots.write_text(json.dumps(d)); self.dep.write_text(f"x: {source}\n"); self.generate(); source.write_bytes(source.read_bytes()+b"drift\n"); self.assertIn("file drift",self.generate(ok=False).stderr)

    def test_missing_escape_and_escaping_symlink_rejected(self):
        self.dep.write_text(f"x: {self.root}/missing.h\n")
        self.assertIn("missing", self.generate(ok=False).stderr)
        outside = self.base / "outside.c"; outside.write_text("x")
        self.dep.write_text(f"x: {outside}\n")
        self.assertIn("escapes declared", self.generate(ok=False).stderr)
        link = self.root / "link.c"; link.symlink_to(outside)
        self.dep.write_text(f"x: {link}\n")
        self.assertIn("generated symlink sets differ", self.generate(ok=False).stderr)

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
        self.assertIn("generated symlink sets differ", result.stderr)

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

    def test_exact_nxwidgets_discovery_override_pins_dual_boundary(self):
        source = self.root / "graphics/nxwidgets/Make.defs"; source.parent.mkdir(parents=True)
        repository = Path(__file__).resolve().parents[1]
        source.write_bytes((repository / "nuttx-apps/graphics/nxwidgets/Make.defs").read_bytes())
        copying = source.parent / "COPYING"
        copying.write_bytes((repository / "nuttx-apps/graphics/nxwidgets/COPYING").read_bytes())
        subprocess.run(["git", "-C", self.root, "add", "."], check=True)
        subprocess.run(["git", "-C", self.root, "commit", "-qm", "nxwidgets"], check=True)
        self.commit = subprocess.check_output(["git", "-C", self.root, "rev-parse", "HEAD"], text=True).strip()
        document={"schema":1,"roots":[{"name":"nuttx-apps","path":str(self.root),"repository":"https://example.invalid/apps","commit":self.commit,"license":"Apache-2.0","role":"application","license_overrides":[{"path":"graphics/nxwidgets/Make.defs","license":"Apache-2.0","require_spdx":True}]}]}
        self.roots.write_text(json.dumps(document)); self.dep.write_text(f"x: {source}\n"); self.generate()
        entry=next(item for item in json.loads(self.manifest.read_text())["files"] if item["path"]=="graphics/nxwidgets/Make.defs")
        self.assertEqual("reviewed-build-discovery-boundary",entry["license_audit"]["kind"])
        sbom=json.loads(self.sbom.read_text()); item=next(item for item in sbom["files"] if item["fileName"].endswith("Make.defs"))
        self.assertIn("COPYING",item["comment"])
        copying.write_bytes(copying.read_bytes()+b"drift\n")
        self.assertIn("nested license boundary drift",self.generate(ok=False).stderr)
        copying.write_bytes((repository / "nuttx-apps/graphics/nxwidgets/COPYING").read_bytes())
        outside=self.base/"outside-copying"; outside.write_bytes(copying.read_bytes())
        copying.unlink(); copying.symlink_to(outside)
        self.assertIn("nested license boundary drift",self.generate(ok=False).stderr)
        copying.unlink(); copying.write_bytes(outside.read_bytes())
        future=source.parent/"future.c"; future.write_text("/* SPDX-License-Identifier: Apache-2.0 */\n")
        self.dep.write_text(f"x: {future}\n")
        self.assertIn("nested license boundary lacks an override",self.generate(ok=False).stderr)

    def test_exact_twm4nx_discovery_override_pins_boundary(self):
        source=self.root/"graphics/twm4nx/Make.defs"; source.parent.mkdir(parents=True); repository=Path(__file__).resolve().parents[1]
        source.write_bytes((repository/"nuttx-apps/graphics/twm4nx/Make.defs").read_bytes()); copying=source.parent/"COPYING"; copying.write_bytes((repository/"nuttx-apps/graphics/twm4nx/COPYING").read_bytes())
        subprocess.run(["git","-C",self.root,"add","."],check=True); subprocess.run(["git","-C",self.root,"commit","-qm","twm"],check=True); commit=subprocess.check_output(["git","-C",self.root,"rev-parse","HEAD"],text=True).strip()
        self.roots.write_text(json.dumps({"schema":1,"roots":[{"name":"nuttx-apps","path":str(self.root),"repository":"https://example.invalid/apps","commit":commit,"license":"Apache-2.0","role":"application","license_overrides":[{"path":"graphics/twm4nx/Make.defs","license":"Apache-2.0","require_spdx":True}]}]})); self.dep.write_text(f"x: {source}\n"); self.generate()
        copying.write_bytes(copying.read_bytes()+b"drift\n"); self.assertIn("boundary drift",self.generate(ok=False).stderr)
        outside=self.base/"copy"; outside.write_bytes((repository/"nuttx-apps/graphics/twm4nx/COPYING").read_bytes()); copying.unlink(); copying.symlink_to(outside); self.assertIn("boundary drift",self.generate(ok=False).stderr)
        copying.unlink(); copying.write_bytes(outside.read_bytes()); future=source.parent/"future.c"; future.write_text("/* SPDX-License-Identifier: Apache-2.0 */\n"); self.dep.write_text(f"x: {future}\n"); self.assertIn("boundary lacks an override",self.generate(ok=False).stderr)

    def test_exact_nxwm_discovery_boundary_records_discrepancy(self):
        source=self.root/"graphics/nxwm/Make.defs"; source.parent.mkdir(parents=True); repo=Path(__file__).resolve().parents[1]; source.write_bytes((repo/"nuttx-apps/graphics/nxwm/Make.defs").read_bytes()); copying=source.parent/"COPYING"; copying.write_bytes((repo/"nuttx-apps/graphics/nxwm/COPYING").read_bytes())
        subprocess.run(["git","-C",self.root,"add","."],check=True); subprocess.run(["git","-C",self.root,"commit","-qm","nxwm"],check=True); commit=subprocess.check_output(["git","-C",self.root,"rev-parse","HEAD"],text=True).strip(); self.roots.write_text(json.dumps({"schema":1,"roots":[{"name":"nuttx-apps","path":str(self.root),"repository":"x","commit":commit,"license":"Apache-2.0","role":"application","license_overrides":[{"path":"graphics/nxwm/Make.defs","license":"Apache-2.0","require_spdx":True}]}]})); self.dep.write_text(f"x: {source}\n"); self.generate(); audit=next(x for x in json.loads(self.manifest.read_text())["files"] if x["path"].endswith("Make.defs"))["license_audit"]; self.assertIn("no BSD license is inferred",audit["note"])
        copying.write_bytes(copying.read_bytes()+b"drift"); self.assertIn("boundary drift",self.generate(ok=False).stderr); outside=self.base/"nxwm-license"; outside.write_bytes((repo/"nuttx-apps/graphics/nxwm/COPYING").read_bytes()); copying.unlink(); copying.symlink_to(outside); self.assertIn("boundary drift",self.generate(ok=False).stderr); copying.unlink(); copying.write_bytes(outside.read_bytes()); future=source.parent/"future.c"; future.write_text("/* SPDX-License-Identifier: Apache-2.0 */\n"); self.dep.write_text(f"x: {future}\n"); self.assertIn("boundary lacks an override",self.generate(ok=False).stderr)

    def test_mbedtls_blank_cmake_selects_apache_from_pinned_license(self):
        import runpy
        module=runpy.run_path(str(TOOL)); source=self.root/"framework/CMakeLists.txt"; source.parent.mkdir(); source.write_bytes(b"# blank\n"); boundary=source.parent/"LICENSE"; boundary.write_bytes(b"choose Apache OR GPL; warranty\n")
        selection={"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"boundary_path":"framework/LICENSE","boundary_sha256":hashlib.sha256(boundary.read_bytes()).hexdigest(),"declared":"Apache-2.0 OR GPL-2.0-or-later","concluded":"Apache-2.0","markers":[b"Apache OR GPL",b"warranty"]}
        key=("mbedtls","framework/CMakeLists.txt"); production=module["REVIEWED_BOUNDARY_LICENSE_SELECTIONS"][key]; module["REVIEWED_BOUNDARY_LICENSE_SELECTIONS"][key]=selection; root={"name":"mbedtls","path":str(self.root),"license":"Apache-2.0","license_overrides":[]}; result=module["file_license"](source,root,Path("framework/CMakeLists.txt")); self.assertEqual(("Apache-2.0","Apache-2.0 OR GPL-2.0-or-later"),result[:2]); self.assertEqual("framework/LICENSE",result[2]["license_source"])
        source.write_bytes(b"drift"); self.assertRaises(SystemExit,module["file_license"],source,root,Path("framework/CMakeLists.txt")); source.write_bytes(b"# blank\n"); boundary.write_bytes(b"wrong expression"); self.assertRaises(SystemExit,module["file_license"],source,root,Path("framework/CMakeLists.txt")); boundary.write_bytes(b"choose Apache OR GPL; warranty\n"); outside=self.base/"outside"; outside.write_bytes(boundary.read_bytes()); boundary.unlink(); boundary.symlink_to(outside); self.assertRaises(SystemExit,module["file_license"],source,root,Path("framework/CMakeLists.txt"))
        self.assertEqual({"source_sha256":"bdcf4a6aa867ba4855d26043ec869961fa5ac8a6b2fa6856689d0ae4d6aac5b6","boundary_path":"framework/LICENSE","boundary_sha256":"11402351e38392230bb8934ba1095c0c0049a296c0f8821f76e4672dff54b490","declared":"Apache-2.0 OR GPL-2.0-or-later","concluded":"Apache-2.0","markers":[b"dual [Apache-2.0]",b"OR [GPL-2.0-or-later]",b"users may choose which of these licenses"]},production)

    def test_future_mbedtls_framework_source_fails_generator_boundary(self):
        framework=self.root/"framework"; framework.mkdir(); (framework/"LICENSE").write_text("dual terms\n"); future=framework/"future.c"; future.write_text("/* SPDX-License-Identifier: Apache-2.0 */\n")
        self.roots.write_text(json.dumps({"schema":1,"roots":[{"name":"mbedtls","path":str(self.root),"repository":"x","commit":self.commit,"license":"Apache-2.0","role":"crypto","license_overrides":[{"path":"framework/CMakeLists.txt","license":"Apache-2.0","require_spdx":False}]}]})); self.dep.write_text(f"x: {future}\n")
        self.assertIn("nested license boundary lacks an override",self.generate(ok=False).stderr)

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
