#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regenerate and verify the separately licensed TI payload container."""
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile
from pathlib import Path, PurePosixPath
IMAGE="sha256:8d304601acccf0fd2d6bcbf4e1ec1377b5e89cbdd669a60c1cf5c0e581b3c3fa"; HEX=re.compile(r"[0-9a-f]{64}")
ARGV=["python3","tools/import_ti_service_pack.py","third_party/ti-cc2564c/TIInit_6.12.26.bts","--license","third_party/ti-cc2564c/LICENSE.ti","--output-dir","$OUTPUT"]
INPUTS={"tools/import_ti_service_pack.py","policy/ti-service-packs.json","third_party/ti-cc2564c/TIInit_6.12.26.bts","third_party/ti-cc2564c/LICENSE.ti"}
OUTPUTS={"TIInit_6.12.26.bts","LICENSE.ti","import-manifest.json","ti_bts_local_payload.h"}
BOUNDARY={"concluded":"NOASSERTION","scope":"TI-licensed CC2564C controller firmware; not project-licensed","license_path":"third_party/ti-cc2564c/LICENSE.ti","device_restriction":"TI CC2564C"}
def fail(s): raise SystemExit("ti-payload-proof: ERROR: "+s)
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def regular(repo,name,label):
 p=PurePosixPath(name) if isinstance(name,str) else PurePosixPath()
 if p.is_absolute() or not p.parts or ".." in p.parts: fail(label+" path is unsafe")
 q=repo
 for part in p.parts:
  q/=part
  if q.is_symlink(): fail(label+" path contains symlink")
 if not q.is_file() or not q.resolve().is_relative_to(repo): fail(label+" is missing or escaping")
 return q
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--proof",required=True); ap.add_argument("--repository",required=True); ap.add_argument("--declaration",required=True); a=ap.parse_args()
 repo=Path(a.repository).resolve(); d=json.loads(Path(a.proof).read_text())
 if d.get("schema")!="brickwright/ti-payload-generation-proof/v1" or d.get("status")!="exact-output-match": fail("invalid proof header")
 if d.get("container_image")!=IMAGE or d.get("isolation")!={"network_namespace":"none","successful_connects":0}: fail("invalid isolation identity")
 if d.get("generator_argv")!=ARGV: fail("generator argv differs")
 boundary=d.get("license_boundary",{})
 if boundary!=BOUNDARY: fail("invalid TI license boundary")
 inputs={}
 input_items=d.get("inputs")
 if not isinstance(input_items,list) or not input_items: fail("invalid inputs")
 for item in input_items:
  if not isinstance(item,dict): fail("invalid input")
  name=item.get("path"); path=regular(repo,name,"input")
  if name in inputs or not HEX.fullmatch(item.get("sha256",'')) or digest(path)!=item["sha256"]: fail("input duplicate or changed")
  inputs[name]=item["sha256"]
 if set(inputs)!=INPUTS: fail("input set mismatch")
 expected={}
 output_items=d.get("outputs")
 if not isinstance(output_items,list) or not output_items: fail("invalid outputs")
 for item in output_items:
  if not isinstance(item,dict) or item.get("path") in expected or item.get("path") not in OUTPUTS or not HEX.fullmatch(item.get("sha256",'')) or not isinstance(item.get("size"),int): fail("invalid output declaration")
  expected[item["path"]]=(item["sha256"],item["size"])
 if set(expected)!=OUTPUTS: fail("output set mismatch")
 declaration=json.loads(Path(a.declaration).read_text()); files=declaration.get("files")
 if not isinstance(files,list): fail("invalid generated declaration")
 matches=[x for x in files if isinstance(x,dict) and x.get("path")==".local/ti/cc2564c/ti_bts_local_payload.h"]
 if declaration.get("schema")!="brickwright/generated-build-inputs/v1" or len(matches)!=1 or matches[0].get("sha256")!=expected["ti_bts_local_payload.h"][0] or matches[0].get("license_boundary")!=boundary or matches[0].get("generator_argv")!=ARGV: fail("generated declaration differs")
 with tempfile.TemporaryDirectory(prefix="brickwright-ti-proof-") as tmp:
  docker=["docker"] if shutil.which("docker") and os.access("/var/run/docker.sock",os.W_OK) else ["sudo","-n","docker"]
  command=docker+["run","--rm","--network","none","--read-only","--tmpfs","/tmp","--user",f"{os.getuid()}:{os.getgid()}","-v",str(repo)+":/src:ro","-v",tmp+":/out","-w","/src",IMAGE]+ARGV[:-1]+["/out"]
  result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
  if result.returncode: fail("network-none regeneration failed")
  found={p.name for p in Path(tmp).iterdir()}
  if found!=OUTPUTS: fail("regenerated output set differs")
  for name,(sha,size) in expected.items():
   path=regular(Path(tmp).resolve(),name,"regenerated output")
   if path.stat().st_size!=size or digest(path)!=sha: fail("regenerated output differs: "+name)
 print("ti-payload-proof: verified restricted output without emitting payload bytes")
if __name__=="__main__": main()
