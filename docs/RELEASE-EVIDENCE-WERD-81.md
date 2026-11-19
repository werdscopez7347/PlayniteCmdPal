# WERD-81 release MSIX evidence record

**Status (2026-11-19): complete. Both release-candidate packages were built, signed and chain-verified on the
Windows build machine from commit `f2c2854`, and both pass strict package inspection. All six acceptance criteria
pass. Nothing was uploaded, submitted or published.**

This record accompanies the release pipeline in [`scripts/release/`](../scripts/release/) and the process in
[Release packaging](RELEASE-PACKAGING.md#10-release-msix-build-and-inspection-werd-81). It records what ran, on
which commit, with which certificate, and what the resulting artifacts were. Nothing here authorizes publication:
distribution remains gated on the licensing review in [WERD-78](LICENSING-AND-RELEASE.md) and on Store
certification.

## 1. Result

| Item | Value |
| --- | --- |
| Source commit | `f2c2854` on `arena/2e83f054-playnitecmdpal` (PR #42), branched from `dev` at `b62cc8e` |
| Build machine | Windows build host; commands run from a clean checkout with `git status --short` empty |
| Tool | `python scripts/release/release_tool.py build --inventory artifacts/dependency-inventory.json --certificate-thumbprint 018EBC36ABEB48F1550AFD658369B2C9BC9FB560` |
| Preflight | PASS, 33 checks |
| Signing | Test certificate `CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70`, thumbprint `018EBC36ABEB48F1550AFD658369B2C9BC9FB560`, in `Cert:\CurrentUser\My` with its public `.cer` in `Cert:\CurrentUser\Root`; `signtool verify /pa /all /v` succeeded for both packages |
| signtool | `C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe` |
| Runtime notice SHA-256 | `6D15E10A101C6BFFF2AB4429ED061BF76C456FC4B23AD6B03E0D0F8377148A21` for both RIDs |
| Evidence bundle | `artifacts\release\0.0.8.0` (`evidence.json`, `evidence.md`, `SHA256SUMS`, `environment.json`, `inspection\*.json`, `manifests\*.xml`); `artifacts/` is git-ignored, so the bundle stays on the build machine and the values below are copied from it |

### Packages

| Architecture | File | SHA-256 | Inspection |
| --- | --- | --- | --- |
| x64 | `PlayniteCmdPal_0.0.8.0_x64.msix` | `C2F101A0D2F9943C4B5318D78FC2DEDCD5F0F570180C47F532379CA25BFDE8C4` | PASS (strict) |
| ARM64 | `PlayniteCmdPal_0.0.8.0_arm64.msix` | `45CEA6BEC5B4B2E2C4E0897C359AB89FA5A3F50E63B877F154D207935BF823D9` | PASS (strict) |

Both packages were signed before inspection, so these hashes cover the signed archives. Signing is timestamped,
so a later re-signing produces different bytes even from the same inputs; reproduce the build from `f2c2854` to
get packages that are equivalent but not necessarily byte-identical.

`SHA256SUMS` in the evidence bundle lists every artifact and extracted part. Per-file payload hashes, the
extracted `AppxManifest.xml` for each architecture and every command with its exit code are in `evidence.json`
and `evidence.md`.

## 2. Run history

Five Windows attempts were needed; each one found a defect in the inspection tooling rather than in the packages,
and each fix was committed and re-run rather than worked around.

| # | Commit | Outcome |
| --- | --- | --- |
| 1–2 | `4a17113` and earlier | Built and signed, but stopped at `signtool.exe` not being on `PATH`, then at a false identity mismatch (signtool prints the common name; the manifest Publisher carries the `CN=` prefix). |
| 3 | `4a17113` | Both packages signed and chain-verified; inspection failed on five tool defects (language case, one-arbitrary-TFM comparison, a hand-maintained payload list, block-map metadata, a property-supplied package missing from the inventory). |
| 4 | `fcef43c` | Both packages signed and chain-verified; one defect left — `deps.json` prefixes runtime-pack keys with `runtimepack.`, hiding 187 runtime files from the runtime classification. |
| 5 | `f2c2854` | **Preflight PASS, both packages signed and chain-verified, strict inspection PASS on both, all six criteria pass.** |

### The implementation session (sandbox, 2026-11-17)

The branch was written and self-tested without a Windows host, so the pipeline was proven against synthetic
fixtures before any real package existed.

| Step | Command | Result |
| --- | --- | --- |
| Repository preflight | `python -m unittest discover -s scripts/release/tests -v` (case `test_repository_matches_reviewed_expectations`) | 33 preflight checks pass: manifest, project, central properties, publish profiles, notices and the `10.0.26100.84` SDK pin agree with `scripts/release/release_expectations.json`. |
| Release-tool self-tests | `python -m unittest discover -s scripts/release/tests` | 35 tests pass at that point, 58 after the run-time fixes below (inspection pass/fail paths, preflight drift detection, signing/subject gating, dirty-tree gating, build orchestration with stub `dotnet`/`signtool`, evidence generation). |
| CI (PR #42) | GitHub Actions on the pull request | `Restore, build, and test (Windows)` pass (2m04s) and `Release tooling self-tests (cross-platform)` pass (7s on Ubuntu); `Analyze C#` and `CodeQL` pass. The Windows job runs `scripts/ci.ps1`, whose `Invoke-PythonStep` exits non-zero on failure (127 when `python` is absent), so the pass is proof that the self-tests also pass on `windows-latest`. It is **not** a package build. |
| Build-command plan | `python scripts/release/release_tool.py build --dry-run` | Prints the two `dotnet publish` invocations and the `signtool sign`/`verify` steps without executing them. |
| MSIX generation | — | **Not executed.** No Windows host or .NET SDK. |
| Signing / `signtool verify` | — | **Not executed.** No certificate and no `signtool`. |
| Archive inspection of real packages | — | **Not executed at that point.** No packages existed until the Windows runs below. |
| Install / launch / activation | — | Out of scope; tracked by WERD-82. |

Test-only fixtures are synthetic ZIP archives. They prove the checks work; they are not evidence about the
product's own package.

### The first Windows attempt (2026-11-17)

The first run of the sequence in section 4 happened on the supported Windows build machine and stopped at the
first step, so it produced no package. Recorded because it is real evidence about the tooling:

| Step | Command | Observed result |
| --- | --- | --- |
| Restore | `dotnet restore .\PlayniteCmdPal.sln` | `Restore complete (5.0s)`, `Build succeeded in 5.5s`. |
| Inventory | `pwsh -File scripts/licensing/New-DependencyInventory.ps1 -Configuration Release` | **Failed:** `pwsh` is not installed on that machine (`CommandNotFoundException`). No inventory was written, so the `--inventory` gate could not pass. The documented command is now `powershell -File ...` (Windows PowerShell 5.1), which is the host the generator was validated on. |
| Preflight | `python scripts/release/release_tool.py preflight` | **PASS (33 checks)** against the real checkout: identity, `0.0.8.0`, `10.0.26100.84` pin, both publish profiles, notice copies, runtime-notice hashes and expectation coverage all agree. |
| Build | `python scripts/release/release_tool.py build --inventory artifacts/dependency-inventory.json --certificate-pfx C:\secure\PlayniteCmdPal-test-signing.pfx` | **Refused:** the working tree had uncommitted changes, so no publish ran and no evidence bundle was written. The revision in use did not say which paths were dirty; `build` now prints them (at most ten, then a count) and records them in `environment.source.dirtyPaths`. |
| Working tree | `git status` | The only entries were untracked `PlayniteCmdPal-Test.cer`, `PlayniteCmdPal-Test.pfx` and the MSBuild `PlayniteCmdPal/AppPackages/` output — no source edits. Staging the PFX by accident was therefore one `git add -A` away. `.gitignore` now covers `*.pfx`, `*.p12`, `*.cer`, `*.pvk` and `[Aa]ppPackages/`, and `build` warns (and records `environment.signing.certificateInsideRepository`) when the certificate path is inside the checkout. |

Nothing above is a substitute for the package run: the two MSIX files, the signatures and the inspection results
are still missing.

### The second Windows attempt (2026-11-19)

The checkout was cleaned (test certificate moved to `C:\secure\`, stale `AppPackages/` removed) and the sequence
was re-run. Packaging works; signing did not run:

| Step | Command | Observed result |
| --- | --- | --- |
| Working tree | `git status --short` | Empty after the certificate and packaging output were removed from the checkout. |
| Restore | `dotnet restore .\PlayniteCmdPal.sln` | `Restore complete (4.9s)`, `Build succeeded in 5.4s`. |
| Inventory | `powershell -File scripts\licensing\New-DependencyInventory.ps1 -Configuration Release` | **Ran under Windows PowerShell 5.1** and wrote `artifacts/dependency-inventory.json`: 4 shipped-runtime, 4 shipped-build, 12 test-only, 0 developer-tool, 0 unclassified, 5 review flags (4 in shipped classifications). The JSON SHA-256 has not been captured yet. |
| Preflight | `python scripts/release/release_tool.py preflight` | **PASS (33 checks)**. |
| Build (win-x64) | `python scripts/release/release_tool.py build --inventory artifacts/dependency-inventory.json --certificate-pfx C:\secure\PlayniteCmdPal-Test.pfx` | `dotnet publish` produced `artifacts\release\0.0.8.0\appx\win-x64\PlayniteCmdPal_0.0.8.0_x64_Test\PlayniteCmdPal_0.0.8.0_x64.msix`. Signing then failed with `Executable not found: signtool.exe` and the run stopped, so no signature, no inspection and no evidence bundle exist for either architecture. |

What this establishes: the single-project MSIX packaging switches used by `build`
(`GenerateAppxPackageOnBuild`, `UapAppxPackageBuildMode=SideloadOnly`, `AppxBundle=Never`) do produce one
architecture-specific package under the requested `AppxPackageDir`, and the package name and layout match the
expectations file. What it does not establish: any signature, any inspection result, the ARM64 package, or any
hash.

The `signtool.exe` failure is an environment issue, not a package issue: the Windows SDK installer does not add
its `bin` directory to `PATH`. `build` now resolves `signtool.exe` and `makeappx.exe` from
`%ProgramFiles(x86)%\Windows Kits\10\bin\<version>\x64` (newest SDK first) before falling back to the name, and
prints a warning naming `--signtool` when nothing is found.

The retry with the discovery fix found `C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe`
and published the `win-x64` package again, then failed with `SignTool Error: The specified PFX password is not
correct`: the test PFX is password-protected and the password is no longer known. `build` now names both remedies
(set the password variable, or sign with `--certificate-thumbprint` from `Cert:\CurrentUser\My`) instead of
reporting only that signing failed; the recovery paths are in [MSIX signing](MSIX-SIGNING.md#6-signing-a-package-when-the-pfx-password-is-unknown).

The fix is exercised on `windows-latest` by the CI job: it runs the full self-test suite (45 tests, including the
SDK tool-discovery cases) through `scripts/ci.ps1` in 2m02s, so the resolution path is known to work on Windows
before the next manual run.

### The signed Windows run (2026-11-19, commit `4a17113`)

| Step | Result |
| --- | --- |
| Signing certificate | A test certificate with the manifest Publisher as subject was created in `Cert:\CurrentUser\My` (thumbprint `018EBC36ABEB48F1550AFD658369B2C9BC9FB560`) and its public `.cer` imported into `Cert:\CurrentUser\Root`. |
| Preflight | **PASS** (33 checks), including the runtime-notice SHA-256 `6D15E10A101C6BFFF2AB4429ED061BF76C456FC4B23AD6B03E0D0F8377148A21` for both RIDs. |
| Build and sign | **Both packages built, signed and chain-verified**: `PlayniteCmdPal_0.0.8.0_x64.msix` (SHA-256 `E1740F0FDEFC797A10CF32729E7FE6F3F09B4EF1A4CB305E6FEDC0CF59C0F554`) and `PlayniteCmdPal_0.0.8.0_arm64.msix` (SHA-256 `FDD77C318ED24830122575FA8348AA4E26FAF4E2E13573B7BAD2B767317CB72D`); `signtool verify /pa /all /v` succeeded for both. Evidence was written to `artifacts\release\0.0.8.0`. |
| Acceptance | Criteria **4, 5 and 6 passed**. Criteria 1 and 2 failed only because package inspection failed; criterion 3 failed and now named its five causes. |

Those hashes are from a run whose package verdicts were wrong (inspection produced false failures), so they are not
authoritative: re-signing also changes the bytes through the timestamp. The authoritative values will come from the
next clean run.

#### Inspection findings from that run

Five causes, all in the inspection tooling rather than in the packages:

| Finding | Cause | Correction |
| --- | --- | --- |
| `manifest.languages` expected `en-US`, observed `EN-US` | MakeAppx upper-cases BCP-47 resource languages, and the comparison was case-sensitive | Language tags are compared case-insensitively on both architectures |
| `WinRT.Runtime.dll does not match Microsoft.Windows.CsWinRT 2.3.1` | The check compared against one arbitrary target-framework copy in the NuGet cache while the publish selected another, byte-different copy | Every copy of the file in the package folder is a candidate; any byte-identical copy satisfies the check, and a genuine mismatch names how many copies were compared |
| Nine unreviewed payload files (`System.dll`, `clrgc.dll`, `clrgcexp.dll`, `clretwrc.dll`, `msquic.dll`, `Microsoft.DiaSymReader.Native.amd64.dll`, `Microsoft.CommandPalette.Extensions*.dll`, `AppxMetadata/CodeIntegrity.cat`) | The payload gate relied on a hand-maintained pattern list | Attribution now comes from the SDK-generated `*.deps.json`: each file maps to the package or runtime pack that ships it, package-shipped files are compared with their NuGet sources, and `AppxMetadata/` counts as package metadata |
| `AppxBlockMap.xml lists 213 payload files` | The block-map comparison counted every `<File>` entry, including generated OPC metadata, against a payload set that excluded it | OPC metadata is excluded from both sides, `AppxMetadata/` entries are allowed, and the detail names every file that is missing from or extra in the block map |
| `Microsoft.Windows.SDK.NET.Ref is not in the inventory` | The package is supplied by the `WindowsSdkPackageVersion` property, so the inventory generator cannot list it | `inventoryExemptPackages` records the exemption and its reason; the version pin is still enforced by preflight |

#### The run that followed (`fcef43c`, 2026-11-19)

Both packages built, signed and chain-verified again — x64 `81FF4F21FD6A8BA8F804227C74D1BCF7EEBA4136822FF6C4EE1353C6190B3C59`,
arm64 `254A53BF984D2E47B773461E9BFCEF60543A050AACB072DA81F6348222B8CCB7` — and criteria 4, 5 and 6 passed. One
finding remained, again in the tooling: `deps.json` names a runtime pack as
`runtimepack.Microsoft.NETCore.App.Runtime.win-x64/10.0.14`, so the type prefix hid 187 runtime files from the
runtime classification and they were reported as unreviewed. Runtime libraries are now recognised by the
`runtimepack.`/`runtime.` key prefix, by `"type": "runtimepack"` in the `libraries` section, and by the id itself,
and the same fix applies to the library name shown in messages and evidence. These hashes are superseded as well.

Inventory review flags from that run remain open for the licensing gate: `Microsoft.NETFramework.ReferenceAssemblies`
and `.net462` (license URL only), `Microsoft.Windows.CsWinRT` 2.3.1 (license file in package),
`Microsoft.Windows.SDK.BuildTools.MSIX` 1.7.261102100 (`sdk_license.txt`), and `xunit.abstractions` (test-only,
license URL only).

## 3. Acceptance criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| x64 package builds, signs, and passes package inspection | **Pass** | `dotnet publish` succeeded; package signed and chain-verified; strict inspection PASS; SHA-256 `C2F101A0D2F9943C4B5318D78FC2DEDCD5F0F570180C47F532379CA25BFDE8C4`. |
| ARM64 package builds, signs, and passes package inspection | **Pass** | `dotnet publish` succeeded; package signed and chain-verified; strict inspection PASS; SHA-256 `45CEA6BEC5B4B2E2C4E0897C359AB89FA5A3F50E63B877F154D207935BF823D9`. |
| Package contents match the reviewed dependency inventory | **Pass** | Strict inspection passed on both architectures: required application and dependency assemblies present, every reviewed package-source hash matched, every payload file attributed through `*.deps.json` to the app, a reviewed package or the .NET runtime, no build-only or test-only content. |
| Required licenses/notices are present in each package | **Pass** | `LICENSE`, `THIRD-PARTY-NOTICES.md` and `Microsoft-PowerToys-LICENSE.txt` match the repository copies byte-for-byte; the RID-specific .NET runtime notice matches the reviewed SHA-256 `6D15E10A101C6BFFF2AB4429ED061BF76C456FC4B23AD6B03E0D0F8377148A21`. |
| Hashes and reproducible build evidence are recorded | **Pass** | `artifacts\release\0.0.8.0` holds `evidence.json`, `evidence.md`, `SHA256SUMS`, `environment.json`, extracted `AppxManifest.xml` per architecture, per-file payload hashes and every command with its exit code; the package hashes are recorded above. |
| No package is submitted or published by this issue | **Satisfied by design** | The tooling has no upload, submission or publishing step and writes only to the git-ignored `artifacts/` tree. |

## 4. Reproducing the record

Run from a clean checkout of the merge commit on the supported Windows build machine. `git status --short` must
print nothing: `build` refuses an uncommitted revision, because evidence that cannot be tied to a commit is not
reproducible. The sequence below is the one that produced the record above — restore, regenerate the inventory,
check the repository declarations, then build, sign and inspect both architectures.

```powershell
dotnet restore .\PlayniteCmdPal.sln
powershell -File scripts\licensing\New-DependencyInventory.ps1 -Configuration Release
python scripts/release/release_tool.py preflight
$env:PLAYNITECMDPAL_MSIX_PFX_PASSWORD = '<pfx password>'
python scripts/release/release_tool.py build `
    --inventory artifacts/dependency-inventory.json `
    --certificate-pfx C:\secure\PlayniteCmdPal-test-signing.pfx
```

`build` validates the inventory and certificate paths before it starts publishing, so a missing file fails in
seconds rather than after two MSIX builds.

The run must exit `0`. The bundle is the authoritative artifact; attach `artifacts/release/0.0.8.0` to the
WERD-81 review and leave the packages out of Git.

| Field | Where it is recorded |
| --- | --- |
| Source commit, dirty-tree state, branch | `evidence.json` (`source.commit`, `source.branch`, `source.clean`) |
| Windows build, .NET SDK, MSBuild and `signtool` versions | `environment.json` and the `environment` block of `evidence.json` |
| Package filename, size and SHA-256 per architecture | `SHA256SUMS` and `evidence.json` (`packages[]`) |
| Signing certificate subject and thumbprint | `evidence.json` (`environment.signing`); the private key never leaves the build machine |
| `signtool verify /pa /all /v` transcript | `evidence.json` (`commands[]`) |
| Inspection result and every check detail per architecture | `inspection/win-x64.json`, `inspection/win-arm64.json` |
| Per-file payload hashes and the extracted manifests | `evidence.json` (`packages[].inspection.payload.files`), `manifests/*.xml` |
| Regenerated dependency-inventory SHA-256 | `Get-FileHash artifacts\dependency-inventory.json -Algorithm SHA256`; used by the WERD-78 licensing review |

## 5. Why the earlier ARM64 artifact is not reused

PR #40 recorded `PlayniteCmdPal_0.0.8.0_arm64.msix` (42,589,226 bytes, SHA-256
`4DF5ABA49B151F291B4B85FF370FAB74240BBEFCB7F6A4FEB99CC11F444A8FF1`) from the WERD-77 branch. That artifact is
historical evidence only and must not be reused or carried into a release:

- It was produced with the `10.0.26100.87` targeting pack, not the `10.0.26100.84` package selected by the
  WERD-76 REDIST review that governs distribution (see the reconciliation note in
  [Release packaging](RELEASE-PACKAGING.md#release-pin-reconciliation-2026-11-17)).
- It predates the merged dependency bumps in PR #41 (`Microsoft.Windows.CsWinRT 2.3.1`,
  `Shmuelie.WinRTServer 2.2.1`, `Microsoft.CommandPalette.Extensions 0.12.260812002`,
  `Microsoft.Windows.SDK.BuildTools.MSIX 1.7.261102100`), so its payload no longer matches the current
  dependency graph.
- There is no matching x64 package from the same source revision, transaction or inspection run.

## 6. Signing model

Store-distributed packages are signed by Microsoft after certification; no publisher-managed production
certificate is required for that path (see [MSIX signing](MSIX-SIGNING.md)). A local release candidate still has
to be signed to prove the package identity is valid and installable: use a test certificate whose subject equals
the manifest Publisher (`CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70`), keep the PFX and its password outside the
repository, and let `release_tool.py` run `signtool sign` and `signtool verify /pa /all /v`. The tool records the
signer subject and fails when it differs from the Publisher. This validates signability and identity alignment; it
does not claim Store certification or a trusted production certificate.

## 7. Known risks and follow-ups

1. **Packaging flags are validated.** `dotnet publish` with `-p:GenerateAppxPackageOnBuild=true`,
   `-p:UapAppxPackageBuildMode=SideloadOnly`, `-p:AppxBundle=Never` and `-p:AppxPackageDir=...` produced both
   packages on the first attempt, so the documented single-project MSIX pattern holds for this project. Keep the
   commands in `evidence.json` as the reference if the project's packaging targets change.
2. **Licensing review is still open (WERD-78).** The dependency inventory was regenerated for this run and
   `inspect --inventory` compared its versions and shipped classifications against the reviewed expectations, but
   the audit tables in [Licensing and release readiness](LICENSING-AND-RELEASE.md) still carry five flagged
   packages: `Microsoft.NETFramework.ReferenceAssemblies` and `.net462` (license URL only),
   `Microsoft.Windows.CsWinRT` 2.3.1 (license file inside the package),
   `Microsoft.Windows.SDK.BuildTools.MSIX` 1.7.261102100 (`sdk_license.txt`) and `xunit.abstractions` (test-only,
   license URL only). Record the inventory SHA-256
   (`Get-FileHash artifacts\dependency-inventory.json -Algorithm SHA256`) with the assessment.
3. **Runtime-notice hash is pinned.** The expected `.NET` runtime notice SHA-256
   (`6D15E10A101C6BFFF2AB4429ED061BF76C456FC4B23AD6B03E0D0F8377148A21`) matched on both RIDs. A different .NET
   runtime patch changes the notice file; the run fails with the observed hash so the reviewer can confirm and
   update `release_expectations.json` deliberately.
4. **Payload review never relaxes.** `build` runs inspection in strict mode, so any payload file that is not
   attributable to the app, a reviewed dependency package or the .NET runtime fails the gate. Attribution is read
   from the generated `*.deps.json`; a failure names the package that ships the file, so the fix is to review that
   package in the inventory (or record an exemption with a reason), never to add the file to a pattern list to make
   a run pass. The five defects found during these runs were all fixed this way.
5. **Signing is a test certificate.** `CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70` proves the package identity is
   valid and installable and that it matches the manifest Publisher. It is not a trusted production certificate and
   it is not Store certification; the private key stays on the build machine and outside the repository, and the
   public `.cer` was imported into `Cert:\CurrentUser\Root` only to let `signtool verify /pa` succeed locally.
6. **Python prerequisite.** The tool needs Python 3.9+ on the build machine. It uses only the standard library;
   no package installation is required.
7. **Install, first run, update, uninstall and rollback** are out of scope here and tracked by WERD-82.
