# SPDX-License-Identifier: Apache-2.0
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
TOOL=Path(__file__).resolve().parents[1]/"tools/capture_arm_invocation.py"
class CaptureTest(unittest.TestCase):
 def test_compile_depfile_and_link_response_are_preserved(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw); real=root/"real"; wrappers=root/"wrappers"; capture=root/"capture"; real.mkdir()
   fake=real/"arm-none-eabi-gcc"; fake.write_text("#!/bin/sh\nexit 0\n"); fake.chmod(0o755)
   ar=real/"arm-none-eabi-ar"; ar.write_text("#!/bin/sh\ntouch \"$2\"\n"); ar.chmod(0o755)
   subprocess.run([sys.executable,TOOL,"prepare",wrappers],check=True)
   env={**os.environ,"BRICKWRIGHT_REAL_ARM_BIN":str(real),"BRICKWRIGHT_CAPTURE_DIR":str(capture)}
   subprocess.run([wrappers/"arm-none-eabi-gcc","-c","x.c","-o","x.o"],cwd=root,env=env,check=True)
   compile_doc=json.loads(next((capture/"compiles").glob("*.json")).read_text()); self.assertTrue(compile_doc["depfile"].endswith(".d"))
   subprocess.run([wrappers/"arm-none-eabi-gcc","-M","x.c"],cwd=root,env=env,check=True)
   self.assertFalse((capture/"links").exists())
   subprocess.run([wrappers/"arm-none-eabi-gcc","-E","x.c","-o","generated.i"],cwd=root,env=env,check=True)
   generator=json.loads(next((capture/"generators").glob("*.json")).read_text())
   self.assertIn("-E",generator["argv"]); self.assertFalse((capture/"links").exists())
   (root/"args.rsp").write_text("x.o -Map=firmware.map")
   (root/"kernel.ld").write_text("SECTIONS {}\n")
   subprocess.run([wrappers/"arm-none-eabi-gcc","@args.rsp","-T","kernel.ld","-o","firmware"],cwd=root,env=env,check=True)
   link_doc=json.loads(next((capture/"links").glob("*.json")).read_text()); self.assertEqual(1,len(link_doc["response_files"]))
   self.assertEqual((root/"args.rsp").read_bytes(),next((capture/"responses").glob("*.rsp")).read_bytes())
   self.assertEqual("kernel.ld",link_doc["link_inputs"][0]["argument"])
   self.assertEqual((root/"kernel.ld").read_bytes(),next((capture/"link-inputs").glob("*.bin")).read_bytes())
   subprocess.run([wrappers/"arm-none-eabi-ar","rcs","libx.a","x.o"],cwd=root,env=env,check=True)
   archive=json.loads(next((capture/"archives").glob("*.json")).read_text()); self.assertEqual("libx.a",archive["output"]); self.assertTrue(archive["output_sha256"])
if __name__=="__main__": unittest.main()
