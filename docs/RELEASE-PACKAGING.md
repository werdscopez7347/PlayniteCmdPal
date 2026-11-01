# Release Packaging and Windows SDK Validation

## Windows SDK targeting-pack selection

The project previously forced the preview targeting-pack version `10.0.26100.68-preview`. This has been replaced with the stable Microsoft NuGet package `Microsoft.Windows.SDK.NET.Ref 10.0.26100.87`, selected through the shared `WindowsSdkPackageVersion` property in [Directory.Build.props](../Directory.Build.props).

Evidence for the candidate:

- NuGet identifies `Microsoft.Windows.SDK.NET.Ref` as the Windows SDK targeting pack for .NET 9 and later; its compatibility table includes .NET 10 as a computed compatible target. Version `10.0.26100.87` is published by the Microsoft/WindowsSDK package owners and has no `-preview` suffix: https://www.nuget.org/packages/Microsoft.Windows.SDK.NET.Ref/10.0.26100.87
- Microsoft's Windows SDK downloads page distinguishes stable SDK releases from preview releases and directs users to the Windows SDK NuGet feed for NuGet packages: https://learn.microsoft.com/en-us/windows/apps/windows-sdk/downloads
- The 26100 SDK family corresponds to Windows 11 24H2 and is the same API family embedded in `net10.0-windows10.0.26100.0`. The minimum supported OS remains Windows 10 build 19041. The Windows SDK compile-time API surface and the OS runtime API availability are separate: https://learn.microsoft.com/en-us/windows/apps/get-started/versioning-overview
- The targeting-pack package is independent of the `Microsoft.CommandPalette.Extensions` package version. x64 and ARM64 are runtime identifiers/build platforms and do not require different Windows SDK targeting-pack package versions.

### Support and licensing

The package is published under the Microsoft and WindowsSDK NuGet owner identities. The Windows SDK is a development-time component; its headers, libraries, and metadata are used to compile the app and are not shipped as app payload. The Microsoft Windows SDK software license terms govern use of the SDK and its associated APIs, updates, and supplements; review and accept the applicable license before installing or using it. Do not redistribute the SDK/targeting-pack package as a standalone product. The application MSIX must contain only the app's required runtime/package assets, not the SDK itself.

References:
- Microsoft Windows SDK license terms: https://github.com/microsoft/win32metadata/blob/main/licenses/sdk_license.txt
- Microsoft SDK/runtime distinction and packaging notes: https://learn.microsoft.com/en-us/windows/apps/get-started/versioning-overview

The candidate is selected on package identity, stable release status, TFM compatibility metadata, and matching SDK family. This is not a claim that the project's full Windows toolchain has passed validation.

## Required Windows validation

Run from a clean checkout on a supported Windows development machine with the .NET 10 SDK and the Visual Studio Windows/WinUI/MSIX components required by the generated project. Record the actual versions and outputs in the pull request.

- [ ] `dotnet --info` and Visual Studio version/components recorded.
- [ ] `dotnet restore .\testExtension.sln` succeeds using the stable targeting pack.
- [ ] `dotnet build .\testExtension.sln -c Release` succeeds.
- [ ] `dotnet test .\testExtension.sln -c Release` succeeds (or record why no test project is present).
- [ ] Visual Studio **Build > Deploy** successfully registers the MSIX package; Command Palette extension reload and activation work.
- [ ] x64 Release publish/package path succeeds.
- [ ] ARM64 Release publish/package path succeeds.
- [ ] Compare package manifests and runtime notices for both architectures; record any API or behavior differences.
- [ ] Confirm no preview Windows SDK targeting-pack dependency remains in evaluated MSBuild properties or restore assets.

Suggested publish commands (adjust only if the generated publish profiles require additional properties):
```powershell
dotnet publish .\testExtension\testExtension.csproj -c Release -r win-x64 -p:Platform=x64
dotnet publish .\testExtension\testExtension.csproj -c Release -r win-arm64 -p:Platform=ARM64
```

Do not mark the migration complete or the release go/no-go gate satisfied until these Windows-only checks have evidence. A non-Windows environment cannot validate Visual Studio deployment or the Windows MSIX packaging path.
