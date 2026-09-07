// SPDX-License-Identifier: Apache-2.0
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {FrameDecoder, pack, unpack} = require('./spike-codec');

const hex = value => Uint8Array.from(Buffer.from(value, 'hex'));
const asHex = value => Buffer.from(value).toString('hex');
const fixtures = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'spike-cobs-v1.json')));

for (const vector of fixtures.vectors) {
    assert.equal(asHex(pack(hex(vector.payload_hex))), vector.frame_hex, `${vector.name} encode`);
    assert.equal(asHex(unpack(hex(vector.frame_hex))), vector.payload_hex, `${vector.name} decode`);
}

for (const test of fixtures.stream_cases) {
    const decoder = new FrameDecoder();
    const actual = test.chunks_hex.flatMap((chunk, index) => decoder.push(hex(chunk), index));
    assert.deepEqual(actual.map(asHex), test.payloads_hex, test.name);
}

for (const invalid of fixtures.invalid_frames_hex) {
    assert.throws(() => unpack(hex(invalid)), undefined, `invalid ${invalid}`);
}

const timed = new FrameDecoder({timeoutMs: 10});
timed.push(hex('0700'), 1);
assert.equal(timed.expire(11), true);
assert.deepEqual(timed.push(hex('000002'), 12).map(asHex), ['00'], 'timeout clears partial frame');

const reconnect = new FrameDecoder();
reconnect.push(hex('0700'), 1);
reconnect.reset();
assert.deepEqual(reconnect.push(hex('000002'), 2).map(asHex), ['00'], 'reconnect clears partial frame');

const bounded = new FrameDecoder({maxFrameSize: 2});
assert.throws(() => bounded.push(hex('000000'), 0), /too large/);

console.log('JavaScript spike codec: all fixture and lifecycle cases passed');
