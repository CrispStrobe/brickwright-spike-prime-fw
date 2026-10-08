# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
*** Settings ***
Library          OperatingSystem
Test Teardown    Reset Emulation
Test Timeout     600 seconds

*** Variables ***
${PLATFORM}      @${CURDIR}/../../.local/lump-active-topology/platforms/boards/spike-prime.repl
${IMAGES}        ${CURDIR}/../../.local/firmware-images
${EXISTING_FILESYSTEM}    ${IMAGES}/existing-filesystem

*** Test Cases ***
Actual protected userspace consumes external DATA with session identity
    [Tags]    brickwright-lump-active
    Execute Command    mach create "lump-active"
    Execute Command    machine LoadPlatformDescription ${PLATFORM}
    Execute Command    emulation CreatePrimeElectricalPorts "lump-active"
    FOR    ${port}    IN    A    B    C    D    E    F
        Execute Command    port${port} Detach
    END
    # Begin without devices: preserve the previously qualified startup checks.
    File Should Exist    ${EXISTING_FILESYSTEM}/receipt.json
    Execute Command    include @${CURDIR}/../../tools/renode_load_littlefs_fixture.py
    Execute Command    python "load_fixture(monitor.Machine['sysbus.spi2.primeStorageMux.primeStorage'], '${EXISTING_FILESYSTEM}')"
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
    # The startup check reads the guest publication without submitting requests.
    # The separately declared mailbox requests follow below.
    Execute Command    include @${CURDIR}/lump_requests.py
    ${requests}=    Execute Command    sysbus GetSymbolAddress "g_bw_lump_request"
    ${batch}=    Execute Command    check_lump_requests ${requests.strip()}
    Should Contain    ${batch}    LUMP protected fixed request batch passed: requests=6
    # External attachment and DATA budgets affect the model only. The only
    # guest writes remain the four declared ELF-resolved mailbox request words.
    ${mailbox}=    Execute Command    sysbus GetSymbolAddress "g_bw_lump_request_mailbox"
    Execute Command    include @${CURDIR}/../../tools/lump_queue_observer.py
    Execute Command    include @${CURDIR}/../../tools/lump_request_transport.py
    ${queue}=    Execute Command    sysbus GetSymbolAddress "g_lump"
    ${active}=    Execute Command    check_lump_active ${mailbox.strip()} ${requests.strip()} @${IMAGES}/lump-queue-layout.json @${IMAGES}/brickwright/nuttx ${queue.strip()}
    Log To Console    ${active}
    Should Contain    ${active}    LUMP active F session fixture passed:

    # Keep the original F-only fixture above, then reset its external inputs.
    Execute Command    portF Detach
    Execute Command    emulation RunFor "5.0"
    Execute Command    include @${CURDIR}/../../tools/lump_two_port.py
    ${pair}=    Execute Command    check_lump_two_port ${mailbox.strip()} ${requests.strip()} @${IMAGES}/lump-queue-layout.json @${IMAGES}/brickwright/nuttx ${queue.strip()}
    Log To Console    ${pair}
    Should Contain    ${pair}    LUMP two-port isolation fixture passed:
