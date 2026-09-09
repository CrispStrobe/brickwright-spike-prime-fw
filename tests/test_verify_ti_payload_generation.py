# SPDX-License-Identifier: Apache-2.0
import json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; TOOL=ROOT/"tools/verify_ti_payload_generation.py"; PROOF=ROOT/"evidence/source-closure/ti-payload-generation.json"; DECL=ROOT/"policy/firmware-generated-inputs.json"
class TestTiProof(unittest.TestCase):
 def invoke(self,proof=PROOF,decl=DECL,repo=ROOT,ok=True):
  r=subprocess.run([sys.executable,TOOL,"--proof",proof,"--repository",repo,"--declaration",decl],text=True,capture_output=True)
  self.assertEqual(ok,r.returncode==0,r.stderr); return r
 def test_exact_network_none_regeneration(self): self.invoke()
 def test_evidence_tamper_fails_before_regeneration(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/"proof.json"; d=json.loads(PROOF.read_text()); d["isolation"]["network_namespace"]="host"; p.write_text(json.dumps(d)); self.assertIn("isolation",self.invoke(p,ok=False).stderr)
 def test_declaration_boundary_tamper_fails(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/"declaration.json"; d=json.loads(DECL.read_text()); item=next(x for x in d["files"] if x.get("path","").endswith("ti_bts_local_payload.h")); item["license_boundary"]["concluded"]="Apache-2.0"; p.write_text(json.dumps(d)); self.assertIn("declaration",self.invoke(decl=p,ok=False).stderr)
 def test_input_escape_hash_drift_and_license_symlink_fail(self):
  with tempfile.TemporaryDirectory() as t:
   base=Path(t); proof=base/"proof.json"; d=json.loads(PROOF.read_text()); d["inputs"][0]["path"]="../escape"; proof.write_text(json.dumps(d)); self.assertIn("unsafe",self.invoke(proof,ok=False).stderr)
   d=json.loads(PROOF.read_text()); d["inputs"][0]["sha256"]="0"*64; proof.write_text(json.dumps(d)); self.assertIn("changed",self.invoke(proof,ok=False).stderr)
   repo=base/"repo"; repo.mkdir()
   for name in [x["path"] for x in json.loads(PROOF.read_text())["inputs"]]:
    target=repo/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/name,target)
   outside=base/"LICENSE.ti"; shutil.copy2(ROOT/"third_party/ti-cc2564c/LICENSE.ti",outside)
   license_path=repo/"third_party/ti-cc2564c/LICENSE.ti"; license_path.unlink()
   self.assertIn("missing",self.invoke(repo=repo,ok=False).stderr)
   license_path.symlink_to(outside)
   self.assertIn("symlink",self.invoke(repo=repo,ok=False).stderr)
if __name__=="__main__": unittest.main()
