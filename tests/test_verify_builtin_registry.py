#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import hashlib, json, subprocess, sys, tempfile, unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools/verify_builtin_registry.py"

class RegistryProofTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.repo = self.root / "repo"; self.out = self.root / "out"
        self.repo.mkdir(); self.out.mkdir(); (self.repo / "Make.defs").write_bytes(b"rule")
        (self.out / "app.bdat").write_bytes(b"data"); (self.out / ".updated").write_bytes(b"")
        sha = lambda data: hashlib.sha256(data).hexdigest()
        self.evidence = self.root / "evidence.json"
        self.evidence.write_text(json.dumps({
            "schema":"brickwright/generated-input-proof/v1",
            "status":"exact-output-match",
            "isolation":{"network_namespace":"none","successful_connects":0},
            "generator_argv":["make","register_all"],
            "trace_sha256":sha(b"trace"),
            "output_set":{"consumed_data_file_count":1,"metadata_output_count":1},
            "generator_inputs":[{"path":"Make.defs","sha256":sha(b"rule")}],
            "files":[{"path":"app.bdat","sha256":sha(b"data")}],
            "outputs":[
                {"path":".updated","sha256":sha(b""),"disposition":"metadata-only"},
                {"path":"app.bdat","sha256":sha(b"data"),"disposition":"consumed-generated-input"},
            ],
        }))
    def tearDown(self): self.temp.cleanup()
    def invoke(self, ok=True):
        result=subprocess.run([sys.executable,TOOL,"--evidence",self.evidence,"--repository",self.repo,"--output-root",self.out],text=True,capture_output=True)
        self.assertEqual(ok,result.returncode==0,result.stderr); return result
    def test_exact_and_negative_cases(self):
        self.invoke()
        (self.out / "extra").write_bytes(b"x"); self.assertIn("output set",self.invoke(False).stderr)
        (self.out / "extra").unlink(); (self.out / "app.bdat").write_bytes(b"drift")
        self.assertIn("hash mismatch",self.invoke(False).stderr)
        (self.out / "app.bdat").unlink(); self.assertIn("output set",self.invoke(False).stderr)

    def test_input_and_output_escapes_are_rejected(self):
        document=json.loads(self.evidence.read_text())
        for escaped in ("../escape", "/escape"):
            document["generator_inputs"][0]["path"]=escaped
            self.evidence.write_text(json.dumps(document))
            self.assertIn("escapes root",self.invoke(False).stderr)
        document["generator_inputs"][0]["path"]="Make.defs"
        self.evidence.write_text(json.dumps(document))
        (self.out / "app.bdat").unlink()
        (self.out / "app.bdat").symlink_to(self.repo / "Make.defs")
        self.assertIn("symlink",self.invoke(False).stderr)

if __name__ == "__main__": unittest.main()
