// SPDX-License-Identifier: MIT
using System;
using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals;
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

    // TLC5955 digital SPI/LAT subset, following TI SBVS237 sections 8.3.2.1-7.
    // Reset deterministically clears state that is unspecified at power-on.
    // No analog current, GSCLK/PWM timing, SID or SOUT behavior is modeled.
    public sealed class TLC5955 : ISPIPeripheral, IGPIOReceiver
    {
        public TLC5955() { Reset(); }

        public byte Transmit(byte data)
        {
            // SIN enters bit 0, MSB first: one byte shifts the previous data
            // eight positions towards bit 768, discarding the oldest bits.
            for(var i = shift.Length - 1; i > 0; --i) shift[i] = shift[i - 1];
            shift[shift.Length - 1] &= 1;
            shift[0] = data;
            totalBytes++;
            return 0; // SOUT is deliberately outside this digital subset.
        }

        public void FinishTransmission() { }

        public void OnGPIO(int number, bool value)
        {
            if(number != 0) throw new ArgumentOutOfRangeException(nameof(number), "Only LAT input 0 is supported");
            var rising = value && !lat;
            lat = value;
            if(!rising) return;
            if(shift[96] == 0)
            {
                Array.Copy(shift, grayscale, grayscale.Length);
                grayscaleLatches++;
                return;
            }
            if(shift[95] != 0x96)
            {
                invalidControlLatches++;
                return;
            }
            Array.Copy(shift, control, control.Length);
            control[46] &= 7; // Only bits 370:0 belong to the control latch.
            var incomingMc = GetBits(control, 336, 9);
            if(hasPreviousMc && incomingMc == previousMc) maximumCurrent = incomingMc;
            previousMc = incomingMc;
            hasPreviousMc = true;
            controlLatches++;
        }

        public void Reset()
        {
            Array.Clear(shift, 0, shift.Length);
            Array.Clear(grayscale, 0, grayscale.Length);
            Array.Clear(control, 0, control.Length);
            lat = false;
            hasPreviousMc = false;
            maximumCurrent = previousMc = 0;
            grayscaleLatches = controlLatches = invalidControlLatches = totalBytes = 0;
        }

        // Chip output 0 is OUTR0 (bits 15:0); output 47 is OUTB15.
        public ushort GetGrayscale(int output)
        {
            CheckIndex(output, 48);
            return (ushort)GetBits(grayscale, output * 16, 16);
        }

        // The first serialized firmware word corresponds to chip output 47.
        public ushort GetWireWord(int index)
        {
            CheckIndex(index, 48);
            return GetGrayscale(47 - index);
        }

        // DC is the stored control value, not a modeled analog output level.
        public byte GetControlDotCorrection(int output)
        {
            CheckIndex(output, 48);
            return (byte)GetBits(control, output * 7, 7);
        }

        // Color indices 0/1/2 are R/G/B, matching the control bit assignments.
        public byte GetMaximumCurrent(int color)
        {
            CheckIndex(color, 3);
            return (byte)((maximumCurrent >> (color * 3)) & 7);
        }

        public byte GetControlBrightness(int color)
        {
            CheckIndex(color, 3);
            return (byte)GetBits(control, 345 + color * 7, 7);
        }

        public byte ControlFunction => (byte)GetBits(control, 366, 5);
        public long Frames => grayscaleLatches + controlLatches;
        public long GrayscaleLatches => grayscaleLatches;
        public long ControlLatches => controlLatches;
        public long InvalidControlLatches => invalidControlLatches;
        public long TotalBytes => totalBytes;

        private static void CheckIndex(int index, int count)
        {
            if(index < 0 || index >= count) throw new ArgumentOutOfRangeException(nameof(index));
        }

        private static int GetBits(byte[] data, int offset, int width)
        {
            var value = 0;
            for(var bit = 0; bit < width; ++bit)
                value |= ((data[(offset + bit) / 8] >> ((offset + bit) % 8)) & 1) << bit;
            return value;
        }

        private readonly byte[] shift = new byte[97];
        private readonly byte[] grayscale = new byte[96];
        private readonly byte[] control = new byte[47];
        private bool lat;
        private bool hasPreviousMc;
        private int maximumCurrent;
        private int previousMc;
        private long grayscaleLatches;
        private long controlLatches;
        private long invalidControlLatches;
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
