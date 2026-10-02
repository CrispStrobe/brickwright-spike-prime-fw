// SPDX-License-Identifier: MIT
using System;
using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals.I2C;
using Antmicro.Renode.Peripherals.SPI;

namespace Antmicro.Renode.Peripherals.SPIKEPrime
{
    // Deterministic LSM6DS3TR-C subset used by the SPIKE board driver.
    public sealed class LSM6DS3TRC : II2CPeripheral
    {
        public LSM6DS3TRC()
        {
            registers = new byte[256];
            Reset();
        }

        public void Reset()
        {
            Array.Clear(registers, 0, registers.Length);
            registers[WhoAmI] = 0x6a;
            pointer = 0;
        }

        public void Write(byte[] data)
        {
            if(data.Length == 0) return;
            pointer = data[0];
            for(var i = 1; i < data.Length; ++i)
            {
                var address = pointer++;
                // SW_RESET completes immediately, as it may on real silicon
                // before the driver's first 1 ms poll.
                registers[address] = address == Ctrl3C && (data[i] & 1) != 0
                    ? (byte)0 : data[i];
            }
        }

        public byte[] Read(int count)
        {
            var result = new byte[count];
            for(var i = 0; i < count; ++i) result[i] = registers[pointer++];
            return result;
        }

        public void FinishTransmission() { }

        private const byte WhoAmI = 0x0f;
        private const byte Ctrl3C = 0x12;
        private readonly byte[] registers;
        private byte pointer;
    }

    // Write-only TLC5955 sink. Frames are retained for deterministic test
    // inspection while the firmware drives the real STM32 SPI controller.
    public sealed class TLC5955 : ISPIPeripheral
    {
        public TLC5955() { Reset(); }
        public byte Transmit(byte data)
        {
            if(frameLength < lastFrame.Length) lastFrame[frameLength] = data;
            frameLength++;
            totalBytes++;
            return 0;
        }
        public void FinishTransmission() { frameLength = 0; frames++; }
        public void Reset()
        {
            Array.Clear(lastFrame, 0, lastFrame.Length);
            frameLength = 0;
            frames = 0;
            totalBytes = 0;
        }
        public long Frames => frames;
        public long TotalBytes => totalBytes;
        private readonly byte[] lastFrame = new byte[97];
        private int frameLength;
        private long frames;
        private long totalBytes;
    }

    // Command-level W25Q256JV subset: JEDEC/status/probe plus the 4-byte
    // read/program/erase commands used by the NuttX MTD and LittleFS path.
    public sealed class W25Q256JV : ISPIPeripheral
    {
        public W25Q256JV()
        {
            storage = new byte[32 * 1024 * 1024];
            Reset();
        }

        public byte Transmit(byte data)
        {
            if(position++ == 0)
            {
                command = data;
                address = 0;
                if(command == 0x06) writeEnable = true;
                if(command == 0xc7 && writeEnable)
                {
                    Array.Fill(storage, (byte)0xff);
                    writeEnable = false;
                }
                return 0;
            }
            switch(command)
            {
                case 0x9f:
                    return position == 2 ? (byte)0xef : position == 3 ? (byte)0x40 : (byte)0x19;
                case 0x05:
                    return writeEnable ? (byte)0x02 : (byte)0;
                case 0x35:
                    return 0;
                case 0x0c:
                    if(position <= 5) { address = (address << 8) | data; return 0; }
                    if(position == 6) return 0; // fast-read dummy byte
                    return storage[address++ % storage.Length];
                case 0x12:
                    if(position <= 5) { address = (address << 8) | data; return 0; }
                    if(writeEnable) storage[address++ % storage.Length] &= data;
                    return 0;
                case 0x21:
                case 0xdc:
                    if(position <= 5) address = (address << 8) | data;
                    return 0;
                default:
                    return 0;
            }
        }

        public void FinishTransmission()
        {
            if(writeEnable && (command == 0x21 || command == 0xdc) && position >= 5)
            {
                var size = command == 0x21 ? 4096 : 65536;
                var start = (int)(address & ~(uint)(size - 1));
                Array.Fill(storage, (byte)0xff, start, size);
                writeEnable = false;
            }
            else if(command == 0x12) writeEnable = false;
            position = 0;
            command = 0;
            address = 0;
        }

        public void Reset()
        {
            Array.Fill(storage, (byte)0xff);
            position = 0;
            command = 0;
            address = 0;
            writeEnable = false;
        }

        private readonly byte[] storage;
        private int position;
        private byte command;
        private uint address;
        private bool writeEnable;
    }
}
