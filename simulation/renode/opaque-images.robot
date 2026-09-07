*** Settings ***
Library          OperatingSystem
Test Setup       Create SPIKE Machine
Test Teardown    Reset Emulation
Test Timeout     45 seconds

*** Variables ***
${PLATFORM}      @${CURDIR}/spike-prime.repl
${IMAGES}        ${CURDIR}/../../.local/firmware-images

*** Keywords ***
Create SPIKE Machine
    Execute Command    include @${CURDIR}/SpikePrimeDevices.cs
    Execute Command    mach create
    Execute Command    machine LoadPlatformDescription ${PLATFORM}

Boot Raw Image And Prove Progress
    [Arguments]    ${target}    ${initial_sp}    ${reset_pc}
    File Should Exist    ${IMAGES}/${target}/firmware.bin
    Execute Command    sysbus LoadBinary @${IMAGES}/${target}/firmware.bin 0x08008000
    Execute Command    cpu VectorTableOffset 0x08008000
    Execute Command    cpu SP ${initial_sp}
    ${thumb_pc}=    Evaluate    ${reset_pc} & ~1
    Execute Command    cpu PC ${thumb_pc}
    ${before}=    Execute Command    cpu GetRegister "PC"
    Execute Command    cpu Step 2000
    ${after}=    Execute Command    cpu GetRegister "PC"
    Should Be Equal As Numbers    ${thumb_pc}    ${before.strip()}
    Should Not Be Equal As Numbers    ${before.strip()}    ${after.strip()}
    ${after_value}=    Convert To Integer    ${after.strip()}
    Should Be True    0x08000000 <= ${after_value} < 0x08200000

*** Test Cases ***
Official LEGO v2 executes from its real vector table
    Boot Raw Image And Prove Progress    lego-v2    0x2004fad0    0x08093fe1

Official LEGO v3 executes from its real vector table
    Boot Raw Image And Prove Progress    lego-v3    0x2001e000    0x0800b8bd

Pybricks v4.0.1 executes from its real vector table
    Boot Raw Image And Prove Progress    pybricks    0x20050000    0x080447e1
