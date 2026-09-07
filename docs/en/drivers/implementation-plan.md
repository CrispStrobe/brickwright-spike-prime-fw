# Driver readiness and remaining scope

This page maps production interfaces to the remaining simulation work. Ordered
tasks and acceptance gates are in the repository `PLAN.md`.

| Area | Production interface | Current simulation boundary | Required next model |
| --- | --- | --- | --- |
| Port detection | `/dev/legoport[0-5]` | board initialization | attach/detach electrical classification and generations |
| LPF2 UART | internal plus sensor ioctls | not end-to-end | negotiation, modes, keepalive, malformed frames |
| Motors | `/dev/legomotor[N]` | bounded command adapter | PWM/H-bridge, encoder, load, stall, braking |
| Sensors | `/dev/uorb/sensor_lego[N]` | synthetic protocol values | time-based mode data and disconnect behavior |
| Matrix | `/dev/leds` | TLC5955 register/latch state | rendered matrix and timing snapshots |
| IMU | `/dev/imu0` and uORB | register/data subset | ODR, FIFO, interrupt, timestamp, calibration faults |
| Sound | `/dev/tone0`, `/dev/pcm0` | command cleanup tests | TIM6/DAC/DMA timing and observable samples |
| Battery/buttons | `/dev/bat0`, `/dev/charge0` | protocol battery value | ADC ladder, charger, low-power and button events |
| Storage | W25Q256 plus LittleFS | NOR command subset | persistence, busy timing, corruption and power loss |
| Power | board lifecycle | reset path | hold, shutdown, brownout, watchdog and reboot |
| Bluetooth | H4 plus Classic/BLE services | daemon-ready H4 bridge | complete peer sessions, credits, faults and bond reload |

## Shared requirements

- Hardware seams use deterministic virtual time and observable state.
- Model reset values, bounds, interrupts, and failure behavior, not only happy
  path register reads.
- Production firmware remains unchanged except for stable observation symbols.
- Port operations validate attachment generation and capabilities.
- Motor operations have bounded duration and a defined coast/brake safe state.
- No simulated result is physical-hardware evidence.

Pin assignments and DMA ownership are in
[pin-mapping.md](../hardware/pin-mapping.md) and
[dma-irq.md](../hardware/dma-irq.md). Normative device behavior remains in the
individual driver documents.
