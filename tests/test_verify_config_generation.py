# SPDX-License-Identifier: Apache-2.0
import json,subprocess,sys,tempfile,unittest
import hashlib
from pathlib import Path
TOOL=Path(__file__).resolve().parents[1]/"tools/verify_config_generation.py"
PROOF=Path(__file__).resolve().parents[1]/"evidence/source-closure/config-generation.json"
class ConfigProofTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.repo=Path(self.tmp.name)/"repo"; self.repo.mkdir()
  def git_root(root, files):
   root.mkdir(parents=True,exist_ok=True); subprocess.run(["git","init","-q",root],check=True)
   subprocess.run(["git","-C",root,"config","user.email","test@example.invalid"],check=True); subprocess.run(["git","-C",root,"config","user.name","Test"],check=True)
   for name,data in files.items(): target=root/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
   subprocess.run(["git","-C",root,"add","."],check=True); subprocess.run(["git","-C",root,"commit","-qm","fixture"],check=True)
   return subprocess.check_output(["git","-C",root,"rev-parse","HEAD"],text=True).strip()
  project=git_root(self.repo,{"apps/Kconfig":b"apps\n","boards/spike-prime-hub/configs/usbnsh/defconfig":b"defconfig\n"})
  nuttx=git_root(self.repo/"nuttx",{"tools/version.sh":b"version\n"})
  apps=git_root(self.repo/"nuttx-apps",{"Kconfig":b"apps upstream\n"})
  (self.repo/"nuttx/.config").write_bytes(b"config\n"); (self.repo/"nuttx/.version").write_bytes(b"version output\n")
  self.roots=Path(self.tmp.name)/"roots.json"; self.roots.write_text(json.dumps({"roots":[{"name":"project","path":".","commit":project},{"name":"nuttx","path":"nuttx","commit":nuttx},{"name":"nuttx-apps","path":"nuttx-apps","commit":apps}]}))
  d=json.loads(PROOF.read_text()); sha=lambda b:hashlib.sha256(b).hexdigest()
  d["generator_inputs"]=[{"path":"boards/spike-prime-hub/configs/usbnsh/defconfig","sha256":sha(b"defconfig\n")},{"path":"nuttx/tools/version.sh","sha256":sha(b"version\n")}]
  d["outputs"]=[{"path":"nuttx/.config","sha256":sha(b"config\n")},{"path":"nuttx/.version","sha256":sha(b"version output\n")}]
  d["source_identities"]=[{"commit":project,"path":"apps","root":".","tree":subprocess.check_output(["git","-C",self.repo,"rev-parse",project+":apps"],text=True).strip()},{"commit":nuttx,"path":".","root":"nuttx","tree":subprocess.check_output(["git","-C",self.repo/"nuttx","rev-parse",nuttx+"^{tree}"],text=True).strip()},{"commit":apps,"path":".","root":"nuttx-apps","tree":subprocess.check_output(["git","-C",self.repo/"nuttx-apps","rev-parse",apps+"^{tree}"],text=True).strip()}]
  self.proof=Path(self.tmp.name)/"proof.json"; self.proof.write_text(json.dumps(d))
  self.declaration=Path(self.tmp.name)/"generated.json"; self.declaration.write_text(json.dumps({"schema":"brickwright/generated-build-inputs/v1","files":[{"path":x["path"],"sha256":x["sha256"]} for x in d["outputs"]]}))
 def tearDown(self): self.tmp.cleanup()
 def invoke(self,ok=True):
  r=subprocess.run([sys.executable,TOOL,"--proof",self.proof,"--repository",self.repo,"--declaration",self.declaration,"--roots",self.roots],text=True,capture_output=True); self.assertEqual(ok,r.returncode==0,r.stderr); return r
 def test_exact(self): self.invoke()
 def test_hash_drift(self):
  d=json.loads(self.proof.read_text()); d["outputs"][0]["sha256"]="0"*64; self.proof.write_text(json.dumps(d)); self.invoke(False)
 def test_identity_and_isolation_tamper(self):
  d=json.loads(self.proof.read_text()); d["source_identities"][0]["tree"]="0"*40; self.proof.write_text(json.dumps(d)); self.invoke(False)
  d=json.loads(self.proof.read_text()); d["isolation"]["network_namespace"]="host"; self.proof.write_text(json.dumps(d)); self.invoke(False)
 def test_output_escape_fails(self):
  d=json.loads(self.proof.read_text()); d["outputs"][0]["path"]="../escape"; self.proof.write_text(json.dumps(d)); self.invoke(False)
 def test_declaration_mismatch_and_duplicate_fail(self):
  d=json.loads(self.declaration.read_text()); item=next(x for x in d["files"] if x["path"]=="nuttx/.config"); item["sha256"]="0"*64; self.declaration.write_text(json.dumps(d)); self.invoke(False)
  d=json.loads(self.declaration.read_text()); d["files"].append(dict(d["files"][0])); self.declaration.write_text(json.dumps(d)); self.invoke(False)
 def test_parent_symlink_is_rejected_before_identity_check(self):
  fake=Path(self.tmp.name)/"fake"; fake.mkdir(); (fake/"boards").symlink_to(self.repo/"boards",target_is_directory=True); (fake/"nuttx").symlink_to(self.repo/"nuttx",target_is_directory=True)
  old=self.repo; self.repo=fake; self.assertIn("symlink",self.invoke(False).stderr); self.repo=old
 def test_malformed_input_and_output_fail_cleanly(self):
  original=json.loads(self.proof.read_text()); d=dict(original); d["generator_inputs"]=[None]; self.proof.write_text(json.dumps(d)); self.assertIn("invalid generator input",self.invoke(False).stderr)
  d=dict(original); d["outputs"]=[None]; self.proof.write_text(json.dumps(d)); self.assertIn("invalid output",self.invoke(False).stderr)
if __name__=="__main__": unittest.main()
