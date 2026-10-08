# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
*** Settings ***
Library          OperatingSystem
Test Teardown    Reset Emulation
Test Timeout     600 seconds

*** Variables ***
${PLATFORM}      @${CURDIR}/spike-prime-custom-dma.repl
${IMAGES}        ${CURDIR}/../../.local/firmware-images
${EXISTING_FILESYSTEM}    ${IMAGES}/existing-filesystem

*** Test Cases ***
Actual protected userspace refuses invalid session poll outputs
    [Tags]    brickwright-lump-probe
    Execute Command    include @${CURDIR}/SpikePrimeDevices.cs
    Execute Command    mach create
    Execute Command    machine LoadPlatformDescription ${PLATFORM}
    ${uart}=    Create Terminal Tester    sysbus.usart2    timeout=20    defaultPauseEmulation=true
    # This platform has no attached UART device on F. No DATA/queue writes.
    File Should Exist    ${EXISTING_FILESYSTEM}/receipt.json
    Execute Command    include @${CURDIR}/../../tools/renode_load_littlefs_fixture.py
    Execute Command    load_littlefs_fixture @${EXISTING_FILESYSTEM}
    File Should Exist    ${IMAGES}/brickwright/nuttx
    File Should Exist    ${IMAGES}/brickwright/nuttx_user.elf
    ${manifest_text}=    Get File    ${IMAGES}/brickwright/manifest.json
    ${manifest}=    Evaluate    json.loads($manifest_text)    json
    Execute Command    sysbus LoadELF @${IMAGES}/brickwright/nuttx
    Execute Command    sysbus LoadELF @${IMAGES}/brickwright/nuttx_user.elf
    Execute Command    cpu VectorTableOffset 0x08008000
    Execute Command    cpu SP ${manifest}[initial_sp]
    ${reset_pc}=    Evaluate    int($manifest['reset_pc'], 16) & ~1
    Execute Command    cpu PC ${reset_pc}
    ${result}=    Execute Command    sysbus GetSymbolAddress "g_bw_lump_probe"
    ${readonly}=    Execute Command    sysbus GetSymbolAddress "g_bw_lump_probe_readonly"
    Execute Command    include @${CURDIR}/lump_probe.py
    ${proof}=    Execute Command    check_lump_probe ${result.strip()} ${readonly.strip()}
    Should Contain    ${proof}    LUMP protected refusal probe passed: checks=511
    # The existing NSH entry runs the fixed batch after publishing the original
    # refusal result. Match every complete line, in order, through descriptor close.
    Wait For Line On Uart    ^BW_LUMP_REQUEST v=1 op=invalid-then-poll step=1 rc=-1 errno=22 bytes=-$    testerId=${uart}    treatAsRegex=true    pauseEmulation=true
    FOR    ${step}    IN RANGE    2    6
        Wait For Line On Uart    ^BW_LUMP_REQUEST v=1 op=invalid-then-poll step=${step} rc=-1 errno=14 bytes=-$    testerId=${uart}    treatAsRegex=true    pauseEmulation=true    matchNextLine=true
    END
    ${sentinel}=    Evaluate    'a5' * 48
    Wait For Line On Uart    ^BW_LUMP_REQUEST v=1 op=invalid-then-poll step=6 rc=-1 errno=11 bytes=${sentinel}$    testerId=${uart}    treatAsRegex=true    pauseEmulation=true    matchNextLine=true
    Wait For Line On Uart    ^BW_LUMP_REQUEST_END v=1 op=invalid-then-poll calls=6 close_rc=0 close_errno=0$    testerId=${uart}    treatAsRegex=true    pauseEmulation=true    matchNextLine=true
    Log To Console    LUMP protected fixed request batch passed: requests=6 exclusive_fd=true
