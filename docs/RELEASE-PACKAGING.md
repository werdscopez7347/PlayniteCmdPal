# Release packaging and Command Palette Gallery readiness

**Status (2026-11-19): the release-candidate build, signing and inspection run is complete — both architectures
pass strict inspection and all six WERD-81 acceptance criteria pass (see
[WERD-81 release evidence](RELEASE-EVIDENCE-WERD-81.md)). No public release or Gallery submission is approved:
the licensing review, the clean-machine walkthrough and Store certification remain open.**

This document is the release checklist for PlayniteCmdPal. It supersedes the generic examples in the publish-extension skill where those examples conflict with this repository's actual package, manifest, or licensing review.

## 1. Keep the two artifacts separate

This repository produces two different Windows artifacts:

| Artifact | Project / script | Purpose | Distribution status |
|---|---|---|---|
| Command Palette extension | `PlayniteCmdPal/PlayniteCmdPal.csproj`, `PlayniteCmdPal/Package.appxmanifest` | The MSIX-packaged out-of-process Command Palette extension | Candidate public product; not release-approved |
| Playnite companion plugin | `PlayniteCmdPal.PlaynitePlugin/`, `scripts/package-playnite-plugin.ps1` | Exports the Playnite catalog snapshot consumed by the CmdPal extension; produces a Playnite `.pext` | Local integration artifact; **not** the Command Palette installer and **not** a Gallery install source |

Do not upload `PlayniteCmdPalBridge.pext` to the Store or list it as the Command Palette extension's Gallery install source. The Gallery installs the CmdPal extension, not its companion Playnite bridge.

The CmdPal project is an MSIX/packaged extension. Its project targets `net10.0-windows10.0.26100.0`, declares `win-x64` and `win-arm64`, and has self-contained publish profiles for both architectures. The package manifest and project both declare version `0.0.8.0`, Partner Center identity `werdscopez7347.PlayniteforCommandPalette`, and publisher `CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70`. The publisher display name is `werdscopez7347`. The COM registration is an out-of-process executable server (`com:ExeServer`); it is not an InprocServer32 DLL registration. Release builds use the stable `Microsoft.Windows.SDK.NET.Ref 10.0.26100.84` targeting pack selected centrally in `Directory.Build.props`; `scripts/release/release_tool.py preflight` fails if any of these declarations drift.

## 2. Distribution decision

Microsoft's current guidance says the Extension Gallery is a curated catalogue, not a hosting service. Each listing must point to an extension already published through one of the supported install sources: Microsoft Store or WinGet. Microsoft currently recommends the Store; WinGet is also supported when its manifest uses the `windows-commandpalette-extension` tag.

**Distribution decision: Microsoft Store via MSIX bundle is the primary channel.** GitHub Releases provide direct-download assets, and WinGet is an additional install route. The Command Palette Gallery will expose Microsoft Store and WinGet as its two install options after both sources are live. Do not create an Inno Setup EXE based on the old generic example: it changes the project to unpackaged mode and uses an InprocServer32 registration, which does not match this project's packaged out-of-process COM server.

Microsoft Store handles production signing for Store-distributed MSIX packages after certification. No publisher-managed production certificate is required for this path. GitHub-hosted packages and WinGet downloads do not inherit Store signing or Store installation reputation; treat their signing/trust requirements separately. No package should be published until the maintainer approves the completed release review.

## 3. Release version and package identity

- Keep the public version in Semantic Versioning form and map it to the four-part MSIX version. For example, SemVer `0.0.8` maps to MSIX `0.0.8.0`.
- The current development package version is `0.0.8.0` in both `PlayniteCmdPal/Package.appxmanifest` and `PlayniteCmdPal/PlayniteCmdPal.csproj`. Keep every declaration synchronized with `scripts/release/release_expectations.json`; public release versions must still follow the maintainer-approved release process.
- The release Windows SDK pin is `Microsoft.Windows.SDK.NET.Ref 10.0.26100.84`. This is a stable package whose `lib/net8.0` projection assets are enumerated by Microsoft's [Windows SDK REDIST list](https://learn.microsoft.com/en-us/legal/windows-sdk/redist), which is the WERD-76 distribution decision. `10.0.26100.87` was evaluated under WERD-77 but is not the distribution pin; see the reconciliation note in section 10.
- The Partner Center identity supplied by the maintainer is applied in `PlayniteCmdPal/Package.appxmanifest`: Name `werdscopez7347.PlayniteforCommandPalette`, Publisher `CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70`, and PublisherDisplayName `werdscopez7347`.
- Keep the manifest version, evaluated package version, Store submission version, and release tag aligned.
- Microsoft Store performs production signing for Store-distributed packages. Follow [Microsoft Store package identity and MSIX signing](MSIX-SIGNING.md) for the identity record, Store-managed signing model, package validation, and submission evidence.

## 4. Assets and Gallery metadata

### Existing assets

The repository has an original brand asset pack at `PlayniteCmdPal-Brand-Assets/`. Its `icons/png/app-icon-256.png` is documented as a 256×256 PNG (5,393 bytes), which fits the Gallery guide's recommended 256×256 size and 100 KB maximum. Use this asset as the candidate Gallery icon after checking the actual file and previewing it at small sizes.

The MSIX-specific exports are in `PlayniteCmdPal-Brand-Assets/icons/png/msix/`. Their integration was completed by [branding PR #18](https://github.com/werdscopez7347/PlayniteCmdPal/pull/18), which has merged into `dev`. The merged `docs/BRANDING.md` and asset-package README define the asset mapping. Before producing a release candidate, verify the manifest-to-file paths and inspect the packaged visuals against that mapping.

### Gallery listing draft

A schema-shaped, deliberately unlisted template is in [`gallery/extension.json.template`](gallery/extension.json.template). It is not a publishable listing: its author/path and Microsoft Store product ID are placeholders, and `listed` is `false`. Replace every placeholder only after the publisher identity and a live install source are confirmed.

The current official Gallery contribution guide and schema require:

- A folder named `extensions/<author>/<extension-name>/`; both path segments use lowercase letters, digits, and hyphens.
- An `extension.json` with required `id`, `title`, `shortDescription`, `description`, `author`, `icon`, and at least one `installSources` entry.
- An ID of `<author>.<extension-name>` matching the folder path.
- A PNG or JPEG icon (SVG is not supported), no larger than 100 KB; 256×256 is recommended.
- Optional tags (up to five, max 30 characters each), categories (up to three from the official enum), and up to five screenshots (PNG/JPEG, max 1 MB each).
- A pull request to `microsoft/CmdPal-Extensions` targeting that repository's `main` branch. Its CI validates the schema, required fields, path/ID match, and icon presence/size. Gallery contributors may need to complete Microsoft's Contributor License Agreement (CLA).

The Gallery PR is a separate contribution to Microsoft's repository. It is not this repository's WERD-63 PR, which targets this project's `dev` branch.

### Do not create a live listing yet

The schema requires a real `installSources` entry. Do not insert a guessed WinGet package identifier or Store product ID just to make the JSON look complete. The draft remains unlisted until a real source exists and the release has passed its approval gates.

## 5. Build and package evidence

The checked-in publish profiles select `win-x64` and `win-arm64`, use self-contained publishing, and disable trimming, ReadyToRun and single-file publishing so the reviewed SDK projection assemblies ship byte-for-byte. The project also has a post-publish target that copies the runtime pack's `THIRD-PARTY-NOTICES.TXT` into the publish output and into the MSIX payload, and fails if the source notice is absent.

The repository's documented automated baseline is:

```powershell
.\scripts\ci.ps1
```

That command restores, builds, runs the core and adapter test projects, and executes the .NET Framework snapshot smoke test. It is not an MSIX packaging test.

A release candidate still needs a Windows packaging run for both architectures. That run is automated by the
release tool described in section 10: it builds, signs, inspects and records the evidence bundle. Do not copy a
generic `dotnet publish`, MakeAppx or Inno Setup command into release instructions; use the checked-in tool so the
commands, tool versions, package hashes, manifest contents and inspection results are recorded together. The local
Visual Studio **Build > Deploy** path in [Developer Setup](DEVELOPER-SETUP.md) is a development deployment, not
proof of a distributable release package.

Do not commit generated packages, certificates, or private keys. The tool writes to `artifacts/release/<version>/`,
which is git-ignored.

## 6. Licensing and release blockers

The current audit in [Licensing and release readiness](LICENSING-AND-RELEASE.md) records the selected Windows SDK package and the remaining public-release obligations.

1. **Historical WERD-76 Windows SDK projection-package evidence (10.0.26100.84).** The earlier WERD-76 change evaluated stable `Microsoft.Windows.SDK.NET.Ref 10.0.26100.84`; its `lib/net8.0` assets matched the framework paths enumerated in Microsoft's [Windows SDK REDIST.TXT](https://learn.microsoft.com/en-us/legal/windows-sdk/redist). Release trimming and ReadyToRun were disabled for both RIDs, and the two SDK-derived DLLs in the WERD-76 x64/ARM64 candidate packages matched their package-source hashes byte-for-byte. The package, DLL and MSIX hashes, NuGet signature verification, and test evidence in [Licensing and release readiness](LICENSING-AND-RELEASE.md) are historical evidence for WERD-76 / version 10.0.26100.84 only. **Those package and DLL hashes do not validate WERD-77's 10.0.26100.87 selection or its package payload.** Individual written Microsoft confirmation is not an engineering prerequisite for the historical WERD-76 engineering path.

2. **Windows SDK licence conditions — public-release review.** The SDK licence still contains downstream distributor/end-user terms, copyright and indemnification conditions. The Store, GitHub Releases and WinGet terms have been reviewed as context, not legally approved. Do not infer that the package choice alone satisfies every channel-specific obligation. Resolve those conditions as part of public-release approval; no public binary is approved by WERD-76's engineering change alone.

3. **Runtime notices — historical package evidence and current WERD-77 checks.** The earlier filesystem-publish notice files for both RIDs matched their restored runtime-pack notice files (SHA-256 `6D15E10A101C6BFFF2AB4429ED061BF76C456FC4B23AD6B03E0D0F8377148A21`). The earlier x64/ARM64 package-inspection record reported `dotnet-runtime-THIRD-PARTY-NOTICES.txt`, the project `LICENSE`, `THIRD-PARTY-NOTICES.md`, and `Microsoft-PowerToys-LICENSE.txt`; that is historical release-audit evidence and does not establish the contents of WERD-77's .87 ARM64 package. For WERD-77, both .87 publish outputs contain the runtime notice and the installed x64 MSIX payload was verified to contain it. The final .87 ARM64 MSIX archive still requires its own inspection (item 6). Release notes must still reference the .NET Library License.

4. **Dependency inventory and publish-payload verification — Windows evidence recorded.** The corrected Windows PowerShell 5.1 inventory run reported 4 shipped-runtime, 4 shipped-build, 13 test-only, 0 developer-tool and 0 unclassified packages; its JSON SHA-256 is `A32B318636DC6AC98974524DBD014F5C915C80E967281FC50C5A5C86F51F174C`. Five review flags remain (four in shipped classifications); these flags are not a count of redistributed binaries. The inspected publish outputs did not contain the searched BuildTools, ReferenceAssemblies, xUnit or test-platform files. The earlier package-inspection record reports both architecture MSIX archives contained the required notices and `Microsoft.CommandPalette.Extensions.winmd`; that historical result is not an archive-content check of the WERD-77 .87 PR head. Disabling WinMD registration harvesting removed APPX1707 while retaining the WinMD payload. The `.pext` archive contains `LICENSE` and `THIRD-PARTY-NOTICES.md`; `System.Text.Json.dll` and `PlayniteSDK.dll` are absent.

5. **Store identity and signing.** Partner Center identity values have been supplied and applied to the manifest. Confirm them against the Partner Center product dashboard, then complete the Store packaging, validation, and certification workflow. No publisher-managed signing certificate is required for Store distribution. Direct GitHub/WinGet downloads need a separately evaluated trust model.

6. **Windows SDK targeting pack — WERD-77 evaluated .87; the release pin is .84.** WERD-77 selected stable `Microsoft.Windows.SDK.NET.Ref 10.0.26100.87` and validated restore, Release solution build, tests, Visual Studio x64 deployment/activation and x64/ARM64 publishing on Windows 11 build 26200 with .NET SDK 10.0.403 and MSBuild 18.9.15. WERD-76's distribution decision requires the `.84` package because its `lib/net8.0` projection assets are the group enumerated by the REDIST list; `.87` ships a `lib/net9.0` asset group that the WERD-76 review did not clear. WERD-81 therefore pins `10.0.26100.84` for release candidates and keeps the trimming/ReadyToRun restrictions that preserve the two shipped projection DLLs. The WERD-77 validation history remains recorded below; it validates the stable targeting-pack migration, not redistribution of `.87`. **Outstanding:** run `scripts/release/release_tool.py build` for both architectures and record the new package hashes; see section 10 and [WERD-81 release evidence](RELEASE-EVIDENCE-WERD-81.md).

7. **Clean-machine acceptance:** replay install, first launch, update, uninstall, and rollback on a clean supported Windows environment. This independent walkthrough remains outstanding and must not be marked complete without evidence.

A successful CI build does not clear the separate public-release obligations above. Do not publish a binary or submit a Gallery listing until the release checklist is satisfied.

### Historical WERD-76 implementation update — 2026-11-08

The WERD-76 branch pinned `Microsoft.Windows.SDK.NET.Ref 10.0.26100.84`, retains the `net10.0-windows10.0.26100.0` application target, and disables `PublishTrimmed` and `PublishReadyToRun` in both x64 and ARM64 Release profiles. The package's `lib/net8.0` assets are explicitly enumerated by the REDIST list, and the isolated Windows builds preserved both shipped SDK DLLs byte-for-byte. NuGet signature verification succeeded and the filtered solution tests passed 341 tests; see [Licensing and release readiness](LICENSING-AND-RELEASE.md) for exact evidence.

Individual written Microsoft confirmation is not an engineering prerequisite for this selected package path. The SDK licence's downstream terms and indemnification conditions remain part of the public-release review. The unsigned candidate MSIX packages were not installed or runtime-tested. Windows restore/build/test CI and C# analysis passed on PR #23 head `13a3e94022e69788e6d667ed4f92cf934b935c30` on 2026-11-08. The unsigned MSIX candidates have not yet been installed or runtime-tested. No changes were made to WERD-77, its branch, PR or source files.
## 7. Installation, update, uninstall, and rollback

### Development install (not public distribution)

For contributor testing, follow [Developer Setup](DEVELOPER-SETUP.md): enable Developer Mode, build and deploy the packaged project from Visual Studio, then use Command Palette's **Reload Command Palette extensions** command. This verifies a development deployment only; it is not the end-user installation flow.

### Public install

The public instructions depend on the selected live install source:

- **Microsoft Store:** install from the Store product page or the Gallery's Store action after the Store listing is live. Do not publish a Store URL or product ID before Partner Center provides it.
- **WinGet:** the selected additional Gallery install source. Document `winget install` only after the manifest and installer are accepted and install/upgrade/uninstall are validated. The manifest must include the official Command Palette discovery tag.

### Update

- **Store:** publish a higher package version through Partner Center; Store handles updates for installed users. Validate an upgrade from the previous released version before submission.
- **WinGet:** publish a new manifest version with verified installer URLs and hashes; validate `winget upgrade` on a clean test machine before listing it as supported.

### Uninstall

- **Store/MSIX:** use Windows **Settings → Apps → Installed apps → PlayniteCmdPal → Uninstall**. Verify the package is removed and that no stale extension entry remains after reloading Command Palette.
- **WinGet:** use `winget uninstall --id <verified-package-id> --exact` only if a WinGet package is eventually selected. Verify that the installer removes only the files and registration it owns.

### Rollback

Do not recommend manually downgrading an MSIX package. For a Store release, prepare a corrected higher-version package using the last known-good source revision and submit it as an update. For WinGet, publish a new higher package version containing the known-good build and validate the upgrade path. Keep the prior signed release and its release notes available for diagnosis; never overwrite a published asset in place.

## 8. Troubleshooting checklist

| Symptom | Checks |
|---|---|
| Extension does not appear after development deployment | Confirm Command Palette is enabled; redeploy the packaged project; run **Reload Command Palette extensions**; inspect Event Viewer and the extension process logs. |
| Package fails to install or register | Confirm package signature trust for the distribution source, exact package identity, architecture, and Store certification state where applicable. |
| Extension activation fails | Confirm the extension CLSID matches in the C# `[Guid]`, `com:Class Id`, and `CreateInstance ClassId`; confirm the manifest still declares the executable COM server and its activation arguments. |
| Gallery entry is visible but install fails | Confirm the listing's install-source type and identifier exactly match the live Store product or accepted WinGet package. The Gallery does not host the binary. |
| WinGet package is not discoverable in Command Palette | Confirm the published WinGet locale manifest includes `windows-commandpalette-extension`; verify the package is installable independently of the Gallery. |
| Upgrade leaves old behaviour or duplicate entries | Verify the package identity has not changed unintentionally, uninstall/reinstall on a clean VM, reload Command Palette, and capture package inventory before and after. |

## 9. Ownership and go/no-go checklist

The repository maintainer owns the release decision and must explicitly approve each external action. The engineering contributor prepares and validates artifacts but must not reserve identities, accept legal terms, sign with a private certificate, publish releases, or submit Gallery PRs on the maintainer's behalf.

Before the first public release, the maintainer must confirm:

- [ ] **Historical WERD-76 scope:** confirm the `10.0.26100.84` package's `lib/net8.0` assets and exact x64/ARM64 SDK DLL payloads remain within Microsoft's published REDIST scope and unmodified; this evidence does not validate WERD-77's `10.0.26100.87`. Complete the documented downstream-terms, copyright, indemnification, and distribution-channel review before public release.
- [ ] The dependency inventory has been regenerated and all review items resolved.
- [ ] Runtime notices are present in both architecture outputs.
- [ ] Partner Center identity is confirmed against the product dashboard; x64 and ARM64 MSIX packages pass validation and Store certification. Direct GitHub/WinGet distribution has a separately documented trust model.
- [x] x64 and ARM64 packages build, sign and pass `scripts/release/release_tool.py` inspection, with the evidence bundle recorded in [WERD-81 release evidence](RELEASE-EVIDENCE-WERD-81.md) (x64 `C2F101A0…8C4`, ARM64 `45CEA6BE…3D9`, both inspected strict at `f2c2854`).
- [ ] A clean supported Windows machine passes install, first-run, update, uninstall, and rollback checks.
- [ ] Release notes, support/troubleshooting instructions, version, hashes, and notices are complete.
- [ ] The live Gallery metadata uses a real install source, validates against the current schema, and has a matching icon.
- [ ] The maintainer approves the public release and the separate Gallery contribution; any required Microsoft CLA is completed.

Until every required item is checked, the project remains **prepared for review, not ready to publish**.

## 10. Release MSIX build and inspection (WERD-81)

`scripts/release/release_tool.py` is the reproducible release-candidate pipeline for the Command Palette
extension. It never uploads or publishes anything; it writes a self-contained evidence bundle to
`artifacts/release/<version>/` (git-ignored).

| Path | Purpose |
|---|---|
| `scripts/release/release_expectations.json` | Reviewed release gates: package identity, version, architecture, COM/app-extension registration, required payload files, notices, reviewed dependency assemblies, forbidden content, runtime-notice hashes. |
| `scripts/release/release_tool.py` | `preflight`, `inspect` and `build` commands. Standard-library Python 3 only. |
| `scripts/release/tests/` | Self-tests with synthetic MSIX archives and stub build tools. |
| [WERD-81 release evidence](RELEASE-EVIDENCE-WERD-81.md) | Current evidence record and the exact Windows run instructions. |

### Prerequisites for the Windows run

- Windows 11 with the .NET 10 SDK, MSBuild, the Windows SDK build tools (`signtool.exe`, `makeappx.exe`) and the
  Visual Studio MSIX/WinUI components required by the project.
- Python 3.9 or later on `PATH` (`python --version`).
- A clean working tree: `build` refuses to record evidence for an uncommitted revision and prints the changed
  paths. Signing material and MSBuild's `AppPackages/` output are ignored, so only real source changes or
  unclassified files remain. Commit or stash them first; `--allow-dirty` records a diagnostic run whose evidence names no usable
  revision.
- An existing dependency inventory and signing certificate. `build` checks both paths before it publishes
  anything, so a missing file fails in seconds instead of after two MSIX builds.
- A NuGet restore of the solution (the tool compares shipped dependency assemblies byte-for-byte with the
  restored packages in `%USERPROFILE%\.nuget\packages`).
- `signtool.exe` reachable. The Windows SDK installer does not put it on `PATH`, so `build` also searches
  `%ProgramFiles(x86)%\Windows Kits\10\bin\<version>\x64` (newest SDK first) and the App Certification Kit;
  pass `--signtool <path>` if it lives somewhere else. `makeappx.exe` is resolved the same way and recorded for
  the environment evidence.
- A trusted signing certificate. A self-signed test certificate must be imported into the current user's root
  store before `signtool verify` can succeed: `Import-Certificate -FilePath <file.cer> -CertStoreLocation
  Cert:\CurrentUser\Root`. Import the public `.cer`, never the `.pfx`.
- A signing certificate whose subject matches the manifest Publisher, or the Partner Center Store submission
  path. Signing material must stay outside the repository — a copy at the checkout root is ignored by
  `.gitignore` (`*.pfx`, `*.p12`, `*.cer`, `*.pvk`) so it can never be staged by accident, and `build` warns when
  the `--certificate-pfx` path resolves inside the checkout. The PFX password is read from the
  `PLAYNITECMDPAL_MSIX_PFX_PASSWORD` environment variable.

### Commands

```powershell
# 1. Restore, then regenerate the reviewed dependency inventory (WERD-78).
dotnet restore .\PlayniteCmdPal.sln
powershell -File scripts\licensing\New-DependencyInventory.ps1 -Configuration Release

# 2. Check that repository declarations match the reviewed expectations.
python scripts/release/release_tool.py preflight

# 3. Build, sign and inspect both architectures and write the evidence bundle.
$env:PLAYNITECMDPAL_MSIX_PFX_PASSWORD = '<pfx password, never committed>'
python scripts/release/release_tool.py build `
    --inventory artifacts/dependency-inventory.json `
    --certificate-pfx C:\secure\PlayniteCmdPal-test-signing.pfx
```

`Windows PowerShell 5.1` (`powershell.exe`) is present on every supported Windows build machine and is what the
inventory generator targets; substitute `pwsh -File ...` only when PowerShell 7 is installed. The inventory
generator has been run successfully under 5.1 (see [Licensing and release](LICENSING-AND-RELEASE.md)).

The packaging switches below were validated on the supported Windows build machine on 2026-11-19: `dotnet
publish` for `win-x64` produced `PlayniteCmdPal_0.0.8.0_x64_Test\PlayniteCmdPal_0.0.8.0_x64.msix` under
`artifacts/release/0.0.8.0/appx/win-x64`.

The `build` command runs `dotnet publish` with `-p:GenerateAppxPackageOnBuild=true`,
`-p:UapAppxPackageBuildMode=SideloadOnly` and `-p:AppxBundle=Never` for `win-x64` and `win-arm64`, then signs each
package with `signtool`, verifies it with `signtool verify /pa /all /v`, inspects the archive and records the
evidence. A separate `inspect` command re-inspects an archived package without rebuilding:

```powershell
$package = Get-ChildItem artifacts/release/0.0.8.0/appx -Recurse -Filter *x64*.msix | Select-Object -First 1
python scripts/release/release_tool.py inspect $package.FullName --rid win-x64 --strict
```

### What `inspect` verifies

- OPC structure: `[Content_Types].xml`, `AppxBlockMap.xml` coverage of every payload file, and a signature block.
- Manifest identity, version, `ProcessorArchitecture`, display properties, languages, capabilities and minimum OS.
- Application executable and `AppListEntry`, the out-of-process `com:ExeServer` registration (executable,
  activation arguments and CLSID), the absence of in-process/surrogate COM registration, and that the
  `com.microsoft.commandpalette` app extension's `CreateInstance` class matches the COM class.
- Every manifest asset reference (including scale/targetsize-qualified variants).
- Presence of the application and reviewed dependency assemblies, byte-for-byte comparison of the shipped
  dependency DLLs/WinMD with the restored NuGet package sources, and detection of build-only or test-only content.
- `LICENSE`, `THIRD-PARTY-NOTICES.md` and `Microsoft-PowerToys-LICENSE.txt` against the repository copies, plus
  the RID-specific `dotnet-runtime-THIRD-PARTY-NOTICES.txt` against the reviewed SHA-256.
- Every payload file is attributable to the application, a reviewed dependency package, the .NET runtime, or
  package metadata. Attribution is read from the SDK-generated `*.deps.json` rather than a hand list: each file is
  mapped to the package or runtime pack that ships it, package-shipped assemblies are compared byte-for-byte with
  every copy in the restored NuGet cache (a package may ship the same DLL for several target frameworks), and a
  file from a package that is not in the reviewed inventory is a failure that names the package. Runtime packs are
  recognised by the `runtimepack.`/`runtime.` key prefix, by `"type": "runtimepack"` in the `libraries` section and
  by the library id, because `deps.json` keys them as `runtimepack.Microsoft.NETCore.App.Runtime.win-x64/10.0.14`.
  `AppxMetadata/` (the generated catalog) and the OPC parts are treated as package metadata, and the block map may
  list them.
  `knownExtraPatterns` remains only as the fallback for files the SDK does not describe. `--strict` (used by
  `build`) makes an unreviewed file a failure.
- Language tags are compared case-insensitively, because MakeAppx writes BCP-47 resource languages in upper case.
- Property-supplied packages (`inventoryExemptPackages`, currently `Microsoft.Windows.SDK.NET.Ref`, which comes
  from `WindowsSdkPackageVersion`) are exempt from the inventory listing; their pin is still enforced by preflight.

The command exits `0` only when every check passes. The evidence bundle records the source commit, tool versions,
every command with its exit code, the package SHA-256, per-file payload hashes, the extracted `AppxManifest.xml`,
and a pass/fail table for each WERD-81 acceptance criterion.

### When signing or verification fails

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Executable not found: signtool.exe` | The Windows SDK bin directory is not on `PATH` | Let `build` discover the SDK copy, or pass `--signtool "C:\Program Files (x86)\Windows Kits\10\bin\<version>\x64\signtool.exe"` |
| `0x800B0109`, "not trusted by the trust provider" | The self-signed test certificate is not trusted by the machine | `Import-Certificate -FilePath <file.cer> -CertStoreLocation Cert:\CurrentUser\Root` (public certificate only) |
| `SignTool Error: The specified PFX password is not correct` | The PFX is password-protected and the variable is unset or wrong | Set `PLAYNITECMDPAL_MSIX_PFX_PASSWORD`, or sign with `--certificate-thumbprint` from a certificate in `Cert:\CurrentUser\My`; if the password is lost, regenerate the test certificate — see [MSIX signing](MSIX-SIGNING.md#7-if-the-test-pfx-password-is-unknown) |
| `signing certificate ... does not exist` | The PFX path is wrong or the file is outside the machine | Point `--certificate-pfx` at the real file, or use `--certificate-thumbprint` |
| `--certificate-thumbprint must be the 40 hexadecimal characters ...` | A placeholder or truncated thumbprint was passed | Copy the value from `Get-ChildItem Cert:\CurrentUser\My \| Select-Object Subject, Thumbprint` |
| `the signing certificate subject is CN=..., but the manifest Publisher is ...` | The certificate is a development certificate, not the package identity | Create a test certificate with the Publisher as subject (see [MSIX signing](MSIX-SIGNING.md#6-signing-a-package-when-the-pfx-password-is-unknown)) |

### Current status

The run is complete. On 2026-11-19, from commit `f2c2854`, preflight passed its 33 checks, `dotnet publish` produced
both architecture packages, both were signed with the test certificate and chain-verified by
`signtool verify /pa /all /v`, and both passed strict package inspection: all six WERD-81 acceptance criteria pass.
The hashes, the certificate thumbprint and the command sequence are recorded in
[WERD-81 release evidence](RELEASE-EVIDENCE-WERD-81.md), with the full bundle in `artifacts\release\0.0.8.0` on the
build machine. Package publication stays out of scope: distribution is still gated on refreshing the licensing
audit for the package versions this build uses (see the currentness note in
[Licensing and release readiness](LICENSING-AND-RELEASE.md#dependency-and-redistribution-audit)), on the remaining
go/no-go items above, and on Store certification.

## Official references

- [Microsoft: Publish Command Palette extensions](https://learn.microsoft.com/en-us/windows/powertoys/command-palette/publish-extension)
- [Microsoft: Making your extension discoverable](https://learn.microsoft.com/en-us/windows/powertoys/command-palette/extension-gallery)
- [Gallery contribution guide](https://github.com/microsoft/CmdPal-Extensions/blob/main/docs/CONTRIBUTING.md)
- [Gallery extension schema](https://github.com/microsoft/CmdPal-Extensions/blob/main/.github/schemas/extension.schema.json)
- [Gallery sample extension](https://github.com/microsoft/CmdPal-Extensions/tree/main/extensions/microsoft/sample-extension)


## Windows SDK targeting-pack migration (WERD-77, 2026-11-01)

The project previously pinned preview `Microsoft.Windows.SDK.NET.Ref 10.0.26100.68-preview`. That project-level override has been removed. WERD-77 selected the stable candidate `10.0.26100.87` centrally through `WindowsSdkPackageVersion` in [Directory.Build.props](../Directory.Build.props); the **release pin is `10.0.26100.84`** because that package's projection assets are the ones the WERD-76 REDIST review cleared (see [Release-pin reconciliation](#release-pin-reconciliation-2026-11-17)). The `.87` validation record below is retained as the stable-migration evidence.

Compatibility rationale:

- NuGet identifies this as the Windows SDK .NET targeting pack and reports compatibility with .NET 9 and later, including .NET 10: https://www.nuget.org/packages/Microsoft.Windows.SDK.NET.Ref/10.0.26100.87
- Version 10.0.26100.87 is a stable servicing release in the 26100 SDK family matching `net10.0-windows10.0.26100.0`; the minimum OS target remains Windows 10 build 19041: https://learn.microsoft.com/en-us/windows/apps/windows-sdk/downloads and https://learn.microsoft.com/en-us/windows/apps/get-started/versioning-overview
- The targeting pack is independent of `Microsoft.CommandPalette.Extensions` and is shared by the project's x64 and ARM64 runtime targets.

The targeting pack is a development-time compile reference. Its use is governed by Microsoft's Windows SDK license terms; the SDK package itself is not to be redistributed as application payload. Review the [Microsoft SDK license](https://github.com/microsoft/win32metadata/blob/main/licenses/sdk_license.txt). This package-selection evidence does not establish redistribution rights for Windows SDK projection assemblies that may be shipped at runtime; that remains a separate licensing gate tracked by WERD-76.

### Migration validation checklist

- [x] Clean Windows restore succeeds; evaluated properties selected the then-current `10.0.26100.87` and no preview targeting pack remains. (The release pin is now `10.0.26100.84`, enforced by the WERD-81 preflight.)
- [x] Release solution build succeeds.
- [x] Automated tests and the .NET Framework smoke test pass.
- [x] Visual Studio Build > Deploy registers the x64 MSIX and Command Palette activation succeeds.
- [x] x64 Release publish succeeds.
- [x] ARM64 Release publish succeeds.
- [x] Evaluated MSBuild properties confirm the expected target framework, minimum OS, runtime identifiers, and stable targeting-pack version.
- [x] Both publish outputs contain matching runtime-notice files.
- [x] The installed x64 MSIX payload contains the runtime notice.
- [x] The ARM64 packaging recipe references the ARM64 runtime notice source and expected package path.
- [ ] Generate the actual ARM64 MSIX/MSIX bundle with the existing ARM64 packaging pipeline on the available x64 Windows machine. Extract/inspect it with MakeAppx or an archive tool and verify that the manifest declares ARM64, `dotnet-runtime-THIRD-PARTY-NOTICES.txt` is in the payload, and the expected `LICENSE`, `THIRD-PARTY-NOTICES.md`, and `Microsoft-PowerToys-LICENSE.txt` files are present. Record the exact package filename, SHA-256, inspection method, and results in the PR.
- [ ] Complete any remaining architecture-specific package-content comparison after ARM64 archive generation.

The migration validation above was performed on Windows 11 build 26200 with .NET SDK 10.0.403 and MSBuild 18.9.15. The ARM64 publish and packaging-recipe checks do not establish the contents of the final ARM64 MSIX archive, which is why that archive is inspected separately: the WERD-81 run inspected the ARM64 package on this x64 Windows machine and it passed, so ARM64 hardware is not required for archive inspection. A separate ARM64 install/launch/runtime-activation test does require ARM64 hardware and has not been performed. The clean-machine installation/update/uninstall/rollback walkthrough and public-release licensing obligations remain independent release gates.

### Release-pin reconciliation (2026-11-17)

WERD-77's completion selected and validated stable `10.0.26100.87`. WERD-76's distribution decision requires
`10.0.26100.84` because only that package's `lib/net8.0` projection asset group is enumerated by the Windows SDK
REDIST list, and WERD-81 inherited that constraint when producing release candidates. `Directory.Build.props`
therefore pins `10.0.26100.84`, and `scripts/release/release_tool.py preflight` fails if the pin, the trimming settings
or the ReadyToRun settings drift. The WERD-77 validation evidence above remains accurate for the migration itself;
it does not establish redistribution clearance for `.87`. Revisit the pin only after a new REDIST review.

Run `.\scripts\ci.ps1` for the repository's automated baseline, then use `scripts/release/release_tool.py` for the
package build and inspection described in section 10. Windows 11 build 26200 validation for WERD-77 is recorded
above; the independent clean-machine validation remains outstanding as documented in
[Developer Setup](DEVELOPER-SETUP.md).
Run `.\scripts\ci.ps1` for the repository's automated baseline, then perform the Visual Studio and package checks above on Windows. Do not mark WERD-77 complete until evidence is attached. The existing maintainer-reported Windows 10 validation and CI results predate this targeting-pack migration and do not validate the new package version. Windows 11 clean-machine validation remains separately deferred as documented in [Developer Setup](DEVELOPER-SETUP.md).
