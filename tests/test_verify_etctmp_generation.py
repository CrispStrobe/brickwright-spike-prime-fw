# SPDX-License-Identifier: Apache-2.0
import hashlib, json, subprocess, sys, tempfile, unittest
from pathlib import Path
TOOL = Path(__file__).resolve().parents[1] / "tools/verify_etctmp_generation.py"
class TestEtctmpProof(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.repo = Path(self.tmp.name)
        (self.repo / "in").write_text("input"); out = self.repo / "out"; out.mkdir(); (out / "rcS").write_text("output")
        self.proof = self.repo / "proof.json"
        self.data = {"schema":"brickwright/etctmp-generation-proof/v1", "status":"exact-output-match",
          "container_image":"sha256:8d304601acccf0fd2d6bcbf4e1ec1377b5e89cbdd669a60c1cf5c0e581b3c3fa", "isolation":{"network_namespace":"none","successful_connects":0},
          "generator_commands":[], "output_root":"boards/spike-prime-hub/src/etctmp/etc/init.d",
          "generator_inputs":[], "outputs":[]}
        for path in ("boards/spike-prime-hub/src/etc/init.d/rcS", "boards/spike-prime-hub/src/etc/init.d/rc.sysinit", "nuttx/include/nuttx/config.h"):
            target=self.repo/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_text("input"); self.data["generator_inputs"].append({"path":path,"sha256":hashlib.sha256(b"input").hexdigest()})
        target=self.repo/self.data["output_root"]; target.mkdir(parents=True); (target/"rcS").write_text("output"); (target/"rc.sysinit").write_text("")
        self.data["outputs"]=[{"path":"rcS","sha256":hashlib.sha256(b"output").hexdigest()},{"path":"rc.sysinit","sha256":hashlib.sha256(b"").hexdigest()}]
        def cmd(s): return ["arm-none-eabi-gcc","-E","-P","-x","c","-isystem","$REPOSITORY/nuttx/include","-isystem","$REPOSITORY/nuttx/include/newlib","-D__NuttX__","-D__KERNEL__","etc/init.d/"+s,"-o","$OUTPUT/"+s]
        self.data["generator_commands"]=[cmd("rc.sysinit"),cmd("rcS")]
    def tearDown(self): self.tmp.cleanup()
    def invoke(self, ok=True):
        self.proof.write_text(json.dumps(self.data)); result=subprocess.run([sys.executable,str(TOOL),"--proof",self.proof,"--repository",self.repo],text=True,capture_output=True)
        self.assertEqual(ok,result.returncode==0,result.stderr); return result
    def test_exact(self): self.invoke()
    def test_hash_drift(self): self.data["outputs"][0]["sha256"]="0"*64; self.invoke(False)
    def test_missing_extra_and_unsafe_fail(self):
        self.data["outputs"].append({"path":"missing","sha256":"0"*64}); self.invoke(False)
        self.data["outputs"]=self.data["outputs"][:1]; self.data["generator_inputs"][0]["path"]="../in"; self.invoke(False)
    def test_isolation_and_image_fail(self):
        self.data["isolation"]["network_namespace"]="host"; self.invoke(False)
        self.data["isolation"]={"network_namespace":"none","successful_connects":0}; self.data["container_image"]="sha256:bad"; self.invoke(False)
    def test_symlink_output_fails(self):
        path=self.repo/self.data["output_root"]/"rcS"; path.unlink(); path.symlink_to(self.repo/"in"); self.invoke(False)
if __name__ == "__main__": unittest.main()
