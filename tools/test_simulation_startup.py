#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Preprocess the actual boot script across physical and simulation modes."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'boards/spike-prime-hub/src/etc/init.d/rcS'
with tempfile.TemporaryDirectory() as directory:
    include=Path(directory);(include/'nuttx').mkdir();(include/'nuttx/config.h').write_text('')
    def commands(simulation,virtual_hci,hub=True,bluetooth=True,probe=False):
        defines=['CONFIG_APP_DRIVEBASE']
        if hub:defines.append('CONFIG_APP_HUBPROGRAM')
        if bluetooth:defines.append('CONFIG_APP_BTSENSOR')
        if simulation:defines.append('CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK')
        if virtual_hci:defines.append('CONFIG_APP_BTSENSOR_SIM_VIRTUAL_HCI')
        if probe:defines.extend(['CONFIG_APP_PORT','CONFIG_LEGO_LUMP','CONFIG_BUILD_PROTECTED'])
        result=subprocess.check_output(['cc','-E','-P','-x','c','-I'+str(include),*['-D'+name for name in defines],str(SCRIPT)],text=True)
        return [line.strip() for line in result.splitlines() if line.strip()]
    for simulation,virtual_hci,expected in [(False,False,True),(True,False,False),(True,True,True)]:
        actual=commands(simulation,virtual_hci)
        assert actual.count('hubprogram serve')==1,actual
        assert ('btsensor start' in actual)==expected,actual
        assert 'drivebase start' not in actual,actual
    assert commands(True,False,hub=False)==['drivebase start']
    assert commands(False,False,bluetooth=False)==['hubprogram serve']
    # NSH aborts rcS on a failed command. A diagnostic must not prevent normal
    # services starting, including in fixtures with intentionally absent ports.
    assert commands(True,False,probe=True)==['hubprogram serve','port simulation-poll-probe']
    # HCI scenarios may attach F before boot; omit the unattached-F diagnostic
    # there rather than compete for the port's exclusive descriptor.
    assert commands(True,True,probe=True)==['hubprogram serve','btsensor start']
    assert 'port simulation-poll-probe' not in commands(False,False,probe=True)
defconfig=(ROOT/'boards/spike-prime-hub/configs/simulation/defconfig').read_text().splitlines()
assert 'CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK=y' in defconfig
assert '# CONFIG_APP_BTSENSOR_SIM_VIRTUAL_HCI is not set' in defconfig
assert 'CONFIG_APP_BTSENSOR_SIM_VIRTUAL_HCI=y' not in defconfig
hci_defconfig=(ROOT/'boards/spike-prime-hub/configs/simulation-hci/defconfig').read_text().splitlines()
assert hci_defconfig == [
    'CONFIG_APP_BTSENSOR_SIM_VIRTUAL_HCI=y'
    if line == '# CONFIG_APP_BTSENSOR_SIM_VIRTUAL_HCI is not set' else line
    for line in defconfig
], 'HCI qualification profile must differ only by explicit virtual-controller startup'
kconfig=(ROOT/'apps/btsensor/Kconfig').read_text().split('config APP_BTSENSOR_SIM_VIRTUAL_HCI\n',1)[1].split('\nconfig ',1)[0]
assert '\tbool ' in kconfig and '\tdefault n\n' in kconfig
assert '\tdepends on APP_BTSENSOR_SIM_NO_SERVICE_PACK\n' in kconfig
print('startup: physical Bluetooth, TI-free simulation default, explicit virtual HCI and independent hubprogram verified')
