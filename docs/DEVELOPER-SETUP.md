# Developer Setup

**Status (2026-10-27):** Validated on the maintainer's Windows machine with .NET SDK 10.0.403 and Windows 10.0.19044. Restore succeeded; x64 and ARM64 builds succeeded both with and without `-p:DefaultLanguage=en-US`; Visual Studio package deployment succeeded; the extension was reloaded in Command Palette and its placeholder page was confirmed. The manifest explicitly declares `en-US` to prevent the earlier locale-dependent `APPX1685` failure. Exact Visual Studio version/workloads and PowerToys version were not captured. Do not regenerate the template.

## Checked-in toolchain

Source of truth: `testExtension.sln`, `testExtension/testExtension.csproj`, `Directory.Build.props`, and `Directory.Packages.props`.

- Target framework: `net10.0-windows10.0.26100.0`.
- Target Windows SDK package property: `10.0.26100.68-preview`.
- Minimum and supported OS platform version: `10.0.19041.0` (Windows 10, build 19041).
- Runtime identifiers: `win-x64;win-arm64`.
- MSBuild platforms: `x64;ARM64`; the solution also declares `x86` configurations, but the shared props list only `x64;ARM64`.
- Central package management is enabled.
- Package versions pinned in `Directory.Packages.props`:
  - `Microsoft.CommandPalette.Extensions` — `0.9.260303001`
  - `Microsoft.CodeAnalysis.NetAnalyzers` — `9.0.0-preview.24508.2`
  - `Microsoft.Web.WebView2` — `1.0.3719.77`
  - `Microsoft.Windows.CsWin32` — `0.3.183`
  - `Microsoft.Windows.CsWinRT` — `2.2.0`
  - `Microsoft.Windows.SDK.BuildTools` — `10.0.26100.4188`
  - `Microsoft.Windows.SDK.BuildTools.MSIX` — `1.7.20250829.1`
  - `Microsoft.WindowsAppSDK` — `2.0.1`
  - `Shmuelie.WinRTServer` — `2.1.1`
  - `StyleCop.Analyzers` — `1.2.0-beta.556`
  - `System.Text.Json` — `9.0.8`
- Exact SDK reported by maintainer: .NET SDK `10.0.403`. The repository does not pin an SDK with `global.json`.
- Visual Studio: solution metadata records Visual Studio `17.13.35507.96` in the generating environment, not a verified minimum. Use Visual Studio with the .NET desktop/.NET 10 SDK and Windows application development tooling required for MSIX/Windows SDK packaging. Exact installed workloads/components still need recording from the machine that successfully builds.
- Runtime requirement: Windows with Command Palette available in a current PowerToys installation, Command Palette enabled/running, and Windows Developer Mode enabled for local deployment as directed by Microsoft.

## Manifest language fix

The manifest originally used `<Resource Language="x-generate"/>`. The reported build selected `en-AE` as its default language and failed with `APPX1685`. This extension has no localized resources; `en-US` is a valid BCP-47 language tag and a suitable explicit default. The source manifest now declares `<Resource Language="en-US"/>`, avoiding dependence on the build machine's locale. Packaging validation remains enabled; no warning/error is suppressed.

Microsoft documents that `x-generate` is expanded using project resource qualifiers and that the first generated resource language is the package default. See [manifest generation](https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/generate-package-manifest) and [language/region management](https://github.com/MicrosoftDocs/windows-dev-docs/blob/docs/hub/apps/design/globalizing/manage-language-and-region.md).

## Restore and build verification

Run from a clean Windows checkout using PowerShell. Capture exit codes and complete output.

```powershell
dotnet --info
dotnet restore .\testExtension.sln
$restoreExit = $LASTEXITCODE
dotnet build .\testExtension.sln --no-restore -c Debug -p:DefaultLanguage=en-US -p:Platform=x64
$x64Exit = $LASTEXITCODE
dotnet build .\testExtension.sln --no-restore -c Debug -p:DefaultLanguage=en-US -p:Platform=ARM64
$arm64Exit = $LASTEXITCODE
"restore=$restoreExit x64=$x64Exit arm64=$arm64Exit"
```

The explicit `DefaultLanguage=en-US` is retained in the reproduction command as a deterministic diagnostic, although the source manifest now pins the language. Also run the normal build without the property to prove the source fix is sufficient:

```powershell
dotnet build .\testExtension.sln --no-restore -c Debug -p:Platform=x64
dotnet build .\testExtension.sln --no-restore -c Debug -p:Platform=ARM64
```

**Observed on the maintainer's Windows machine (SDK 10.0.403, OS build 19044):** `dotnet restore .\testExtension.sln` completed successfully (`RESTORE_EXIT=0`). The x64 and ARM64 builds each succeeded with `-p:DefaultLanguage=en-US` and again without the override; all four build commands returned exit code `0`. Outputs targeted `win-x64` and `win-arm64`, respectively. The earlier `APPX1685` failure with default language `en-AE` was resolved by the explicit `en-US` manifest resource language. These results were run locally by the maintainer.

## Deploy, reload, and debug

1. Open `testExtension.sln` in Visual Studio on Windows.
2. Select `Debug` and the intended platform (`x64` or `ARM64`).
3. Use **Build > Deploy testExtension**. A normal build alone does not register/update the MSIX package.
4. Select the `testExtension (Package)` launch profile, not `testExtension (Unpackaged)`. The package profile has `doNotLaunchApp: true` because Command Palette activates the extension as its out-of-process COM server.
5. Start/enable Command Palette in PowerToys. Run `Reload` and select **Reload Command Palette extensions**.
6. Find `testExtension` at the bottom of the command list and open it. The untouched template should display `TODO: Implement your extension here`.
7. For debugging, start the packaged profile as configured, attach/use the Visual Studio debugger for the extension process as appropriate, and inspect **View > Output** (Debug). Reload the extension after each redeploy to force re-instantiation.
8. Record the exact PowerToys version, Windows build, Visual Studio version/workloads, actual deploy result, and runtime behavior after this loop has been performed.

## Template lifecycle and search behavior

- `testExtension` implements `IExtension` and `IDisposable`; `GetProvider(ProviderType.Commands)` returns the single `testExtensionCommandsProvider`. Disposal signals the hosting event.
- The manifest registers the extension as an out-of-process COM server and an app extension named `com.microsoft.commandpalette`. Its CLSID must match the `[Guid]` in the extension class and the manifest registrations.
- `testExtensionCommandsProvider` derives from `CommandProvider` and returns one cached top-level `CommandItem` from `TopLevelCommands()`. It does not override `FallbackCommands()`.
- `testExtensionPage` derives from static `ListPage`; `GetItems()` returns the placeholder item. It does not override `UpdateSearchText` and does not implement dynamic filtering. For a search-reactive list, Microsoft documents `DynamicListPage.UpdateSearchText(oldSearch, newSearch)`; after changing backing items, call `RaiseItemsChanged()` so the host fetches the new list.
- The official overview says only the Commands provider type is currently supported. Top-level commands come from `TopLevelCommands()`; fallback commands are optional. Context actions are attached to command items and return a `CommandResult` to control dismissal/navigation.

Sources: [create an extension](https://learn.microsoft.com/en-us/windows/powertoys/command-palette/creating-an-extension), [extensibility overview](https://learn.microsoft.com/en-us/windows/powertoys/command-palette/extensibility-overview), [DynamicListPage.UpdateSearchText](https://learn.microsoft.com/en-us/windows/powertoys/command-palette/microsoft-commandpalette-extensions-toolkit/dynamiclistpage_updatesearchtext), [updating a list of commands](https://learn.microsoft.com/en-us/windows/powertoys/command-palette/update-a-list-of-commands).

## Troubleshooting

- `APPX1685` with `en-AE`: verify the manifest's resource language is explicitly `en-US`; do not disable packaging validation.
- Extension absent after build: use **Build > Deploy**, then reload Command Palette extensions.
- Launching the unpackaged profile does not register the extension package; use `(Package)`.
- Verify the three CLSID occurrences agree between C# and manifest.
- Check Visual Studio Output (Debug), Windows event/debug output, Command Palette state, package registration, and architecture selection.
- Do not commit local game-library exports, private metadata, credentials, local paths, or build output.

## References

- [Create a Command Palette extension](https://learn.microsoft.com/en-us/windows/powertoys/command-palette/creating-an-extension)
- [Extensibility overview](https://learn.microsoft.com/en-us/windows/powertoys/command-palette/extensibility-overview)
- [PowerToys Command Palette source](https://github.com/microsoft/PowerToys/tree/main/src/modules/cmdpal)
- [MSIX manifest generation](https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/generate-package-manifest)

## Validation status

- [x] Checked-in solution, project, shared props, package versions, manifest, provider, page, extension lifecycle, and package launch profile inspected.
- [x] Deterministic manifest language fix applied on the issue branch.
- [x] Windows restore succeeded after fix (`dotnet restore .\\testExtension.sln`, exit code 0).
- [x] x64 and ARM64 builds succeeded with and without the `DefaultLanguage=en-US` override (all four builds exit code 0).
- [x] Visual Studio package deployment succeeded; Command Palette extension reload and placeholder-page runtime check succeeded.
- [x] Windows version recorded as 10.0.19044 and .NET SDK as 10.0.403.
- [ ] Exact installed Visual Studio version/workloads and PowerToys version recorded.
