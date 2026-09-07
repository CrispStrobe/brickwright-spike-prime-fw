# ImuViewer

ImuViewer is a desktop telemetry client for the SPIKE Prime `btsensor`
service. It parses IMU frames, estimates orientation with a Madgwick filter,
and renders the result in 3D. During the firmware's simulation-only phase it
is primarily a protocol and visualization test client; it is not evidence that
the firmware or radio path is safe on physical hardware.

- Frameworks: .NET 10, Avalonia 11.x, and Silk.NET
- Supported proof-of-concept host: Linux with BlueZ and `BTPROTO_RFCOMM`
- macOS and Windows currently throw `PlatformNotSupportedException`
- The current transport is Classic SPP/RFCOMM; a direct Renode byte-stream
  adapter and BLE transport are not yet implemented in this application.

## Project structure

| Project | Responsibility |
| --- | --- |
| `ImuViewer.Core` | Frame parsing, Madgwick filter, coordinate conversion, and Bluetooth transport abstraction |
| `ImuViewer.Rendering` | Silk.NET OpenGL cube, world axes, and grid rendering |
| `ImuViewer.App` | Avalonia UI with an RViz-inspired layout |
| `ImuViewer.Core.Tests` | xUnit unit tests |

## Build and test

```bash
cd host/ImuViewer
dotnet restore ImuViewer.slnx
dotnet build ImuViewer.slnx -c Debug
dotnet test tests/ImuViewer.Core.Tests/ImuViewer.Core.Tests.csproj
```

The parser, filter, and coordinate tests require neither Bluetooth nor a hub.
To run the current Linux RFCOMM UI explicitly:

```bash
dotnet run --project src/ImuViewer.App/ImuViewer.App.csproj
```

Opening an `AF_BLUETOOTH` socket requires `cap_net_raw` on Linux, or the
application must run with `sudo`:

```bash
sudo setcap cap_net_raw,cap_net_admin+ep "$(realpath "$(which dotnet)")"
```

Granting capabilities changes the local `dotnet` executable. It is unnecessary
for builds and unit tests. Do not use this application as a reason to flash the
work-in-progress firmware; follow the repository-level `SAFETY.md` gate.

## Related documentation

- Frame and command protocol: `docs/en/development/pc-receive-spp.md`
- Hub command handler: `apps/btsensor/btsensor_cmd.c`
