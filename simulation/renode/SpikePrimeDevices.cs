// SPDX-License-Identifier: MIT
using System;
using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals;
using Antmicro.Renode.Peripherals.I2C;
using Antmicro.Renode.Peripherals.SPI;
using Antmicro.Renode.Peripherals.Timers;

namespace Antmicro.Renode.Peripherals.SPIKEPrime
{
    // Synthetic paired acquisition subset. Register/routing semantics follow ST
    // AN5130 sections 4.2-4.4; no FIFO or physical motion. Periodic synthetic
    // feeding is explicitly armed, bounded and disabled by default.
    public sealed class LSM6DS3TRC : II2CPeripheral
    {
        public LSM6DS3TRC(IMachine machine)
        {
            INT1 = new GPIO();
            fixtureTimer = new LimitTimer(machine.ClockSource, 1, this, "fixture",
                limit: 1, enabled: false, eventEnabled: true);
            fixtureTimer.LimitReached += FixtureTick;
            Reset();
        }

        public GPIO INT1 { get; private set; }

        // Nonmutating atomic observation for synthetic fixture receipts. Unlike
        // I2C pointer selection, this cannot interrupt a guest bus transaction.
        public byte[] GetFixtureState()
        {
            lock(sync)
            {
                return new[] { registers[Ctrl1XL], registers[Ctrl2G], registers[Status] };
            }
        }

        // Explicit fixture command, gyro XYZ then accel XYZ, signed raw counts.
        // Returns false while powered down or while an earlier paired sample is
        // unread. This bounded fixture admission policy preserves pair identity;
        // it does not claim to reproduce silicon overrun/BDU timing.
        public bool InjectSample(int gx, int gy, int gz, int ax, int ay, int az)
        {
            var values = new[] { gx, gy, gz, ax, ay, az };
            foreach(var value in values)
            {
                if(value < short.MinValue || value > short.MaxValue)
                    throw new ArgumentOutOfRangeException(nameof(value), "Raw sample must fit signed 16 bits");
            }
            lock(sync)
            {
                if(!PairEnabled || unreadOutputs != 0) return false;
                for(var i = 0; i < values.Length; ++i)
                {
                    registers[OutGyro + 2 * i] = (byte)values[i];
                    registers[OutGyro + 2 * i + 1] = (byte)(values[i] >> 8);
                }
                registers[Status] = 3;
                unreadOutputs = 0xfff;
                if((registers[PulseConfig] & 0x80) != 0)
                {
                    // Digital edge only: the silicon's 75 us pulse width is
                    // deliberately not simulated by this explicit fixture.
                    if((registers[Int1Control] & 3) != 0) INT1.Blink();
                }
                else UpdateInterrupt();
                return true;
            }
        }

        // Attempt exactly one paired synthetic sample per configured guest-time
        // ODR period. Unread pairs are skipped rather than overwritten/retried.
        // The tick bound limits both successful and skipped attempts. Mismatched
        // accel/gyro rates are outside this paired fixture and cannot be armed.
        public bool StartFixtureFeed(int gx, int gy, int gz, int ax, int ay, int az, int ticks)
        {
            var values = new[] { gx, gy, gz, ax, ay, az };
            foreach(var value in values)
                if(value < short.MinValue || value > short.MaxValue)
                    throw new ArgumentOutOfRangeException(nameof(value), "Raw sample must fit signed 16 bits");
            if(ticks < 1 || ticks > 10000)
                throw new ArgumentOutOfRangeException(nameof(ticks), "Fixture tick count must be 1..10000");
            lock(sync)
            {
                if(fixtureActive || !PairEnabled ||
                   (registers[Ctrl1XL] >> 4) != (registers[Ctrl2G] >> 4)) return false;
                fixtureValues = values;
                fixtureFrequency = OdrHz[registers[Ctrl1XL] >> 4];
                fixtureAttempts = fixtureAccepted = fixtureSkipped = 0;
                fixtureRemaining = ticks;
                fixtureTimer.Frequency = (ulong)fixtureFrequency;
                fixtureTimer.ResetValue();
                fixtureActive = true;
                fixtureTimer.Enabled = true;
                return true;
            }
        }

        public void StopFixtureFeed()
        {
            lock(sync)
            {
                fixtureActive = false;
                fixtureTimer.Enabled = false;
            }
        }

        // Atomic copied diagnostics: active, Hz, attempted, accepted, skipped,
        // remaining. Stopping retains counters and any published unread pair.
        public long[] GetFixtureFeedState()
        {
            lock(sync)
            {
                return new long[] { fixtureActive ? 1 : 0, fixtureFrequency,
                    fixtureAttempts, fixtureAccepted, fixtureSkipped, fixtureRemaining };
            }
        }

        private void FixtureTick()
        {
            lock(sync)
            {
                if(!fixtureActive) return;
                fixtureAttempts++;
                fixtureRemaining--;
                if(InjectSample(fixtureValues[0], fixtureValues[1], fixtureValues[2],
                                fixtureValues[3], fixtureValues[4], fixtureValues[5]))
                    fixtureAccepted++;
                else fixtureSkipped++;
                if(fixtureRemaining == 0) StopFixtureFeed();
            }
        }

        public void Reset()
        {
            lock(sync)
            {
                StopFixtureFeed();
                fixtureFrequency = fixtureAttempts = fixtureAccepted = fixtureSkipped = fixtureRemaining = 0;
                fixtureValues = null;
                fixtureTimer.ResetValue();
                Array.Clear(registers, 0, registers.Length);
                registers[WhoAmI] = 0x6a;
                registers[Ctrl3C] = 4; // IF_INC reset value.
                pointer = 0;
                unreadOutputs = 0;
                INT1.Unset();
            }
        }

        public void Write(byte[] data)
        {
            if(data == null) throw new ArgumentNullException(nameof(data));
            lock(sync)
            {
                if(data.Length == 0) return;
                pointer = data[0];
                for(var i = 1; i < data.Length; ++i)
                {
                    var address = pointer;
                    if(address == Ctrl3C && (data[i] & 1) != 0)
                    {
                        Reset();
                        return;
                    }
                    if((address == Ctrl1XL || address == Ctrl2G) &&
                       (registers[address] >> 4) != (data[i] >> 4))
                        StopFixtureFeed();
                    if(address != WhoAmI && address != Status &&
                       !(address >= OutGyro && address < OutGyro + 12))
                        registers[address] = data[i];
                    if(!PairEnabled)
                    {
                        registers[Status] = 0;
                        unreadOutputs = 0;
                    }
                    UpdateInterrupt();
                    if((registers[Ctrl3C] & 4) != 0) pointer++;
                }
            }
        }

        public byte[] Read(int count)
        {
            if(count < 0 || count > 256) throw new ArgumentOutOfRangeException(nameof(count));
            lock(sync)
            {
                var result = new byte[count];
                for(var i = 0; i < count; ++i)
                {
                    var address = pointer;
                    result[i] = registers[address];
                    if(address >= OutGyro && address < OutGyro + 12)
                        unreadOutputs &= (ushort)~(1 << (address - OutGyro));
                    // Reading any output high byte acknowledges that sensor's
                    // latched DRDY, as specified by AN5130 section 4.3.
                    if(address == 0x23 || address == 0x25 || address == 0x27)
                        registers[Status] &= 0xfd;
                    if(address == 0x29 || address == 0x2b || address == 0x2d)
                        registers[Status] &= 0xfe;
                    if((registers[Ctrl3C] & 4) != 0) pointer++;
                }
                UpdateInterrupt();
                return result;
            }
        }

        public void FinishTransmission() { }

        private bool PairEnabled
        {
            get { return ValidOdr(registers[Ctrl1XL]) && ValidOdr(registers[Ctrl2G]); }
        }

        private static bool ValidOdr(byte control)
        {
            var odr = control >> 4;
            return odr >= 1 && odr <= 10;
        }

        private void UpdateInterrupt()
        {
            INT1.Set(PairEnabled && (registers[PulseConfig] & 0x80) == 0 &&
                     (registers[Status] & registers[Int1Control] & 3) != 0);
        }

        private const byte PulseConfig = 0x0b;
        private const byte Int1Control = 0x0d;
        private const byte WhoAmI = 0x0f;
        private const byte Ctrl1XL = 0x10;
        private const byte Ctrl2G = 0x11;
        private const byte Ctrl3C = 0x12;
        private const byte Status = 0x1e;
        private const byte OutGyro = 0x22;
        private static readonly int[] OdrHz = { 0, 13, 26, 52, 104, 208, 416, 833, 1660, 3330, 6660 };
        private readonly LimitTimer fixtureTimer;
        private bool fixtureActive;
        private int[] fixtureValues;
        private int fixtureFrequency, fixtureAttempts, fixtureAccepted, fixtureSkipped, fixtureRemaining;
        private readonly object sync = new object();
        private readonly byte[] registers = new byte[256];
        private byte pointer;
        private ushort unreadOutputs;
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
