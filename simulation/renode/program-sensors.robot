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
Actual ARM programs address E and F through external UART DATA
    [Tags]    brickwright-program-sensors
    Execute Command    mach create "program-sensors"
    Execute Command    machine LoadPlatformDescription ${PLATFORM}
    Execute Command    emulation CreatePrimeElectricalPorts "program-sensors"
    FOR    ${port}    IN    A    B    C    D    E    F
        Execute Command    port${port} Detach
    END
    File Should Exist    ${EXISTING_FILESYSTEM}/receipt.json
    Execute Command    include @${CURDIR}/../../tools/renode_load_littlefs_fixture.py
    Execute Command    python "load_fixture(monitor.Machine['sysbus.spi2.primeStorageMux.primeStorage'], '${EXISTING_FILESYSTEM}')"
    ${manifest_text}=    Get File    ${IMAGES}/brickwright/manifest.json
    ${manifest}=    Evaluate    json.loads($manifest_text)    json
    Execute Command    sysbus LoadELF @${IMAGES}/brickwright/nuttx
    Execute Command    sysbus LoadELF @${IMAGES}/brickwright/nuttx_user.elf
    Execute Command    cpu VectorTableOffset 0x08008000
    Execute Command    cpu SP ${manifest}[initial_sp]
    ${reset_pc}=    Evaluate    int($manifest['reset_pc'], 16) & ~1
    Execute Command    cpu PC ${reset_pc}
    ${probe}=    Execute Command    sysbus GetSymbolAddress "g_bw_lump_probe"
    ${readonly}=    Execute Command    sysbus GetSymbolAddress "g_bw_lump_probe_readonly"
    Execute Command    include @${CURDIR}/lump_probe.py
    ${startup}=    Execute Command    check_lump_probe ${probe.strip()} ${readonly.strip()}
    Should Contain    ${startup}    LUMP protected refusal probe passed: checks=511
    ${feature}=    Execute Command    sysbus GetSymbolAddress "g_bw_program_addressed_sensor_abi"
    ${feature_value}=    Execute Command    sysbus ReadDoubleWord ${feature.strip()}
    ${feature_integer}=    Evaluate    int($feature_value.strip(), 0)
    Should Be Equal As Integers    ${feature_integer}    1
    ${mailbox}=    Execute Command    sysbus GetSymbolAddress "g_bw_program_debug"
    ${queue}=    Execute Command    sysbus GetSymbolAddress "g_lump"
    Execute Command    include @${CURDIR}/../../tools/lump_queue_observer.py
    Execute Command    include @${CURDIR}/program_workflow.py
    Execute Command    include @${CURDIR}/program_sensors.py
    ${proof}=    Execute Command    check_program_sensors ${mailbox.strip()} @${IMAGES}/lump-queue-layout.json @${IMAGES}/brickwright/nuttx ${queue.strip()}
    Log To Console    ${proof}
    Should Contain    ${proof}    ARM explicit program sensor fixture passed:
    Execute Command    include @%{RENODE_DIR}/scripts/spike-state-server.py
    Execute Command    include @${CURDIR}/addressed_runtime_capability.py
    ${live}=    Execute Command    check_addressed_runtime_capability ${mailbox.strip()} ${feature.strip()} @${IMAGES}/brickwright/nuttx_user.elf
    Log To Console    ${live}
    Should Contain    ${live}    ARM live addressed Runtime capability passed: live=1 legacy=0 foreign=refused
