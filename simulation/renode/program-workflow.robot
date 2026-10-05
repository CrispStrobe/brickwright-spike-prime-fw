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
Actual ARM retained program restarts through the published service mailbox
    [Tags]    brickwright-program-workflow
    Execute Command    include @${CURDIR}/SpikePrimeDevices.cs
    Execute Command    mach create
    Execute Command    machine LoadPlatformDescription ${PLATFORM}
    # This is an explicitly prepared filesystem fixture, not a mount bypass.
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
    ${mailbox}=    Execute Command    sysbus GetSymbolAddress "g_bw_program_debug"
    Should Be True    0x20020000 <= int($mailbox.strip(), 0) <= 0x20040000 - 112
    Execute Command    include @${CURDIR}/program_workflow.py
    ${proof}=    Execute Command    check_program_workflow ${mailbox.strip()}
    Should Contain    ${proof}    Program workflow passed: ARM worker
