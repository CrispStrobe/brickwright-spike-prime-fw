# ImuViewer

ImuViewer parses SPIKE `btsensor` IMU frames, estimates orientation with a
Madgwick filter, and renders it with Avalonia and Silk.NET. It is currently a
protocol/visualization client, not physical-hardware evidence.

| Project | Responsibility |
| --- | --- |
| `ImuViewer.Core` | parsing, orientation, coordinates, transport abstraction |
| `ImuViewer.Rendering` | OpenGL cube, axes, and grid |
| `ImuViewer.App` | Avalonia desktop UI |
| `ImuViewer.Core.Tests` | transport-independent unit tests |

## Build and test

```bash
cd host/ImuViewer
dotnet restore ImuViewer.slnx
dotnet build ImuViewer.slnx -c Debug
dotnet test tests/ImuViewer.Core.Tests/ImuViewer.Core.Tests.csproj
```

The proof-of-concept live transport is Linux BlueZ Classic RFCOMM. macOS,
Windows, direct Renode streams, and BLE are unsupported. Running the live Linux
client may require `cap_net_raw`; parser and rendering tests require no special
privilege and no hub.

Protocol: `docs/en/development/pc-receive-spp.md`

Wire definitions: `apps/btsensor/btsensor_wire.h`

Do not use this client as a reason to flash the simulation-only firmware.
