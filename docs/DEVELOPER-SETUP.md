# Developer Setup

Follow this guide to build, test, and run PlayniteCmdPal on Windows.

## 1. Prerequisites

Install these before cloning the repository:

| Requirement | Used for |
|---|---|
| Windows 11, x64 or ARM64 | Running PowerToys Command Palette and the extension |
| Git | Cloning the repository |
| .NET 10 SDK (10.0.x) | Restoring, building, and testing the solution |
| Python 3.9 or later | Running the repository's CI script |
| Visual Studio with the **WinUI application development** workload | Deploying the MSIX package from the IDE |
| PowerToys with **Command Palette** enabled | Loading and using the extension |
| Developer Mode enabled in Windows | Installing the locally built MSIX package |
| Playnite | Optional: testing against a real game library |

Playnite is only required for the real-library integration steps. You do not need it to build or run the automated tests.

### Install the .NET SDK

Install the [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0). Then open a new PowerShell window and verify:

```powershell
dotnet --list-sdks
dotnet --version
```

At least one `10.0.x` SDK must be installed and selected.

### Install Python

Install [Python 3.9 or later](https://www.python.org/downloads/) and make sure it is available on `PATH`:

```powershell
python --version
```

The CI script uses only Python's standard library. No `pip` packages are required.

### Install Visual Studio

Install [Visual Studio](https://visualstudio.microsoft.com/downloads/) with the **WinUI application development** workload.

If Visual Studio is already installed, open Visual Studio Installer, select **Modify**, and add that workload.

### Enable Developer Mode

Open **Settings → System → For developers**, turn on **Developer Mode**, and accept the prompt. This allows Visual Studio to deploy the locally built MSIX package.

Install [PowerToys](https://learn.microsoft.com/en-us/windows/powertoys/install) and make sure **Command Palette** is enabled in PowerToys settings.

## 2. Clone the repository

Open PowerShell and run:

```powershell
git clone https://github.com/werdscopez7347/PlayniteCmdPal.git
cd PlayniteCmdPal
```

Use the `dev` branch for development:

```powershell
git switch dev
git pull
```

## 3. Restore and build

From the repository root, restore the solution:

```powershell
dotnet restore .\PlayniteCmdPal.sln
```

Build the solution:

```powershell
dotnet build .\PlayniteCmdPal.sln --configuration Release --no-restore
```

To run the complete local CI checks instead, use the repository's script:

```powershell
.\scripts\ci.ps1
```

The script runs the release-tooling checks, restores and builds the solution, runs the automated test suites, and runs the .NET Framework bridge smoke test. A successful run ends with:

```
All local CI checks passed.
```

You need network access for NuGet restore. Visual Studio, PowerToys, and Playnite are not required to run these automated checks.

For individual test commands and details about the test projects, see [Testing](TESTING.md).

## 4. Deploy the extension

Deployment registers the extension with Windows. A normal build alone does not do this.

1. Open `PlayniteCmdPal.sln` in Visual Studio.
2. Select **Debug** and the platform matching your machine: **x64** or **ARM64**.
3. Select **Build → Deploy PlayniteCmdPal**.
4. Select the `PlayniteCmdPal (Package)` launch profile.
5. Start PowerToys and confirm Command Palette is enabled.
6. Open Command Palette, search for `Reload`, and select **Reload Command Palette extensions**.
7. Find and open **PlayniteCmdPal** in the command list.

The extension should now open in Command Palette.

### After changing code

Repeat **Build → Deploy PlayniteCmdPal**, then reload Command Palette extensions. Command Palette caches loaded extensions, so changes may not appear until you reload.

## 5. Connect your Playnite library (optional)

Skip this section if you only want to build, test, or open the extension.

The Playnite companion plugin supplies the game-library data used by the extension.

1. Install [Playnite](https://playnite.link/).
2. From the repository root, package the companion plugin:

   ```powershell
   .\scripts\package-playnite-plugin.ps1
   ```

3. When the script succeeds, find the package here:

   ```
   artifacts\playnite-plugin\PlayniteCmdPalBridge.pext
   ```

4. Drag `PlayniteCmdPalBridge.pext` onto the Playnite window and confirm the installation.
5. Restart Playnite.
6. Open PlayniteCmdPal in Command Palette and search for a game in your library.

For the bridge architecture, diagnostics, and more detailed verification steps, see [Catalog Bridge](CATALOG-BRIDGE.md).

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| `dotnet` is not recognized | Open a new PowerShell window and check that the .NET 10 SDK is installed and on `PATH`. |
| NuGet restore fails | Check your network connection, then run `dotnet restore .\PlayniteCmdPal.sln` again. |
| Visual Studio cannot deploy the package | Confirm Developer Mode is enabled and the WinUI application development workload is installed. |
| The extension does not appear | Confirm PowerToys and Command Palette are enabled. Run **Build → Deploy PlayniteCmdPal**, then reload Command Palette extensions. |
| Code changes do not appear | Deploy again and reload Command Palette extensions. |
| The extension opens but no games appear | Install and enable the Playnite companion plugin, then restart Playnite. |

When reporting a problem, include the command or Visual Studio action that failed and the complete error message. Remove personal paths and any private Playnite library data.

## More documentation

- [Testing](TESTING.md) — test projects and commands.
- [Catalog Bridge](CATALOG-BRIDGE.md) — Playnite integration and diagnostics.
- [Release Packaging](RELEASE-PACKAGING.md) — release builds and package inspection.
