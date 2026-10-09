# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Observe the exact Runtime snapshot adapter on our real protected guest.

No listener, guest-memory writes, program substitution or reference image.
Include the pinned Runtime's state server before this fixture.
"""


def mc_check_addressed_runtime_capability(base, marker, user_path):
    import hashlib
    from Antmicro.Renode.Core import EmulationManager
    from Antmicro.Renode.Time import TimeInterval
    from System import UInt64
    base, marker = int(str(base), 0), int(str(marker), 0)
    user_path = str(user_path).lstrip('@')
    hub = monitor.Machine
    if not hub.IsPaused:
        raise AssertionError('Live capability probe requires paused guest')
    with open(user_path, 'rb') as stream:
        digest = hashlib.sha256(stream.read()).hexdigest()
    metadata = dict(abi=1, address=marker, userspaceSha256=digest)
    config = dict(identity=dict(board='spike-prime', firmware='brickwright-nuttx',
                  transport='none', imageSha256=digest), paths={}, programMailbox=base,
                  addressedSensorCapability=metadata)
    validate_config(config)
    expected = 'nuttx-addressed-distance/v1'
    retries = 0
    for retry in range(20):
        try:
            frame = _snapshot(config, 1, 1)
            break
        except ValueError as error:
            if str(error) != 'full-firmware publication is not ready or changed':
                raise
            retries += 1
            EmulationManager.Instance.CurrentEmulation.RunFor(TimeInterval.FromMilliseconds(UInt64(10)))
            if not hub.IsPaused:
                raise AssertionError('Capability retry did not leave guest paused')
    else:
        raise AssertionError('No stable real guest publication within bounded retries')
    if expected not in frame['target']['capabilities']:
        raise AssertionError('Actual guest marker did not yield addressed capability')
    legacy = dict(config)
    del legacy['addressedSensorCapability']
    legacy_frame = _snapshot(legacy, 2, 1)
    if expected in legacy_frame['target']['capabilities']:
        raise AssertionError('Legacy config falsely advertised addressed capability')
    foreign = dict(config, addressedSensorCapability=dict(metadata, userspaceSha256='0'*64))
    try:
        validate_config(foreign)
    except ValueError:
        pass
    else:
        raise AssertionError('Foreign image metadata accepted')
    if not hub.IsPaused:
        raise AssertionError('Capability observation changed paused state')
    print('ARM live addressed Runtime capability passed: live=1 legacy=0 foreign=refused retries=%d imageSha256=%s' % (retries, digest))
