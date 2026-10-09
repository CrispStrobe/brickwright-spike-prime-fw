#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Compile actual host boundaries; demand assertion failures for source mutants.

Run on hosted CI with the ordinary hubprogram controls. No ARM image or emulator
is executed. Mutation failures must name the intended new control function.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    variants = [
        ('session', 'device.c', 'if(g_sensor_sessions[port] && sample.session!=g_sensor_sessions[port])', 'if(0)', 'control', 'explicit_sensor_tests'),
        ('sticky', 'device.c', 'if(g_sensor_stale[port])return -ESTALE;', 'if(0)return -ESTALE;', 'control', 'explicit_sensor_tests'),
        ('port', 'device.c', 'explicit_distance((predicate-0x100)>>3,value)', 'explicit_distance(3,value)', 'control', 'explicit_sensor_tests'),
        ('type', 'device.c', 'else if(info.type_id!=type)return -ENODEV;', 'else if(0)return -ENODEV;', 'control', 'explicit_sensor_tests'),
        ('lifecycle', 'service.c', 'g_program.state!=BW_PROGRAM_RUNNING || !value || !g_program.io.sensor', '!value || !g_program.io.sensor', 'service', 'sensor_lifecycle_guards'),
        ('polarity', 'program.c', 'if (selector==1 || selector==5) return value<threshold;', 'if (selector==1 || selector==5) return value>threshold;', 'program', 'explicit_distance_conditions'),
        ('unknown', 'program.c', 'if ((selector==1 || selector==2) && value<0) return 0;', 'if (0) return 0;', 'program', 'explicit_distance_conditions'),
        ('conditional', 'program.c', 'p->pc=rc ? (uint32_t)ins->c : p->pc+1;', 'p->pc=rc ? p->pc+1 : (uint32_t)ins->c;', 'program', 'explicit_distance_conditions'),
    ]
    for name, filename, old, new, target, assertion in variants:
        with tempfile.TemporaryDirectory(prefix='bw-sensor-mutant-') as owned:
            tree = Path(owned)
            app = tree/'apps/hubprogram'; app.mkdir(parents=True)
            for source in (ROOT/'apps/hubprogram').glob('*'):
                if source.is_file() and source.suffix in ('.c','.h'):
                    shutil.copyfile(source,app/source.name)
            (app/'test').mkdir()
            for fixture in ('service_test.c', 'program_test.c'):
                shutil.copyfile(ROOT/'apps/hubprogram/test'/fixture, app/'test'/fixture)
            controls = tree/'tests/hubprogram';controls.mkdir(parents=True)
            shutil.copyfile(ROOT/'tests/hubprogram/control_test.c',controls/'control_test.c')
            path=app/filename;source=path.read_text()
            assert source.count(old)==1, 'Mutation binding changed: '+name
            path.write_text(source.replace(old,new))
            output=tree/'control'
            cc=[os.environ.get('CC','cc'),'-std=c99','-Wall','-Wextra','-Werror']
            if target=='control':
                cc += ['-I'+str(ROOT/'tests/hubprogram/include'),'-I'+str(ROOT/'boards/spike-prime-hub/include'),str(app/'motor.c'),str(controls/'control_test.c')]
            elif target=='program':
                cc += [str(app/'program.c'),str(app/'upload.c'),str(app/'test/program_test.c')]
            else:
                cc += [str(app/'program.c'),str(app/'upload.c'),str(app/'test/service_test.c'),'-pthread']
            subprocess.run(cc+['-o',str(output)],check=True,capture_output=True,text=True)
            run=subprocess.run([str(output)],capture_output=True,text=True)
            assert run.returncode != 0 and assertion in run.stderr and 'Assertion' in run.stderr, 'Mutant escaped intended assertion: '+name
            print('Assertion-detected sensor mutant:',name)

if __name__=='__main__':main()
