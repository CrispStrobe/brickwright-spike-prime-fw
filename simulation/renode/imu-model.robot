# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
# Synthetic digital transactions and explicitly armed guest-clock cadence;
# no firmware, physical motion, FIFO or silicon overrun timing.
*** Settings ***
Library          OperatingSystem
Test Setup       Create IMU Model Machine
Test Teardown    Reset Emulation
Test Timeout     90 seconds

*** Variables ***
${I}    ${SPACE}${SPACE}${SPACE}${SPACE}
${MODEL_CHECK}    SEPARATOR=\n
...    # SPDX-License-Identifier: MIT
...    # Copyright (c) 2026 Brickwright contributors
...    from System import Array, Byte, UInt64
...    from Antmicro.Renode.Time import TimeInterval
...    def mc_check_imu_model(case):
...    ${I}imu = monitor.Machine['sysbus.i2c2.imu']
...    ${I}port = monitor.Machine['sysbus.gpioPortB']
...    ${I}def write(address, value):
...    ${I}${I}imu.Write(Array[Byte]([address, value]))
...    ${I}def read(address, count=1):
...    ${I}${I}imu.Write(Array[Byte]([address]))
...    ${I}${I}return list(imu.Read(count))
...    ${I}def pin():
...    ${I}${I}return bool(port.ReadDoubleWord(0x10) & 16)
...    ${I}def configure(pulse=False):
...    ${I}${I}write(0x12, 0x44)
...    ${I}${I}write(0x10, 0x70)
...    ${I}${I}write(0x11, 0x78)
...    ${I}${I}write(0x0b, 0x80 if pulse else 0)
...    ${I}${I}write(0x0d, 2)
...    ${I}def inject():
...    ${I}${I}return imu.InjectSample(-32768, -1, 32767, 1234, -2345, 0)
...    ${I}expected = [0,128,255,255,255,127,210,4,215,246,0,0]
...    ${I}assert list(imu.GetFixtureState()) == [0,0,0]
...    ${I}assert read(0x0f) == [0x6a] and read(0x1e) == [0] and not pin()
...    ${I}assert not inject(), 'Reset model accepted powered-down sample'
...    ${I}if case == 'burst':
...    ${I}${I}configure()
...    ${I}${I}assert inject() and read(0x1e) == [3] and pin()
...    ${I}${I}imu.Write(Array[Byte]([0x22]))
...    ${I}${I}state = imu.GetFixtureState()
...    ${I}${I}assert list(state) == [0x70,0x78,3]
...    ${I}${I}state[0] = 0
...    ${I}${I}assert list(imu.GetFixtureState()) == [0x70,0x78,3]
...    ${I}${I}assert list(imu.Read(1)) == [0], 'Fixture state changed I2C pointer'
...    ${I}${I}imu.FinishTransmission()
...    ${I}${I}assert read(0x1e) == [3] and pin(), 'Status/STOP consumed data'
...    ${I}${I}assert not imu.InjectSample(1,2,3,4,5,6), 'Unread pair overwritten'
...    ${I}${I}assert read(0x22,12) == expected, 'Paired LE gyro/accel burst differs'
...    ${I}${I}assert read(0x1e) == [0] and not pin()
...    ${I}${I}assert inject() and read(0x22,12) == expected, 'Second acquisition failed'
...    ${I}elif case == 'routing':
...    ${I}${I}configure()
...    ${I}${I}write(0x0d,0)
...    ${I}${I}assert inject() and read(0x1e) == [3] and not pin()
...    ${I}${I}write(0x0d,2)
...    ${I}${I}assert pin(), 'Late latched routing did not assert PB4'
...    ${I}${I}assert read(0x22) == [0] and pin(), 'Low byte cleared gyro DRDY'
...    ${I}${I}assert read(0x23) == [128] and read(0x1e) == [1] and not pin()
...    ${I}${I}write(0x0d,1)
...    ${I}${I}assert pin(), 'Accelerometer routing differs'
...    ${I}${I}read(0x29)
...    ${I}${I}assert read(0x1e) == [0] and not pin()
...    ${I}${I}assert not inject(), 'Partial output read permitted pair overwrite'
...    ${I}${I}assert read(0x22,12) == expected
...    ${I}${I}configure(True)
...    ${I}${I}exti = monitor.Machine['sysbus.exti']
...    ${I}${I}syscfg = monitor.Machine['sysbus.syscfg']
...    ${I}${I}syscfg.WriteDoubleWord(0x0c, 1) # EXTI4 selects PB4.
...    ${I}${I}exti.WriteDoubleWord(0x00,16) # Enable EXTI4 interrupt mask.
...    ${I}${I}exti.WriteDoubleWord(0x08,16) # Rising trigger on line4.
...    ${I}${I}exti.WriteDoubleWord(0x14,16) # Clear pending W1C.
...    ${I}${I}assert inject() and not pin() and read(0x1e) == [3]
...    ${I}${I}assert exti.ReadDoubleWord(0x14) & 16, 'Pulsed INT1 did not reach EXTI4'
...    ${I}${I}read(0x22,12)
...    ${I}${I}exti.WriteDoubleWord(0x14,16)
...    ${I}${I}assert inject() and (exti.ReadDoubleWord(0x14) & 16), 'Second pulse lost'
...    ${I}elif case == 'feed':
...    ${I}${I}def advance(ms):
...    ${I}${I}${I}monitor.Machine.ClockSource.Advance(TimeInterval.FromNanoseconds(UInt64(ms*1000000)), True)
...    ${I}${I}def feed(ticks):
...    ${I}${I}${I}return imu.StartFixtureFeed(-32768,-1,32767,1234,-2345,0,ticks)
...    ${I}${I}def state(): return list(imu.GetFixtureFeedState())
...    ${I}${I}assert state() == [0]*6 and not feed(5)
...    ${I}${I}configure()
...    ${I}${I}write(0x10,0x40)
...    ${I}${I}write(0x11,0x48)
...    ${I}${I}advance(50)
...    ${I}${I}assert state() == [0]*6 and read(0x1e) == [0], 'Default feeder produced samples'
...    ${I}${I}assert feed(5) and not feed(5), 'Active feeder was restarted'
...    ${I}${I}assert state() == [1,104,0,0,0,5]
...    ${I}${I}advance(9)
...    ${I}${I}assert state() == [1,104,0,0,0,5] and read(0x1e) == [0], 'Sample arrived before ODR period'
...    ${I}${I}advance(1)
...    ${I}${I}assert state() == [1,104,1,1,0,4] and pin()
...    ${I}${I}assert read(0x22,12) == expected
...    ${I}${I}advance(9)
...    ${I}${I}assert state() == [1,104,1,1,0,4], 'Cadence drifted from configured ODR'
...    ${I}${I}advance(1)
...    ${I}${I}assert state() == [1,104,2,2,0,3]
...    ${I}${I}advance(30)
...    ${I}${I}assert state() == [0,104,5,2,3,0], 'Unread attempts were not skipped/bounded'
...    ${I}${I}assert read(0x22,12) == expected
...    ${I}${I}advance(50)
...    ${I}${I}assert state() == [0,104,5,2,3,0] and read(0x1e) == [0], 'Completed feeder kept running'
...    ${I}${I}assert feed(5)
...    ${I}${I}advance(10)
...    ${I}${I}assert state() == [1,104,1,1,0,4]
...    ${I}${I}imu.StopFixtureFeed()
...    ${I}${I}advance(50)
...    ${I}${I}assert state() == [0,104,1,1,0,4] and read(0x22,12) == expected, 'Stop changed pending sample/counters'
...    ${I}${I}assert feed(5)
...    ${I}${I}write(0x10,0x30)
...    ${I}${I}advance(50)
...    ${I}${I}assert state() == [0,104,0,0,0,5] and not feed(5), 'ODR change/mismatch did not stop feeder'
...    ${I}${I}write(0x11,0x38)
...    ${I}${I}assert feed(5) and state()[1] == 52
...    ${I}${I}write(0x10,0)
...    ${I}${I}advance(50)
...    ${I}${I}assert state() == [0,52,0,0,0,5] and read(0x1e) == [0], 'Powerdown retained feeder'
...    ${I}${I}write(0x10,0x30)
...    ${I}${I}assert feed(5)
...    ${I}${I}write(0x12,1)
...    ${I}${I}advance(50)
...    ${I}${I}assert state() == [0]*6 and read(0x1e) == [0], 'Reset retained feeder'
...    ${I}${I}for ticks in [0,10001]:
...    ${I}${I}${I}rejected = False
...    ${I}${I}${I}try: feed(ticks)
...    ${I}${I}${I}except Exception: rejected = True
...    ${I}${I}${I}assert rejected and state() == [0]*6
...    ${I}${I}configure()
...    ${I}${I}assert inject() and read(0x22,12) == expected, 'Manual injection changed after feeder reset'
...    ${I}elif case == 'reset':
...    ${I}${I}configure()
...    ${I}${I}assert inject() and pin()
...    ${I}${I}write(0x10,0)
...    ${I}${I}assert not pin() and read(0x1e) == [0] and not inject()
...    ${I}${I}write(0x10,0xf0)
...    ${I}${I}assert not inject(), 'Reserved ODR accepted'
...    ${I}${I}configure()
...    ${I}${I}assert inject()
...    ${I}${I}write(0x12,1)
...    ${I}${I}assert read(0x12) == [4] and read(0x0f) == [0x6a]
...    ${I}${I}assert read(0x10,2) == [0,0] and read(0x22,12) == [0]*12
...    ${I}${I}assert read(0x1e) == [0] and not pin() and not inject()
...    ${I}${I}configure()
...    ${I}${I}for args in [(32768,0,0,0,0,0),(0,0,0,0,-32769,0)]:
...    ${I}${I}${I}rejected = False
...    ${I}${I}${I}try: imu.InjectSample(*args)
...    ${I}${I}${I}except Exception: rejected = True
...    ${I}${I}${I}assert rejected and read(0x1e) == [0] and not pin()
...    ${I}${I}assert inject() and read(0x22,12) == expected
...    ${I}${I}imu.Reset()
...    ${I}${I}assert not pin() and read(0x1e) == [0] and not inject()
...    ${I}else:
...    ${I}${I}raise ValueError('Unknown IMU test case')

*** Keywords ***
Create IMU Model Machine
    Execute Command    include @${CURDIR}/SpikePrimeDevices.cs
    Execute Command    mach create
    Execute Command    machine LoadPlatformDescription @${CURDIR}/spike-prime.repl
    Create File    ${OUTPUT DIR}/imu-model-check.py    ${MODEL_CHECK}
    Execute Command    include @${OUTPUT DIR}/imu-model-check.py

*** Test Cases ***
Paired IMU Burst Is Coherent And Repeatable
    [Tags]    brickwright-imu-model
    Execute Command    check_imu_model "burst"

IMU Data Ready Routes Through PB4 And EXTI4
    [Tags]    brickwright-imu-model
    Execute Command    check_imu_model "routing"

IMU Stop Reset And Invalid Inputs Are Safe
    [Tags]    brickwright-imu-model
    Execute Command    check_imu_model "reset"

Explicit IMU Feeder Uses Bounded Guest Time Cadence
    [Tags]    brickwright-imu-model
    Execute Command    check_imu_model "feed"
