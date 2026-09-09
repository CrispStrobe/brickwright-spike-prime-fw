#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the pinned, networkless NuttX configuration outputs."""
import argparse, hashlib, json, re, stat, subprocess
from pathlib import Path, PurePosixPath
HEX=re.compile(r"[0-9a-f]{64}"); IMAGE="sha256:8d304601acccf0fd2d6bcbf4e1ec1377b5e89cbdd669a60c1cf5c0e581b3c3fa"
OUTPUTS={"nuttx/.config","nuttx/.version","nuttx/tools/incdir"}
INPUTS={"boards/spike-prime-hub/configs/usbnsh/defconfig","nuttx/tools/version.sh","nuttx/tools/incdir.c"}
COMMANDS=[["ln","-s","$TREE/apps","$TREE/nuttx-apps/external"],["nuttx/tools/configure.sh","-l","-a","../nuttx-apps","../boards/spike-prime-hub/configs/usbnsh"],["make","-C","nuttx","olddefconfig"],["nuttx/tools/version.sh","-v","12.12.0","-b","a67efb31cf","nuttx/.version"],["make","-C","nuttx/tools","-f","Makefile.host","incdir"]]
HOST_TOOL={"compiler_argv":["cc","-O2","-Wall","-Wstrict-prototypes","-Wshadow","-DHAVE_STRTOK_C=1","-DHAVE_STRNDUP=1","-o","incdir","incdir.c"],"makefile":"nuttx/tools/Makefile.host","makefile_sha256":"4433262b615aae57a80b1b9d60248e78089632520e0d4855fe3576e240b49d1b","rule":"incdir$(HOSTEXEEXT): incdir.c"}
SYMLINKS=[{"path":"nuttx/Make.defs","target":"boards/spike-prime-hub/scripts/Make.defs","target_type":"file"},{"path":"nuttx/arch/arm/include/board","target":"boards/spike-prime-hub/include","target_type":"directory"},{"path":"nuttx/arch/arm/include/chip","target":"nuttx/arch/arm/include/stm32","target_type":"directory"}]
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
 ap=argparse.ArgumentParser(); ap.add_argument("--proof",required=True); ap.add_argument("--repository",required=True); ap.add_argument("--declaration",required=True); ap.add_argument("--roots",required=True); a=ap.parse_args()
 repo=Path(a.repository).resolve(); d=json.loads(Path(a.proof).read_text())
 if d.get("schema")!="brickwright/config-generation-proof/v1" or d.get("status")!="exact-output-match": fail("invalid proof header")
 if d.get("container_image")!=IMAGE or d.get("isolation")!={"network_namespace":"none","successful_connects":0}: fail("invalid isolation identity")
 commands=d.get("generator_commands");
 if commands!=COMMANDS: fail("generator commands differ")
 if d.get("native_host_tool")!=HOST_TOOL: fail("native host-tool proof differs")
 if sha(regular(repo,HOST_TOOL["makefile"],"host-tool Makefile"))!=HOST_TOOL["makefile_sha256"]: fail("host-tool Makefile changed")
 seen=set()
 inputs=d.get("generator_inputs")
 if not isinstance(inputs,list) or not inputs: fail("generator inputs are missing")
 for item in inputs:
  if not isinstance(item,dict): fail("invalid generator input")
  name=rel(item.get("path"),"input").as_posix(); path=regular(repo,name,"input")
  if name in seen: fail("duplicate input")
  seen.add(name)
  if not HEX.fullmatch(item.get("sha256",'')) or sha(path)!=item["sha256"]: fail("input missing or changed: "+name)
 if seen!=INPUTS: fail("input set mismatch")
 outputs={}
 output_items=d.get("outputs")
 if not isinstance(output_items,list) or not output_items: fail("outputs are missing")
 for item in output_items:
  if not isinstance(item,dict): fail("invalid output")
  name=rel(item.get("path"),"output").as_posix(); path=regular(repo,name,"output")
  if name in outputs: fail("duplicate output")
  if not HEX.fullmatch(item.get("sha256",'')) or sha(path)!=item["sha256"]: fail("output missing or changed: "+name)
  outputs[name]=item["sha256"]
 if set(outputs)!=OUTPUTS: fail("output set mismatch")
 if d.get("symlinks")!=SYMLINKS: fail("configured symlink set differs")
 for item in SYMLINKS:
  logical=rel(item["path"],"symlink"); target_relative=rel(item["target"],"symlink target")
  link=repo/logical.as_posix(); target_path=repo/target_relative.as_posix()
  if any(repo.joinpath(*logical.parts[:i]).is_symlink() for i in range(1,len(logical.parts))): fail("configured symlink parent contains symlink")
  if any(repo.joinpath(*target_relative.parts[:i]).is_symlink() for i in range(1,len(target_relative.parts)+1)): fail("configured symlink target contains symlink")
  target=target_path.resolve()
  if not link.is_symlink() or not target.is_relative_to(repo): fail("configured symlink is missing or escaping")
  try: actual=link.resolve(strict=True)
  except (OSError,RuntimeError): fail("configured symlink is dangling or loops")
  if actual!=target or (item["target_type"]=="directory")!=target.is_dir() or (item["target_type"]=="file")!=target.is_file(): fail("configured symlink target differs")
 identities=d.get("source_identities")
 roots_document=json.loads(Path(a.roots).read_text())
 if roots_document.get("schema")!=1: fail("invalid roots declaration schema")
 roots=roots_document.get("roots",[])
 if not isinstance(roots,list) or any(not isinstance(item,dict) for item in roots): fail("invalid roots declaration")
 names=[item.get("name") for item in roots]
 if None in names or len(names)!=len(set(names)): fail("duplicate or missing source root name")
 by_name={item["name"]:item for item in roots}
 expected=[]
 for name,subpath,logical in (("project","apps","."),("nuttx",".","nuttx"),("nuttx-apps",".","nuttx-apps")):
  source=by_name.get(name)
  if not source or not source.get("commit") or not source.get("path"): fail("roots lack config source identity")
  root_label=source["path"]
  if root_label==".": root=repo
  else:
   root_relative=rel(root_label,"source root"); current=repo
   for component in root_relative.parts:
    current/=component
    if current.is_symlink(): fail("source root contains symlink")
   root=current.resolve()
   if not root.is_relative_to(repo): fail("source root escapes repository")
  spec=source["commit"]+('^{tree}' if subpath=='.' else ':'+subpath)
  result=subprocess.run(["git","-C",str(root),"rev-parse",spec],text=True,capture_output=True)
  if result.returncode: fail("source identity object is missing")
  expected.append({"commit":source["commit"],"path":subpath,"root":logical,"tree":result.stdout.strip()})
 if identities!=expected: fail("source identities differ")
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
 declared_links=declaration.get("symlinks")
 expected_links=[dict(item,evidence="evidence/source-closure/config-generation.json") for item in SYMLINKS]
 if declared_links!=expected_links: fail("generated symlink declaration differs")
 print("config-proof: verified 3 outputs")
if __name__=="__main__": main()
