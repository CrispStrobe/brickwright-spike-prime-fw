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
    # The real console is USB CDC; USART2 is HCI. Observe only the guest-owned
    # publication, never inject a request or write diagnostic guest RAM.
    Execute Command    include @${CURDIR}/lump_requests.py
    ${requests}=    Execute Command    sysbus GetSymbolAddress "g_bw_lump_request"
    ${batch}=    Execute Command    check_lump_requests ${requests.strip()}
    Should Contain    ${batch}    LUMP protected fixed request batch passed: requests=6
    # New, separate request words are the only writable fixture extent. The
    # existing program worker issues the real ioctls; reply/result words stay read-only.
    ${mailbox}=    Execute Command    sysbus GetSymbolAddress "g_bw_lump_request_mailbox"
    Execute Command    include @${CURDIR}/../../tools/lump_request_transport.py
    ${roundtrips}=    Execute Command    check_lump_mailbox ${mailbox.strip()} ${requests.strip()}
    Should Contain    ${roundtrips}    LUMP protected mailbox roundtrip passed: selector=7 sequence=1
    Should Contain    ${roundtrips}    LUMP protected mailbox roundtrip passed: selector=0 sequence=2
    Should Contain    ${roundtrips}    LUMP protected mailbox roundtrip passed: selector=1 sequence=3
