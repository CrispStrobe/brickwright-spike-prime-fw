*** Settings ***
Library          OperatingSystem
Library          Process
Test Setup       Create SPIKE Machine
Test Teardown    Reset SPIKE Test
Test Timeout     90 seconds

*** Variables ***
${PLATFORM}      @${CURDIR}/spike-prime.repl
${IMAGES}        ${CURDIR}/../../.local/firmware-images
${EXISTING_FILESYSTEM}    ${IMAGES}/existing-filesystem
${HCI_BRIDGE}    ${EMPTY}
${HCI_PORT}      34561

*** Keywords ***
Create SPIKE Machine
    Execute Command    include @${CURDIR}/SpikePrimeDevices.cs
    Execute Command    mach create
    Execute Command    machine LoadPlatformDescription ${PLATFORM}

Reset SPIKE Test
    Terminate All Processes    kill=True
    Reset Emulation

Wait For Paused Milestone
    [Arguments]    ${pattern}    ${timeout}
    # StartAll before installing LogTester's predicate can race with the hook:
    # a late log delivery makes WaitForEntry restart the just-paused guest.
    # Stop synchronously, then let the waiter arm before its internal start.
    Execute Command    emulation PauseAll
    ${entry}=    Wait For Log Entry    ${pattern}    timeout=${timeout}    pauseEmulation=${True}
    # Buffered matches return without WaitForEntry's stop wait.
    Execute Command    emulation PauseAll
    RETURN    ${entry}

Boot Protected Pair And Prove Progress
    [Arguments]    ${target}
    File Should Exist    ${IMAGES}/${target}/nuttx
    File Should Exist    ${IMAGES}/${target}/nuttx_user.elf
    File Should Exist    ${IMAGES}/${target}/manifest.json
    ${manifest_text}=    Get File    ${IMAGES}/${target}/manifest.json
    ${manifest}=    Evaluate    json.loads($manifest_text)    json
    Execute Command    sysbus LoadELF @${IMAGES}/${target}/nuttx
    Execute Command    sysbus LoadELF @${IMAGES}/${target}/nuttx_user.elf
    Execute Command    cpu VectorTableOffset 0x08008000
    Execute Command    cpu SP ${manifest}[initial_sp]
    ${reset_pc}=    Evaluate    int($manifest['reset_pc'], 16) & ~1
    Execute Command    cpu PC ${reset_pc}
    ${nx_start}=    Execute Command    sysbus GetSymbolAddress "nx_start"
    ${board_late}=    Execute Command    sysbus GetSymbolAddress "board_late_initialize"
    ${bringup}=    Execute Command    sysbus GetSymbolAddress "stm32_bringup"
    Should Be True    0x08008000 <= int($nx_start.strip(), 0) < 0x08080000
    ${userspace}=    Execute Command    sysbus ReadDoubleWord 0x08080000
    Should Not Be Equal As Numbers    0x00000000    ${userspace.strip()}
    Should Not Be Equal As Numbers    0xffffffff    ${userspace.strip()}
    ${before}=    Execute Command    cpu GetRegister "PC"
    Create Log Tester    1
    Execute Command    cpu AddHook ${nx_start.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE nx_start\\"')"
    Execute Command    cpu AddHook ${board_late.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE board_late_initialize\\"')"
    Execute Command    cpu AddHook ${bringup.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE stm32_bringup\\"')"
    Wait For Paused Milestone    MILESTONE nx_start    10
    Wait For Paused Milestone    MILESTONE board_late_initialize    10
    Wait For Paused Milestone    MILESTONE stm32_bringup    10
    ${after}=    Execute Command    cpu GetRegister "PC"
    Should Not Be Equal As Numbers    ${before.strip()}    ${after.strip()}
    ${after_value}=    Convert To Integer    ${after.strip()}
    Should Be True    0x08000000 <= ${after_value} < 0x08200000

Complete Modeled Flash Initialization Successfully
    # Called at the paused initializer entry: observe its actual return value
    # without changing guest registers or skipping the mount and blank scan.
    # Publish snapshots after requesting the pause, and wait for global stop:
    # a log notification alone can wake Robot before the hook has paused.
    Execute Command    emulation PauseAll
    ${flash_entry}=    Execute Command    sysbus GetSymbolAddress "stm32_w25q256_initialize"
    ${flash_entry_pc}=    Evaluate    int($flash_entry.strip(), 0) & ~1
    ${entry_pc}=    Execute Command    cpu GetRegister 15
    Should Be Equal As Integers    ${entry_pc.strip()}    ${flash_entry_pc}    CPU must be stopped at the flash initializer entry
    ${link_register}=    Execute Command    cpu GetRegister 14
    ${return_site}=    Evaluate    int($link_register.strip(), 0) & ~1
    Execute Command    cpu AddHook ${return_site} "flash_return_r0=int(self.GetRegister(0).RawValue); flash_return_pc=int(self.GetRegister(15).RawValue); machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE flash initialized R0=%d PC=%d\\"' % (flash_return_r0, flash_return_pc))"
    ${return_log}=    Wait For Paused Milestone    MILESTONE flash initialized    15
    Log To Console    ${return_log}
    ${status}=    Execute Command    cpu GetRegister 0
    ${paused_pc}=    Execute Command    cpu GetRegister 15
    Log To Console    Flash initializer observation: R0=${status.strip()} PC=${paused_pc.strip()} expected return site=${return_site}
    Should Match Regexp    ${return_log}    MILESTONE flash initialized R0=0 PC=${return_site}(?![0-9])
    Should Be Equal As Integers    ${status.strip()}    0    Flash initializer must return zero
    Should Be Equal As Integers    ${paused_pc.strip()}    ${return_site}    CPU must remain at the observed flash return site
    Execute Command    cpu RemoveHooksAt ${return_site}

Load Explicit Existing LittleFS Fixture
    File Should Exist    ${EXISTING_FILESYSTEM}/receipt.json
    File Should Exist    ${EXISTING_FILESYSTEM}/flash-blocks.bin
    Execute Command    include @${CURDIR}/../../tools/renode_load_littlefs_fixture.py
    Create Log Tester    1
    Execute Command    load_littlefs_fixture @${EXISTING_FILESYSTEM}
    Wait For Log Entry    MILESTONE existing filesystem ready    timeout=0

Boot Through Modeled Board Devices
    Boot Protected Pair And Prove Progress    brickwright
    ${imu_init}=    Execute Command    sysbus GetSymbolAddress "stm32_lsm6dsl_initialize"
    ${flash_init}=    Execute Command    sysbus GetSymbolAddress "stm32_w25q256_initialize"
    ${display_init}=    Execute Command    sysbus GetSymbolAddress "tlc5955_initialize"
    Execute Command    cpu AddHook ${imu_init.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE imu bus-model\\"')"
    Execute Command    cpu AddHook ${flash_init.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE flash bus-model\\"')"
    Execute Command    cpu AddHook ${display_init.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE display bus-model\\"')"
    Wait For Paused Milestone    MILESTONE imu bus-model    10
    Wait For Paused Milestone    MILESTONE flash bus-model    10
    Complete Modeled Flash Initialization Successfully
    Wait For Paused Milestone    MILESTONE display bus-model    15

Boot Simulation HCI Through Modeled Board Devices
    Skip If    '${HCI_BRIDGE}' == ''    HCI bridge executable was not supplied
    Boot Protected Pair And Prove Progress    brickwright-simulation
    ${bridge_log}=    Set Variable    ${CURDIR}/../../.local/renode-hci-bridge-simulation.log
    Execute Command    emulation CreateServerSocketTerminal ${HCI_PORT} "hci" false
    Execute Command    connector Connect sysbus.usart2 hci
    # The simulated controller refuses vendor commands: this image has no
    # service pack, so none may arrive and none is silently acknowledged.
    Start Process    ${HCI_BRIDGE}    --trace    --reject-vendor    127.0.0.1    ${HCI_PORT}    alias=hci    stdout=${bridge_log}    stderr=STDOUT
    ${imu_init}=    Execute Command    sysbus GetSymbolAddress "stm32_lsm6dsl_initialize"
    ${flash_init}=    Execute Command    sysbus GetSymbolAddress "stm32_w25q256_initialize"
    ${physical_open}=    Execute Command    sysbus GetSymbolAddress "physical_open"
    ${load_firmware}=    Execute Command    sysbus GetSymbolAddress "physical_load_firmware"
    ${physical_start}=    Execute Command    sysbus GetSymbolAddress "physical_start_host"
    ${bt_enable}=    Execute Command    sysbus GetSymbolAddress "bt_enable"
    ${settings_load}=    Execute Command    sysbus GetSymbolAddress "settings_load"
    ${transport_register}=    Execute Command    sysbus GetSymbolAddress "brickwright_hub_transport_register"
    ${daemon_ready}=    Execute Command    sysbus GetSymbolAddress "daemon_wait_for_stop"
    # IMU, flash and display functions run against the bus models.
    Execute Command    cpu AddHook ${imu_init.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE imu bus-model\\"')"
    Execute Command    cpu AddHook ${flash_init.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE flash bus-model\\"')"
    Execute Command    cpu AddHook ${physical_open.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE physical_open\\"')"
    Execute Command    cpu AddHook ${load_firmware.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE physical_load_firmware\\"')"
    Execute Command    cpu AddHook ${physical_start.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE physical_start_host\\"')"
    Execute Command    cpu AddHook ${bt_enable.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE bt_enable\\"')"
    Execute Command    cpu AddHook ${settings_load.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE settings_load\\"')"
    Execute Command    cpu AddHook ${transport_register.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE transport_register\\"')"
    Execute Command    cpu AddHook ${daemon_ready.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE daemon_ready\\"')"
    Wait For Paused Milestone    MILESTONE imu bus-model    15
    Wait For Paused Milestone    MILESTONE flash bus-model    15
    Complete Modeled Flash Initialization Successfully
    Wait For Paused Milestone    MILESTONE bt_enable    30
    Wait For Paused Milestone    MILESTONE physical_open    15
    Wait For Paused Milestone    MILESTONE physical_load_firmware    15
    Wait For Paused Milestone    MILESTONE physical_start_host    15
    Wait For Paused Milestone    MILESTONE settings_load    45
    Wait For Paused Milestone    MILESTONE transport_register    15
    Wait For Paused Milestone    MILESTONE daemon_ready    15
    Execute Command    include @${CURDIR}/../../tools/renode_check_tlc5955.py
    ${display_proof}=    Execute Command    check_tlc5955_guest
    Should Contain    ${display_proof}    TLC5955 guest passed
    ${trace}=    Get File    ${bridge_log}
    Should Contain    ${trace}    command=0x0c03
    Should Not Match Regexp    ${trace}    command=0xf[c-f]

*** Test Cases ***
SPI display latches data through the selected GPIO pin
    [Tags]    brickwright-display-latch
    Execute Command    include @${CURDIR}/../../tools/renode_check_tlc5955.py
    ${proof}=    Execute Command    check_tlc5955
    Should Contain    ${proof}    TLC5955 passed

Timer-triggered ADC updates the circular DMA buffer
    [Tags]    brickwright-adc-dma
    Execute Command    include @${CURDIR}/../../tools/renode_check_adc_dma.py
    ${proof}=    Execute Command    check_adc_dma
    Should Contain    ${proof}    ADC DMA passed

GPIO external interrupts honor the selected port
    [Tags]    brickwright-exti-routing
    Execute Command    include @${CURDIR}/../../tools/renode_check_exti_routing.py
    ${proof}=    Execute Command    check_exti_routing
    Should Contain    ${proof}    SYSCFG routing passed

Original spike-nx protected pair executes
    [Tags]    spike-nx
    Boot Protected Pair And Prove Progress    spike-nx

Brickwright protected pair executes
    [Tags]    brickwright
    Boot Protected Pair And Prove Progress    brickwright

Brickwright tickless timer services repeated hardware rollovers
    [Tags]    brickwright-tickless
    Boot Protected Pair And Prove Progress    brickwright
    # Isolate board bring-up, then run the actual kernel and TIM9 ISR. This
    # qualifies elapsed timer periods without claiming USB or board fidelity.
    Execute Command    cpu PC `cpu LR`
    ${timer_state}=    Execute Command    sysbus GetSymbolAddress "g_tickless"
    # In the pinned STM32 tickless implementation, overflow is the uint32_t
    # field at offset 12. Its reviewed layout is part of the source manifest.
    ${overflow_address}=    Evaluate    int($timer_state.strip(), 0) + 12
    ${callbacks_path}=    Set Variable    ${CURDIR}/../../.local/renode-tickless-callbacks.txt
    Create File    ${callbacks_path}
    ${scheduler_timer}=    Execute Command    sysbus GetSymbolAddress "nxsched_process_timer"
    # Count actual scheduler callbacks without changing guest registers or
    # skipping the compare ISR. The diagnostic file stays with local results.
    Execute Command    cpu AddHook ${scheduler_timer.strip()} "f=open('${callbacks_path}', 'a'); f.write('1'); f.close()"
    Execute Command    emulation RunFor "0.1"
    ${initial}=    Execute Command    sysbus ReadDoubleWord ${overflow_address}
    ${initial_callbacks}=    Get File    ${callbacks_path}
    Execute Command    emulation RunFor "2.0"
    ${middle}=    Execute Command    sysbus ReadDoubleWord ${overflow_address}
    ${middle_callbacks}=    Get File    ${callbacks_path}
    Should Be True    int($middle.strip(), 0) >= int($initial.strip(), 0) + 2
    Should Be True    len($middle_callbacks) > len($initial_callbacks)
    Execute Command    emulation RunFor "2.0"
    ${final}=    Execute Command    sysbus ReadDoubleWord ${overflow_address}
    ${final_callbacks}=    Get File    ${callbacks_path}
    Should Be True    int($final.strip(), 0) >= int($middle.strip(), 0) + 2
    Should Be True    len($final_callbacks) > len($middle_callbacks)

Brickwright reaches protected userspace with board boundary isolated
    [Tags]    brickwright-userspace
    Boot Protected Pair And Prove Progress    brickwright
    ${nsh_main}=    Execute Command    sysbus GetSymbolAddress "nsh_main"
    ${hubprogram_main}=    Execute Command    sysbus GetSymbolAddress "hubprogram_main"
    Execute Command    cpu AddHook ${nsh_main.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE nsh_main\\"')"
    Execute Command    cpu AddHook ${hubprogram_main.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE hubprogram_main\\"')"
    Execute Command    cpu PC `cpu LR`
    Wait For Paused Milestone    MILESTONE nsh_main    10
    Wait For Paused Milestone    MILESTONE hubprogram_main    10

Brickwright formats initially erased flash and reaches TLC5955
    [Tags]    brickwright-board-models    brickwright-erased-first-boot
    # Full 31 MiB scan measured 470s on the contended qualification host.
    # Log waits retain 15 guest seconds; this is only a host wall bound.
    [Timeout]    900 seconds
    Boot Through Modeled Board Devices

Brickwright mounts an existing LittleFS filesystem and reaches TLC5955
    [Tags]    brickwright-existing-filesystem-board
    Load Explicit Existing LittleFS Fixture
    Boot Through Modeled Board Devices

Brickwright reaches userspace with synchronous board functions isolated
    [Tags]    brickwright-board-stubs
    Boot Protected Pair And Prove Progress    brickwright
    ${imu_init}=    Execute Command    sysbus GetSymbolAddress "stm32_lsm6dsl_initialize"
    ${flash_init}=    Execute Command    sysbus GetSymbolAddress "stm32_w25q256_initialize"
    ${display_init}=    Execute Command    sysbus GetSymbolAddress "tlc5955_initialize"
    ${display_update}=    Execute Command    sysbus GetSymbolAddress "tlc5955_update_sync"
    ${display_set}=    Execute Command    sysbus GetSymbolAddress "tlc5955_set_duty"
    ${nsh_main}=    Execute Command    sysbus GetSymbolAddress "nsh_main"
    ${hubprogram_main}=    Execute Command    sysbus GetSymbolAddress "hubprogram_main"
    Execute Command    cpu AddHook ${imu_init.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${flash_init.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${display_init.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${display_update.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${display_set.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${nsh_main.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE nsh_main bus-stubs\\"')"
    Execute Command    cpu AddHook ${hubprogram_main.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE hubprogram_main bus-stubs\\"')"
    Wait For Paused Milestone    MILESTONE nsh_main bus-stubs    10
    Wait For Paused Milestone    MILESTONE hubprogram_main bus-stubs    10

Brickwright crosses the protected UART HCI bootstrap boundary
    [Tags]    brickwright-hci
    [Timeout]    180 seconds
    Skip If    '${HCI_BRIDGE}' == ''    HCI bridge executable was not supplied
    Boot Protected Pair And Prove Progress    brickwright
    Execute Command    emulation CreateServerSocketTerminal ${HCI_PORT} "hci" false
    Execute Command    connector Connect sysbus.usart2 hci
    Start Process    ${HCI_BRIDGE}    --trace    127.0.0.1    ${HCI_PORT}    alias=hci    stdout=${CURDIR}/../../.local/renode-hci-bridge.log    stderr=STDOUT
    ${imu_init}=    Execute Command    sysbus GetSymbolAddress "stm32_lsm6dsl_initialize"
    ${flash_init}=    Execute Command    sysbus GetSymbolAddress "stm32_w25q256_initialize"
    ${display_init}=    Execute Command    sysbus GetSymbolAddress "tlc5955_initialize"
    ${display_update}=    Execute Command    sysbus GetSymbolAddress "tlc5955_update_sync"
    ${display_set}=    Execute Command    sysbus GetSymbolAddress "tlc5955_set_duty"
    ${physical_open}=    Execute Command    sysbus GetSymbolAddress "physical_open"
    ${load_firmware}=    Execute Command    sysbus GetSymbolAddress "physical_load_firmware"
    ${bts_execute}=    Execute Command    sysbus GetSymbolAddress "ti_bts_execute"
    ${init_send}=    Execute Command    sysbus GetSymbolAddress "init_send"
    ${physical_start}=    Execute Command    sysbus GetSymbolAddress "physical_start_host"
    ${settings_load}=    Execute Command    sysbus GetSymbolAddress "settings_load"
    ${transport_register}=    Execute Command    sysbus GetSymbolAddress "brickwright_hub_transport_register"
    ${daemon_ready}=    Execute Command    sysbus GetSymbolAddress "daemon_wait_for_stop"
    Execute Command    cpu AddHook ${imu_init.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${flash_init.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${display_init.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${display_update.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${display_set.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${physical_open.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE physical_open\\"')"
    Execute Command    cpu AddHook ${load_firmware.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE physical_load_firmware\\"')"
    Execute Command    cpu AddHook ${bts_execute.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE ti_bts_execute\\"')"
    Execute Command    cpu AddHook ${init_send.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE init_send\\"')"
    Execute Command    cpu AddHook ${physical_start.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE physical_start_host\\"')"
    Execute Command    cpu AddHook ${settings_load.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE settings_load\\"')"
    Execute Command    cpu AddHook ${transport_register.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE transport_register\\"')"
    Execute Command    cpu AddHook ${daemon_ready.strip()} "machine.PauseAndRequestEmulationPause(True); monitor.Parse('log \\"MILESTONE daemon_ready\\"')"
    Wait For Paused Milestone    MILESTONE physical_open    10
    Wait For Paused Milestone    MILESTONE physical_load_firmware    10
    Wait For Paused Milestone    MILESTONE ti_bts_execute    10
    Wait For Paused Milestone    MILESTONE init_send    10
    Execute Command    cpu RemoveHooksAt ${init_send.strip()}
    Wait For Paused Milestone    MILESTONE physical_start_host    45
    Wait For Paused Milestone    MILESTONE settings_load    30
    Wait For Paused Milestone    MILESTONE transport_register    15
    Wait For Paused Milestone    MILESTONE daemon_ready    15

Brickwright simulation profile boots from initially erased flash without a TI service pack
    [Tags]    brickwright-simulation-hci    brickwright-erased-simulation-hci
    [Timeout]    900 seconds
    Boot Simulation HCI Through Modeled Board Devices

Brickwright simulation profile boots from existing LittleFS without a TI service pack
    [Tags]    brickwright-simulation-hci-existing-filesystem
    [Timeout]    240 seconds
    Skip If    '${HCI_BRIDGE}' == ''    HCI bridge executable was not supplied
    Load Explicit Existing LittleFS Fixture
    Boot Simulation HCI Through Modeled Board Devices
