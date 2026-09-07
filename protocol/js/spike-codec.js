// SPDX-License-Identifier: Apache-2.0
'use strict';

const END = 0x02;
const XOR = 0x03;
const BLOCK_MAX = 84;

const cobsEncode = input => {
    const output = [0xff];
    let codeIndex = 0;
    let block = 1;
    for (const byte of input) {
        if (byte <= 2) {
            output[codeIndex] = block + 2 + (byte * BLOCK_MAX);
            codeIndex = output.length;
            output.push(0xff);
            block = 1;
        } else {
            output.push(byte);
            block++;
            if (block > BLOCK_MAX) {
                codeIndex = output.length;
                output.push(0xff);
                block = 1;
            }
        }
    }
    output[codeIndex] = block + 2;
    return Uint8Array.from(output);
};

const cobsDecode = input => {
    if (input.length === 0) throw new Error('empty COBS payload');
    const output = [];
    for (let offset = 0; offset < input.length;) {
        const code = input[offset++];
        if (code <= 2) throw new Error('reserved COBS code');
        let block;
        let delimiter = null;
        if (code === 0xff) {
            block = BLOCK_MAX;
        } else {
            const adjusted = code - 3;
            delimiter = Math.floor(adjusted / BLOCK_MAX);
            block = adjusted % BLOCK_MAX;
            if (delimiter > 2) throw new Error('invalid COBS delimiter');
        }
        if (offset + block > input.length) throw new Error('truncated COBS block');
        for (let i = 0; i < block; i++) output.push(input[offset++]);
        if (delimiter !== null && offset < input.length) output.push(delimiter);
    }
    return Uint8Array.from(output);
};

const pack = (payload, highPriority = false) => {
    const encoded = cobsEncode(payload);
    const frame = new Uint8Array(encoded.length + 1 + (highPriority ? 1 : 0));
    let offset = 0;
    if (highPriority) frame[offset++] = 1;
    for (const byte of encoded) frame[offset++] = byte ^ XOR;
    frame[offset] = END;
    return frame;
};

const unpack = frame => {
    if (frame.length < 2 || frame[frame.length - 1] !== END) throw new Error('unterminated frame');
    const start = frame[0] === 1 ? 1 : 0;
    if (frame.length - start - 1 === 0) throw new Error('empty encoded frame');
    const encoded = frame.slice(start, -1);
    for (let i = 0; i < encoded.length; i++) {
        if (encoded[i] >= 1 && encoded[i] <= 3) throw new Error('unescaped control byte');
        encoded[i] ^= XOR;
    }
    return cobsDecode(encoded);
};

class FrameDecoder {
    constructor({maxFrameSize = 4096, timeoutMs = 5000} = {}) {
        this.maxFrameSize = maxFrameSize;
        this.timeoutMs = timeoutMs;
        this.reset();
    }

    reset() {
        this.low = [];
        this.high = null;
        this.lastByteAt = null;
    }

    expire(nowMs) {
        if (this.lastByteAt !== null && nowMs - this.lastByteAt >= this.timeoutMs) {
            this.reset();
            return true;
        }
        return false;
    }

    push(chunk, nowMs = 0) {
        const payloads = [];
        for (const byte of chunk) {
            this.lastByteAt = nowMs;
            if (byte === 1) {
                this.high = [];
                continue;
            }
            if (byte === END) {
                const active = this.high === null ? this.low : this.high;
                if (active.length > 0) payloads.push(unpack(Uint8Array.from([...active, END])));
                if (this.high === null) this.low = [];
                else this.high = null;
                continue;
            }
            if (byte === 3) {
                this.reset();
                throw new Error('unescaped control byte');
            }
            const active = this.high === null ? this.low : this.high;
            active.push(byte);
            if (active.length > this.maxFrameSize) {
                this.reset();
                throw new Error('frame too large');
            }
        }
        return payloads;
    }
}

module.exports = {FrameDecoder, cobsDecode, cobsEncode, pack, unpack};
