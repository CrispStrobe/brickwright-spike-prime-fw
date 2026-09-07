*** Settings ***
Library          OperatingSystem
Library          Process
Test Setup       Create SPIKE Machine
Test Teardown    Reset SPIKE Test
Test Timeout     90 seconds

*** Variables ***
${PLATFORM}      @${CURDIR}/spike-prime.repl
${IMAGES}        ${CURDIR}/../../.local/firmware-images
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
    Execute Command    cpu AddHook ${nx_start.strip()} "monitor.Parse('log \\"MILESTONE nx_start\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${board_late.strip()} "monitor.Parse('log \\"MILESTONE board_late_initialize\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${bringup.strip()} "monitor.Parse('log \\"MILESTONE stm32_bringup\\"'); machine.PauseAndRequestEmulationPause()"
    Start Emulation
    Wait For Log Entry    MILESTONE nx_start    timeout=10
    Start Emulation
    Wait For Log Entry    MILESTONE board_late_initialize    timeout=10
    Start Emulation
    Wait For Log Entry    MILESTONE stm32_bringup    timeout=10
    ${after}=    Execute Command    cpu GetRegister "PC"
    Should Not Be Equal As Numbers    ${before.strip()}    ${after.strip()}
    ${after_value}=    Convert To Integer    ${after.strip()}
    Should Be True    0x08000000 <= ${after_value} < 0x08200000

*** Test Cases ***
Original spike-nx protected pair executes
    [Tags]    spike-nx
    Boot Protected Pair And Prove Progress    spike-nx

Brickwright protected pair executes
    [Tags]    brickwright
    Boot Protected Pair And Prove Progress    brickwright

Brickwright reaches protected userspace with board boundary isolated
    [Tags]    brickwright-userspace
    Boot Protected Pair And Prove Progress    brickwright
    ${nsh_main}=    Execute Command    sysbus GetSymbolAddress "nsh_main"
    ${btsensor_main}=    Execute Command    sysbus GetSymbolAddress "btsensor_main"
    Execute Command    cpu AddHook ${nsh_main.strip()} "monitor.Parse('log \\"MILESTONE nsh_main\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${btsensor_main.strip()} "monitor.Parse('log \\"MILESTONE btsensor_main\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu PC `cpu LR`
    Start Emulation
    Wait For Log Entry    MILESTONE nsh_main    timeout=10
    Start Emulation
    Wait For Log Entry    MILESTONE btsensor_main    timeout=10

Brickwright reaches TLC5955 through modeled IMU and flash buses
    [Tags]    brickwright-board-models
    Boot Protected Pair And Prove Progress    brickwright
    ${imu_init}=    Execute Command    sysbus GetSymbolAddress "stm32_lsm6dsl_initialize"
    ${flash_init}=    Execute Command    sysbus GetSymbolAddress "stm32_w25q256_initialize"
    ${display_init}=    Execute Command    sysbus GetSymbolAddress "tlc5955_initialize"
    Execute Command    cpu AddHook ${imu_init.strip()} "monitor.Parse('log \\"MILESTONE imu bus-model\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${flash_init.strip()} "monitor.Parse('log \\"MILESTONE flash bus-model\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${display_init.strip()} "monitor.Parse('log \\"MILESTONE display bus-model\\"'); machine.PauseAndRequestEmulationPause()"
    Start Emulation
    Wait For Log Entry    MILESTONE imu bus-model    timeout=10
    Start Emulation
    Wait For Log Entry    MILESTONE flash bus-model    timeout=10
    Start Emulation
    Wait For Log Entry    MILESTONE display bus-model    timeout=15

Brickwright reaches userspace with synchronous board functions isolated
    [Tags]    brickwright-board-stubs
    Boot Protected Pair And Prove Progress    brickwright
    ${imu_init}=    Execute Command    sysbus GetSymbolAddress "stm32_lsm6dsl_initialize"
    ${flash_init}=    Execute Command    sysbus GetSymbolAddress "stm32_w25q256_initialize"
    ${display_init}=    Execute Command    sysbus GetSymbolAddress "tlc5955_initialize"
    ${display_update}=    Execute Command    sysbus GetSymbolAddress "tlc5955_update_sync"
    ${display_set}=    Execute Command    sysbus GetSymbolAddress "tlc5955_set_duty"
    ${nsh_main}=    Execute Command    sysbus GetSymbolAddress "nsh_main"
    ${btsensor_main}=    Execute Command    sysbus GetSymbolAddress "btsensor_main"
    Execute Command    cpu AddHook ${imu_init.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${flash_init.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${display_init.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${display_update.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${display_set.strip()} "self.PC = self.LR"
    Execute Command    cpu AddHook ${nsh_main.strip()} "monitor.Parse('log \\"MILESTONE nsh_main bus-stubs\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${btsensor_main.strip()} "monitor.Parse('log \\"MILESTONE btsensor_main bus-stubs\\"'); machine.PauseAndRequestEmulationPause()"
    Start Emulation
    Wait For Log Entry    MILESTONE nsh_main bus-stubs    timeout=10
    Start Emulation
    Wait For Log Entry    MILESTONE btsensor_main bus-stubs    timeout=10

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
    Execute Command    cpu AddHook ${physical_open.strip()} "monitor.Parse('log \\"MILESTONE physical_open\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${load_firmware.strip()} "monitor.Parse('log \\"MILESTONE physical_load_firmware\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${bts_execute.strip()} "monitor.Parse('log \\"MILESTONE ti_bts_execute\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${init_send.strip()} "monitor.Parse('log \\"MILESTONE init_send\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${physical_start.strip()} "monitor.Parse('log \\"MILESTONE physical_start_host\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${settings_load.strip()} "monitor.Parse('log \\"MILESTONE settings_load\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${transport_register.strip()} "monitor.Parse('log \\"MILESTONE transport_register\\"'); machine.PauseAndRequestEmulationPause()"
    Execute Command    cpu AddHook ${daemon_ready.strip()} "monitor.Parse('log \\"MILESTONE daemon_ready\\"'); machine.PauseAndRequestEmulationPause()"
    Start Emulation
    Wait For Log Entry    MILESTONE physical_open    timeout=10
    Start Emulation
    Wait For Log Entry    MILESTONE physical_load_firmware    timeout=10
    Start Emulation
    Wait For Log Entry    MILESTONE ti_bts_execute    timeout=10
    Start Emulation
    Wait For Log Entry    MILESTONE init_send    timeout=10
    Execute Command    cpu RemoveHooksAt ${init_send.strip()}
    Start Emulation
    Wait For Log Entry    MILESTONE physical_start_host    timeout=45
    Start Emulation
    Wait For Log Entry    MILESTONE settings_load    timeout=30
    Start Emulation
    Wait For Log Entry    MILESTONE transport_register    timeout=15
    Start Emulation
    Wait For Log Entry    MILESTONE daemon_ready    timeout=15
