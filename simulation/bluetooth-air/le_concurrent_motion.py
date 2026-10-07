# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Real Classic motor jobs observed alongside changing-distance LE traffic."""
import asyncio
import time

from classic_motor_probe import MotorPeer, require_move


def require_overlap(samples):
    for sample in samples:
        a, b = sample['motor_observations']
        if (a['power'] != 0 and b['power'] != 0 and
                a['speed'] > 1 and b['speed'] < -1):
            return
    raise AssertionError('No distance sample observed alongside powered opposite motor motion')


async def run_with_motion(air, renode, log, frames, errors, step, receipt, classic):
    record = receipt['classic_motors'] = dict(requests=[], replies=[], model_states=[], cases=[])

    async def exercise(dlc, received):
        peer = MotorPeer(dlc, received, renode, log, record)
        await peer.establish_encoder('A', tag='a')
        await peer.establish_encoder('B', tag='b')
        before = [await peer.model(port) for port in 'AB']
        peer.degrees('l001', 'A', 360)
        peer.degrees('l002', 'B', -360)
        receipt['moving_before_distance_change'] = await peer.moving('A', 'B')

        async def observe(sample):
            sample['motor_observations'] = [await peer.model(port) for port in 'AB']
            sample['motors_observed_at_host_s'] = time.monotonic()

        async def replies():
            await peer.collect('l001')
            await peer.collect('l002')

        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(replies())
            tasks.create_task(step.run(frames, errors, receipt.setdefault('distance_step', {}), observe=observe))
        require_overlap(receipt['distance_step']['samples'])
        for index, (port, degrees) in enumerate((('A', 360), ('B', -360))):
            after = await peer.model(port)
            record['cases'].append(dict(case='le-motion-' + port,
                delta=require_move(before[index], after, degrees)))
        await peer.quiet(150)
        record['passed'] = True

    central = (await air.add_peer('le-motion-central', '02:B1:0E:5A:17:C4')).device
    try:
        await classic(central, receipt, motor_action=exercise)
    finally:
        await asyncio.wait_for(air.remove('le-motion-central'), 5)
