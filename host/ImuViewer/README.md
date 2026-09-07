# ImuViewer

ImuViewer is the Issue #60 desktop proof of concept. It receives the LSM6DSL
IMU stream published by the SPIKE Prime Hub `btsensor` service over
SPP/RFCOMM, estimates orientation with a Madgwick filter, and renders it in 3D.

- Frameworks: .NET 10, Avalonia 11.x, and Silk.NET
- Supported proof-of-concept host: Linux with BlueZ and `BTPROTO_RFCOMM`
- macOS and Windows currently throw `PlatformNotSupportedException`

## Project structure

| Project | Responsibility |
| --- | --- |
| `ImuViewer.Core` | Frame parsing, Madgwick filter, coordinate conversion, and Bluetooth transport abstraction |
| `ImuViewer.Rendering` | Silk.NET OpenGL cube, world axes, and grid rendering |
| `ImuViewer.App` | Avalonia UI with an RViz-inspired layout |
| `ImuViewer.Core.Tests` | xUnit unit tests |

## Build and run on Linux

```bash
cd host/ImuViewer
dotnet restore ImuViewer.slnx
dotnet build ImuViewer.slnx -c Debug
dotnet test tests/ImuViewer.Core.Tests/ImuViewer.Core.Tests.csproj
dotnet run --project src/ImuViewer.App/ImuViewer.App.csproj
```

Opening an `AF_BLUETOOTH` socket requires `cap_net_raw` on Linux, or the
application must run with `sudo`:

```bash
sudo setcap cap_net_raw,cap_net_admin+ep "$(realpath "$(which dotnet)")"
```

## Related documentation

- Frame and command protocol: `docs/en/development/pc-receive-spp.md`
- Hub command handler: `apps/btsensor/btsensor_cmd.c`
