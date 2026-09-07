# Protected firmware resource gates

The protected build uses a 512 KiB user-flash region and 128 KiB of directly
addressable user SRAM. CI reserves the complete 10,211-byte CC2564C service-pack
footprint with synthetic, non-TI bytes before linking. No restricted controller
firmware is stored or uploaded.

`policy/resource-budgets.json` deliberately leaves these margins:

| Resource | CI ceiling | Physical region | Minimum link-time margin |
|---|---:|---:|---:|
| User flash (`text + data`) | 523,264 B | 524,288 B | 1,024 B |
| Static user RAM (`data + bss`) | 98,304 B | 131,072 B | 32,768 B |

The RAM margin is reserved for the user heap and runtime stacks; it is not a
claim that peak dynamic usage has been measured. CI also bounds the configured
Bluetooth buffer counts, delayed-work slots, telemetry ring depth, daemon stack,
and long-workqueue stack. The gate fails closed if a required setting, ELF, or
linked synthetic payload symbol is missing.

Run the gate after a protected build inside the pinned build container:

```sh
python3 tools/check_resource_budgets.py
```

Stack high-water marks, throughput, latency, and motor-stop timing require a
running hub and remain hardware qualification measurements. They must not be
inferred from these static ceilings.
