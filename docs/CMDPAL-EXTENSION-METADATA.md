# Command Palette extension metadata: what is displayed, and why

**Investigated:** 2026-10-31 for WERD-70.
**Scope:** why Command Palette shows the PlayniteCmdPal extension's logo but not the extension's manifest `Description`, and which metadata each Command Palette surface actually renders.

This document records evidence, not preference. Where a conclusion depends on PowerToys source, the file is named. Nothing here changes the manifest: the extension description is correct and stays as it is.

## Question

The installed AppX manifest declares:

```xml
<uap3:AppExtension Name="com.microsoft.commandpalette"
  Id="ID"
  PublicFolder="Public"
  DisplayName="Playnite"
  Description="Search and launch games from your Playnite library using PowerToys Command Palette.">
```

`Get-AppxPackage`/`Get-AppxPackageManifest` confirm that string is present in the registered package, and Command Palette shows the new logo. The description does not appear anywhere in the UI. Is that a deployment defect, a mistake in this repository's manifest, or expected behaviour?

**Answer: expected behaviour in the current SDK and shell.** Command Palette never reads the `uap3:AppExtension` `Description` attribute. It reads `DisplayName` and the package's `DisplayName`, and it builds every user-visible subtext from the command model the extension returns at runtime. The description is valid, declared, registered, and simply unused by the host.

## Evidence

### 1. The host does not read the property

PowerToys' extension wrapper projects only a fixed subset of `Windows.ApplicationModel.AppExtensions.AppExtension` into its own model. In `src/modules/cmdpal/Microsoft.CmdPal.UI.ViewModels/Models/ExtensionWrapper.cs` the constructor assigns:

- `PackageDisplayName = appExtension.Package.DisplayName`
- `ExtensionDisplayName = appExtension.DisplayName`
- `PackageFullName`, `PackageFamilyName`, `Publisher`, `InstalledDate`, `Version`
- the app user model id and the extension id

`AppExtension.Description` is not assigned, and the interface it satisfies (`src/modules/cmdpal/Microsoft.CmdPal.Common/Services/IExtensionWrapper.cs`) has no description member at all. A repository-wide search of `src/modules/cmdpal` for a read of `Description` on the `AppExtension` type returns nothing. The same is true at the newer `v0.103.3012` tag as at the `main` checkout: `ExtensionWrapper` still copies only `DisplayName`, and `IExtensionWrapper` still has no description property. This is not a regression in one build; it is the shape of the host contract.

### 2. Every subtext surface is computed, not read from the manifest

Command Palette's list rows and settings rows take their secondary line from the command provider, not from package metadata.

- Search/list rows: `TopLevelViewModel.Subtitle` returns the `ICommandItem.Subtitle` the extension set on the item (`src/modules/cmdpal/Microsoft.CmdPal.UI.ViewModels/TopLevelViewModel.cs`). The extension's own item is a `CommandItem` with `Title` set and no `Subtitle`, so the row has no secondary line.
- Settings → Extensions rows: `ExtensionsPage.xaml` binds `Description="{x:Bind ExtensionSubtext}"` and `Header="{x:Bind DisplayName}"`. `ProviderSettingsViewModel.ExtensionSubtext` formats a resource string from the extension name and command counts — `"{0}, {1} commands"` (`Properties/Resources.resx`, `builtin_extension_subtext`) — and the disabled variant from `builtin_extension_subtext_disabled`. The About card binds `Extension.Publisher` and `Extension.PackageDisplayName`.

So the description that a user would see in Settings is generated from live command counts. Even a fully populated `AppExtension.Description` would not reach those strings.

### 3. The extension metadata requirement is `DisplayName`, and it is satisfied

Microsoft documents `uap3:AppExtension` with `DisplayName` as **required** and `Description` as **optional**, a free string of 1–2048 characters ("The description of the app"). The schema imposes no requirement that a host display it, and `uap3:Properties` is explicitly "stored and not read by the operating system … only read by the host app". PowerToys, as the host, reads `DisplayName` and ignores `Description`, which is permitted. Microsoft's own extension template declares both attributes but does not rely on the description being surfaced either.

### 4. What the logo proves, and what it does not

The logo appearing is evidence that the package is registered and discovered: the icon in a Command Palette row comes from `IconHelpers.FromRelativePath("Assets\\StoreLogo.png")` resolved inside the extension's own package. It is not evidence that the manifest `Description` failed to register — those are independent paths through the manifest, and section 1 shows the description has no consumer.

### 5. The description value in this repository is correct

`PlayniteCmdPal/Package.appxmanifest` declares the same string that `Get-AppxPackageManifest` reports on the installed package. It is within the schema's length bounds, it is not localized to a missing resource, and `en-US` is declared in `<Resources>`. There is nothing to repair in the value.

## What the user actually sees, by surface

| Surface | Source | Current value in this repository |
|---|---|---|
| Command Palette result row, primary line | `CommandItem.Title` (falling back to `ExtensionDisplayName`) | `Playnite` |
| Command Palette result row, secondary line | `CommandItem.Subtitle` | not set → no secondary line |
| Settings → Extensions row, header | provider `DisplayName` | `Playnite` |
| Settings → Extensions row, description | generated `"{extension name}, {n} commands"` | `Playnite, 1 command` |
| Settings → Extension about card | `PackageDisplayName`, `Publisher` | `PlayniteCmdPal`, `PlayniteCmdPal` |
| Windows Start / app list entry | `uap:VisualElements` + `AppListEntry="none"` | hidden by design |
| Gallery listing (if listed) | `extensions.json` `shortDescription` / `description` | repository draft in `docs/gallery/extension.json.template` |
| `uap3:AppExtension` `Description` | nothing reads it | correct value, unused |

## If a description must be visible

Only the extension can supply it, through the command model. The supported, non-invented options are:

1. **Leave it as is.** One result named `Playnite` with no secondary line. This is what the current stable host renders for the declared metadata, and it matches the `Reload Command Palette extensions` reload behaviour Microsoft documents (rebuild → deploy → reload).
2. **Set `CommandItem.Subtitle`** on the top-level item in `PlayniteCmdPalCommandsProvider` — for example the same sentence as the manifest description. This is a one-line change to the command model, purely presentational, and outside WERD-70's branding scope.
3. **Fill in the Gallery entry** (`docs/gallery/extension.json.template`) if the extension is ever listed; the Gallery surfaces `shortDescription` and `description` from that feed, not from the package manifest.

Adding new `uap3:Properties`, inventing manifest attributes, or duplicating the description into `uap:VisualElements/Description` (which belongs to the hidden host app and is not shown by Command Palette) would not make the description appear. Those are rejected.

## Reproduction and confirmation steps (Windows)

```powershell
Get-AppxPackage -Name PlayniteCmdPal | Format-List Name, PackageFullName, Version, InstallLocation
(Get-AppxPackageManifest -Package (Get-AppxPackage -Name PlayniteCmdPal).PackageFullName).Package.Applications.Application.Extensions.Extension.AppExtension
```

The second command should print `DisplayName=Playnite` and the description string, proving registration. Then, in Command Palette, run `Reload Command Palette extensions` and compare the row against the table above. If a row still shows a stale subtitle after a reload, that is a discovery/caching question (Command Palette queries `AppExtensionCatalog.Open("com.microsoft.commandpalette").FindAllAsync()` and keeps an in-memory list until a refresh), not a description problem; see the clean-reinstall procedure in [Command Palette search and launch smoke test](CMDPAL-SEARCH-SMOKE-TEST.md).

## Conclusion

No defect, no manifest change, and no repository change are warranted for the missing description. The behaviour is by design in the current Command Palette SDK and host: the extension listing is described by `DisplayName` plus live command metadata, and the `uap3:AppExtension` `Description` attribute is not a display surface.
