# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Private exact-media custody for the own-guest cold calibration experiment."""
import asyncio
import hashlib
import json
from pathlib import Path
import re
import uuid

SIZE=32*1024*1024


def image_hashes(images):
    return {key:hashlib.sha256((images/name).read_bytes()).hexdigest()
            for key,name in [('kernelSha256','nuttx'),('userspaceSha256','nuttx_user.elf')]}


def validate_medium(path, images):
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=SIZE:
        raise ValueError('Cold medium must be a regular complete 32 MiB NOR image')
    sidecar=Path(str(path)+'.json')
    if sidecar.is_symlink() or not sidecar.is_file() or sidecar.stat().st_size>4096:
        raise ValueError('Cold medium requires a regular bounded identity receipt')
    receipt=json.loads(sidecar.read_text())
    expected={'schema':1,'kind':'own-guest-calibration-medium','bytes':SIZE,
              'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),**image_hashes(images)}
    if not isinstance(receipt,dict) or type(receipt.get('schema')) is not int or receipt!=expected:
        raise ValueError('Cold medium or own image identity mismatch')
    return receipt


async def save_medium(process, path, images, log):
    if path.exists() or Path(str(path)+'.json').exists():
        raise ValueError('Cold medium output exists; preserve prior evidence')
    if re.search(r'[\s"\'@;\\]',str(path)):
        raise ValueError('Cold medium output contains monitor metacharacters')
    tag=uuid.uuid4().hex
    marker=('COLD_FLASH '+tag).encode()
    offset=log.stat().st_size
    helper=path.parent/'cold-flash-export.py'
    # The monitor pauses before taking the read-only snapshot. Never reach into
    # private model fields, the guest's RAM, a file cache or a return register.
    helper.write_text('from System.IO import File,FileMode\n'
        'def mc_cold_flash_export(path,tag):\n'
        '    if not monitor.Machine.IsPaused: raise ValueError("Pause before medium export")\n'
        '    data=monitor.Machine["sysbus.spi2.flashMux.norFlash"].SnapshotStorage()\n'
        '    stream=File.Open(str(path),FileMode.CreateNew)\n'
        '    try: stream.Write(data,0,len(data))\n'
        '    finally: stream.Close()\n'
        '    monitor.Parse(\'log "COLD_FLASH \'+str(tag)+\'"\')\n')
    process.stdin.write(('pause\ninclude @'+str(helper)+'\ncold_flash_export "'+str(path)+'" "'+tag+'"\n').encode())
    await process.stdin.drain()
    async with asyncio.timeout(30):
        while True:
            if process.returncode is not None:raise ValueError('Emulator exited before medium export')
            with log.open('rb') as stream:
                stream.seek(offset);observed=stream.read(1024*1024)
            if marker in observed:break
            await asyncio.sleep(.05)
    if path.stat().st_size!=SIZE:raise ValueError('Incomplete exported medium')
    path.chmod(0o600)
    receipt={'schema':1,'kind':'own-guest-calibration-medium','bytes':SIZE,
             'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),**image_hashes(images)}
    sidecar=Path(str(path)+'.json')
    with sidecar.open('x') as output:output.write(json.dumps(receipt,indent=2)+'\n')
    sidecar.chmod(0o600)
    return receipt
