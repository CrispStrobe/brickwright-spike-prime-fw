# SPDX-License-Identifier: Apache-2.0
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
TOOL=Path(__file__).resolve().parents[1]/"tools/verify_config_generation.py"
PROOF=Path(__file__).resolve().parents[1]/"evidence/source-closure/config-generation.json"
class ConfigProofTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  source=Path(__file__).resolve().parents[1]
  self.repo=source
  self.proof=Path(self.tmp.name)/"proof.json"; self.proof.write_bytes(PROOF.read_bytes())
  self.declaration=Path(self.tmp.name)/"generated.json"; self.declaration.write_bytes((source/"policy/firmware-generated-inputs.json").read_bytes())
 def tearDown(self): self.tmp.cleanup()
 def invoke(self,ok=True):
  r=subprocess.run([sys.executable,TOOL,"--proof",self.proof,"--repository",self.repo,"--declaration",self.declaration],text=True,capture_output=True); self.assertEqual(ok,r.returncode==0,r.stderr); return r
 def test_exact(self): self.invoke()
 def test_hash_drift(self):
  d=json.loads(self.proof.read_text()); d["outputs"][0]["sha256"]="0"*64; self.proof.write_text(json.dumps(d)); self.invoke(False)
 def test_identity_and_isolation_tamper(self):
  d=json.loads(self.proof.read_text()); d["source_identities"][0]["tree"]="0"*40; self.proof.write_text(json.dumps(d)); self.invoke(False)
  d=json.loads(PROOF.read_text()); d["isolation"]["network_namespace"]="host"; self.proof.write_text(json.dumps(d)); self.invoke(False)
 def test_output_escape_fails(self):
  d=json.loads(self.proof.read_text()); d["outputs"][0]["path"]="../escape"; self.proof.write_text(json.dumps(d)); self.invoke(False)
 def test_declaration_mismatch_and_duplicate_fail(self):
  d=json.loads(self.declaration.read_text()); item=next(x for x in d["files"] if x["path"]=="nuttx/.config"); item["sha256"]="0"*64; self.declaration.write_text(json.dumps(d)); self.invoke(False)
  d=json.loads((self.repo/"policy/firmware-generated-inputs.json").read_text()); d["files"].append(next(x for x in d["files"] if x["path"]=="nuttx/.config")); self.declaration.write_text(json.dumps(d)); self.invoke(False)
 def test_parent_symlink_is_rejected_before_identity_check(self):
  fake=Path(self.tmp.name)/"fake"; fake.mkdir(); (fake/"boards").symlink_to(self.repo/"boards",target_is_directory=True); (fake/"nuttx").symlink_to(self.repo/"nuttx",target_is_directory=True)
  old=self.repo; self.repo=fake; self.assertIn("symlink",self.invoke(False).stderr); self.repo=old
 def test_malformed_input_and_output_fail_cleanly(self):
  d=json.loads(self.proof.read_text()); d["generator_inputs"]=[None]; self.proof.write_text(json.dumps(d)); self.assertIn("invalid generator input",self.invoke(False).stderr)
  d=json.loads(PROOF.read_text()); d["outputs"]=[None]; self.proof.write_text(json.dumps(d)); self.assertIn("invalid output",self.invoke(False).stderr)
if __name__=="__main__": unittest.main()
