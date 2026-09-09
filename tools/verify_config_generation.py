#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the pinned, networkless NuttX configuration outputs."""
import argparse, hashlib, json, re, stat, subprocess
from pathlib import Path, PurePosixPath
HEX=re.compile(r"[0-9a-f]{64}"); IMAGE="sha256:8d304601acccf0fd2d6bcbf4e1ec1377b5e89cbdd669a60c1cf5c0e581b3c3fa"
OUTPUTS={"nuttx/.config","nuttx/.version"}
COMMANDS=[["ln","-s","$TREE/apps","$TREE/nuttx-apps/external"],["nuttx/tools/configure.sh","-l","-a","../nuttx-apps","../boards/spike-prime-hub/configs/usbnsh"],["make","-C","nuttx","olddefconfig"],["nuttx/tools/version.sh","-v","12.12.0","-b","a67efb31cf","nuttx/.version"]]
IDENTITIES=[{"commit":"999e2d86f9b692abaf63b22dad77d22aeb03029c","path":"apps","root":".","tree":"87478a45a4db3cdb21374f18d86a78d32e435491"},{"commit":"a67efb31cf4f236e456882589b91862f04594528","path":".","root":"nuttx","tree":"f828c9b54198a9adcc01c5042b6d1cc64472e385"},{"commit":"55f0bc216565ccab8dee600a88f4485c7693bf8b","path":".","root":"nuttx-apps","tree":"2dca909c592142cc9c496165ef46de3a7496eca7"}]
def fail(s): raise SystemExit("config-proof: ERROR: "+s)
def rel(s,label):
 p=PurePosixPath(s) if isinstance(s,str) else PurePosixPath()
 if p.is_absolute() or not p.parts or ".." in p.parts: fail(label+" path is unsafe")
 return p
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def regular(repo,name,label):
 current=repo
 for component in rel(name,label).parts:
  current/=component
  if current.is_symlink(): fail(label+" path contains symlink")
 if not current.resolve().is_relative_to(repo) or not current.is_file(): fail(label+" missing or escaping: "+name)
 return current
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--proof",required=True); ap.add_argument("--repository",required=True); ap.add_argument("--declaration",required=True); a=ap.parse_args()
 repo=Path(a.repository).resolve(); d=json.loads(Path(a.proof).read_text())
 if d.get("schema")!="brickwright/config-generation-proof/v1" or d.get("status")!="exact-output-match": fail("invalid proof header")
 if d.get("container_image")!=IMAGE or d.get("isolation")!={"network_namespace":"none","successful_connects":0}: fail("invalid isolation identity")
 commands=d.get("generator_commands");
 if commands!=COMMANDS: fail("generator commands differ")
 seen=set()
 for item in d.get("generator_inputs",[]):
  name=rel(item.get("path"),"input").as_posix(); path=regular(repo,name,"input")
  if name in seen: fail("duplicate input")
  seen.add(name)
  if not HEX.fullmatch(item.get("sha256",'')) or sha(path)!=item["sha256"]: fail("input missing or changed: "+name)
 if seen!={"boards/spike-prime-hub/configs/usbnsh/defconfig","nuttx/tools/version.sh"}: fail("input set mismatch")
 outputs={}
 for item in d.get("outputs",[]):
  name=rel(item.get("path"),"output").as_posix(); path=regular(repo,name,"output")
  if name in outputs: fail("duplicate output")
  if not HEX.fullmatch(item.get("sha256",'')) or sha(path)!=item["sha256"]: fail("output missing or changed: "+name)
  outputs[name]=item["sha256"]
 if set(outputs)!=OUTPUTS: fail("output set mismatch")
 identities=d.get("source_identities")
 if identities!=IDENTITIES: fail("source identities differ")
 for item in identities:
  root=(repo/item["root"]).resolve(); spec=item["commit"]+('^{tree}' if item["path"]=='.' else ':'+item["path"])
  result=subprocess.run(["git","-C",str(root),"rev-parse",spec],text=True,capture_output=True)
  if result.returncode or result.stdout.strip()!=item["tree"]: fail("source identity object mismatch")
 declaration=json.loads(Path(a.declaration).read_text())
 if declaration.get("schema")!="brickwright/generated-build-inputs/v1" or not isinstance(declaration.get("files"),list): fail("invalid generated declaration")
 declared={}
 for item in declaration["files"]:
  if not isinstance(item,dict): fail("invalid declaration item")
  name=item.get("path")
  if name not in OUTPUTS: continue
  if name in declared: fail("duplicate declared config output")
  if not HEX.fullmatch(item.get("sha256",'')): fail("invalid declared config hash")
  declared[name]=item["sha256"]
 if declared!=outputs: fail("generated declaration differs from config outputs")
 print("config-proof: verified 2 outputs")
if __name__=="__main__": main()
