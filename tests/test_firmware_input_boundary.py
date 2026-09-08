# SPDX-License-Identifier: Apache-2.0
import hashlib, json, subprocess, sys, tempfile, unittest
from pathlib import Path
TOOL=Path(__file__).resolve().parents[1]/"tools/firmware_input_boundary.py"
class BoundaryTest(unittest.TestCase):
 def test_tree_patch_and_archive_are_fail_closed(self):
  with tempfile.TemporaryDirectory() as raw:
   d=Path(raw); (d/"stage").mkdir(); (d/"stage/a").write_text("a"); (d/"patch").write_text("p"); (d/"archive").write_text("z")
   digest=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
   tree=hashlib.sha256((1).to_bytes(8,"big")+b"a"+(1).to_bytes(8,"big")+b"a").hexdigest()
   lock={"schema":"brickwright/firmware-build-input-lock/v1","sources":[{"name":"s","license_expression":"MIT","staged_tree_sha256":tree,"archive_sha256":digest(d/"archive"),"patches":[{"path":"patch","sha256":digest(d/"patch")}]}],"host_tools":[]}
   (d/"lock").write_text(json.dumps(lock)); cmd=[sys.executable,TOOL,"--lock",d/"lock","--repo",d,"--stage",f"s={d/'stage'}","--archive",f"s={d/'archive'}"]
   self.assertEqual(0,subprocess.run(cmd,capture_output=True).returncode)
   (d/"stage/a").write_text("changed"); self.assertNotEqual(0,subprocess.run(cmd,capture_output=True).returncode)
if __name__=="__main__": unittest.main()
