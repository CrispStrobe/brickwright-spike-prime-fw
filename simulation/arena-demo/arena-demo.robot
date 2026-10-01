# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
*** Settings ***
Test Setup       Prepare guest
Test Teardown    Reset Emulation
Test Timeout     30 seconds

*** Keywords ***
Prepare guest
    Execute Command    mach create
    Execute Command    machine LoadPlatformDescription @${PLATFORM}
    Execute Command    sysbus LoadELF @${FIRMWARE}
    Execute Command    cpu VectorTableOffset 0x08008000
    Execute Command    cpu SP 0x20050000
    ${reset}=    Execute Command    sysbus GetSymbolAddress "reset_handler"
    Execute Command    cpu PC ${reset.strip()}

*** Test Cases ***
Guest ticks and drives, then stops for arena distance input
    Execute Command    emulation RunFor "0.2"
    ${signature}=    Execute Command    sysbus ReadDoubleWord 0x20040000
    Should Be Equal As Numbers    ${signature.strip()}    0x42574152
    ${ticks}=    Execute Command    sysbus ReadDoubleWord 0x20040008
    Should Be True    195 <= int($ticks.strip(), 0) <= 205
    ${position}=    Execute Command    sysbus ReadDoubleWord 0x20040034
    Should Be True    int($position.strip(), 0) > 10000
    Execute Command    sysbus WriteDoubleWord 0x2004000c 1
    Execute Command    sysbus WriteDoubleWord 0x20040010 100
    Execute Command    sysbus WriteDoubleWord 0x2004000c 2
    Execute Command    emulation RunFor "0.2"
    ${speed}=    Execute Command    sysbus ReadDoubleWord 0x2004003c
    Should Be Equal As Numbers    ${speed.strip()}    0
    ${before}=    Execute Command    sysbus ReadDoubleWord 0x20040034
    Execute Command    emulation RunFor "0.2"
    ${after}=    Execute Command    sysbus ReadDoubleWord 0x20040034
    Should Be Equal As Numbers    ${before.strip()}    ${after.strip()}
