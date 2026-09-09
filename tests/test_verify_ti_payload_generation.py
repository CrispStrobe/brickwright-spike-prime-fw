# SPDX-License-Identifier: Apache-2.0
import hashlib, json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; TOOL=ROOT/"tools/verify_ti_payload_generation.py"; PROOF=ROOT/"evidence/source-closure/ti-payload-generation.json"; DECL=ROOT/"policy/firmware-generated-inputs.json"
class TestTiProof(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.repo=Path(self.temp.name)/"repo"; self.repo.mkdir()
  self.proof=Path(self.temp.name)/"proof.json"; d=json.loads(PROOF.read_text())
  for index,item in enumerate(d["inputs"]):
   target=self.repo/item["path"]; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(("fixture-%d\n"%index).encode()); item["sha256"]=hashlib.sha256(target.read_bytes()).hexdigest()
  self.proof.write_text(json.dumps(d)); self.decl=Path(self.temp.name)/"declaration.json"; self.decl.write_bytes(DECL.read_bytes())
 def tearDown(self): self.temp.cleanup()
 def invoke(self,proof=None,decl=None,repo=None,ok=True):
  proof=proof or self.proof; decl=decl or self.decl; repo=repo or self.repo
  r=subprocess.run([sys.executable,TOOL,"--proof",proof,"--repository",repo,"--declaration",decl],text=True,capture_output=True)
  self.assertEqual(ok,r.returncode==0,r.stderr); return r
 @unittest.skipUnless(all((ROOT/p).is_file() for p in [x["path"] for x in json.loads(PROOF.read_text())["inputs"]]),"restricted local TI package is absent")
 def test_exact_network_none_regeneration(self): self.invoke(PROOF,DECL,ROOT)
 def test_evidence_tamper_fails_before_regeneration(self):
  d=json.loads(self.proof.read_text()); d["isolation"]["network_namespace"]="host"; self.proof.write_text(json.dumps(d)); self.assertIn("isolation",self.invoke(ok=False).stderr)
 def test_declaration_boundary_tamper_fails(self):
  d=json.loads(self.decl.read_text()); item=next(x for x in d["files"] if x.get("path","").endswith("ti_bts_local_payload.h")); item["license_boundary"]["concluded"]="Apache-2.0"; self.decl.write_text(json.dumps(d)); self.assertIn("declaration",self.invoke(ok=False).stderr)
 def test_input_escape_hash_drift_and_license_symlink_fail(self):
  original=self.proof.read_bytes(); d=json.loads(original); d["inputs"][0]["path"]="../escape"; self.proof.write_text(json.dumps(d)); self.assertIn("unsafe",self.invoke(ok=False).stderr)
  self.proof.write_bytes(original); d=json.loads(original); d["inputs"][0]["sha256"]="0"*64; self.proof.write_text(json.dumps(d)); self.assertIn("changed",self.invoke(ok=False).stderr)
  self.proof.write_bytes(original); license_path=self.repo/"third_party/ti-cc2564c/LICENSE.ti"; outside=Path(self.temp.name)/"LICENSE.ti"; shutil.copy2(license_path,outside); license_path.unlink()
  self.assertIn("missing",self.invoke(ok=False).stderr)
  license_path.symlink_to(outside); self.assertIn("symlink",self.invoke(ok=False).stderr)
if __name__=="__main__": unittest.main()
